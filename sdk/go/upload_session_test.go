package openviking

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"testing"
)

// sessionServer is a fake /api/v1/uploads API that records parts per file.
type sessionServer struct {
	t            *testing.T
	partSize     int
	createStatus int
	failPart     string
	mu           sync.Mutex
	created      map[string]any
	parts        map[string][]byte
	calls        []string
	resourceBody map[string]any
}

func (s *sessionServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.calls = append(s.calls, r.Method+" "+r.URL.Path)
	switch {
	case r.Method == http.MethodPost && r.URL.Path == "/api/v1/uploads":
		if s.createStatus != 0 {
			w.WriteHeader(s.createStatus)
			_, _ = w.Write([]byte(`{"status":"error","error":{"code":"NOT_FOUND","message":"no"}}`))
			return
		}
		s.created = readJSONBody(s.t, r)
		writeOK(s.t, w, map[string]any{"upload_id": "u1", "part_size_bytes": s.partSize})
	case r.Method == http.MethodPut && strings.HasPrefix(r.URL.Path, "/api/v1/uploads/u1/files/"):
		if r.URL.Path == s.failPart {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte(`{"status":"error","error":{"code":"INTERNAL","message":"boom"}}`))
			return
		}
		if got := r.Header.Get("Content-Type"); got != "application/octet-stream" {
			s.t.Fatalf("content-type = %q", got)
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			s.t.Fatal(err)
		}
		s.parts[r.URL.Path] = body
		writeOK(s.t, w, map[string]any{})
	case r.Method == http.MethodPost && r.URL.Path == "/api/v1/uploads/u1/complete":
		writeOK(s.t, w, map[string]any{"temp_file_id": "session_u1"})
	case r.Method == http.MethodDelete && r.URL.Path == "/api/v1/uploads/u1":
		writeOK(s.t, w, map[string]any{})
	case r.URL.Path == "/api/v1/resources/temp_upload":
		writeOK(s.t, w, map[string]any{"temp_file_id": "legacy"})
	case r.URL.Path == "/api/v1/resources", r.URL.Path == "/api/v1/skills":
		s.resourceBody = readJSONBody(s.t, r)
		writeOK(s.t, w, map[string]any{"uri": "viking://resources/x"})
	default:
		s.t.Fatalf("unexpected %s %s", r.Method, r.URL.Path)
	}
}

// fileParts concatenates the parts received for file index i, in part order.
func (s *sessionServer) fileParts(i int) string {
	prefix := fmt.Sprintf("/api/v1/uploads/u1/files/%d/parts/", i)
	var keys []string
	for k := range s.parts {
		if strings.HasPrefix(k, prefix) {
			keys = append(keys, k)
		}
	}
	sort.Slice(keys, func(a, b int) bool {
		return len(keys[a]) < len(keys[b]) || (len(keys[a]) == len(keys[b]) && keys[a] < keys[b])
	})
	var out strings.Builder
	for _, k := range keys {
		out.Write(s.parts[k])
	}
	return out.String()
}

func sessionTestClient(t *testing.T, s *sessionServer, uploadMode string) (*Client, func()) {
	t.Helper()
	s.t = t
	s.parts = map[string][]byte{}
	server := httptest.NewServer(s)
	client, err := NewClient(Config{BaseURL: server.URL, APIKey: "key", UploadMode: uploadMode})
	if err != nil {
		t.Fatal(err)
	}
	return client, server.Close
}

func makeUploadFolder(t *testing.T) string {
	t.Helper()
	root := filepath.Join(t.TempDir(), "docs")
	for path, content := range map[string]string{"a.md": "0123456789", "sub/b.txt": "xyz", "empty.txt": ""} {
		full := filepath.Join(root, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func TestAddResourceUploadsFolderThroughSession(t *testing.T) {
	s := &sessionServer{partSize: 4}
	client, closeServer := sessionTestClient(t, s, "")
	defer closeServer()

	if _, err := client.AddResource(context.Background(), makeUploadFolder(t), nil); err != nil {
		t.Fatal(err)
	}

	if s.created["kind"] != "directory" || s.created["name"] != "docs" {
		t.Fatalf("created = %#v", s.created)
	}
	files, _ := json.Marshal(s.created["files"])
	want := `[{"path":"a.md","size":10},{"path":"empty.txt","size":0},{"path":"sub/b.txt","size":3}]`
	if string(files) != want {
		t.Fatalf("files = %s", files)
	}
	if got := s.fileParts(0); got != "0123456789" {
		t.Fatalf("a.md parts = %q", got)
	}
	if got := s.fileParts(2); got != "xyz" {
		t.Fatalf("b.txt parts = %q", got)
	}
	if len(s.parts) != 4 {
		t.Fatalf("parts = %d, want 4", len(s.parts))
	}
	if s.resourceBody["temp_file_id"] != "session_u1" || s.resourceBody["source_name"] != "docs" {
		t.Fatalf("resource body = %#v", s.resourceBody)
	}
}

func TestAddResourceFallsBackWhenSessionsUnavailable(t *testing.T) {
	for _, status := range []int{http.StatusNotFound, http.StatusMethodNotAllowed, http.StatusConflict} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			s := &sessionServer{partSize: 4, createStatus: status}
			client, closeServer := sessionTestClient(t, s, "")
			defer closeServer()

			if _, err := client.AddResource(context.Background(), makeUploadFolder(t), nil); err != nil {
				t.Fatal(err)
			}
			if s.resourceBody["temp_file_id"] != "legacy" {
				t.Fatalf("resource body = %#v", s.resourceBody)
			}
		})
	}
}

func TestAddResourceAbortsSessionWhenAPartFails(t *testing.T) {
	s := &sessionServer{partSize: 4, failPart: "/api/v1/uploads/u1/files/0/parts/2"}
	client, closeServer := sessionTestClient(t, s, "")
	defer closeServer()
	file := filepath.Join(t.TempDir(), "f.bin")
	if err := os.WriteFile(file, []byte("0123456789"), 0o644); err != nil {
		t.Fatal(err)
	}

	if _, err := client.AddResource(context.Background(), file, nil); err == nil {
		t.Fatal("expected error")
	}

	if last := s.calls[len(s.calls)-1]; last != "DELETE /api/v1/uploads/u1" {
		t.Fatalf("last call = %q", last)
	}
	for _, call := range s.calls {
		if strings.HasSuffix(call, "/complete") || strings.HasSuffix(call, "/api/v1/resources") {
			t.Fatalf("unexpected call after failure: %q", call)
		}
	}
}

func TestSkillUploadKeepsSingleRequestUpload(t *testing.T) {
	s := &sessionServer{partSize: 4}
	client, closeServer := sessionTestClient(t, s, "")
	defer closeServer()
	payload := map[string]any{}

	if err := client.addLocalUpload(context.Background(), payload, makeUploadFolder(t), false); err != nil {
		t.Fatal(err)
	}

	if payload["temp_file_id"] != "legacy" {
		t.Fatalf("payload = %#v", payload)
	}
	for _, call := range s.calls {
		if call == "POST /api/v1/uploads" {
			t.Fatal("skills must not use upload sessions")
		}
	}
}
