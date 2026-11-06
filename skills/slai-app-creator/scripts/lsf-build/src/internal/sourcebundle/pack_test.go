package sourcebundle

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func TestPackFilesIsDeterministicAndInspectable(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "Containerfile"), []byte("FROM scratch\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(root, "app"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "app", "run"), []byte("hello\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	first, second := filepath.Join(t.TempDir(), "first.tar.zst"), filepath.Join(t.TempDir(), "second.tar.zst")
	files := []string{"app/run", "Containerfile"}
	if err := PackFiles(root, first, files); err != nil {
		t.Fatal(err)
	}
	if err := PackFiles(root, second, files); err != nil {
		t.Fatal(err)
	}
	a, _ := os.ReadFile(first)
	b, _ := os.ReadFile(second)
	if !bytes.Equal(a, b) {
		t.Fatal("source package is not deterministic")
	}
	result, err := InspectTarZstd(first, testPolicy())
	if err != nil || result.Files != 2 {
		t.Fatalf("InspectTarZstd() = %#v, %v", result, err)
	}
}

func TestPackFilesRejectsSymlink(t *testing.T) {
	root := t.TempDir()
	if err := os.Symlink("missing", filepath.Join(root, "link")); err != nil {
		t.Fatal(err)
	}
	if err := PackFiles(root, filepath.Join(t.TempDir(), "source.tar.zst"), []string{"link"}); err == nil {
		t.Fatal("symlink accepted")
	}
}
