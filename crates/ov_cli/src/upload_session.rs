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
        let mut file = tokio::fs::File::open(&entry.local).await?;
        let mut number = 1u64;
        loop {
            let part = read_part(&mut file, part_size as usize).await?;
            if part.is_empty() {
                break;
            }
            let sent = part.len() as u64;
            let request = client
                .http
                .put(format!(
                    "{}/api/v1/uploads/{}/files/{}/parts/{}",
                    client.base_url, upload_id, index, number
                ))
                .headers(client.build_headers())
                .header(reqwest::header::CONTENT_TYPE, "application/octet-stream")
                .body(part);
            let response = client
                .send_request(request, "Upload part request failed")
                .await?;
            let _: Value = client.handle_response(response).await?;
            if let Some(pb) = progress {
                pb.inc(sent);
            }
            number += 1;
        }
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
