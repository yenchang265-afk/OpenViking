//! S3FS timeout/retry behaviour against an in-process fake S3 endpoint.
//!
//! The fake server speaks just enough HTTP/1.1 to stall, throttle (503 SlowDown)
//! or answer GET/HEAD, so these run without a real S3 backend.

#![cfg(feature = "s3")]

use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use ragfs::core::{ConfigValue, Error};
use ragfs::plugins::s3fs::client::S3Client;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

/// What the fake server does with the N-th request (0-based).
#[derive(Clone, Copy)]
enum Reply {
    /// Read the request and never answer.
    Hang,
    /// Answer after `delay` with `status`; 200 carries `OK_BODY`, others an S3 error.
    Respond { status: u16, delay: Duration },
}

const OK_BODY: &[u8] = b"hello";

struct FakeS3 {
    endpoint: String,
    requests: Arc<AtomicUsize>,
}

impl FakeS3 {
    async fn start(script: impl Fn(usize) -> Reply + Send + Sync + 'static) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let requests = Arc::new(AtomicUsize::new(0));
        let counter = requests.clone();
        let script = Arc::new(script);
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                let counter = counter.clone();
                let script = script.clone();
                tokio::spawn(async move { serve(stream, counter, script).await });
            }
        });
        Self { endpoint, requests }
    }

    fn requests(&self) -> usize {
        self.requests.load(Ordering::SeqCst)
    }

    async fn client(&self, extra: &[(&str, i64)]) -> S3Client {
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
        S3Client::new(&config).await.unwrap()
    }
}

async fn serve(
    mut stream: TcpStream,
    counter: Arc<AtomicUsize>,
    script: Arc<dyn Fn(usize) -> Reply + Send + Sync>,
) {
    let Some(request_line) = read_request_head(&mut stream).await else {
        return;
    };
    let index = counter.fetch_add(1, Ordering::SeqCst);
    let is_head = request_line.starts_with("HEAD ");
    match script(index) {
        Reply::Hang => {
            // Hold the connection open until the client gives up.
            let mut sink = [0u8; 64];
            while matches!(stream.read(&mut sink).await, Ok(n) if n > 0) {}
        }
        Reply::Respond { status, delay } => {
            tokio::time::sleep(delay).await;
            let body: Vec<u8> = if status == 200 {
                OK_BODY.to_vec()
            } else {
                b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
                  <Error><Code>SlowDown</Code><Message>Please reduce your request rate.</Message>\
                  <RequestId>fake-req</RequestId></Error>"
                    .to_vec()
            };
            let head = format!(
                "HTTP/1.1 {status} X\r\nContent-Length: {}\r\nContent-Type: {}\r\n\
                 x-amz-request-id: fake-req\r\nConnection: close\r\n\r\n",
                body.len(),
                if status == 200 {
                    "application/octet-stream"
                } else {
                    "application/xml"
                },
            );
            let _ = stream.write_all(head.as_bytes()).await;
            if !is_head {
                let _ = stream.write_all(&body).await;
            }
            let _ = stream.shutdown().await;
        }
    }
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
    let s3 = FakeS3::start(|_| Reply::Hang).await;
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
    let s3 = FakeS3::start(|i| {
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
    let s3 = FakeS3::start(|_| slow_down()).await;
    let client = s3.client(&[("max_attempts", 2)]).await;

    let result = client.get_object("k").await;

    assert!(matches!(result, Err(Error::Network(_))), "{result:?}");
    assert_eq!(s3.requests(), 2);
}

#[tokio::test]
async fn metadata_calls_use_the_tighter_deadline() {
    // Every response takes 600ms: within the data deadline, beyond the metadata one.
    let s3 = FakeS3::start(|_| ok_after(Duration::from_millis(600))).await;
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
