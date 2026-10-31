//! Chunked upload sessions: send a local file or folder in parts without zipping it.
//!
//! Uses the server's `/api/v1/uploads` API with one part in memory at a time. Returns
//! `Ok(None)` when the server does not offer sessions (older server, or sessions refused
//! because it runs in shared upload mode) so callers fall back to the single-request
//! `/api/v1/resources/temp_upload`.

use std::path::{Path, PathBuf};

use indicatif::{ProgressBar, ProgressStyle};
use reqwest::StatusCode;
use serde_json::{Value, json};
use tokio::io::AsyncReadExt;

use crate::base_client::{BaseClient, ignore_dirs_filter, parse_ignore_dirs, zip_entry_name};
use crate::error::{Error, Result};

/// Statuses meaning "this server cannot take a chunked upload": no route, method not
/// allowed, or sessions refused (shared upload mode).
const SESSIONS_UNAVAILABLE: [StatusCode; 3] = [
    StatusCode::NOT_FOUND,
    StatusCode::METHOD_NOT_ALLOWED,
    StatusCode::CONFLICT,
];

/// One file of an upload: its path inside the upload, size, and local location.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct UploadEntry {
    pub path: String,
    pub size: u64,
    pub local: PathBuf,
}

/// List a file, or every regular file in a folder (same ignore rules as the zip upload).
///
/// Folder entries use forward-slash paths relative to the folder; symlinks are skipped.
pub(crate) fn collect_entries(path: &Path, ignore_dirs: Option<&str>) -> Result<Vec<UploadEntry>> {
    if path.is_file() {
        let name = path
            .file_name()
            .map(|n| zip_entry_name(Path::new(n)))
            .transpose()?
            .ok_or_else(|| Error::InvalidPath(format!("No file name: {}", path.display())))?;
        return Ok(vec![UploadEntry {
            path: name,
            size: std::fs::metadata(path)?.len(),
            local: path.to_path_buf(),
        }]);
    }
    let ignore_list = parse_ignore_dirs(ignore_dirs);
    let mut entries = Vec::new();
    for entry in walkdir::WalkDir::new(path)
        .into_iter()
        .filter_entry(ignore_dirs_filter(path, &ignore_list))
        .filter_map(|e| e.ok())
    {
        if !entry.file_type().is_file() {
            continue;
        }
        let relative = entry.path().strip_prefix(path).unwrap_or(entry.path());
        entries.push(UploadEntry {
            path: zip_entry_name(relative)?,
            size: entry.metadata().map_err(|e| Error::Io(e.into()))?.len(),
            local: entry.path().to_path_buf(),
        });
    }
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(entries)
}

/// A finished chunked upload: its `temp_file_id` and total bytes sent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SessionUpload {
    pub temp_file_id: String,
    pub total_bytes: u64,
}

/// Upload `path` through a chunked session.
///
/// Returns `Ok(None)` when sessions are unavailable, the client uses the shared upload
/// mode, or the folder is empty. On a failure after the session is created, the session
/// is aborted best-effort and the error returned.
pub(crate) async fn upload_via_session(
    client: &BaseClient,
    path: &Path,
    ignore_dirs: Option<&str>,
    upload_mode: Option<&str>,
    show_progress: bool,
) -> Result<Option<SessionUpload>> {
    if upload_mode == Some("shared") {
        return Ok(None);
    }
    let entries = collect_entries(path, ignore_dirs)?;
    if entries.is_empty() {
        return Ok(None);
    }
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| Error::InvalidPath(format!("No UTF-8 name: {}", path.display())))?;
    let kind = if path.is_file() { "file" } else { "directory" };
    let files: Vec<Value> = entries
        .iter()
        .map(|e| json!({"path": e.path, "size": e.size}))
        .collect();

    let request = client
        .http
        .post(format!("{}/api/v1/uploads", client.base_url))
        .headers(client.build_headers())
        .json(&json!({"kind": kind, "name": name, "files": files}));
    let response = client
        .send_request(request, "Upload session request failed")
        .await?;
    if SESSIONS_UNAVAILABLE.contains(&response.status()) {
        return Ok(None);
    }
    let created: Value = client.handle_response(response).await?;
    let upload_id = created["upload_id"]
        .as_str()
        .ok_or_else(|| Error::Parse("Missing upload_id in response".to_string()))?
        .to_string();
    let part_size = created["part_size_bytes"]
        .as_u64()
        .filter(|size| *size > 0)
        .ok_or_else(|| Error::Parse("Missing part_size_bytes in response".to_string()))?;

    let total_bytes: u64 = entries.iter().map(|e| e.size).sum();
    let progress = show_progress.then(|| {
        let pb = ProgressBar::new(total_bytes);
        if let Ok(style) =
            ProgressStyle::with_template("{bar:30} {bytes}/{total_bytes} ({bytes_per_sec}) {msg}")
        {
            pb.set_style(style);
        }
        pb
    });

    let result =
        send_all_and_complete(client, &upload_id, &entries, part_size, progress.as_ref()).await;
    if result.is_err() {
        let abort = client
            .http
            .delete(format!("{}/api/v1/uploads/{}", client.base_url, upload_id))
            .headers(client.build_headers());
        let _ = client.send_request(abort, "Abort upload failed").await;
    }
    if let Some(pb) = &progress {
        pb.finish_and_clear();
    }
    result.map(|temp_file_id| {
        Some(SessionUpload {
            temp_file_id,
            total_bytes,
        })
    })
}

/// Extra attempts for a part after a transient failure (network, timeout, 5xx, 408, 429).
const PART_RETRIES: u32 = 3;
/// First backoff before re-sending a part; doubled per attempt.
const PART_RETRY_BASE_DELAY: std::time::Duration = if cfg!(test) {
    std::time::Duration::from_millis(1)
} else {
    std::time::Duration::from_millis(500)
};

/// The file is no longer the size the session was created with: written, truncated or
/// removed while the upload ran (often `.git/` or a log or database being written to).
fn changed_while_uploading(entry: &UploadEntry) -> Error {
    // FAILED_PRECONDITION, like the SDKs; no HTTP status, so it is never retried.
    Error::Api {
        code: Some("FAILED_PRECONDITION".into()),
        message: format!(
            "'{}' changed while uploading (it was {} bytes when the upload started). \
             Retry, or leave out files that are being written, e.g. --ignore-dirs .git",
            entry.path, entry.size
        ),
        details: Some(json!({"path": entry.path, "size": entry.size})),
        status: None,
    }
}

fn is_transient(error: &Error) -> bool {
    match error {
        Error::Network(_) | Error::Timeout(_) => true,
        Error::Api {
            status: Some(status),
            ..
        } => *status >= 500 || *status == 408 || *status == 429,
        _ => false,
    }
}

async fn put_part(client: &BaseClient, url: &str, part: bytes::Bytes) -> Result<()> {
    let mut attempt = 0;
    loop {
        let request = client
            .http
            .put(url)
            .headers(client.build_headers())
            .header(reqwest::header::CONTENT_TYPE, "application/octet-stream")
            .body(part.clone());
        let result = match client
            .send_request(request, "Upload part request failed")
            .await
        {
            Ok(response) => client.handle_response::<Value>(response).await.map(drop),
            Err(error) => Err(error),
        };
        match result {
            Err(error) if attempt < PART_RETRIES && is_transient(&error) => {
                tokio::time::sleep(PART_RETRY_BASE_DELAY * 2u32.pow(attempt)).await;
                attempt += 1;
            }
            other => return other,
        }
    }
}

/// Send exactly the `entry.size` bytes the session declared, as numbered parts.
async fn send_file_parts(
    client: &BaseClient,
    upload_id: &str,
    index: usize,
    entry: &UploadEntry,
    part_size: u64,
    progress: Option<&ProgressBar>,
) -> Result<()> {
    let mut file =
        tokio::fs::File::open(&entry.local)
            .await
            .map_err(|error| match error.kind() {
                std::io::ErrorKind::NotFound => changed_while_uploading(entry),
                _ => Error::Io(error),
            })?;
    let mut remaining = entry.size;
    let mut number = 1u64;
    while remaining > 0 {
        let want = remaining.min(part_size);
        let part = read_part(&mut file, want as usize).await?;
        if (part.len() as u64) < want {
            return Err(changed_while_uploading(entry));
        }
        let url = format!(
            "{}/api/v1/uploads/{}/files/{}/parts/{}",
            client.base_url, upload_id, index, number
        );
        put_part(client, &url, bytes::Bytes::from(part)).await?;
        if let Some(pb) = progress {
            pb.inc(want);
        }
        remaining -= want;
        number += 1;
    }
    // More bytes than declared: the file grew after the listing.
    if !read_part(&mut file, 1).await?.is_empty() {
        return Err(changed_while_uploading(entry));
    }
    Ok(())
}

async fn send_all_and_complete(
    client: &BaseClient,
    upload_id: &str,
    entries: &[UploadEntry],
    part_size: u64,
    progress: Option<&ProgressBar>,
) -> Result<String> {
    for (index, entry) in entries.iter().enumerate() {
        if let Some(pb) = progress {
            pb.set_message(entry.path.clone());
        }
        send_file_parts(client, upload_id, index, entry, part_size, progress).await?;
    }
    let request = client
        .http
        .post(format!(
            "{}/api/v1/uploads/{}/complete",
            client.base_url, upload_id
        ))
        .headers(client.build_headers());
    let response = client
        .send_request(request, "Complete upload request failed")
        .await?;
    let done: Value = client.handle_response(response).await?;
    done["temp_file_id"]
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| Error::Parse("Missing temp_file_id in response".to_string()))
}

/// Read up to `part_size` bytes (fewer only at end of file).
async fn read_part(file: &mut tokio::fs::File, part_size: usize) -> Result<Vec<u8>> {
    let mut buffer = vec![0u8; part_size];
    let mut filled = 0;
    while filled < part_size {
        let read = file.read(&mut buffer[filled..]).await?;
        if read == 0 {
            break;
        }
        filled += read;
    }
    buffer.truncate(filled);
    Ok(buffer)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
    use tokio::net::TcpListener;

    type Recorded = Arc<Mutex<Vec<(String, String, Vec<u8>)>>>;

    /// Minimal HTTP/1.1 responder: records each request and answers via `respond`.
    async fn serve(
        respond: impl Fn(&str, &str) -> (u16, String) + Send + Sync + 'static,
    ) -> (String, Recorded) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let recorded: Recorded = Arc::new(Mutex::new(Vec::new()));
        let log = recorded.clone();
        let respond = Arc::new(respond);
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                let log = log.clone();
                let respond = respond.clone();
                tokio::spawn(async move {
                    let mut reader = BufReader::new(stream);
                    let mut line = String::new();
                    reader.read_line(&mut line).await.unwrap();
                    let mut parts = line.split_whitespace();
                    let method = parts.next().unwrap_or_default().to_string();
                    let path = parts.next().unwrap_or_default().to_string();
                    let mut length = 0usize;
                    loop {
                        let mut header = String::new();
                        reader.read_line(&mut header).await.unwrap();
                        if header == "\r\n" || header.is_empty() {
                            break;
                        }
                        if let Some((key, value)) = header.split_once(':')
                            && key.eq_ignore_ascii_case("content-length")
                        {
                            length = value.trim().parse().unwrap();
                        }
                    }
                    let mut body = vec![0u8; length];
                    reader.read_exact(&mut body).await.unwrap();
                    let (status, payload) = respond(&method, &path);
                    log.lock().unwrap().push((method, path, body));
                    let reply = format!(
                        "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
                        payload.len()
                    );
                    reader
                        .into_inner()
                        .write_all(reply.as_bytes())
                        .await
                        .unwrap();
                });
            }
        });
        (format!("http://{address}"), recorded)
    }

    fn session_api(
        part_size: u64,
        create_status: u16,
        fail_put: Option<&'static str>,
    ) -> impl Fn(&str, &str) -> (u16, String) + Send + Sync + 'static {
        move |method, path| {
            let ok = |result: Value| (200, json!({"status": "ok", "result": result}).to_string());
            match (method, path) {
                ("POST", "/api/v1/uploads") if create_status != 200 => {
                    (create_status, json!({"status": "error"}).to_string())
                }
                ("POST", "/api/v1/uploads") => {
                    ok(json!({"upload_id": "u1", "part_size_bytes": part_size}))
                }
                ("PUT", p) if Some(p) == fail_put => (
                    500,
                    json!({"status": "error", "error": {"code": "INTERNAL", "message": "boom"}})
                        .to_string(),
                ),
                ("PUT", _) => ok(json!({})),
                ("POST", "/api/v1/uploads/u1/complete") => {
                    ok(json!({"temp_file_id": "session_u1"}))
                }
                ("DELETE", "/api/v1/uploads/u1") => ok(json!({})),
                _ => (404, json!({"status": "error"}).to_string()),
            }
        }
    }

    fn client(base_url: String) -> BaseClient {
        BaseClient::new(base_url, None, None, None, None, 5.0, false, None)
    }

    fn folder() -> tempfile::TempDir {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("docs");
        std::fs::create_dir_all(root.join("sub")).unwrap();
        std::fs::create_dir_all(root.join("node_modules")).unwrap();
        std::fs::write(root.join("a.md"), b"0123456789").unwrap();
        std::fs::write(root.join("sub").join("b.txt"), b"xyz").unwrap();
        std::fs::write(root.join("node_modules").join("skip.js"), b"skip").unwrap();
        dir
    }

    fn parts_by_file(recorded: &Recorded) -> HashMap<String, Vec<u8>> {
        let mut parts: Vec<(String, Vec<u8>)> = recorded
            .lock()
            .unwrap()
            .iter()
            .filter(|(method, _, _)| method == "PUT")
            .map(|(_, path, body)| (path.clone(), body.clone()))
            .collect();
        parts.sort();
        let mut files: HashMap<String, Vec<u8>> = HashMap::new();
        for (path, body) in parts {
            let index = path.split('/').nth(6).unwrap().to_string();
            files.entry(index).or_default().extend(body);
        }
        files
    }

    #[tokio::test]
    async fn folder_upload_sends_parts_per_file_and_honours_ignore_dirs() {
        let dir = folder();
        let (url, recorded) = serve(session_api(4, 200, None)).await;

        let id = upload_via_session(
            &client(url),
            &dir.path().join("docs"),
            Some("node_modules"),
            None,
            false,
        )
        .await
        .unwrap();

        assert_eq!(
            id,
            Some(SessionUpload {
                temp_file_id: "session_u1".into(),
                total_bytes: 13
            })
        );
        let log = recorded.lock().unwrap().clone();
        let create: Value = serde_json::from_slice(&log[0].2).unwrap();
        assert_eq!(create["kind"], "directory");
        assert_eq!(create["name"], "docs");
        assert_eq!(
            create["files"],
            json!([{"path": "a.md", "size": 10}, {"path": "sub/b.txt", "size": 3}])
        );
        let files = parts_by_file(&recorded);
        assert_eq!(files["0"], b"0123456789");
        assert_eq!(files["1"], b"xyz");
        assert_eq!(log.iter().filter(|(m, _, _)| m == "PUT").count(), 4);
        assert_eq!(log.last().unwrap().1, "/api/v1/uploads/u1/complete");
    }

    #[tokio::test]
    async fn unavailable_sessions_and_shared_mode_return_none() {
        let dir = folder();
        for status in [404, 405, 409] {
            let (url, _) = serve(session_api(4, status, None)).await;
            let id = upload_via_session(&client(url), &dir.path().join("docs"), None, None, false)
                .await
                .unwrap();
            assert_eq!(id, None, "status {status}");
        }

        let (url, recorded) = serve(session_api(4, 200, None)).await;
        let id = upload_via_session(
            &client(url),
            &dir.path().join("docs"),
            None,
            Some("shared"),
            false,
        )
        .await
        .unwrap();
        assert_eq!(id, None);
        assert!(recorded.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn failed_part_aborts_session() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("f.bin");
        std::fs::write(&file, b"0123456789").unwrap();
        let (url, recorded) = serve(session_api(
            4,
            200,
            Some("/api/v1/uploads/u1/files/0/parts/2"),
        ))
        .await;

        let result = upload_via_session(&client(url), &file, None, None, false).await;

        assert!(result.is_err());
        let log = recorded.lock().unwrap().clone();
        assert_eq!(log.last().unwrap().0, "DELETE");
        assert!(!log.iter().any(|(_, p, _)| p.ends_with("/complete")));
    }

    /// Session API whose part `fail_path` answers `status` for its first `failures` attempts.
    fn flaky_part_api(
        fail_path: &'static str,
        status: u16,
        failures: usize,
    ) -> impl Fn(&str, &str) -> (u16, String) + Send + Sync + 'static {
        let attempts = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let api = session_api(4, 200, None);
        move |method, path| {
            if method == "PUT" && path == fail_path {
                let attempt = attempts.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                if attempt < failures {
                    let body = json!({"status": "error", "error": {"code": "X", "message": "x"}});
                    return (status, body.to_string());
                }
            }
            api(method, path)
        }
    }

    fn puts_to(recorded: &Recorded, path: &str) -> usize {
        recorded
            .lock()
            .unwrap()
            .iter()
            .filter(|(method, p, _)| method == "PUT" && p == path)
            .count()
    }

    /// List `docs`, let `change` touch it, then send the listing as a session.
    async fn send_after_change(change: impl FnOnce(&Path)) -> (Result<String>, Recorded) {
        let dir = folder();
        let root = dir.path().join("docs");
        let entries = collect_entries(&root, Some("node_modules")).unwrap();
        change(&root);
        let (url, recorded) = serve(session_api(4, 200, None)).await;
        let result = send_all_and_complete(&client(url), "u1", &entries, 4, None).await;
        (result, recorded)
    }

    fn assert_changed_error(result: Result<String>, path: &str) {
        let error = result.unwrap_err();
        assert_eq!(error.code(), "FAILED_PRECONDITION");
        let message = error.to_string();
        assert!(message.contains(path), "{message}");
        assert!(message.contains("changed while uploading"), "{message}");
    }

    #[tokio::test]
    async fn file_that_grows_after_listing_fails_naming_it() {
        let (result, recorded) = send_after_change(|root| {
            std::fs::write(root.join("a.md"), b"0123456789-and-more").unwrap();
        })
        .await;

        assert_changed_error(result, "a.md");
        // Only the declared 10 bytes were offered, never the appended ones.
        assert_eq!(parts_by_file(&recorded)["0"], b"0123456789");
        assert!(
            !recorded
                .lock()
                .unwrap()
                .iter()
                .any(|(_, p, _)| p.ends_with("/complete"))
        );
    }

    #[tokio::test]
    async fn file_that_shrinks_after_listing_fails_naming_it() {
        let (result, recorded) = send_after_change(|root| {
            std::fs::write(root.join("sub").join("b.txt"), b"x").unwrap();
        })
        .await;

        assert_changed_error(result, "sub/b.txt");
        assert_eq!(puts_to(&recorded, "/api/v1/uploads/u1/files/1/parts/1"), 0);
    }

    #[tokio::test]
    async fn file_removed_after_listing_fails_naming_it() {
        let (result, _) = send_after_change(|root| {
            std::fs::remove_file(root.join("sub").join("b.txt")).unwrap();
        })
        .await;

        assert_changed_error(result, "sub/b.txt");
    }

    #[tokio::test]
    async fn transient_part_failure_is_retried() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("f.bin");
        std::fs::write(&file, b"0123456789").unwrap();
        let part = "/api/v1/uploads/u1/files/0/parts/2";
        let (url, recorded) = serve(flaky_part_api(part, 503, 2)).await;

        let result = upload_via_session(&client(url), &file, None, None, false).await;

        assert_eq!(result.unwrap().unwrap().temp_file_id, "session_u1");
        assert_eq!(puts_to(&recorded, part), 3);
        assert_eq!(parts_by_file(&recorded)["0"].len(), 10 + 4 * 2);
    }

    #[tokio::test]
    async fn rejected_part_is_not_retried() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("f.bin");
        std::fs::write(&file, b"0123456789").unwrap();
        let part = "/api/v1/uploads/u1/files/0/parts/2";
        let (url, recorded) = serve(flaky_part_api(part, 400, usize::MAX)).await;

        let result = upload_via_session(&client(url), &file, None, None, false).await;

        assert!(result.is_err());
        assert_eq!(puts_to(&recorded, part), 1);
        assert_eq!(recorded.lock().unwrap().last().unwrap().0, "DELETE");
    }

    #[test]
    fn file_entry_uses_its_name() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("report.pdf");
        std::fs::write(&file, b"abc").unwrap();

        let entries = collect_entries(&file, None).unwrap();

        assert_eq!(
            entries,
            vec![UploadEntry {
                path: "report.pdf".into(),
                size: 3,
                local: file
            }]
        );
    }
}
