//! Stable values stored behind the provider contract.

use super::versions::VersionSnapshot;
use crate::cache_runtime::{CacheError, CacheResult};
use crate::core::FileInfo;
use bytes::Bytes;
use serde::{Deserialize, Serialize};

const CACHE_ENVELOPE_VERSION: u8 = 2;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) enum CacheObjectKind {
    File,
    Directory,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
enum CachePayload {
    File(Vec<u8>),
    Directory(Vec<FileInfo>),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct CacheEnvelope {
    version: u8,
    kind: CacheObjectKind,
    path: String,
    versions: Vec<VersionSnapshot>,
    payload: CachePayload,
}

impl CacheEnvelope {
    pub fn file(path: String, data: Vec<u8>, versions: Vec<VersionSnapshot>) -> Self {
        Self {
            version: CACHE_ENVELOPE_VERSION,
            kind: CacheObjectKind::File,
            path,
            versions,
            payload: CachePayload::File(data),
        }
    }

    pub fn directory(path: String, entries: Vec<FileInfo>, versions: Vec<VersionSnapshot>) -> Self {
        Self {
            version: CACHE_ENVELOPE_VERSION,
            kind: CacheObjectKind::Directory,
            path,
            versions,
            payload: CachePayload::Directory(entries),
        }
    }

    pub fn encode(&self) -> CacheResult<Bytes> {
        serde_json::to_vec(self)
            .map(Bytes::from)
            .map_err(|error| CacheError::InvalidData(error.to_string()))
    }

    pub fn decode(value: &[u8]) -> CacheResult<Self> {
        let envelope: Self = serde_json::from_slice(value)
            .map_err(|error| CacheError::InvalidData(error.to_string()))?;
        if envelope.version != CACHE_ENVELOPE_VERSION {
            return Err(CacheError::InvalidData(format!(
                "unsupported envelope version {}",
                envelope.version
            )));
        }
        Ok(envelope)
    }

    pub fn matches(&self, kind: CacheObjectKind, path: &str) -> bool {
        self.kind == kind && self.path == path
    }

    /// Counter values snapshotted before the backend read that produced this entry.
    pub fn versions(&self) -> &[VersionSnapshot] {
        &self.versions
    }

    pub fn into_file(self) -> CacheResult<Vec<u8>> {
        match self.payload {
            CachePayload::File(data) => Ok(data),
            CachePayload::Directory(_) => {
                Err(CacheError::InvalidData("expected file payload".to_string()))
            }
        }
    }

    pub fn into_directory(self) -> CacheResult<Vec<FileInfo>> {
        match self.payload {
            CachePayload::Directory(entries) => Ok(entries),
            CachePayload::File(_) => Err(CacheError::InvalidData(
                "expected directory payload".to_string(),
            )),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn file_envelope_round_trips_with_versions() {
        let versions = vec![VersionSnapshot {
            key: "k".to_string(),
            value: 7,
        }];
        let encoded = CacheEnvelope::file("/f".to_string(), b"x".to_vec(), versions.clone())
            .encode()
            .unwrap();
        let decoded = CacheEnvelope::decode(&encoded).unwrap();
        assert!(decoded.matches(CacheObjectKind::File, "/f"));
        assert_eq!(decoded.versions(), versions.as_slice());
        assert_eq!(decoded.into_file().unwrap(), b"x");
    }

    #[test]
    fn version_one_envelopes_are_rejected() {
        let legacy =
            br#"{"version":1,"kind":"File","path":"/f","generations":[],"payload":{"File":[120]}}"#;
        assert!(matches!(
            CacheEnvelope::decode(legacy),
            Err(CacheError::InvalidData(_))
        ));
    }
}
