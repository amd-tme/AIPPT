package sourcebundle

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWriteScratchFixtureIsDeterministicAndExtractable(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0o700); err != nil {
		t.Fatal(err)
	}
	first := filepath.Join(root, "first.tar.zst")
	second := filepath.Join(root, "second.tar.zst")
	if err := WriteScratchFixture(first); err != nil {
		t.Fatal(err)
	}
	if err := WriteScratchFixture(second); err != nil {
		t.Fatal(err)
	}
	left, _ := os.ReadFile(first)
	right, _ := os.ReadFile(second)
	if string(left) != string(right) {
		t.Fatal("same fixed source produced different archive bytes")
	}
	result, err := ExtractTarZstd(first, filepath.Join(root, "source"), testPolicy())
	if err != nil || result.Files != 2 {
		t.Fatalf("fixed source did not round-trip: result=%#v err=%v", result, err)
	}
	containerfile, err := os.ReadFile(filepath.Join(root, "source/Containerfile"))
	if err != nil || string(containerfile) != string(scratchFixture[0].data) {
		t.Fatal("fixed Containerfile changed during packaging")
	}
}

func TestWriteRunningCancellationFixtureIsDeterministicAndPinned(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0o700); err != nil {
		t.Fatal(err)
	}
	first := filepath.Join(root, "first.tar.zst")
	second := filepath.Join(root, "second.tar.zst")
	if err := WriteRunningCancellationFixture(first); err != nil {
		t.Fatal(err)
	}
	if err := WriteRunningCancellationFixture(second); err != nil {
		t.Fatal(err)
	}
	left, _ := os.ReadFile(first)
	right, _ := os.ReadFile(second)
	if string(left) != string(right) {
		t.Fatal("same cancellation source produced different archive bytes")
	}
	result, err := ExtractTarZstd(first, filepath.Join(root, "source"), testPolicy())
	if err != nil || result.Files != 1 {
		t.Fatalf("cancellation source did not round-trip: result=%#v err=%v", result, err)
	}
	containerfile, err := os.ReadFile(filepath.Join(root, "source/Containerfile"))
	if err != nil || string(containerfile) != string(runningCancellationFixture[0].data) {
		t.Fatal("fixed cancellation Containerfile changed during packaging")
	}
}

func TestWriteRepresentativeWebFixtureIsDeterministicAndPinned(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0o700); err != nil {
		t.Fatal(err)
	}
	first := filepath.Join(root, "first.tar.zst")
	second := filepath.Join(root, "second.tar.zst")
	if err := WriteRepresentativeWebFixture(first); err != nil {
		t.Fatal(err)
	}
	if err := WriteRepresentativeWebFixture(second); err != nil {
		t.Fatal(err)
	}
	left, _ := os.ReadFile(first)
	right, _ := os.ReadFile(second)
	if string(left) != string(right) {
		t.Fatal("same representative source produced different archive bytes")
	}
	result, err := ExtractTarZstd(first, filepath.Join(root, "source"), testPolicy())
	if err != nil || result.Files != 3 {
		t.Fatalf("representative source did not round-trip: result=%#v err=%v", result, err)
	}
	containerfile, err := os.ReadFile(filepath.Join(root, "source/Containerfile"))
	if err != nil || string(containerfile) != string(representativeWebFixture[0].data) {
		t.Fatal("representative Containerfile changed during packaging")
	}
	for _, required := range []string{"@sha256:", "FROM scratch", "USER 65532:65532", "EXPOSE 8080"} {
		if !strings.Contains(string(containerfile), required) {
			t.Fatalf("representative Containerfile omitted %q", required)
		}
	}
}
