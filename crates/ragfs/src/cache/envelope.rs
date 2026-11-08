//! Stable values stored behind the provider contract.

use crate::cache_runtime::{CacheError, CacheResult};
use bytes::Bytes;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct QueryCacheEnvelope<T> {
    request: Value,
    payload: T,
}

impl<T> QueryCacheEnvelope<T> {
    /// Build a query cache envelope for one canonical request and payload.
    pub fn new(request: Value, payload: T) -> Self {
        Self { request, payload }
    }

    /// Encode this envelope for provider storage.
    pub fn encode(&self) -> CacheResult<Bytes>
    where
        T: Serialize,
    {
        serde_json::to_vec(self)
            .map(Bytes::from)
            .map_err(|error| CacheError::InvalidData(error.to_string()))
    }

    /// Decode one query cache envelope from provider bytes.
    pub fn decode(value: &[u8]) -> CacheResult<Self>
    where
        T: DeserializeOwned,
    {
        serde_json::from_slice(value).map_err(|error| CacheError::InvalidData(error.to_string()))
    }

    /// Return true when the stored request matches the current request.
    pub fn request_matches(&self, request: &Value) -> bool {
        self.request == *request
    }

    /// Consume the envelope and return its cached payload.
    pub fn into_payload(self) -> T {
        self.payload
    }
}

const FILE_ENVELOPE_MAGIC: &[u8; 4] = b"OVF1";

/// Encode cached file contents as `OVF1 | u32 path length | path | bytes`.
///
/// File contents stay raw bytes instead of a JSON array, and the stored path
/// is checked on decode like the request of a query envelope.
pub(crate) fn encode_file_content(path: &str, data: &[u8]) -> CacheResult<Bytes> {
    let path_len = u32::try_from(path.len())
        .map_err(|_| CacheError::InvalidData("cached file path is too long".to_string()))?;
    let mut value = Vec::with_capacity(8 + path.len() + data.len());
    value.extend_from_slice(FILE_ENVELOPE_MAGIC);
    value.extend_from_slice(&path_len.to_be_bytes());
    value.extend_from_slice(path.as_bytes());
    value.extend_from_slice(data);
    Ok(Bytes::from(value))
}

/// Decode cached file contents, or `None` when the value names another path.
pub(crate) fn decode_file_content(value: &[u8], path: &str) -> CacheResult<Option<Vec<u8>>> {
    let invalid = || CacheError::InvalidData("invalid cached file envelope".to_string());
    let rest = value
        .strip_prefix(FILE_ENVELOPE_MAGIC)
        .ok_or_else(invalid)?;
    let (len, rest) = rest.split_first_chunk::<4>().ok_or_else(invalid)?;
    let len = u32::from_be_bytes(*len) as usize;
    if rest.len() < len {
        return Err(invalid());
    }
    let (stored_path, data) = rest.split_at(len);
    Ok((stored_path == path.as_bytes()).then(|| data.to_vec()))
}

#[cfg(test)]
mod file_content_tests {
    use super::*;

    #[test]
    fn file_content_round_trips_and_checks_its_path() {
        let value = encode_file_content("/a/b.bin", &[0, 159, 255, b'x']).unwrap();
        assert_eq!(
            decode_file_content(&value, "/a/b.bin").unwrap(),
            Some(vec![0, 159, 255, b'x'])
        );
        assert_eq!(decode_file_content(&value, "/a/c.bin").unwrap(), None);
        assert!(decode_file_content(b"OVF1\0\0\0\x09/a", "/a").is_err());
        assert!(decode_file_content(b"{\"request\":1}", "/a").is_err());
    }
}
