package sourcebundle

import (
	"archive/tar"
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/klauspost/compress/zstd"
)

type testEntry struct {
	name     string
	typeflag byte
	mode     int64
	data     []byte
}

func TestExtractTarZstdCommitsValidatedTree(t *testing.T) {
	root := t.TempDir()
	archive := writeArchive(t, root, []testEntry{
		{name: "app", typeflag: tar.TypeDir, mode: 0o755},
		{name: "app/Containerfile", typeflag: tar.TypeReg, mode: 0o644, data: []byte("FROM scratch\n")},
		{name: "app/run.sh", typeflag: tar.TypeReg, mode: 0o755, data: []byte("#!/bin/sh\n")},
	})
	destination := filepath.Join(root, "source")
	result, err := ExtractTarZstd(archive, destination, testPolicy())
	if err != nil {
		t.Fatal(err)
	}
	if result.Files != 2 || result.ExpandedBytes != 23 {
		t.Fatalf("unexpected extraction result: %#v", result)
	}
	data, err := os.ReadFile(filepath.Join(destination, "app/Containerfile"))
	if err != nil || string(data) != "FROM scratch\n" {
		t.Fatal("validated source was not committed")
	}
	info, err := os.Stat(filepath.Join(destination, "app/run.sh"))
	if err != nil || info.Mode().Perm() != 0o755 {
		t.Fatal("safe executable mode was not preserved")
	}
}

func TestExtractTarZstdRejectsUnsafeEntriesAndRemovesStaging(t *testing.T) {
	tests := map[string][]testEntry{
		"parent traversal": {{name: "../escape", typeflag: tar.TypeReg, mode: 0o600, data: []byte("x")}},
		"absolute":         {{name: "/escape", typeflag: tar.TypeReg, mode: 0o600, data: []byte("x")}},
		"backslash":        {{name: `dir\file`, typeflag: tar.TypeReg, mode: 0o600, data: []byte("x")}},
		"symlink":          {{name: "link", typeflag: tar.TypeSymlink, mode: 0o777}},
		"hardlink":         {{name: "link", typeflag: tar.TypeLink, mode: 0o600}},
		"fifo":             {{name: "pipe", typeflag: tar.TypeFifo, mode: 0o600}},
		"setuid":           {{name: "tool", typeflag: tar.TypeReg, mode: 0o4755, data: []byte("x")}},
		"case collision": {
			{name: "Readme", typeflag: tar.TypeReg, mode: 0o600, data: []byte("a")},
			{name: "README", typeflag: tar.TypeReg, mode: 0o600, data: []byte("b")},
		},
	}
	for name, entries := range tests {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			archive := writeArchive(t, root, entries)
			destination := filepath.Join(root, "source")
			if _, err := ExtractTarZstd(archive, destination, testPolicy()); err == nil {
				t.Fatal("unsafe archive was accepted")
			}
			if _, err := os.Lstat(destination); !os.IsNotExist(err) {
				t.Fatal("failed extraction committed a destination")
			}
			if _, err := os.Lstat(destination + ".extracting"); !os.IsNotExist(err) {
				t.Fatal("failed extraction retained staging state")
			}
		})
	}
}

func TestExtractTarZstdEnforcesBounds(t *testing.T) {
	root := t.TempDir()
	archive := writeArchive(t, root, []testEntry{{name: "large", typeflag: tar.TypeReg, mode: 0o600, data: bytes.Repeat([]byte("x"), 128)}})
	policy := testPolicy()
	policy.MaxExpandedBytes = 64
	if _, err := ExtractTarZstd(archive, filepath.Join(root, "source"), policy); err == nil {
		t.Fatal("expanded-byte overflow was accepted")
	}
}

func TestExtractTarZstdCountsDirectoriesAndFilesAgainstEntryLimit(t *testing.T) {
	root := t.TempDir()
	archive := writeArchive(t, root, []testEntry{
		{name: "dir", typeflag: tar.TypeDir, mode: 0o700},
		{name: "dir/file", typeflag: tar.TypeReg, mode: 0o600, data: []byte("x")},
	})
	policy := testPolicy()
	policy.MaxEntries = 1
	if _, err := ExtractTarZstd(archive, filepath.Join(root, "source"), policy); err == nil {
		t.Fatal("entry-count overflow was accepted")
	}
}

func TestExtractTarZstdRejectsTrailingArchiveData(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0o700); err != nil {
		t.Fatal(err)
	}
	filename := filepath.Join(root, "source.tar.zst")
	file, err := os.OpenFile(filename, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	encoder, err := zstd.NewWriter(file, zstd.WithEncoderConcurrency(1))
	if err != nil {
		t.Fatal(err)
	}
	writer := tar.NewWriter(encoder)
	payload := []byte("safe")
	if err := writer.WriteHeader(&tar.Header{Name: "file", Typeflag: tar.TypeReg, Mode: 0o600, Size: int64(len(payload))}); err != nil {
		t.Fatal(err)
	}
	if _, err := writer.Write(payload); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := encoder.Write([]byte("not tar padding")); err != nil {
		t.Fatal(err)
	}
	if err := encoder.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := ExtractTarZstd(filename, filepath.Join(root, "source"), testPolicy()); err == nil {
		t.Fatal("trailing archive data was accepted")
	}
}

func writeArchive(t *testing.T, root string, entries []testEntry) string {
	t.Helper()
	if err := os.Chmod(root, 0o700); err != nil {
		t.Fatal(err)
	}
	filename := filepath.Join(root, "source.tar.zst")
	file, err := os.OpenFile(filename, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	encoder, err := zstd.NewWriter(file, zstd.WithEncoderConcurrency(1))
	if err != nil {
		t.Fatal(err)
	}
	writer := tar.NewWriter(encoder)
	for _, entry := range entries {
		header := &tar.Header{Name: entry.name, Typeflag: entry.typeflag, Mode: entry.mode, Size: int64(len(entry.data))}
		if err := writer.WriteHeader(header); err != nil {
			t.Fatal(err)
		}
		if len(entry.data) > 0 {
			if _, err := writer.Write(entry.data); err != nil {
				t.Fatal(err)
			}
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := encoder.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	return filename
}

func testPolicy() Policy {
	return Policy{
		MaxArchiveBytes:  1 << 20,
		MaxExpandedBytes: 1 << 20,
		MaxEntries:       100,
		MaxPathBytes:     256,
		MaxDepth:         16,
		MaxExpansion:     100,
	}
}
