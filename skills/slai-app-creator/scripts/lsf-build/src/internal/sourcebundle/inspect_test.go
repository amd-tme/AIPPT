package sourcebundle

import (
	"archive/tar"
	"path/filepath"
	"testing"
)

func TestInspectTarZstdAcceptsSafeArchiveWithoutExtraction(t *testing.T) {
	root := t.TempDir()
	archive := writeArchive(t, root, []testEntry{
		{name: "app", typeflag: tar.TypeDir, mode: 0o755},
		{name: "app/Dockerfile", typeflag: tar.TypeReg, mode: 0o644, data: []byte("FROM scratch\n")},
		{name: ".env.example", typeflag: tar.TypeReg, mode: 0o644, data: []byte("PORT=8080\n")},
	})
	result, err := InspectTarZstd(archive, testPolicy())
	if err != nil || result.Files != 2 {
		t.Fatalf("safe source inspection failed: result=%#v err=%v", result, err)
	}
	if _, err := filepath.Abs(archive); err != nil {
		t.Fatal(err)
	}
}

func TestInspectTarZstdRejectsSecretPathsAndMarkers(t *testing.T) {
	for name, entry := range map[string]testEntry{
		"dotenv":       {name: ".env.production", typeflag: tar.TypeReg, mode: 0o600, data: []byte("VALUE=x")},
		"private key":  {name: "fixture.txt", typeflag: tar.TypeReg, mode: 0o600, data: []byte("-----BEGIN " + "PRIVATE KEY-----")},
		"git metadata": {name: ".git/config", typeflag: tar.TypeReg, mode: 0o600, data: []byte("safe")},
	} {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			archive := writeArchive(t, root, []testEntry{entry})
			if _, err := InspectTarZstd(archive, testPolicy()); err == nil {
				t.Fatal("prohibited source content was accepted")
			}
		})
	}
}

func TestInspectTarZstdRejectsMarkerAcrossReadBoundary(t *testing.T) {
	prefix := make([]byte, (32<<10)-8)
	payload := append(prefix, []byte("-----BEGIN "+"OPENSSH PRIVATE KEY-----")...)
	root := t.TempDir()
	archive := writeArchive(t, root, []testEntry{{name: "fixture.txt", typeflag: tar.TypeReg, mode: 0o600, data: payload}})
	if _, err := InspectTarZstd(archive, testPolicy()); err == nil {
		t.Fatal("split credential marker was accepted")
	}
}
