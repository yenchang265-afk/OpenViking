package openviking

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// uploadEntry is one file of a chunked upload: its path inside the upload, size and
// location on disk.
type uploadEntry struct {
	Path  string
	Size  int64
	Local string
}

// sessionsUnavailable reports statuses meaning the server cannot take a chunked
// upload: no route, method not allowed, or sessions refused (shared upload mode).
func sessionsUnavailable(err error) bool {
	var apiErr *Error
	if !errors.As(err, &apiErr) {
		return false
	}
	switch apiErr.StatusCode {
	case http.StatusNotFound, http.StatusMethodNotAllowed, http.StatusConflict:
		return true
	}
	return false
}

// collectUploadEntries lists a file, or every regular file in a folder with the same
// rules as zipDirectory (symlinks and anything outside the folder are skipped).
func collectUploadEntries(path string, info os.FileInfo) ([]uploadEntry, error) {
	if info.Mode().IsRegular() {
		return []uploadEntry{{Path: filepath.Base(path), Size: info.Size(), Local: path}}, nil
	}
	root, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	var entries []uploadEntry
	err = filepath.WalkDir(root, func(p string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if p == root {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		rel, err := filepath.Rel(root, p)
		if err != nil || strings.HasPrefix(rel, "..") {
			return nil
		}
		fi, err := entry.Info()
		if err != nil {
			return err
		}
		entries = append(entries, uploadEntry{Path: filepath.ToSlash(rel), Size: fi.Size(), Local: p})
		return nil
	})
	return entries, err
}

// uploadViaSession uploads a file or folder through /api/v1/uploads, streaming each
// part from disk. It reports used=false when the client is in shared upload mode, the
// folder is empty, or the server has no chunked uploads, so the caller can fall back.
// A failure after the session is created aborts the session.
func (c *Client) uploadViaSession(ctx context.Context, path string, info os.FileInfo) (tempID string, used bool, err error) {
	if c.uploadMode == "shared" {
		return "", false, nil
	}
	entries, err := collectUploadEntries(path, info)
	if err != nil || len(entries) == 0 {
		return "", false, err
	}
	kind := "directory"
	if info.Mode().IsRegular() {
		kind = "file"
	}
	files := make([]map[string]any, len(entries))
	for i, e := range entries {
		files[i] = map[string]any{"path": e.Path, "size": e.Size}
	}
	var created struct {
		UploadID string `json:"upload_id"`
		PartSize int64  `json:"part_size_bytes"`
	}
	payload := map[string]any{"kind": kind, "name": filepath.Base(path), "files": files}
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/uploads", nil, payload, &created); err != nil {
		if sessionsUnavailable(err) {
			return "", false, nil
		}
		return "", false, err
	}
	if created.UploadID == "" || created.PartSize <= 0 {
		return "", false, fmt.Errorf("invalid upload session response: %+v", created)
	}

	tempID, err = c.sendSessionParts(ctx, created.UploadID, created.PartSize, entries)
	if err != nil {
		_ = c.doJSON(context.WithoutCancel(ctx), http.MethodDelete, "/api/v1/uploads/"+created.UploadID, nil, nil, nil)
		return "", false, err
	}
	return tempID, true, nil
}

func (c *Client) sendSessionParts(ctx context.Context, uploadID string, partSize int64, entries []uploadEntry) (string, error) {
	for index, entry := range entries {
		if err := c.sendFileParts(ctx, uploadID, index, entry, partSize); err != nil {
			return "", fmt.Errorf("upload %s: %w", entry.Path, err)
		}
	}
	var done struct {
		TempFileID string `json:"temp_file_id"`
	}
	if err := c.doJSON(ctx, http.MethodPost, "/api/v1/uploads/"+uploadID+"/complete", nil, nil, &done); err != nil {
		return "", err
	}
	return done.TempFileID, nil
}

// partRetries is how many extra attempts a part gets after a transient failure;
// partRetryBaseDelay is the first backoff, doubled per attempt.
const partRetries = 3

var partRetryBaseDelay = 500 * time.Millisecond

// changedWhileUploading reports a file that no longer has the size the session was
// created with: written, truncated or removed while the upload ran.
func changedWhileUploading(entry uploadEntry) error {
	return &Error{
		Code: "FAILED_PRECONDITION",
		Message: fmt.Sprintf("'%s' changed while uploading (it was %d bytes when the upload started). "+
			"Retry, or leave out files that are being written, such as .git or logs.", entry.Path, entry.Size),
		Details: map[string]any{"path": entry.Path, "size": entry.Size},
	}
}

// isTransientPartError reports failures worth re-sending a part for: network errors
// and 5xx, 408 and 429 responses. Cancellation and other API errors are final.
func isTransientPartError(err error) bool {
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return false
	}
	var apiErr *Error
	if !errors.As(err, &apiErr) {
		return true
	}
	status := apiErr.StatusCode
	return status >= 500 || status == http.StatusRequestTimeout || status == http.StatusTooManyRequests
}

func (c *Client) putPart(ctx context.Context, path string, data []byte) error {
	for attempt := 0; ; attempt++ {
		req, err := c.newRequest(ctx, http.MethodPut, path, nil, bytes.NewReader(data))
		if err != nil {
			return err
		}
		req.ContentLength = int64(len(data))
		req.Header.Set("Content-Type", "application/octet-stream")
		_, err = c.doRequest(req, nil)
		if err == nil || attempt >= partRetries || !isTransientPartError(err) {
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(partRetryBaseDelay << attempt):
		}
	}
}

// sendFileParts sends exactly the entry.Size bytes the session declared, as parts.
func (c *Client) sendFileParts(ctx context.Context, uploadID string, index int, entry uploadEntry, partSize int64) error {
	file, err := os.Open(entry.Local)
	if errors.Is(err, os.ErrNotExist) {
		return changedWhileUploading(entry)
	}
	if err != nil {
		return err
	}
	defer file.Close()
	for number, offset := 1, int64(0); offset < entry.Size; number, offset = number+1, offset+partSize {
		data := make([]byte, min(partSize, entry.Size-offset))
		if _, err := file.ReadAt(data, offset); errors.Is(err, io.EOF) {
			return changedWhileUploading(entry)
		} else if err != nil {
			return err
		}
		path := fmt.Sprintf("/api/v1/uploads/%s/files/%d/parts/%d", uploadID, index, number)
		if err := c.putPart(ctx, path, data); err != nil {
			return err
		}
	}
	// A byte past the declared size: the file grew after the listing.
	if n, _ := file.ReadAt(make([]byte, 1), entry.Size); n > 0 {
		return changedWhileUploading(entry)
	}
	return nil
}
