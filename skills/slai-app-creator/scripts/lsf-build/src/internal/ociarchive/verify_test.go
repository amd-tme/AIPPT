package ociarchive

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestVerifyOCIArchive(t *testing.T) {
	archive := makeArchive(t, "linux", "amd64", false)
	result, err := Verify(archive)
	if err != nil {
		t.Fatal(err)
	}
	if result.OS != "linux" || result.Architecture != "amd64" {
		t.Fatalf("unexpected platform: %#v", result)
	}
	if len(result.TransportDigest) != len("sha256:")+64 || len(result.ManifestDigest) != len("sha256:")+64 {
		t.Fatalf("unexpected digests: %#v", result)
	}
}

func TestRejectsWrongPlatform(t *testing.T) {
	if _, err := Verify(makeArchive(t, "linux", "arm64", false)); err == nil {
		t.Fatal("expected wrong-platform rejection")
	}
}

func TestRejectsDigestMismatch(t *testing.T) {
	if _, err := Verify(makeArchive(t, "linux", "amd64", true)); err == nil {
		t.Fatal("expected digest mismatch rejection")
	}
}

func TestVerifyValueAbsentScansRawAndCompressedEntries(t *testing.T) {
	canary := []byte("OCI_BUILD_BOUNDARY_0123456789abcdef")
	clean := bytes.Repeat([]byte("safe"), 10_000)
	if err := VerifyValueAbsent(makeScanArchive(t, clean, false), canary); err != nil {
		t.Fatal(err)
	}
	payload := append(bytes.Repeat([]byte{'x'}, 32_760), canary...)
	for _, compressed := range []bool{false, true} {
		t.Run(map[bool]string{false: "raw", true: "gzip"}[compressed], func(t *testing.T) {
			if err := VerifyValueAbsent(makeScanArchive(t, payload, compressed), canary); err == nil {
				t.Fatal("embedded canary was accepted")
			} else if bytes.Contains([]byte(err.Error()), canary) {
				t.Fatal("canary value was returned in the error")
			}
		})
	}
}

func makeScanArchive(t *testing.T, payload []byte, compressed bool) string {
	t.Helper()
	entry := payload
	if compressed {
		var encoded bytes.Buffer
		gz := gzip.NewWriter(&encoded)
		if _, err := gz.Write(payload); err != nil {
			t.Fatal(err)
		}
		if err := gz.Close(); err != nil {
			t.Fatal(err)
		}
		entry = encoded.Bytes()
	}
	filename := filepath.Join(t.TempDir(), "scan.oci.tar")
	f, err := os.OpenFile(filename, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	tw := tar.NewWriter(f)
	if err := tw.WriteHeader(&tar.Header{Name: "blobs/sha256/layer", Mode: 0o600, Size: int64(len(entry)), Typeflag: tar.TypeReg}); err != nil {
		t.Fatal(err)
	}
	if _, err := tw.Write(entry); err != nil {
		t.Fatal(err)
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	return filename
}

func makeArchive(t *testing.T, osName, arch string, corrupt bool) string {
	t.Helper()
	config, _ := json.Marshal(map[string]any{"os": osName, "architecture": arch})
	configDigest := digest(config)
	manifest, _ := json.Marshal(map[string]any{
		"schemaVersion": 2,
		"config": map[string]any{
			"mediaType": "application/vnd.oci.image.config.v1+json",
			"digest":    configDigest,
			"size":      len(config),
		},
		"layers": []any{},
	})
	manifestDigest := digest(manifest)
	index, _ := json.Marshal(map[string]any{
		"schemaVersion": 2,
		"manifests": []any{map[string]any{
			"mediaType": "application/vnd.oci.image.manifest.v1+json",
			"digest":    manifestDigest,
			"size":      len(manifest),
			"platform":  map[string]string{"os": osName, "architecture": arch},
		}},
	})
	layout := []byte(`{"imageLayoutVersion":"1.0.0"}`)
	if corrupt {
		manifest = append(manifest, ' ')
	}

	filename := filepath.Join(t.TempDir(), "image.oci.tar")
	f, err := os.OpenFile(filename, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	tw := tar.NewWriter(f)
	for _, name := range []string{"blobs/", "blobs/sha256/"} {
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o700, Typeflag: tar.TypeDir}); err != nil {
			t.Fatal(err)
		}
	}
	entries := map[string][]byte{
		"oci-layout": layout,
		"index.json": index,
		"blobs/sha256/" + configDigest[len("sha256:"):]:   config,
		"blobs/sha256/" + manifestDigest[len("sha256:"):]: manifest,
	}
	for name, data := range entries {
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o600, Size: int64(len(data)), Typeflag: tar.TypeReg}); err != nil {
			t.Fatal(err)
		}
		if _, err := tw.Write(data); err != nil {
			t.Fatal(err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	return filename
}

func TestSafeArchivePathAllowsCanonicalDirectoriesOnly(t *testing.T) {
	for _, name := range []string{"blobs/", "blobs/sha256/"} {
		if !safeArchivePath(name, tar.TypeDir) {
			t.Errorf("rejected canonical directory %q", name)
		}
	}
	for _, name := range []string{"../escape", "blobs/../../escape", "/absolute", "./index.json", "blobs//sha256/"} {
		if safeArchivePath(name, tar.TypeReg) || safeArchivePath(name, tar.TypeDir) {
			t.Errorf("accepted unsafe path %q", name)
		}
	}
}

func digest(data []byte) string {
	sum := sha256.Sum256(data)
	return "sha256:" + hex.EncodeToString(sum[:])
}
