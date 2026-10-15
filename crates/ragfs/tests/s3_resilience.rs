//! S3FS timeout/retry behaviour against an in-process fake S3 endpoint.
//!
//! The fake server speaks just enough HTTP/1.1 to stall, throttle (503 SlowDown),
//! answer GET/HEAD/LIST, and log what it received, so these run without a real
//! S3 backend.

#![cfg(feature = "s3")]

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use ragfs::core::{ConfigValue, Error, FileSystem, PluginConfig};
use ragfs::plugins::s3fs::client::S3Client;
use ragfs::plugins::S3FileSystem;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

/// What the fake server does with a request.
#[derive(Clone, Copy)]
enum Reply {
    /// Read the request and never answer.
    Hang,
    /// Answer after `delay` with `status`; 200 carries `OK_BODY`, others a SlowDown error.
    Respond { status: u16, delay: Duration },
    /// 404 NoSuchKey.
    NotFound,
    /// 200 with an XML body (e.g. a ListObjectsV2 result).
    Xml(&'static str),
}

const OK_BODY: &[u8] = b"hello";
const EMPTY_LISTING: &str = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
    <ListBucketResult><Name>bucket</Name><KeyCount>0</KeyCount><MaxKeys>1</MaxKeys>\
    <IsTruncated>false</IsTruncated></ListBucketResult>";

/// Decides the reply from the request's 0-based index and its request line
/// (e.g. `GET /bucket/dir/file.txt?x-id=GetObject HTTP/1.1`).
type Script = dyn Fn(usize, &str) -> Reply + Send + Sync;

struct FakeS3 {
    endpoint: String,
    log: Arc<Mutex<Vec<String>>>,
}

impl FakeS3 {
    async fn start(script: impl Fn(usize, &str) -> Reply + Send + Sync + 'static) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let log = Arc::new(Mutex::new(Vec::new()));
        let server_log = log.clone();
        let script: Arc<Script> = Arc::new(script);
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                let log = server_log.clone();
                let script = script.clone();
                tokio::spawn(async move { serve(stream, log, script).await });
            }
        });
        Self { endpoint, log }
    }

    fn requests(&self) -> usize {
        self.log.lock().unwrap().len()
    }

    /// Request lines received so far, method and path only.
    fn request_log(&self) -> Vec<String> {
        self.log.lock().unwrap().clone()
    }

    fn config(&self, extra: &[(&str, i64)]) -> HashMap<String, ConfigValue> {
        let mut config = HashMap::from([
            ("bucket".to_string(), ConfigValue::String("bucket".into())),
            (
                "endpoint".to_string(),
                ConfigValue::String(self.endpoint.clone()),
            ),
            (
                "access_key_id".to_string(),
                ConfigValue::String("ak".into()),
            ),
            (
                "secret_access_key".to_string(),
                ConfigValue::String("sk".into()),
            ),
            ("initial_backoff_ms".to_string(), ConfigValue::Int(1)),
            ("max_backoff_ms".to_string(), ConfigValue::Int(5)),
        ]);
        for (key, value) in extra {
            config.insert(key.to_string(), ConfigValue::Int(*value));
        }
        config
    }

    async fn client(&self, extra: &[(&str, i64)]) -> S3Client {
        S3Client::new(&self.config(extra)).await.unwrap()
    }

    async fn filesystem(&self, extra: &[(&str, i64)]) -> S3FileSystem {
        let config = PluginConfig {
            name: "s3fs".to_string(),
            mount_path: "/s3".to_string(),
            params: self.config(extra),
            ..PluginConfig::default()
        };
        S3FileSystem::new(&config).await.unwrap()
    }
}

async fn serve(mut stream: TcpStream, log: Arc<Mutex<Vec<String>>>, script: Arc<Script>) {
    let Some(request_line) = read_request_head(&mut stream).await else {
        return;
    };
    let index = {
        let mut log = log.lock().unwrap();
        let mut parts = request_line.split(' ');
        let method = parts.next().unwrap_or("");
        let path = parts.next().unwrap_or("").split('?').next().unwrap_or("");
        log.push(format!("{method} {path}"));
        log.len() - 1
    };
    let is_head = request_line.starts_with("HEAD ");
    let (status, content_type, body): (u16, &str, Vec<u8>) = match script(index, &request_line) {
        Reply::Hang => {
            // Hold the connection open until the client gives up.
            let mut sink = [0u8; 64];
            while matches!(stream.read(&mut sink).await, Ok(n) if n > 0) {}
            return;
        }
        Reply::Respond { status: 200, delay } => {
            tokio::time::sleep(delay).await;
            (200, "application/octet-stream", OK_BODY.to_vec())
        }
        Reply::Respond { status, delay } => {
            tokio::time::sleep(delay).await;
            (status, "application/xml", s3_error("SlowDown"))
        }
        Reply::NotFound => (404, "application/xml", s3_error("NoSuchKey")),
        Reply::Xml(xml) => (200, "application/xml", xml.as_bytes().to_vec()),
    };
    let head = format!(
        "HTTP/1.1 {status} X\r\nContent-Length: {}\r\nContent-Type: {content_type}\r\n\
         x-amz-request-id: fake-req\r\nConnection: close\r\n\r\n",
        body.len(),
    );
    let _ = stream.write_all(head.as_bytes()).await;
    if !is_head {
        let _ = stream.write_all(&body).await;
    }
    let _ = stream.shutdown().await;
}

fn s3_error(code: &str) -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>{code}</Code>\
         <Message>fake</Message><RequestId>fake-req</RequestId></Error>"
    )
    .into_bytes()
}

/// Read until the end of the request headers and return the request line.
async fn read_request_head(stream: &mut TcpStream) -> Option<String> {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 1024];
    while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
        let n = stream.read(&mut chunk).await.ok()?;
        if n == 0 {
            return None;
        }
        buf.extend_from_slice(&chunk[..n]);
    }
    let text = String::from_utf8_lossy(&buf);
    text.lines().next().map(str::to_string)
}

fn ok_after(delay: Duration) -> Reply {
    Reply::Respond { status: 200, delay }
}

fn slow_down() -> Reply {
    Reply::Respond {
        status: 503,
        delay: Duration::ZERO,
    }
}

#[tokio::test]
async fn stalled_endpoint_times_out_instead_of_hanging() {
    let s3 = FakeS3::start(|_, _| Reply::Hang).await;
    let client = s3
        .client(&[
            ("read_timeout_ms", 200),
            ("operation_attempt_timeout_ms", 300),
            ("operation_timeout_ms", 1_000),
            ("max_attempts", 1),
        ])
        .await;

    let started = Instant::now();
    let result = client.get_object("k").await;

    assert!(matches!(result, Err(Error::Timeout(_))), "{result:?}");
    assert!(
        started.elapsed() < Duration::from_secs(3),
        "{:?}",
        started.elapsed()
    );
}

#[tokio::test]
async fn throttling_is_retried_until_success() {
    let s3 = FakeS3::start(|i, _| {
        if i < 2 {
            slow_down()
        } else {
            ok_after(Duration::ZERO)
        }
    })
    .await;
    let client = s3.client(&[("max_attempts", 3)]).await;

    let body = client.get_object("k").await.unwrap();

    assert_eq!(body, OK_BODY);
    assert_eq!(s3.requests(), 3);
}

#[tokio::test]
async fn persistent_throttling_surfaces_as_network_error() {
    let s3 = FakeS3::start(|_, _| slow_down()).await;
    let client = s3.client(&[("max_attempts", 2)]).await;

    let result = client.get_object("k").await;

    assert!(matches!(result, Err(Error::Network(_))), "{result:?}");
    assert_eq!(s3.requests(), 2);
}

#[tokio::test]
async fn metadata_calls_use_the_tighter_deadline() {
    // Every response takes 600ms: within the data deadline, beyond the metadata one.
    let s3 = FakeS3::start(|_, _| ok_after(Duration::from_millis(600))).await;
    let client = s3
        .client(&[
            ("operation_attempt_timeout_ms", 5_000),
            ("metadata_attempt_timeout_ms", 200),
            ("metadata_operation_timeout_ms", 300),
            ("max_attempts", 1),
        ])
        .await;

    let head = client.head_object("k").await;
    assert!(matches!(head, Err(Error::Timeout(_))), "{head:?}");

    let body = client.get_object("k").await.unwrap();
    assert_eq!(body, OK_BODY);
}

/// Route GET/HEAD/LIST for a bucket holding `dir/file.txt` and a `dir/` marker.
fn bucket_with_file(_: usize, request_line: &str) -> Reply {
    let path = request_line.split(' ').nth(1).unwrap_or("");
    let object = path.split('?').next().unwrap_or("");
    match object {
        "/bucket/dir/file.txt" => ok_after(Duration::ZERO),
        "/bucket/dir/" => ok_after(Duration::ZERO),
        "/bucket/" if path.contains("list-type=2") => Reply::Xml(EMPTY_LISTING),
        _ => Reply::NotFound,
    }
}

#[tokio::test]
async fn read_of_existing_file_is_a_single_get() {
    let s3 = FakeS3::start(bucket_with_file).await;
    let fs = s3.filesystem(&[]).await;

    let body = fs.read("/dir/file.txt", 0, 0).await.unwrap();

    assert_eq!(body, OK_BODY);
    assert_eq!(s3.request_log(), ["GET /bucket/dir/file.txt"]);
}

#[tokio::test]
async fn read_of_directory_reports_is_a_directory() {
    let s3 = FakeS3::start(bucket_with_file).await;
    let fs = s3.filesystem(&[]).await;

    let result = fs.read("/dir", 0, 0).await;

    assert!(matches!(result, Err(Error::IsADirectory(_))), "{result:?}");
}

#[tokio::test]
async fn read_of_missing_path_reports_not_found() {
    let s3 = FakeS3::start(bucket_with_file).await;
    let fs = s3.filesystem(&[]).await;

    let result = fs.read("/missing.txt", 0, 0).await;

    assert!(matches!(result, Err(Error::NotFound(_))), "{result:?}");
}

#[tokio::test]
async fn concurrent_stat_misses_share_one_lookup() {
    // HEAD is slow, so all callers miss the cache while the first lookup runs.
    let s3 = FakeS3::start(|_, line| {
        if line.starts_with("HEAD /bucket/dir/file.txt ") {
            ok_after(Duration::from_millis(200))
        } else {
            Reply::NotFound
        }
    })
    .await;
    let fs = s3.filesystem(&[]).await;

    let results = futures::future::join_all((0..20).map(|_| fs.stat("/dir/file.txt"))).await;

    for result in results {
        let info = result.unwrap();
        assert!(!info.is_dir);
        assert_eq!(info.size, OK_BODY.len() as u64);
    }
    assert_eq!(s3.request_log(), ["HEAD /bucket/dir/file.txt"]);
}

#[tokio::test]
async fn concurrent_stat_failures_reach_every_caller() {
    let s3 = FakeS3::start(|_, _| Reply::Respond {
        status: 503,
        delay: Duration::from_millis(100),
    })
    .await;
    let fs = s3.filesystem(&[("max_attempts", 1)]).await;

    let results = futures::future::join_all((0..5).map(|_| fs.stat("/dir/file.txt"))).await;

    for result in results {
        assert!(matches!(result, Err(Error::Network(_))), "{result:?}");
    }
    assert_eq!(s3.requests(), 1);
}

#[tokio::test]
async fn in_flight_requests_are_capped() {
    let s3 = FakeS3::start(|_, _| ok_after(Duration::from_millis(200))).await;
    let client = s3.client(&[("max_concurrent_requests", 2)]).await;

    let started = Instant::now();
    let results =
        futures::future::join_all((0..6).map(|i| client.get_object_range("k", i, 1))).await;

    assert!(results.iter().all(Result::is_ok), "{results:?}");
    // Six 200ms requests, two at a time: three waves.
    assert!(
        started.elapsed() >= Duration::from_millis(550),
        "{:?}",
        started.elapsed()
    );
}

#[tokio::test]
async fn saturated_request_slots_fail_fast_with_timeout() {
    // The GET holds the only slot for 2s; the HEAD gives up waiting at its
    // metadata deadline instead of queueing behind it.
    let s3 = FakeS3::start(|_, _| ok_after(Duration::from_secs(2))).await;
    let client = s3
        .client(&[
            ("max_concurrent_requests", 1),
            ("metadata_attempt_timeout_ms", 200),
            ("metadata_operation_timeout_ms", 200),
        ])
        .await;

    let slow_get = client.get_object("k");
    let head = async {
        tokio::time::sleep(Duration::from_millis(50)).await;
        let started = Instant::now();
        (client.head_object("k").await, started.elapsed())
    };
    let (_, (head, waited)) = tokio::join!(slow_get, head);

    assert!(matches!(head, Err(Error::Timeout(_))), "{head:?}");
    assert!(waited < Duration::from_secs(1), "{waited:?}");
    assert_eq!(s3.requests(), 1);
}
