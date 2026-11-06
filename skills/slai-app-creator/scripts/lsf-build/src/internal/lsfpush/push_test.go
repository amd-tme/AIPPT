package lsfpush

import (
	"archive/tar"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"github.com/google/go-containerregistry/pkg/registry"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

const testImage = "harbor.example.test/project/app:slai-sc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1-1"
const testSecret = "synthetic-push-credential-canary"

func creds() Credentials {
	return Credentials{Location: "harbor.example.test/project", Username: "robot$test", Password: testSecret}
}
func fixture(t *testing.T) (string, string, []byte) {
	t.Helper()
	var b bytes.Buffer
	tw := tar.NewWriter(&b)
	data := []byte("root:*::\n")
	_ = tw.WriteHeader(&tar.Header{Name: "etc/gshadow", Uid: 0, Gid: 42, Mode: 0640, Size: int64(len(data))})
	_, _ = tw.Write(data)
	_ = tw.Close()
	layer := append([]byte(nil), b.Bytes()...)
	blob := func(data []byte) string { sum := sha256.Sum256(data); return "sha256:" + hex.EncodeToString(sum[:]) }
	ld := blob(layer)
	config, _ := json.Marshal(map[string]any{"architecture": "amd64", "os": "linux", "config": map[string]any{"User": "65534:65534"}, "rootfs": map[string]any{"type": "layers", "diff_ids": []string{ld}}})
	cd := blob(config)
	desc := func(d, m string, n int) map[string]any { return map[string]any{"digest": d, "mediaType": m, "size": n} }
	manifest, _ := json.Marshal(map[string]any{"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": desc(cd, "application/vnd.oci.image.config.v1+json", len(config)), "layers": []any{desc(ld, "application/vnd.oci.image.layer.v1.tar", len(layer))}})
	digest := blob(manifest)
	index, _ := json.Marshal(map[string]any{"schemaVersion": 2, "manifests": []any{desc(digest, "application/vnd.oci.image.manifest.v1+json", len(manifest))}})
	entries := map[string][]byte{"oci-layout": []byte(`{"imageLayoutVersion":"1.0.0"}`), "index.json": index, "blobs/sha256/" + strings.TrimPrefix(digest, "sha256:"): manifest, "blobs/sha256/" + strings.TrimPrefix(cd, "sha256:"): config, "blobs/sha256/" + strings.TrimPrefix(ld, "sha256:"): layer}
	a := filepath.Join(t.TempDir(), "image.oci.tar")
	f, err := os.OpenFile(a, os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	tw = tar.NewWriter(f)
	for n, d := range entries {
		_ = tw.WriteHeader(&tar.Header{Name: n, Mode: 0600, Size: int64(len(d))})
		_, _ = tw.Write(d)
	}
	_ = tw.Close()
	_ = f.Close()
	return a, digest, layer
}
func buildJob(t *testing.T) string {
	t.Helper()
	a, d, _ := fixture(t)
	job := t.TempDir()
	_ = os.Chmod(job, 0700)
	_ = os.Mkdir(filepath.Join(job, "output"), 0700)
	data, _ := os.ReadFile(a)
	_ = os.WriteFile(filepath.Join(job, "output", "result.oci.tar"), data, 0600)
	s := sha256.Sum256(data)
	e := map[string]any{"schema_version": 1, "lsf_job_id": "123", "profile": "slai-web-app-v1", "platform": "linux/amd64", "probe_status": 200, "artifact_digest": "sha256:" + hex.EncodeToString(s[:]), "manifest_digest": d, "artifact_bytes": len(data)}
	data, _ = json.Marshal(e)
	_ = os.WriteFile(filepath.Join(job, "output", "success.json"), data, 0600)
	return job
}

type mappingTransport struct {
	base     http.RoundTripper
	endpoint *url.URL
}

func (m mappingTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	original := *r.URL
	r = r.Clone(r.Context())
	u := *r.URL
	r.URL = &u
	r.URL.Scheme = m.endpoint.Scheme
	r.URL.Host = m.endpoint.Host
	response, err := m.base.RoundTrip(r)
	if err == nil {
		response.Request = r.Clone(r.Context())
		response.Request.URL = &original
		if location := response.Header.Get("Location"); location != "" {
			parsed, parseErr := url.Parse(location)
			if parseErr == nil && (parsed.Host == m.endpoint.Host || parsed.Host == "") {
				parsed.Host = original.Host
				parsed.Scheme = original.Scheme
				response.Header.Set("Location", parsed.String())
			}
		}
	}
	return response, err
}
func TestUploadPreservesUnmappedOwnershipAndExactDigest(t *testing.T) {
	a, d, layer := fixture(t)
	dir := t.TempDir()
	if err := materialize(a, dir); err != nil {
		t.Fatal(err)
	}
	handler := registry.New(registry.Logger(log.New(io.Discard, "", 0)))
	var tokenAuth atomic.Bool
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/service/token" {
			u, p, ok := r.BasicAuth()
			if !ok || u != creds().Username || p != testSecret {
				w.WriteHeader(403)
				return
			}
			tokenAuth.Store(true)
			_, _ = io.WriteString(w, `{"token":"synthetic-test-token"}`)
			return
		}
		if r.Header.Get("Authorization") != "Bearer synthetic-test-token" {
			w.Header().Set("WWW-Authenticate", `Bearer realm="https://harbor.example.test/service/token",service="test"`)
			w.WriteHeader(401)
			return
		}
		handler.ServeHTTP(w, r)
	}))
	defer server.Close()
	endpoint, _ := url.Parse(server.URL)
	transport := hostTransport{host: "harbor.example.test", base: mappingTransport{base: server.Client().Transport, endpoint: endpoint}}
	if err := Upload(context.Background(), dir, testImage, d, creds(), transport); err != nil {
		t.Fatal(err)
	}
	if !tokenAuth.Load() {
		t.Fatal("no scoped robot authentication")
	}
	s := sha256.Sum256(layer)
	r, _ := http.NewRequest("GET", server.URL+"/v2/project/app/blobs/sha256:"+hex.EncodeToString(s[:]), nil)
	r.Header.Set("Authorization", "Bearer synthetic-test-token")
	res, err := server.Client().Do(r)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	got, _ := io.ReadAll(res.Body)
	if !bytes.Equal(got, layer) {
		t.Fatal("layer bytes changed")
	}
	tr := tar.NewReader(bytes.NewReader(got))
	h, err := tr.Next()
	if err != nil || h.Uid != 0 || h.Gid != 42 {
		t.Fatal("ownership changed")
	}
	if bytes.Contains(got, []byte(testSecret)) {
		t.Fatal("credential in image")
	}
	if _, err := os.Stat(filepath.Join(dir, "etc", "gshadow")); !os.IsNotExist(err) {
		t.Fatal("layer was extracted")
	}
}
func TestPrepareRejectsWrongCredentialsAndKeepsPrivateFiles(t *testing.T) {
	build := buildJob(t)
	parent := t.TempDir()
	_ = os.Chmod(parent, 0700)
	for _, bad := range []Credentials{{Location: "wrong/project", Username: "robot$test", Password: testSecret}, {Location: creds().Location, Username: "admin", Password: testSecret}} {
		data, _ := json.Marshal(bad)
		if _, err := Prepare(build, testImage, parent, bytes.NewReader(data)); err == nil {
			t.Fatal("invalid credentials accepted")
		}
	}
	data, _ := json.Marshal(creds())
	job, err := Prepare(build, testImage, parent, bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{job, filepath.Join(job, "credentials.json"), filepath.Join(job, "request.json")} {
		if err := PrivatePath(p, p == job); err != nil {
			t.Fatal(err)
		}
	}
	data, _ = os.ReadFile(filepath.Join(job, "request.json"))
	if bytes.Contains(data, []byte(testSecret)) {
		t.Fatal("secret in request")
	}
}
func TestRunRejectsTamperingConsumesCredentialsAndCleans(t *testing.T) {
	build := buildJob(t)
	parent := t.TempDir()
	_ = os.Chmod(parent, 0700)
	data, _ := json.Marshal(creds())
	job, err := Prepare(build, testImage, parent, bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	f, _ := os.OpenFile(filepath.Join(build, "output", "result.oci.tar"), os.O_APPEND|os.O_WRONLY, 0600)
	_, _ = f.Write([]byte("tamper"))
	_ = f.Close()
	if _, err := Run(context.Background(), job, "456", parent); err == nil {
		t.Fatal("tampering accepted")
	}
	if _, err := os.Stat(filepath.Join(job, "credentials.json")); !os.IsNotExist(err) {
		t.Fatal("staged credential survived")
	}
	roots, _ := filepath.Glob(filepath.Join(parent, "oci-push-lsf-*"))
	if len(roots) != 0 {
		t.Fatal("workspace survived")
	}
	failure, _ := os.ReadFile(filepath.Join(job, "output", "failure.json"))
	if bytes.Contains(failure, []byte(testSecret)) || !bytes.Contains(failure, []byte("publication_failed")) {
		t.Fatal("invalid failure evidence")
	}
	if _, err := Result(job); err == nil {
		t.Fatal("failure reported as success")
	}
}
func TestTransportRejectsCrossHostAndCleartext(t *testing.T) {
	tr := hostTransport{host: "harbor.example.test", base: http.DefaultTransport}
	for _, u := range []string{"http://harbor.example.test/v2/", "https://other.example.test/service/token"} {
		r, _ := http.NewRequest("GET", u, nil)
		if _, err := tr.RoundTrip(r); err == nil {
			t.Fatal("unsafe destination accepted")
		}
	}
}
func TestMaterializeRejectsTraversal(t *testing.T) {
	var b bytes.Buffer
	tw := tar.NewWriter(&b)
	_ = tw.WriteHeader(&tar.Header{Name: "../escape", Mode: 0600, Size: 1})
	_, _ = tw.Write([]byte("x"))
	_ = tw.Close()
	a := filepath.Join(t.TempDir(), "bad.tar")
	_ = os.WriteFile(a, b.Bytes(), 0600)
	if err := materialize(a, t.TempDir()); err == nil {
		t.Fatal("traversal accepted")
	}
}
