//! S3 Client wrapper
//!
//! Provides a filesystem-oriented abstraction over the AWS S3 SDK.
//! Supports AWS S3 and S3-compatible services (MinIO, LocalStack, TOS).

use crate::core::{ConfigValue, Error, Result};
use aws_sdk_s3::config::http::HttpResponse;
use aws_sdk_s3::config::retry::RetryConfig;
use aws_sdk_s3::config::{BehaviorVersion, Credentials, Region};
use aws_sdk_s3::error::ProvideErrorMetadata;
use aws_sdk_s3::error::SdkError;
use aws_sdk_s3::operation::{RequestId, RequestIdExt};
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::types::{CompletedMultipartUpload, CompletedPart};
use aws_sdk_s3::Client;
use bytes::Bytes;
use std::collections::HashMap;
use std::fmt::Write as _;
use std::future::Future;
use std::path::Path;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::sync::{Semaphore, SemaphorePermit};

use super::multipart::{effective_part_size, part_ranges, MultipartSettings};
use super::resilience::S3ResilienceSettings;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const ENCODED_SEGMENT_PREFIX: char = '!';
const HEX_UPPER: &[u8; 16] = b"0123456789ABCDEF";

fn partial_delete_error(bucket: &str, errors: &[aws_sdk_s3::types::Error]) -> Option<Error> {
    if errors.is_empty() {
        return None;
    }

    let details = errors
        .iter()
        .map(|error| {
            format!(
                "key={} code={} message={}",
                error.key().unwrap_or("<unknown>"),
                error.code().unwrap_or("<unknown>"),
                error.message().unwrap_or("<unknown>")
            )
        })
        .collect::<Vec<_>>()
        .join("; ");
    Some(Error::internal(format!(
        "S3 DeleteObjects partial failure: bucket={bucket} errors=[{details}]"
    )))
}

fn build_s3_error_message(
    op: &str,
    scope: &str,
    raw_error: &str,
    code: Option<&str>,
    message: Option<&str>,
    request_id: Option<&str>,
    extended_request_id: Option<&str>,
) -> String {
    let mut output = format!("S3 {op} error: {scope}");

    if let Some(code) = code {
        let _ = write!(output, " code={code}");
    }
    if let Some(message) = message {
        let _ = write!(output, " message={message}");
    }
    if let Some(request_id) = request_id {
        let _ = write!(output, " request_id={request_id}");
    }
    if let Some(extended_request_id) = extended_request_id {
        let _ = write!(output, " extended_request_id={extended_request_id}");
    }

    let _ = write!(output, " raw={raw_error}");
    output
}

fn is_s3_compatible_not_found_code<E>(err: &E) -> bool
where
    E: ProvideErrorMetadata,
{
    // AWS S3 uses the modeled NoSuchKey error; some TOS direct backends return NotFound.
    err.code()
        .map(|code| code == "NotFound")
        .unwrap_or(false)
}

/// How a failed S3 request is surfaced, so callers can tell retryable
/// backend trouble (timeouts, throttling, 5xx) from permanent failures.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum S3FailureClass {
    Timeout,
    Transient,
    Permanent,
}

impl S3FailureClass {
    fn into_error(self, message: String) -> Error {
        match self {
            Self::Timeout => Error::timeout(message),
            Self::Transient => Error::Network(message),
            Self::Permanent => Error::internal(message),
        }
    }
}

/// Error codes S3 and S3-compatible services use for throttling or server-side trouble.
const TRANSIENT_S3_ERROR_CODES: &[&str] = &[
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "TooManyRequests",
    "RequestTimeout",
    "InternalError",
    "ServiceUnavailable",
];

fn is_transient_s3_status(status: u16) -> bool {
    matches!(status, 429 | 500 | 502 | 503 | 504)
}

fn classify_sdk_error<E, R>(sdk_err: &SdkError<E, R>) -> S3FailureClass
where
    E: ProvideErrorMetadata,
    R: 'static,
{
    use std::any::Any;

    match sdk_err {
        SdkError::TimeoutError(_) => S3FailureClass::Timeout,
        SdkError::DispatchFailure(failure) if failure.is_timeout() => S3FailureClass::Timeout,
        SdkError::DispatchFailure(failure) if failure.is_user() => S3FailureClass::Permanent,
        SdkError::DispatchFailure(_) | SdkError::ResponseError(_) => S3FailureClass::Transient,
        SdkError::ServiceError(se) => {
            let transient_code = se
                .err()
                .code()
                .is_some_and(|code| TRANSIENT_S3_ERROR_CODES.contains(&code));
            let transient_status = (se.raw() as &dyn Any)
                .downcast_ref::<HttpResponse>()
                .is_some_and(|resp| is_transient_s3_status(resp.status().as_u16()));
            if transient_code || transient_status {
                S3FailureClass::Transient
            } else {
                S3FailureClass::Permanent
            }
        }
        _ => S3FailureClass::Permanent,
    }
}

fn format_sdk_s3_error<E, R>(op: &str, scope: &str, sdk_err: &SdkError<E, R>) -> Error
where
    E: std::fmt::Display + ProvideErrorMetadata + RequestId + RequestIdExt,
    R: std::fmt::Debug + Send + Sync + 'static,
{
    use std::any::Any;

    let class = classify_sdk_error(sdk_err);
    match sdk_err {
        SdkError::ServiceError(se) => {
            if let Some(resp) = (se.raw() as &dyn Any).downcast_ref::<HttpResponse>() {
                let status = resp.status().as_u16();
                let headers = resp.headers();
                class.into_error(build_s3_error_message(
                    op,
                    scope,
                    &format!("HTTP {}: {}", status, se.err()),
                    se.err().code(),
                    se.err().message(),
                    se.err()
                        .request_id()
                        .or_else(|| headers.get("x-amz-request-id")),
                    se.err()
                        .extended_request_id()
                        .or_else(|| headers.get("x-amz-id-2")),
                ))
            } else {
                class.into_error(build_s3_error_message(
                    op,
                    scope,
                    &format!("service error: {}", se.err()),
                    se.err().code(),
                    se.err().message(),
                    se.err().request_id(),
                    se.err().extended_request_id(),
                ))
            }
        }
        _ => class.into_error(build_s3_error_message(
            op,
            scope,
            &sdk_err.to_string(),
            None,
            None,
            None,
            None,
        )),
    }
}

/// Return true when an S3 SDK service error represents a failed conditional request.
fn is_s3_conditional_failure<E, R>(sdk_err: &SdkError<E, R>) -> bool
where
    E: ProvideErrorMetadata,
    R: 'static,
{
    use std::any::Any;

    let SdkError::ServiceError(service_err) = sdk_err else {
        return false;
    };

    if matches!(
        service_err.err().code(),
        Some("PreconditionFailed" | "ConditionalRequestConflict")
    ) {
        return true;
    }

    (service_err.raw() as &dyn Any)
        .downcast_ref::<HttpResponse>()
        .is_some_and(|response| matches!(response.status().as_u16(), 409 | 412))
}

/// Why a conditional request attempt did not apply.
enum ConditionalFailure {
    /// The precondition (If-Match / If-None-Match) did not hold.
    Precondition,
    /// Any other failure, already classified.
    Failed(Error),
}

fn conditional_failure<E, R>(op: &str, scope: &str, sdk_err: &SdkError<E, R>) -> ConditionalFailure
where
    E: std::fmt::Display + ProvideErrorMetadata + RequestId + RequestIdExt,
    R: std::fmt::Debug + Send + Sync + 'static,
{
    if is_s3_conditional_failure(sdk_err) {
        ConditionalFailure::Precondition
    } else {
        ConditionalFailure::Failed(format_sdk_s3_error(op, scope, sdk_err))
    }
}

/// Disable SDK retries for one request; `run_conditional` retries it safely.
fn single_attempt(config: aws_sdk_s3::config::Builder) -> aws_sdk_s3::config::Builder {
    config.retry_config(RetryConfig::disabled())
}

/// User-metadata key tagging each conditional write with a per-call id, so a
/// retry can tell whether an earlier attempt of *this* call was applied (a body
/// hash cannot: a concurrent writer may store identical bytes).
const WRITE_ID_META: &str = "ov-write-id";

fn new_write_id() -> String {
    uuid::Uuid::new_v4().to_string()
}

/// A response body that fails mid-stream (reset, stall, truncation) is a transport failure.
fn format_read_body_error(bucket: &str, key: &str, raw_error: impl std::fmt::Display) -> Error {
    S3FailureClass::Transient.into_error(build_s3_error_message(
        "ReadBody",
        &format!("bucket={bucket} key={key}"),
        &raw_error.to_string(),
        None,
        None,
        None,
        None,
    ))
}

fn format_bucket_s3_error(op: &str, bucket: &str, raw_error: impl std::fmt::Display) -> Error {
    Error::internal(build_s3_error_message(
        op,
        &format!("bucket={bucket}"),
        &raw_error.to_string(),
        None,
        None,
        None,
        None,
    ))
}

fn encode_path(path: &str, normalize_encoding_chars: &str) -> String {
    if normalize_encoding_chars.is_empty() {
        return path.to_string();
    }

    let target_chars: Vec<char> = normalize_encoding_chars.chars().collect();
    if !path
        .chars()
        .any(|ch| ch != '/' && ch.is_ascii() && target_chars.contains(&ch))
    {
        return path.to_string();
    }

    let extra = path
        .chars()
        .filter(|ch| *ch != '/' && ch.is_ascii() && target_chars.contains(ch))
        .count()
        * 2;
    let mut encoded = String::with_capacity(path.len() + extra);

    for ch in path.chars() {
        if ch == '/' || !ch.is_ascii() || !target_chars.contains(&ch) {
            encoded.push(ch);
        } else {
            push_encoded_byte(&mut encoded, ch as u8);
        }
    }

    encoded
}

fn decode_path(path: &str, normalize_encoding_chars: &str) -> String {
    if normalize_encoding_chars.is_empty() {
        return path.to_string();
    }

    decode_segment(path)
}

fn decode_segment(segment: &str) -> String {
    if segment.is_empty() {
        return String::new();
    }

    let bytes = segment.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut idx = 0usize;

    while idx < bytes.len() {
        if bytes[idx] == ENCODED_SEGMENT_PREFIX as u8 && idx + 2 < bytes.len() {
            let hi = decode_hex_nibble(bytes[idx + 1]);
            let lo = decode_hex_nibble(bytes[idx + 2]);
            if let (Some(hi), Some(lo)) = (hi, lo) {
                decoded.push((hi << 4) | lo);
                idx += 3;
                continue;
            }
        }

        decoded.push(bytes[idx]);
        idx += 1;
    }

    String::from_utf8(decoded).unwrap_or_else(|_| segment.to_string())
}

fn push_encoded_byte(output: &mut String, byte: u8) {
    output.push(ENCODED_SEGMENT_PREFIX);
    output.push(HEX_UPPER[(byte >> 4) as usize] as char);
    output.push(HEX_UPPER[(byte & 0x0f) as usize] as char);
}

fn decode_hex_nibble(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        _ => None,
    }
}

/// Directory marker mode
#[derive(Debug, Clone, PartialEq)]
pub enum DirectoryMarkerMode {
    /// No directory markers (pure prefix-based)
    None,
    /// Zero-byte marker objects (default, works with AWS S3 and MinIO)
    Empty,
    /// Single-byte newline marker (for services that reject zero-byte objects like TOS)
    NonEmpty,
}

impl DirectoryMarkerMode {
    /// Parse from string
    pub fn from_str(s: &str) -> Self {
        match s {
            "none" => Self::None,
            "nonempty" => Self::NonEmpty,
            _ => Self::Empty, // default
        }
    }

    /// Get the marker data to write for directory creation
    pub fn marker_data(&self) -> Option<Vec<u8>> {
        match self {
            Self::None => Option::None,
            Self::Empty => Some(Vec::new()),
            Self::NonEmpty => Some(b"\n".to_vec()),
        }
    }
}

/// Object metadata from HeadObject
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ObjectMeta {
    /// Object key
    pub key: String,
    /// Object size in bytes
    pub size: i64,
    /// Last modified time
    pub last_modified: SystemTime,
    /// Whether this is a directory marker
    pub is_dir_marker: bool,
}

/// One flat `ListObjectsV2` page used by S3-backed tree/glob traversal.
#[derive(Debug, Clone)]
pub struct ListTreePage {
    pub objects: Vec<ObjectMeta>,
    pub next_continuation_token: Option<String>,
}

/// Result of a ListObjects operation
#[derive(Debug)]
pub struct ListResult {
    /// Files (non-directory objects)
    pub files: Vec<ObjectMeta>,
    /// Directory prefixes (common prefixes)
    pub directories: Vec<String>,
}

/// Convert AWS DateTime to SystemTime
fn aws_datetime_to_systemtime(dt: &aws_sdk_s3::primitives::DateTime) -> SystemTime {
    let secs = dt.secs();
    if secs >= 0 {
        UNIX_EPOCH + Duration::from_secs(secs as u64)
    } else {
        UNIX_EPOCH
    }
}

/// The Content-Type to be written to S3 is inferred from the filename suffix of the object key.
fn detect_content_type_for_key(key: &str) -> Option<String> {
    if key.ends_with('/') {
        return None;
    }

    Some(
        mime_guess::from_path(key)
            .first_or_octet_stream()
            .essence_str()
            .to_string(),
    )
}

/// S3 Client wrapper
pub struct S3Client {
    client: Client,
    bucket: String,
    prefix: String,
    normalize_encoding_chars: String,
    marker_mode: DirectoryMarkerMode,
    disable_batch_delete: bool,
    auto_detect_content_type: bool,
    multipart: MultipartSettings,
    resilience: S3ResilienceSettings,
    /// Caps in-flight requests per mount; `None` when unlimited.
    limiter: Option<Semaphore>,
}

impl S3Client {
    fn strip_prefix_with_codec(prefix: &str, normalize_encoding_chars: &str, key: &str) -> String {
        let stripped = if prefix.is_empty() {
            key
        } else {
            let prefix = format!("{}/", prefix.trim_end_matches('/'));
            key.strip_prefix(&prefix).unwrap_or(key)
        };

        decode_path(stripped, normalize_encoding_chars)
    }

    /// Create a new S3 client from configuration
    pub async fn new(config: &HashMap<String, ConfigValue>) -> Result<Self> {
        let bucket = config
            .get("bucket")
            .and_then(|v| v.as_string())
            .ok_or_else(|| Error::config("bucket is required for S3FS"))?
            .to_string();

        let region = config
            .get("region")
            .and_then(|v| v.as_string())
            .unwrap_or("us-east-1")
            .to_string();

        let raw_endpoint = config.get("endpoint").and_then(|v| v.as_string());
        let use_ssl = if let Some(v) = config.get("use_ssl").and_then(|v| v.as_bool()) {
            v
        } else if let Some(v) = config.get("disable_ssl").and_then(|v| v.as_bool()) {
            !v
        } else {
            true
        };
        let endpoint = raw_endpoint.map(|ep| {
            if ep.starts_with("https://") || ep.starts_with("http://") {
                ep.to_string()
            } else if use_ssl {
                format!("https://{}", ep)
            } else {
                format!("http://{}", ep)
            }
        });

        let access_key = config
            .get("access_key_id")
            .and_then(|v| v.as_string())
            .map(|s| s.to_string());

        let secret_key = config
            .get("secret_access_key")
            .and_then(|v| v.as_string())
            .map(|s| s.to_string());

        let use_path_style = config
            .get("use_path_style")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);

        let prefix = config
            .get("prefix")
            .and_then(|v| v.as_string())
            .unwrap_or("")
            .to_string();

        let normalize_encoding_chars = config
            .get("normalize_encoding_chars")
            .and_then(|v| v.as_string())
            .unwrap_or("?#%+@")
            .to_string();

        let marker_mode = config
            .get("directory_marker_mode")
            .and_then(|v| v.as_string())
            .map(|s| DirectoryMarkerMode::from_str(s))
            .unwrap_or(DirectoryMarkerMode::Empty);

        let disable_batch_delete = config
            .get("disable_batch_delete")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let auto_detect_content_type = config
            .get("auto_detect_content_type")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let multipart = MultipartSettings::from_config(config)?;
        let resilience = S3ResilienceSettings::from_config(config)?;

        // Build S3 config
        let mut s3_config_builder = resilience.apply(
            aws_sdk_s3::Config::builder()
                .behavior_version(BehaviorVersion::latest())
                .region(Region::new(region))
                .force_path_style(use_path_style),
        );

        // Set endpoint if provided (MinIO, LocalStack, TOS)
        if let Some(ep) = endpoint {
            s3_config_builder = s3_config_builder.endpoint_url(ep.to_string());
        }

        // Set credentials if provided, otherwise SDK uses default chain
        if let (Some(ak), Some(sk)) = (access_key, secret_key) {
            let creds = Credentials::new(ak, sk, None, None, "ragfs-s3fs");
            s3_config_builder = s3_config_builder.credentials_provider(creds);
        }

        let s3_config = s3_config_builder.build();
        let client = Client::from_conf(s3_config);

        Ok(Self {
            client,
            bucket,
            prefix,
            normalize_encoding_chars,
            marker_mode,
            disable_batch_delete,
            auto_detect_content_type,
            multipart,
            resilience,
            limiter: (resilience.max_concurrent_requests > 0)
                .then(|| Semaphore::new(resilience.max_concurrent_requests)),
        })
    }

    /// Take a request slot, held for the whole S3 call including its response body.
    ///
    /// Bounds load on a slow backend; a caller that cannot get a slot within the
    /// metadata deadline fails with a timeout instead of queueing indefinitely.
    async fn acquire_slot(&self) -> Result<Option<SemaphorePermit<'_>>> {
        let Some(limiter) = &self.limiter else {
            return Ok(None);
        };
        let wait = self.resilience.metadata_operation_timeout;
        match tokio::time::timeout(wait, limiter.acquire()).await {
            Ok(Ok(permit)) => Ok(Some(permit)),
            Ok(Err(_)) => Err(Error::internal("S3 request limiter closed")),
            Err(_) => Err(Error::timeout(format!(
                "S3 request queue: no free slot within {wait:?} \
                 (max_concurrent_requests={}, bucket={})",
                self.resilience.max_concurrent_requests, self.bucket
            ))),
        }
    }

    /// Build the full S3 key from a filesystem path
    pub fn build_key(&self, path: &str) -> String {
        let clean = encode_path(path.trim_start_matches('/'), &self.normalize_encoding_chars);
        if self.prefix.is_empty() {
            clean
        } else {
            let prefix = self.prefix.trim_end_matches('/');
            if clean.is_empty() {
                format!("{}/", prefix)
            } else {
                format!("{}/{}", prefix, clean)
            }
        }
    }

    /// Strip the prefix from an S3 key to get the filesystem path
    pub fn strip_prefix(&self, key: &str) -> String {
        Self::strip_prefix_with_codec(&self.prefix, &self.normalize_encoding_chars, key)
    }

    /// Get an object's contents
    pub async fn get_object(&self, key: &str) -> Result<Vec<u8>> {
        let _slot = self.acquire_slot().await?;
        let resp = match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(resp) => resp,
            Err(sdk_err) => {
                // Classify before narrowing to the service error: timeouts and
                // dispatch failures are lost once converted.
                if sdk_err
                    .as_service_error()
                    .is_some_and(|e| e.is_no_such_key() || is_s3_compatible_not_found_code(e))
                {
                    return Err(Error::NotFound(key.to_string()));
                }
                return Err(format_sdk_s3_error(
                    "GetObject",
                    &format!("bucket={} key={}", self.bucket, key),
                    &sdk_err,
                ));
            }
        };

        let bytes = resp
            .body
            .collect()
            .await
            .map_err(|e| format_read_body_error(&self.bucket, key, e))?;

        Ok(bytes.to_vec())
    }

    /// Get an object's contents and ETag for conditional updates.
    pub async fn get_object_with_etag(&self, key: &str) -> Result<Option<(Vec<u8>, String)>> {
        let _slot = self.acquire_slot().await?;
        let resp = match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(resp) => resp,
            Err(sdk_err) => {
                if sdk_err
                    .as_service_error()
                    .is_some_and(|e| e.is_no_such_key() || is_s3_compatible_not_found_code(e))
                {
                    return Ok(None);
                }
                return Err(format_sdk_s3_error(
                    "GetObjectWithEtag",
                    &format!("bucket={} key={}", self.bucket, key),
                    &sdk_err,
                ));
            }
        };

        let etag = resp.e_tag().ok_or_else(|| {
            Error::internal(format!(
                "S3 GetObjectWithEtag missing ETag: bucket={} key={key}",
                self.bucket
            ))
        })?.to_string();

        let bytes = resp
            .body
            .collect()
            .await
            .map_err(|e| format_read_body_error(&self.bucket, key, e))?;

        Ok(Some((bytes.to_vec(), etag)))
    }

    /// Get an object's contents with range request
    pub async fn get_object_range(&self, key: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        let _slot = self.acquire_slot().await?;
        let range = if size == 0 {
            format!("bytes={}-", offset)
        } else {
            format!("bytes={}-{}", offset, offset + size - 1)
        };

        let resp = match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .range(range)
            .send()
            .await
        {
            Ok(resp) => resp,
            Err(sdk_err) => {
                if sdk_err
                    .as_service_error()
                    .is_some_and(|e| e.is_no_such_key() || is_s3_compatible_not_found_code(e))
                {
                    return Err(Error::NotFound(key.to_string()));
                }
                return Err(format_sdk_s3_error(
                    "GetObjectRange",
                    &format!("bucket={} key={}", self.bucket, key),
                    &sdk_err,
                ));
            }
        };

        let bytes = resp
            .body
            .collect()
            .await
            .map_err(|e| format_read_body_error(&self.bucket, key, e))?;

        Ok(bytes.to_vec())
    }

    /// Upload an object
    pub async fn put_object(&self, key: &str, data: Vec<u8>) -> Result<()> {
        let _slot = self.acquire_slot().await?;
        let mut request = self
            .client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(ByteStream::from(data));

        if self.auto_detect_content_type {
            if let Some(content_type) = detect_content_type_for_key(key) {
                request = request.content_type(content_type);
            }
        }

        request.send().await.map_err(|e| {
            format_sdk_s3_error(
                "PutObject",
                &format!("bucket={} key={key}", self.bucket),
                &e,
            )
        })?;

        Ok(())
    }

    /// Upload an object only when the key does not already exist.
    pub async fn put_object_create_new(&self, key: &str, data: Vec<u8>) -> Result<()> {
        let body = Bytes::from(data);
        let write_id = new_write_id();
        let scope = format!("bucket={} key={key}", self.bucket);
        let created = self
            .run_conditional(
                || async {
                    let mut request = self
                        .client
                        .put_object()
                        .bucket(&self.bucket)
                        .key(key)
                        .if_none_match("*")
                        .metadata(WRITE_ID_META, &write_id)
                        .body(ByteStream::from(body.clone()));
                    if self.auto_detect_content_type {
                        if let Some(content_type) = detect_content_type_for_key(key) {
                            request = request.content_type(content_type);
                        }
                    }
                    request
                        .customize()
                        .config_override(single_attempt(aws_sdk_s3::config::Builder::default()))
                        .send()
                        .await
                        .map(|_| ())
                        .map_err(|e| conditional_failure("PutObjectCreateNew", &scope, &e))
                },
                || async { self.has_write_id(key, &write_id).await },
            )
            .await?;
        if created {
            Ok(())
        } else {
            Err(Error::already_exists(key))
        }
    }

    /// Replace an object only when its ETag still matches `etag`.
    ///
    /// Returns `Ok(false)` when the object changed since `etag` was read.
    pub async fn put_object_if_match(&self, key: &str, data: Vec<u8>, etag: &str) -> Result<bool> {
        let body = Bytes::from(data);
        let write_id = new_write_id();
        let scope = format!("bucket={} key={key}", self.bucket);
        self.run_conditional(
            || async {
                let mut request = self
                    .client
                    .put_object()
                    .bucket(&self.bucket)
                    .key(key)
                    .if_match(etag)
                    .metadata(WRITE_ID_META, &write_id)
                    .body(ByteStream::from(body.clone()));
                if self.auto_detect_content_type {
                    if let Some(content_type) = detect_content_type_for_key(key) {
                        request = request.content_type(content_type);
                    }
                }
                request
                    .customize()
                    .config_override(single_attempt(aws_sdk_s3::config::Builder::default()))
                    .send()
                    .await
                    .map(|_| ())
                    .map_err(|e| conditional_failure("PutObjectIfMatch", &scope, &e))
            },
            || async { self.has_write_id(key, &write_id).await },
        )
        .await
    }

    /// Run a conditional request with retries that cannot misreport its own success.
    ///
    /// SDK retries are disabled for conditional requests: when an attempt times
    /// out after S3 applied it, a blind retry fails its precondition and would
    /// report a conflict for a write that succeeded. Here transient failures are
    /// retried with backoff, and a precondition failure on a *retry* asks
    /// `landed` whether an earlier attempt took effect before reporting it.
    ///
    /// Returns `Ok(true)` when applied, `Ok(false)` when the precondition failed.
    /// Takes a request slot per attempt and releases it during backoff.
    async fn run_conditional<S, SFut, L, LFut>(&self, send: S, landed: L) -> Result<bool>
    where
        S: Fn() -> SFut,
        SFut: Future<Output = std::result::Result<(), ConditionalFailure>>,
        L: Fn() -> LFut,
        LFut: Future<Output = Result<bool>>,
    {
        let attempts = self.resilience.max_attempts;
        let mut backoff = self.resilience.initial_backoff;
        let mut attempt = 1;
        loop {
            let outcome = {
                let _slot = self.acquire_slot().await?;
                send().await
            };
            match outcome {
                Ok(()) => return Ok(true),
                Err(ConditionalFailure::Precondition) if attempt == 1 => return Ok(false),
                Err(ConditionalFailure::Precondition) => {
                    let _slot = self.acquire_slot().await?;
                    return landed().await;
                }
                Err(ConditionalFailure::Failed(err))
                    if attempt < attempts
                        && matches!(err, Error::Timeout(_) | Error::Network(_)) =>
                {
                    tokio::time::sleep(backoff).await;
                    backoff = (backoff * 2).min(self.resilience.max_backoff);
                    attempt += 1;
                }
                Err(ConditionalFailure::Failed(err)) => return Err(err),
            }
        }
    }

    /// Whether `key` currently holds the object written with `write_id`.
    async fn has_write_id(&self, key: &str, write_id: &str) -> Result<bool> {
        Ok(self.object_write_id(key).await?.flatten().as_deref() == Some(write_id))
    }

    /// `None` if `key` does not exist, otherwise the write id it was stored with.
    ///
    /// Takes no request slot: callers already hold one.
    async fn object_write_id(&self, key: &str) -> Result<Option<Option<String>>> {
        match self
            .client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .customize()
            .config_override(self.resilience.metadata_override())
            .send()
            .await
        {
            Ok(resp) => Ok(Some(
                resp.metadata()
                    .and_then(|meta| meta.get(WRITE_ID_META))
                    .cloned(),
            )),
            Err(e) if e.as_service_error().is_some_and(|err| err.is_not_found()) => Ok(None),
            Err(e) => Err(format_sdk_s3_error(
                "HeadObject",
                &format!("bucket={} key={key}", self.bucket),
                &e,
            )),
        }
    }

    /// Upload a local file, using multipart above the configured threshold.
    ///
    /// Memory stays bounded by the threshold (single PUT) or one part (multipart).
    /// With `create_new`, small objects use a conditional PUT; multipart uploads check
    /// for an existing key first, which leaves a race window with concurrent creators.
    pub async fn put_object_from_path(
        &self,
        key: &str,
        src: &Path,
        create_new: bool,
    ) -> Result<u64> {
        let total = tokio::fs::metadata(src).await?.len();
        if total <= self.multipart.threshold_bytes {
            let data = tokio::fs::read(src).await?;
            if create_new {
                self.put_object_create_new(key, data).await?;
            } else {
                self.put_object(key, data).await?;
            }
            return Ok(total);
        }
        if create_new && self.head_object(key).await?.is_some() {
            return Err(Error::already_exists(key));
        }
        self.multipart_upload_from_path(key, src, total).await?;
        Ok(total)
    }

    /// Run a multipart upload, aborting it on any failure so no parts are orphaned.
    async fn multipart_upload_from_path(&self, key: &str, src: &Path, total: u64) -> Result<()> {
        let scope = format!("bucket={} key={key}", self.bucket);
        let write_id = new_write_id();
        let mut request = self
            .client
            .create_multipart_upload()
            .bucket(&self.bucket)
            .key(key)
            .metadata(WRITE_ID_META, &write_id);
        if self.auto_detect_content_type {
            if let Some(content_type) = detect_content_type_for_key(key) {
                request = request.content_type(content_type);
            }
        }
        let created = {
            let _slot = self.acquire_slot().await?;
            request.send().await
        }
        .map_err(|e| format_sdk_s3_error("CreateMultipartUpload", &scope, &e))?;
        let upload_id = created
            .upload_id()
            .ok_or_else(|| {
                Error::internal(format!(
                    "CreateMultipartUpload returned no upload id: {scope}"
                ))
            })?
            .to_string();

        let result = self
            .upload_parts_and_complete(key, &upload_id, &write_id, src, total)
            .await;
        if result.is_err() {
            let aborted = match self.acquire_slot().await {
                Ok(_slot) => {
                    self.client
                        .abort_multipart_upload()
                        .bucket(&self.bucket)
                        .key(key)
                        .upload_id(&upload_id)
                        .send()
                        .await
                }
                Err(err) => {
                    tracing::warn!(
                        bucket = %self.bucket,
                        key = %key,
                        upload_id = %upload_id,
                        error = %err,
                        "skipped multipart abort; parts remain until a bucket lifecycle rule removes them"
                    );
                    return result;
                }
            };
            if let Err(abort_err) = aborted {
                tracing::warn!(
                    bucket = %self.bucket,
                    key = %key,
                    upload_id = %upload_id,
                    error = %format_sdk_s3_error("AbortMultipartUpload", &scope, &abort_err),
                    "failed to abort multipart upload; parts remain until a bucket lifecycle rule removes them"
                );
            }
        }
        result
    }

    /// Upload `src` part by part, reading one part into memory at a time.
    async fn upload_parts_and_complete(
        &self,
        key: &str,
        upload_id: &str,
        write_id: &str,
        src: &Path,
        total: u64,
    ) -> Result<()> {
        let _slot = self.acquire_slot().await?;
        let scope = format!("bucket={} key={key}", self.bucket);
        let part_size = effective_part_size(total, self.multipart.part_size_bytes);
        let mut file = tokio::fs::File::open(src).await?;
        let mut completed = Vec::new();

        for (index, (_offset, len)) in part_ranges(total, part_size).into_iter().enumerate() {
            let mut part = vec![0u8; len as usize];
            file.read_exact(&mut part).await?;
            let part_number = i32::try_from(index + 1)
                .map_err(|_| Error::internal(format!("too many multipart parts: {scope}")))?;
            let uploaded = self
                .client
                .upload_part()
                .bucket(&self.bucket)
                .key(key)
                .upload_id(upload_id)
                .part_number(part_number)
                .body(ByteStream::from(part))
                .send()
                .await
                .map_err(|e| format_sdk_s3_error("UploadPart", &scope, &e))?;
            completed.push(
                CompletedPart::builder()
                    .set_e_tag(uploaded.e_tag().map(str::to_string))
                    .part_number(part_number)
                    .build(),
            );
        }

        let completed = self
            .client
            .complete_multipart_upload()
            .bucket(&self.bucket)
            .key(key)
            .upload_id(upload_id)
            .multipart_upload(
                CompletedMultipartUpload::builder()
                    .set_parts(Some(completed))
                    .build(),
            )
            .send()
            .await;
        match completed {
            Ok(_) => Ok(()),
            // The SDK retried a completion whose first attempt was applied but
            // timed out: the upload is gone because our object now exists. The
            // write id (set at CreateMultipartUpload) proves it is ours.
            Err(e)
                if e.as_service_error().and_then(|err| err.code()) == Some("NoSuchUpload")
                    && self.has_write_id(key, write_id).await? =>
            {
                Ok(())
            }
            Err(e) => Err(format_sdk_s3_error("CompleteMultipartUpload", &scope, &e)),
        }
    }

    /// Stream an object into a local file, creating or truncating `dst`.
    pub async fn get_object_to_path(&self, key: &str, dst: &Path) -> Result<u64> {
        let _slot = self.acquire_slot().await?;
        let resp = match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(resp) => resp,
            Err(sdk_err) => {
                if sdk_err
                    .as_service_error()
                    .is_some_and(|e| e.is_no_such_key() || is_s3_compatible_not_found_code(e))
                {
                    return Err(Error::NotFound(key.to_string()));
                }
                return Err(format_sdk_s3_error(
                    "GetObject",
                    &format!("bucket={} key={}", self.bucket, key),
                    &sdk_err,
                ));
            }
        };

        let mut body = resp.body;
        let mut file = tokio::fs::File::create(dst).await?;
        let mut total = 0u64;
        while let Some(chunk) = body.next().await {
            let chunk = chunk.map_err(|e| format_read_body_error(&self.bucket, key, e))?;
            file.write_all(&chunk).await?;
            total += chunk.len() as u64;
        }
        file.flush().await?;
        Ok(total)
    }

    /// Delete a single object
    pub async fn delete_object(&self, key: &str) -> Result<()> {
        let _slot = self.acquire_slot().await?;
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .customize()
            .config_override(self.resilience.metadata_override())
            .send()
            .await
            .map_err(|e| {
                format_sdk_s3_error(
                    "DeleteObject",
                    &format!("bucket={} key={key}", self.bucket),
                    &e,
                )
            })?;

        Ok(())
    }

    /// Delete a single object only when its ETag still matches `etag`.
    ///
    /// Returns `Ok(false)` when the object changed since `etag` was read.
    pub async fn delete_object_if_match(&self, key: &str, etag: &str) -> Result<bool> {
        let scope = format!("bucket={} key={key}", self.bucket);
        self.run_conditional(
            || async {
                self.client
                    .delete_object()
                    .bucket(&self.bucket)
                    .key(key)
                    .if_match(etag)
                    .customize()
                    .config_override(single_attempt(self.resilience.metadata_override()))
                    .send()
                    .await
                    .map(|_| ())
                    .map_err(|e| {
                        // A retried delete finds the object already gone. Match the
                        // object codes only: NoSuchBucket is also a 404 but a real error.
                        if matches!(
                            e.as_service_error().and_then(|err| err.code()),
                            Some("NoSuchKey" | "NotFound")
                        ) {
                            ConditionalFailure::Precondition
                        } else {
                            conditional_failure("DeleteObjectIfMatch", &scope, &e)
                        }
                    })
            },
            // Gone is the goal state; it cannot distinguish our delete from a
            // concurrent one, which leaves the same result.
            || async { Ok(self.object_write_id(key).await?.is_none()) },
        )
        .await
    }

    /// Batch delete objects (up to 1000 per call)
    /// If disable_batch_delete is true, use sequential single-object deletes
    /// for S3-compatible services (e.g., Alibaba Cloud OSS) that require
    /// Content-MD5 for DeleteObjects but AWS SDK v2 does not send it by default.
    pub async fn delete_objects(&self, keys: &[String]) -> Result<()> {
        let _slot = self.acquire_slot().await?;
        if keys.is_empty() {
            return Ok(());
        }

        if self.disable_batch_delete {
            // Sequential single-object delete
            for key in keys {
                self.client
                    .delete_object()
                    .bucket(&self.bucket)
                    .key(key.as_str())
                    .customize()
                    .config_override(self.resilience.metadata_override())
                    .send()
                    .await
                    .map_err(|e| {
                        format_sdk_s3_error(
                            "DeleteObject",
                            &format!("bucket={} key={}", self.bucket, key),
                            &e,
                        )
                    })?;
            }
        } else {
            // S3 batch delete limit is 1000
            for chunk in keys.chunks(1000) {
                let objects: Vec<_> = chunk
                    .iter()
                    .map(|k| {
                        aws_sdk_s3::types::ObjectIdentifier::builder()
                            .key(k.as_str())
                            .build()
                            .unwrap()
                    })
                    .collect();

                let delete = aws_sdk_s3::types::Delete::builder()
                    .set_objects(Some(objects))
                    .build()
                    .map_err(|e| format_bucket_s3_error("BuildDelete", &self.bucket, e))?;

                let response = self
                    .client
                    .delete_objects()
                    .bucket(&self.bucket)
                    .delete(delete)
                    .customize()
                    .config_override(self.resilience.metadata_override())
                    .send()
                    .await
                    .map_err(|e| {
                        format_sdk_s3_error("DeleteObjects", &format!("bucket={}", self.bucket), &e)
                    })?;
                if let Some(error) = partial_delete_error(&self.bucket, response.errors()) {
                    return Err(error);
                }
            }
        }

        Ok(())
    }

    /// Get object metadata (HeadObject)
    pub async fn head_object(&self, key: &str) -> Result<Option<ObjectMeta>> {
        let _slot = self.acquire_slot().await?;
        match self
            .client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .customize()
            .config_override(self.resilience.metadata_override())
            .send()
            .await
        {
            Ok(resp) => {
                let size = resp.content_length.unwrap_or(0);
                let last_modified = resp
                    .last_modified()
                    .map(aws_datetime_to_systemtime)
                    .unwrap_or(UNIX_EPOCH);

                let is_dir_marker = key.ends_with('/');

                Ok(Some(ObjectMeta {
                    key: key.to_string(),
                    size,
                    last_modified,
                    is_dir_marker,
                }))
            }
            Err(sdk_err) => {
                // Check if it's a 404
                if sdk_err
                    .as_service_error()
                    .map(|err| err.is_not_found() || is_s3_compatible_not_found_code(err))
                    .unwrap_or(false)
                {
                    Ok(None)
                } else {
                    Err(format_sdk_s3_error(
                        "HeadObject",
                        &format!("bucket={} key={}", self.bucket, key),
                        &sdk_err,
                    ))
                }
            }
        }
    }

    /// List objects with prefix and delimiter
    pub async fn list_objects(&self, prefix: &str, delimiter: Option<&str>) -> Result<ListResult> {
        let _slot = self.acquire_slot().await?;
        let mut files = Vec::new();
        let mut directories = Vec::new();
        let mut continuation_token: Option<String> = None;

        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(prefix);

            if let Some(d) = delimiter {
                req = req.delimiter(d);
            }

            if let Some(token) = &continuation_token {
                req = req.continuation_token(token);
            }

            let resp = req
                .customize()
                .config_override(self.resilience.metadata_override())
                .send()
                .await
                .map_err(|e| {
                    format_sdk_s3_error(
                        "ListObjectsV2",
                        &format!("bucket={} prefix={prefix}", self.bucket),
                        &e,
                    )
                })?;

            // Process files (contents)
            for obj in resp.contents() {
                let key = obj.key().unwrap_or("");

                // Skip the prefix itself and directory markers
                if key == prefix || key.ends_with('/') {
                    continue;
                }

                let size = obj.size.unwrap_or(0);
                let last_modified = obj
                    .last_modified()
                    .map(aws_datetime_to_systemtime)
                    .unwrap_or(UNIX_EPOCH);

                files.push(ObjectMeta {
                    key: key.to_string(),
                    size,
                    last_modified,
                    is_dir_marker: false,
                });
            }

            // Process directory prefixes (common prefixes)
            for cp in resp.common_prefixes() {
                if let Some(p) = cp.prefix() {
                    // Remove trailing slash for consistency
                    let dir = p.trim_end_matches('/').to_string();
                    if !dir.is_empty() {
                        directories.push(dir);
                    }
                }
            }

            // Check if there are more results
            if resp.is_truncated() == Some(true) {
                continuation_token = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }

        Ok(ListResult { files, directories })
    }

    /// List all objects under a prefix (flat listing, no delimiter).
    /// Preserves directory marker objects (keys ending with '/').
    /// Used by tree_directory for efficient flat traversal.
    pub async fn list_tree_objects(&self, prefix: &str) -> Result<Vec<ObjectMeta>> {
        let _slot = self.acquire_slot().await?;
        let mut objects = Vec::new();
        let mut continuation_token: Option<String> = None;

        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(prefix);

            if let Some(token) = &continuation_token {
                req = req.continuation_token(token);
            }

            let resp = req
                .customize()
                .config_override(self.resilience.metadata_override())
                .send()
                .await
                .map_err(|e| {
                    format_sdk_s3_error(
                        "ListObjectsV2",
                        &format!("bucket={} prefix={prefix}", self.bucket),
                        &e,
                    )
                })?;

            for obj in resp.contents() {
                let key = obj.key().unwrap_or("");
                if key == prefix {
                    continue;
                }

                let size = obj.size.unwrap_or(0);
                let last_modified = obj
                    .last_modified()
                    .map(aws_datetime_to_systemtime)
                    .unwrap_or(UNIX_EPOCH);

                let is_dir_marker = key.ends_with('/');

                objects.push(ObjectMeta {
                    key: key.to_string(),
                    size,
                    last_modified,
                    is_dir_marker,
                });
            }

            if resp.is_truncated() == Some(true) {
                continuation_token = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }

        Ok(objects)
    }

    /// List one flat object page under a prefix (no delimiter).
    pub async fn list_tree_objects_page(
        &self,
        prefix: &str,
        continuation_token: Option<&str>,
        max_keys: usize,
    ) -> Result<ListTreePage> {
        let _slot = self.acquire_slot().await?;
        let mut req = self
            .client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(prefix)
            .max_keys(max_keys.min(1000) as i32);

        if let Some(token) = continuation_token {
            req = req.continuation_token(token);
        }

        let resp = req
            .customize()
            .config_override(self.resilience.metadata_override())
            .send()
            .await
            .map_err(|e| {
                format_sdk_s3_error(
                    "ListObjectsV2",
                    &format!("bucket={} prefix={prefix}", self.bucket),
                    &e,
                )
            })?;

        let mut objects = Vec::new();
        for obj in resp.contents() {
            let key = obj.key().unwrap_or("");
            if key == prefix {
                continue;
            }

            let size = obj.size.unwrap_or(0);
            let last_modified = obj
                .last_modified()
                .map(aws_datetime_to_systemtime)
                .unwrap_or(UNIX_EPOCH);

            objects.push(ObjectMeta {
                key: key.to_string(),
                size,
                last_modified,
                is_dir_marker: key.ends_with('/'),
            });
        }

        Ok(ListTreePage {
            objects,
            next_continuation_token: resp.next_continuation_token().map(|s| s.to_string()),
        })
    }

    /// Copy an object
    pub async fn copy_object(&self, src_key: &str, dst_key: &str) -> Result<()> {
        let _slot = self.acquire_slot().await?;
        let copy_source = format!("{}/{}", self.bucket, src_key);

        self.client
            .copy_object()
            .bucket(&self.bucket)
            .copy_source(&copy_source)
            .key(dst_key)
            .send()
            .await
            .map_err(|e| {
                format_sdk_s3_error(
                    "CopyObject",
                    &format!(
                        "bucket={} src_key={} dst_key={}",
                        self.bucket, src_key, dst_key
                    ),
                    &e,
                )
            })?;

        Ok(())
    }

    /// Check if a directory exists (either marker or any children)
    pub async fn directory_exists(&self, path: &str) -> Result<bool> {
        let dir_key = self.build_key(path);
        let dir_key_slash = if dir_key.ends_with('/') {
            dir_key.clone()
        } else {
            format!("{}/", dir_key)
        };

        // Check if directory marker exists
        if self.head_object(&dir_key_slash).await?.is_some() {
            return Ok(true);
        }

        // Check if any objects exist with this prefix
        let _slot = self.acquire_slot().await?;
        let resp = self
            .client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(&dir_key_slash)
            .max_keys(1)
            .customize()
            .config_override(self.resilience.metadata_override())
            .send()
            .await
            .map_err(|e| {
                format_sdk_s3_error(
                    "ListObjectsV2",
                    &format!("bucket={} prefix={dir_key_slash}", self.bucket),
                    &e,
                )
            })?;

        let has_contents = !resp.contents().is_empty();
        let has_prefixes = !resp.common_prefixes().is_empty();

        Ok(has_contents || has_prefixes)
    }

    /// Delete a directory and all its contents
    pub async fn delete_directory(&self, path: &str) -> Result<()> {
        let dir_key = self.build_key(path);
        let prefix = if dir_key.ends_with('/') {
            dir_key
        } else {
            format!("{}/", dir_key)
        };

        // List and delete all objects under prefix
        loop {
            // Scoped so the slot is released before delete_objects takes its own.
            let listed = {
                let _slot = self.acquire_slot().await?;
                self.client
                    .list_objects_v2()
                    .bucket(&self.bucket)
                    .prefix(&prefix)
                    .max_keys(1000)
                    .customize()
                    .config_override(self.resilience.metadata_override())
                    .send()
                    .await
            };
            let resp = listed.map_err(|e| {
                format_sdk_s3_error(
                    "ListObjectsV2",
                    &format!("bucket={} prefix={prefix}", self.bucket),
                    &e,
                )
            })?;

            let contents = resp.contents();
            if contents.is_empty() {
                break;
            }

            let keys: Vec<String> = contents
                .iter()
                .filter_map(|obj: &aws_sdk_s3::types::Object| obj.key().map(|k| k.to_string()))
                .collect();

            self.delete_objects(&keys).await?;

            if contents.len() < 1000 {
                break;
            }
        }

        Ok(())
    }

    /// Create a directory marker object
    pub async fn create_directory_marker(&self, path: &str) -> Result<()> {
        if let Some(data) = self.marker_mode.marker_data() {
            let dir_key = self.build_key(path);
            let key = if dir_key.ends_with('/') {
                dir_key
            } else {
                format!("{}/", dir_key)
            };

            self.put_object(&key, data).await?;
        }
        Ok(())
    }

    /// Get the marker mode
    pub fn marker_mode(&self) -> &DirectoryMarkerMode {
        &self.marker_mode
    }

    /// Get the bucket name
    pub fn bucket(&self) -> &str {
        &self.bucket
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::Error;
    use aws_sdk_s3::error::{ConnectorError, ErrorMetadata, ProvideErrorMetadata};

    #[derive(Debug)]
    struct FakeServiceError {
        raw: &'static str,
        meta: ErrorMetadata,
    }

    impl std::fmt::Display for FakeServiceError {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            write!(f, "{}", self.raw)
        }
    }

    impl RequestId for FakeServiceError {
        fn request_id(&self) -> Option<&str> {
            self.meta.request_id()
        }
    }

    impl RequestIdExt for FakeServiceError {
        fn extended_request_id(&self) -> Option<&str> {
            self.meta.extended_request_id()
        }
    }

    impl ProvideErrorMetadata for FakeServiceError {
        fn meta(&self) -> &ErrorMetadata {
            &self.meta
        }
    }

    fn test_client(prefix: &str, normalize_encoding_chars: &str) -> S3Client {
        S3Client {
            client: Client::from_conf(
                aws_sdk_s3::Config::builder()
                    .behavior_version(BehaviorVersion::latest())
                    .region(Region::new("us-east-1"))
                    .build(),
            ),
            bucket: "test-bucket".to_string(),
            prefix: prefix.to_string(),
            normalize_encoding_chars: normalize_encoding_chars.to_string(),
            marker_mode: DirectoryMarkerMode::Empty,
            disable_batch_delete: false,
            auto_detect_content_type: false,
            multipart: MultipartSettings::default(),
            resilience: S3ResilienceSettings::default(),
            limiter: None,
        }
    }

    #[test]
    fn test_key_codec_keeps_safe_segments() {
        let path = "dir/ok-name_1.2!*'()";
        assert_eq!(encode_path(path, "?#%+@"), path);
        assert_eq!(decode_path(path, "?#%+@"), path);
    }

    #[test]
    fn test_key_codec_encodes_only_target_characters() {
        let encoded = encode_path("a b/c?d/#frag/%raw", "?#%+@");

        assert_eq!(encoded, "a!20b/c!3Fd/!23frag/!25raw");
        assert_eq!(decode_path(&encoded, "?#%+@"), "a b/c?d/#frag/%raw");
    }

    #[test]
    fn test_key_codec_encodes_segments_with_reserved_prefix() {
        let encoded = encode_path("!literal/normal", "?#%+@");

        assert_eq!(encoded, "!literal/normal");
        assert_eq!(decode_path(&encoded, "?#%+@"), "!literal/normal");
    }

    #[test]
    fn test_key_codec_disabled_is_passthrough() {
        let path = "a b/c?d";
        assert_eq!(encode_path(path, ""), path);
        assert_eq!(decode_path(path, ""), path);
    }

    #[test]
    fn test_key_codec_preserves_non_target_characters_including_unicode() {
        let path = "dir//safe-_.*/@scope+pkg/客戶看板 file/";
        let encoded = encode_path(path, "?#%+@");

        assert_eq!(encoded, "dir//safe-_.*/!40scope!2Bpkg/客戶看板!20file/");
        assert_eq!(decode_path(&encoded, "?#%+@"), path);
    }

    #[test]
    fn test_key_codec_leaves_other_characters_unchanged() {
        let path = "目錄/@scope&name=1";

        assert_eq!(encode_path(path, "?#%+@"), "目錄/!40scope&name=1");
        assert_eq!(decode_path("目錄/!40scope&name=1", "?#%+@"), path);
    }

    #[test]
    fn test_build_key_applies_normalized_encoding_per_segment() {
        let key = test_client("ns", "?#%+@").build_key("/dir/a b/c?d.txt");
        assert_eq!(key, "ns/dir/a!20b/c!3Fd.txt");
    }

    #[test]
    fn test_strip_prefix_decodes_normalized_segments() {
        let client = test_client("ns", "?#%+@");
        let key = client.build_key("/dir/a b/c?d.txt");
        assert_eq!(client.strip_prefix(&key), "dir/a b/c?d.txt".to_string());
    }

    #[test]
    fn test_build_key_preserves_segments_when_normalization_disabled() {
        assert_eq!(test_client("", "").build_key("/a b"), "a b");
    }

    #[test]
    fn test_partial_delete_error_reports_each_failed_key() {
        let errors = [aws_sdk_s3::types::Error::builder()
            .key("denied.txt")
            .code("AccessDenied")
            .message("denied")
            .build()];

        let error = partial_delete_error("bucket", &errors).unwrap();
        assert!(error.to_string().contains("key=denied.txt"));
        assert!(error.to_string().contains("code=AccessDenied"));
    }

    #[test]
    fn test_detect_content_type_for_key_uses_filename_extension() {
        assert_eq!(
            detect_content_type_for_key("tenant/docs/readme.md").as_deref(),
            Some("text/markdown")
        );
        assert_eq!(
            detect_content_type_for_key("tenant/docs/data.json").as_deref(),
            Some("application/json")
        );
        assert_eq!(
            detect_content_type_for_key("tenant/images/logo.png").as_deref(),
            Some("image/png")
        );
    }

    #[test]
    fn test_detect_content_type_for_key_handles_unknown_and_directory_marker() {
        assert_eq!(
            detect_content_type_for_key("tenant/blob/no-extension").as_deref(),
            Some("application/octet-stream")
        );
        assert_eq!(detect_content_type_for_key("tenant/dir/"), None);
    }

    #[test]
    fn test_format_read_body_error_is_network_with_bucket_key_and_raw_error() {
        let err = format_read_body_error("test-bucket", "tenant/a.txt", "stream stalled");

        match err {
            Error::Network(message) => {
                assert!(message.contains("S3 ReadBody error"));
                assert!(message.contains("bucket=test-bucket"));
                assert!(message.contains("key=tenant/a.txt"));
                assert!(message.contains("raw=stream stalled"));
            }
            other => panic!("expected network error, got {other:?}"),
        }
    }

    fn service_sdk_error(
        status: u16,
        code: &'static str,
    ) -> SdkError<FakeServiceError, HttpResponse> {
        let service_err = FakeServiceError {
            raw: "service error",
            meta: ErrorMetadata::builder()
                .code(code)
                .message("signature mismatch")
                .custom("aws_request_id", "req-123")
                .custom("s3_extended_request_id", "ext-456")
                .build(),
        };
        let raw = HttpResponse::new(
            status.try_into().unwrap(),
            aws_sdk_s3::primitives::SdkBody::empty(),
        );
        SdkError::service_error(service_err, raw)
    }

    #[test]
    fn test_format_sdk_s3_error_includes_metadata_fields() {
        let err = format_sdk_s3_error(
            "PutObject",
            "bucket=test-bucket key=tenant/a.txt",
            &service_sdk_error(403, "AccessDenied"),
        );

        match err {
            Error::Internal(message) => {
                assert!(message.contains("S3 PutObject error"));
                assert!(message.contains("bucket=test-bucket key=tenant/a.txt"));
                assert!(message.contains("code=AccessDenied"));
                assert!(message.contains("message=signature mismatch"));
                assert!(message.contains("request_id=req-123"));
                assert!(message.contains("extended_request_id=ext-456"));
                assert!(message.contains("raw=HTTP 403: service error"));
            }
            other => panic!("expected internal error, got {other:?}"),
        }
    }

    #[test]
    fn test_format_sdk_s3_error_maps_timeouts() {
        let attempt_timeout: SdkError<FakeServiceError, HttpResponse> =
            SdkError::timeout_error("operation attempt timed out");
        assert!(matches!(
            format_sdk_s3_error("GetObject", "bucket=b key=k", &attempt_timeout),
            Error::Timeout(_)
        ));

        let connect_timeout: SdkError<FakeServiceError, HttpResponse> =
            SdkError::dispatch_failure(ConnectorError::timeout("connect timed out".into()));
        assert!(matches!(
            format_sdk_s3_error("HeadObject", "bucket=b key=k", &connect_timeout),
            Error::Timeout(_)
        ));
    }

    #[test]
    fn test_format_sdk_s3_error_maps_transport_failures_to_network() {
        let io_failure: SdkError<FakeServiceError, HttpResponse> =
            SdkError::dispatch_failure(ConnectorError::io("connection reset".into()));
        assert!(matches!(
            format_sdk_s3_error("GetObject", "bucket=b key=k", &io_failure),
            Error::Network(_)
        ));

        let bad_response: SdkError<FakeServiceError, HttpResponse> = SdkError::response_error(
            "truncated response",
            HttpResponse::new(
                200.try_into().unwrap(),
                aws_sdk_s3::primitives::SdkBody::empty(),
            ),
        );
        assert!(matches!(
            format_sdk_s3_error("ListObjectsV2", "bucket=b", &bad_response),
            Error::Network(_)
        ));
    }

    #[test]
    fn test_format_sdk_s3_error_maps_throttling_and_5xx_to_network() {
        for (status, code) in [
            (503, "SlowDown"),
            (503, "ServiceUnavailable"),
            (500, "InternalError"),
            (502, "BadGateway"),
            (504, "GatewayTimeout"),
            (429, "TooManyRequests"),
            (400, "RequestTimeout"),
        ] {
            let err = format_sdk_s3_error(
                "PutObject",
                "bucket=b key=k",
                &service_sdk_error(status, code),
            );
            assert!(matches!(err, Error::Network(_)), "{status} {code}: {err:?}");
        }
    }

    #[test]
    fn test_format_sdk_s3_error_keeps_client_errors_internal() {
        for (status, code) in [
            (403, "AccessDenied"),
            (404, "NoSuchBucket"),
            (400, "InvalidArgument"),
        ] {
            let err = format_sdk_s3_error(
                "PutObject",
                "bucket=b key=k",
                &service_sdk_error(status, code),
            );
            assert!(
                matches!(err, Error::Internal(_)),
                "{status} {code}: {err:?}"
            );
        }
    }

    #[test]
    fn test_is_s3_compatible_not_found_code_accepts_tos_code() {
        let tos_not_found = FakeServiceError {
            raw: "service error",
            meta: ErrorMetadata::builder().code("NotFound").build(),
        };
        assert!(is_s3_compatible_not_found_code(&tos_not_found));

        let no_such_key = FakeServiceError {
            raw: "service error",
            meta: ErrorMetadata::builder().code("NoSuchKey").build(),
        };
        assert!(!is_s3_compatible_not_found_code(&no_such_key));

        let access_denied = FakeServiceError {
            raw: "service error",
            meta: ErrorMetadata::builder().code("AccessDenied").build(),
        };
        assert!(!is_s3_compatible_not_found_code(&access_denied));

        let no_code = FakeServiceError {
            raw: "service error",
            meta: ErrorMetadata::builder().build(),
        };
        assert!(!is_s3_compatible_not_found_code(&no_code));
    }
}
