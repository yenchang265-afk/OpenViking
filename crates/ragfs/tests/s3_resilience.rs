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
    /// Answer after `delay` with `status`; 200 carries `OK_BODY`, 412 a
    /// PreconditionFailed error, others a SlowDown error.
    Respond { status: u16, delay: Duration },
    /// 404 NoSuchKey.
    NotFound,
    /// 200 with an XML body (e.g. a ListObjectsV2 result).
    Xml(&'static str),
    /// 200 for an object whose ETag is the given hex digest.
    Etag(&'static str),
    /// An S3 error response with the given status and code.
    S3Error(u16, &'static str),
    /// 200 with the given body and ETag.
    Body(&'static str, &'static str),
    /// 200 for an object stored by the last conditional write received: echoes
    /// its `x-amz-meta-ov-write-id`.
    OurObject,
    /// 200 for an object stored by another writer.
    ObjectWrittenBy(&'static str),
    /// `Etag` answered after a delay.
    SlowEtag(Duration, &'static str),
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

/// The `x-amz-meta-ov-write-id` of the last request that carried one.
type LastWriteId = Arc<Mutex<Option<String>>>;

impl FakeS3 {
    async fn start(script: impl Fn(usize, &str) -> Reply + Send + Sync + 'static) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let log = Arc::new(Mutex::new(Vec::new()));
        let server_log = log.clone();
        let script: Arc<Script> = Arc::new(script);
        let last_write_id = LastWriteId::default();
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                let log = server_log.clone();
                let script = script.clone();
                let last_write_id = last_write_id.clone();
                tokio::spawn(async move { serve(stream, log, script, last_write_id).await });
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

async fn serve(
    mut stream: TcpStream,
    log: Arc<Mutex<Vec<String>>>,
    script: Arc<Script>,
    last_write_id: LastWriteId,
) {
    let Some((request_line, headers)) = read_request_head(&mut stream).await else {
        return;
    };
    if let Some(write_id) = header_value(&headers, "x-amz-meta-ov-write-id") {
        *last_write_id.lock().unwrap() = Some(write_id);
    }
    let index = {
        let mut log = log.lock().unwrap();
        let mut parts = request_line.split(' ');
        let method = parts.next().unwrap_or("");
        let path = parts.next().unwrap_or("").split('?').next().unwrap_or("");
        log.push(format!("{method} {path}"));
        log.len() - 1
    };
    let is_head = request_line.starts_with("HEAD ");
    let mut extra_headers = String::new();
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
            let code = if status == 412 {
                "PreconditionFailed"
            } else {
                "SlowDown"
            };
            (status, "application/xml", s3_error(code))
        }
        Reply::NotFound => (404, "application/xml", s3_error("NoSuchKey")),
        Reply::Xml(xml) => (200, "application/xml", xml.as_bytes().to_vec()),
        Reply::S3Error(status, code) => (status, "application/xml", s3_error(code)),
        Reply::OurObject => {
            let write_id = last_write_id.lock().unwrap().clone().unwrap_or_default();
            extra_headers = format!("x-amz-meta-ov-write-id: {write_id}\r\n");
            (200, "application/octet-stream", OK_BODY.to_vec())
        }
        Reply::ObjectWrittenBy(write_id) => {
            extra_headers = format!("x-amz-meta-ov-write-id: {write_id}\r\n");
            (200, "application/octet-stream", OK_BODY.to_vec())
        }
        Reply::Body(body, etag) => {
            extra_headers = format!("ETag: \"{etag}\"\r\n");
            (200, "application/octet-stream", body.as_bytes().to_vec())
        }
        Reply::SlowEtag(delay, etag) => {
            tokio::time::sleep(delay).await;
            extra_headers = format!("ETag: \"{etag}\"\r\n");
            (200, "application/octet-stream", OK_BODY.to_vec())
        }
        Reply::Etag(etag) => {
            extra_headers = format!("ETag: \"{etag}\"\r\n");
            (200, "application/octet-stream", OK_BODY.to_vec())
        }
    };
    let head = format!(
        "HTTP/1.1 {status} X\r\nContent-Length: {}\r\nContent-Type: {content_type}\r\n\
         x-amz-request-id: fake-req\r\n{extra_headers}Connection: close\r\n\r\n",
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

/// Read until the end of the request headers; return the request line and headers.
async fn read_request_head(stream: &mut TcpStream) -> Option<(String, String)> {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 1024];
    while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
        let n = stream.read(&mut chunk).await.ok()?;
        if n == 0 {
            return None;
        }
        buf.extend_from_slice(&chunk[..n]);
    }
    let header_end = buf.windows(4).position(|w| w == b"\r\n\r\n")? + 4;
    let text = String::from_utf8_lossy(&buf[..header_end]).into_owned();
    let (line, headers) = text.split_once("\r\n")?;
    // Drain the body so large uploads (multipart parts) complete before we answer.
    let body_len: usize = header_value(headers, "content-length")
        .and_then(|len| len.parse().ok())
        .unwrap_or(0);
    let mut received = buf.len() - header_end;
    let mut sink = vec![0u8; 64 * 1024];
    while received < body_len {
        let n = stream.read(&mut sink).await.ok()?;
        if n == 0 {
            return None;
        }
        received += n;
    }
    Some((line.to_string(), headers.to_string()))
}

fn header_value(headers: &str, name: &str) -> Option<String> {
    headers.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.trim()
            .eq_ignore_ascii_case(name)
            .then(|| value.trim().to_string())
    })
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

const PAYLOAD: &[u8] = b"payload";
const PART_ETAG: &str = "321c3cf486ed509164edec1e1981fec8";

/// Deadlines short enough that a hung attempt fails in ~0.3s.
const FAST_ATTEMPTS: &[(&str, i64)] = &[
    ("read_timeout_ms", 200),
    ("operation_attempt_timeout_ms", 300),
    ("operation_timeout_ms", 1_000),
    ("metadata_attempt_timeout_ms", 300),
    ("metadata_operation_timeout_ms", 1_000),
    ("max_attempts", 3),
];

fn precondition_failed() -> Reply {
    Reply::Respond {
        status: 412,
        delay: Duration::ZERO,
    }
}

#[tokio::test]
async fn create_new_that_landed_before_timing_out_is_not_reported_as_existing() {
    // Attempt 1 is applied by S3 but its response never arrives; the retry then
    // fails If-None-Match because our own object is there.
    let s3 = FakeS3::start(|i, line| match (i, line.split(' ').next()) {
        (0, _) => Reply::Hang,
        (1, Some("PUT")) => precondition_failed(),
        (_, Some("HEAD")) => Reply::OurObject,
        _ => Reply::NotFound,
    })
    .await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let result = client.put_object_create_new("k", PAYLOAD.to_vec()).await;

    assert!(result.is_ok(), "{result:?}");
    assert_eq!(
        s3.request_log(),
        ["PUT /bucket/k", "PUT /bucket/k", "HEAD /bucket/k"]
    );
}

#[tokio::test]
async fn create_new_conflict_on_first_attempt_is_reported_without_probing() {
    let s3 = FakeS3::start(|_, _| precondition_failed()).await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let result = client.put_object_create_new("k", PAYLOAD.to_vec()).await;

    assert!(matches!(result, Err(Error::AlreadyExists(_))), "{result:?}");
    assert_eq!(s3.requests(), 1);
}

#[tokio::test]
async fn create_new_retry_conflict_with_someone_elses_object_is_reported() {
    let s3 = FakeS3::start(|i, line| match (i, line.split(' ').next()) {
        (0, _) => Reply::Hang,
        (1, Some("PUT")) => precondition_failed(),
        (_, Some("HEAD")) => Reply::ObjectWrittenBy("someone-else"),
        _ => Reply::NotFound,
    })
    .await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let result = client.put_object_create_new("k", PAYLOAD.to_vec()).await;

    assert!(matches!(result, Err(Error::AlreadyExists(_))), "{result:?}");
}

#[tokio::test]
async fn compare_and_swap_put_that_landed_before_timing_out_reports_success() {
    let s3 = FakeS3::start(|i, line| match (i, line.split(' ').next()) {
        (0, _) => Reply::Hang,
        (1, Some("PUT")) => precondition_failed(),
        (_, Some("HEAD")) => Reply::OurObject,
        _ => Reply::NotFound,
    })
    .await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let swapped = client
        .put_object_if_match("k", PAYLOAD.to_vec(), "\"old\"")
        .await;

    assert!(matches!(swapped, Ok(true)), "{swapped:?}");
}

#[tokio::test]
async fn compare_and_swap_delete_that_landed_before_timing_out_reports_success() {
    let s3 = FakeS3::start(|i, _| match i {
        0 => Reply::Hang,
        1 => precondition_failed(),
        _ => Reply::NotFound,
    })
    .await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let deleted = client.delete_object_if_match("k", "\"old\"").await;

    assert!(matches!(deleted, Ok(true)), "{deleted:?}");
    assert_eq!(
        s3.request_log(),
        ["DELETE /bucket/k", "DELETE /bucket/k", "HEAD /bucket/k"]
    );
}

#[tokio::test]
async fn conditional_writes_still_retry_throttling() {
    let s3 = FakeS3::start(|i, _| {
        if i == 0 {
            slow_down()
        } else {
            ok_after(Duration::ZERO)
        }
    })
    .await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let result = client.put_object_create_new("k", PAYLOAD.to_vec()).await;

    assert!(result.is_ok(), "{result:?}");
    assert_eq!(s3.requests(), 2);
}

const INITIATE_MULTIPART: &str = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
    <InitiateMultipartUploadResult><Bucket>bucket</Bucket><Key>k</Key>\
    <UploadId>upload-1</UploadId></InitiateMultipartUploadResult>";

#[tokio::test]
async fn multipart_completion_that_landed_before_timing_out_reports_success() {
    // CompleteMultipartUpload is applied but its response is lost; the SDK
    // retry then gets NoSuchUpload because the upload no longer exists.
    let completes = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let seen = completes.clone();
    let s3 = FakeS3::start(move |_, line| {
        let target = line.split(' ').nth(1).unwrap_or("");
        match line.split(' ').next() {
            Some("POST") if target.contains("uploads") => Reply::Xml(INITIATE_MULTIPART),
            Some("PUT") => Reply::Etag(PART_ETAG),
            Some("POST") => match seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst) {
                0 => Reply::Hang,
                _ => Reply::S3Error(404, "NoSuchUpload"),
            },
            // The completed object carries the write id set at CreateMultipartUpload.
            Some("HEAD") => Reply::OurObject,
            _ => Reply::NotFound,
        }
    })
    .await;
    let mut extra = FAST_ATTEMPTS.to_vec();
    extra.push(("multipart_threshold_bytes", 1));
    let client = s3.client(&extra).await;
    let src = std::env::temp_dir().join(format!("ragfs-mp-{}", std::process::id()));
    std::fs::write(&src, OK_BODY).unwrap();

    let result = client.put_object_from_path("k", &src, false).await;
    std::fs::remove_file(&src).ok();

    assert!(matches!(result, Ok(5)), "{result:?}");
    assert_eq!(completes.load(std::sync::atomic::Ordering::SeqCst), 2);
}

#[tokio::test]
async fn git_ref_swap_that_landed_before_timing_out_is_not_a_conflict() {
    use ragfs::git::ref_store::RefStore;
    use ragfs::git::{S3Config, S3RefStore};
    use ragfs::plugins::s3fs::resilience::S3ResilienceSettings;

    const OLD: &str = "1111111111111111111111111111111111111111";
    const NEW: &str = "2222222222222222222222222222222222222222";
    // Read OLD, the swap's response is lost after S3 applied it, the SDK retry
    // fails If-Match, and the re-read shows the ref already at NEW.
    let s3 = FakeS3::start(|i, _| match i {
        0 => Reply::Body("1111111111111111111111111111111111111111\n", "etag-old"),
        1 => Reply::Hang,
        2 => precondition_failed(),
        _ => Reply::Body("2222222222222222222222222222222222222222\n", "etag-new"),
    })
    .await;
    let store = S3RefStore::from_config(S3Config {
        bucket: "bucket".to_string(),
        endpoint: Some(s3.endpoint.clone()),
        access_key_id: Some("ak".to_string()),
        secret_access_key: Some("sk".to_string()),
        resilience: S3ResilienceSettings {
            read_timeout: Duration::from_millis(200),
            operation_attempt_timeout: Duration::from_millis(300),
            operation_timeout: Duration::from_secs(1),
            initial_backoff: Duration::from_millis(1),
            max_backoff: Duration::from_millis(5),
            ..S3ResilienceSettings::default()
        },
        ..S3Config::default()
    })
    .await
    .unwrap();
    let oid = |hex: &str| gix_hash::ObjectId::from_hex(hex.as_bytes()).unwrap();

    let result = store
        .cas_update("acct", "refs/heads/main", Some(oid(OLD)), oid(NEW))
        .await;

    assert!(result.is_ok(), "{result:?}");
    assert_eq!(s3.requests(), 4);
}

#[tokio::test]
async fn multipart_no_such_upload_for_someone_elses_object_is_an_error() {
    // The upload was aborted (e.g. by a lifecycle rule) and the key holds an
    // older object of the same size: that is not our write.
    let s3 = FakeS3::start(|_, line| {
        let target = line.split(' ').nth(1).unwrap_or("");
        match line.split(' ').next() {
            Some("POST") if target.contains("uploads") => Reply::Xml(INITIATE_MULTIPART),
            Some("PUT") => Reply::Etag(PART_ETAG),
            Some("POST") => Reply::S3Error(404, "NoSuchUpload"),
            Some("HEAD") => Reply::ObjectWrittenBy("older-writer"),
            Some("DELETE") => Reply::Respond {
                status: 204,
                delay: Duration::ZERO,
            },
            _ => Reply::NotFound,
        }
    })
    .await;
    let mut extra = FAST_ATTEMPTS.to_vec();
    extra.push(("multipart_threshold_bytes", 1));
    let client = s3.client(&extra).await;
    let src = std::env::temp_dir().join(format!("ragfs-mp-old-{}", std::process::id()));
    std::fs::write(&src, OK_BODY).unwrap();

    let result = client.put_object_from_path("k", &src, false).await;
    std::fs::remove_file(&src).ok();

    assert!(result.is_err(), "{result:?}");
}

#[tokio::test]
async fn compare_and_swap_delete_on_missing_bucket_is_an_error() {
    let s3 = FakeS3::start(|_, _| Reply::S3Error(404, "NoSuchBucket")).await;
    let client = s3.client(FAST_ATTEMPTS).await;

    let result = client.delete_object_if_match("k", "\"old\"").await;

    assert!(result.is_err(), "{result:?}");
}

const COMPLETE_MULTIPART: &str = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
    <CompleteMultipartUploadResult><Bucket>bucket</Bucket><Key>k</Key>\
    <ETag>\"done-3\"</ETag></CompleteMultipartUploadResult>";

/// Route a multipart upload whose parts each take `part_delay`, logging part
/// uploads; `fail_part` answers that part number with a 403.
fn multipart_script(
    part_delay: Duration,
    fail_part: Option<&'static str>,
) -> impl Fn(usize, &str) -> Reply + Send + Sync + 'static {
    move |_, line| {
        let target = line.split(' ').nth(1).unwrap_or("");
        match line.split(' ').next() {
            Some("POST") if target.contains("uploads") => Reply::Xml(INITIATE_MULTIPART),
            Some("PUT")
                if fail_part.is_some_and(|n| target.contains(&format!("partNumber={n}&"))) =>
            {
                Reply::S3Error(403, "AccessDenied")
            }
            Some("PUT") => Reply::SlowEtag(part_delay, PART_ETAG),
            Some("POST") => Reply::Xml(COMPLETE_MULTIPART),
            Some("DELETE") => Reply::Respond {
                status: 204,
                delay: Duration::ZERO,
            },
            _ => Reply::NotFound,
        }
    }
}

/// A source file of three multipart parts at the minimum part size (5 MiB).
fn three_part_file(name: &str) -> std::path::PathBuf {
    let path = std::env::temp_dir().join(format!("ragfs-{name}-{}", std::process::id()));
    std::fs::write(&path, vec![7u8; 11 * 1024 * 1024]).unwrap();
    path
}

const MULTIPART_PARALLEL: &[(&str, i64)] = &[
    ("multipart_threshold_bytes", 1),
    ("multipart_part_size_bytes", 5 * 1024 * 1024),
    ("multipart_concurrency", 3),
];

#[tokio::test]
async fn multipart_parts_upload_concurrently() {
    let s3 = FakeS3::start(multipart_script(Duration::from_millis(400), None)).await;
    let client = s3.client(MULTIPART_PARALLEL).await;
    let src = three_part_file("mp-par");

    let started = Instant::now();
    let result = client.put_object_from_path("k", &src, false).await;
    let elapsed = started.elapsed();
    std::fs::remove_file(&src).ok();

    assert!(
        matches!(result, Ok(n) if n == 11 * 1024 * 1024),
        "{result:?}"
    );
    // Three 400ms parts at once take ~400ms; one at a time would take 1.2s+.
    assert!(elapsed < Duration::from_millis(1_000), "{elapsed:?}");
    let parts = s3
        .request_log()
        .iter()
        .filter(|r| r.starts_with("PUT"))
        .count();
    assert_eq!(parts, 3);
}

#[tokio::test]
async fn multipart_part_failure_aborts_the_upload() {
    let s3 = FakeS3::start(multipart_script(Duration::from_millis(50), Some("2"))).await;
    let client = s3.client(MULTIPART_PARALLEL).await;
    let src = three_part_file("mp-fail");

    let result = client.put_object_from_path("k", &src, false).await;
    std::fs::remove_file(&src).ok();

    assert!(result.is_err(), "{result:?}");
    assert!(
        s3.request_log().iter().any(|r| r.starts_with("DELETE")),
        "{:?}",
        s3.request_log()
    );
    // Only CreateMultipartUpload was POSTed (the log drops query strings), no completion.
    let posts = s3
        .request_log()
        .iter()
        .filter(|r| r.starts_with("POST"))
        .count();
    assert_eq!(posts, 1, "completed despite failure");
}
