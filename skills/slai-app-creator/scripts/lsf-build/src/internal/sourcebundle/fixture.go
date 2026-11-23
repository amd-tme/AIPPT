package sourcebundle

import (
	"archive/tar"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/klauspost/compress/zstd"
)

var scratchFixture = []struct {
	name string
	data []byte
}{
	{name: "Containerfile", data: []byte("FROM scratch\nCOPY hello.txt /hello.txt\n")},
	{name: "hello.txt", data: []byte("hello from the fixed OCI build prototype\n")},
}

var runningCancellationFixture = []struct {
	name string
	data []byte
}{
	{
		name: "Containerfile",
		data: []byte("FROM docker.io/library/alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc\n" +
			"RUN sleep 300\n"),
	},
}

var representativeWebFixture = []struct {
	name string
	data []byte
}{
	{
		name: "Containerfile",
		data: []byte("FROM docker.io/library/golang@sha256:e87b2a5f6df2dff71ea330d55d54f4979eb380ae58a7e3aabc9d53121243e689 AS build\n" +
			"WORKDIR /src\n" +
			"ENV GOCACHE=/tmp/go-build GOMODCACHE=/tmp/go-mod\n" +
			"COPY go.mod main.go ./\n" +
			"RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags='-s -w' -o /src/server .\n" +
			"FROM scratch\n" +
			"COPY --from=build /src/server /server\n" +
			"USER 65532:65532\n" +
			"EXPOSE 8080\n" +
			"ENTRYPOINT [\"/server\"]\n"),
	},
	{name: "go.mod", data: []byte("module example.invalid/oci-build-representative\n\ngo 1.20\n")},
	{
		name: "main.go",
		data: []byte("package main\n\n" +
			"import (\n\t\"fmt\"\n\t\"net/http\"\n)\n\n" +
			"func main() {\n" +
			"\tmux := http.NewServeMux()\n" +
			"\tmux.HandleFunc(\"/healthz\", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })\n" +
			"\tmux.HandleFunc(\"/\", func(w http.ResponseWriter, _ *http.Request) { _, _ = fmt.Fprintln(w, \"oci-build-service representative\") })\n" +
			"\tif err := http.ListenAndServe(\":8080\", mux); err != nil { panic(err) }\n" +
			"}\n"),
	},
}

// WriteScratchFixture creates only the fixed, secret-free prototype source bundle.
func WriteScratchFixture(filename string) (retErr error) {
	return writeFixture(filename, scratchFixture)
}

// WriteRunningCancellationFixture creates the fixed, secret-free long-running fixture.
func WriteRunningCancellationFixture(filename string) (retErr error) {
	return writeFixture(filename, runningCancellationFixture)
}

// WriteRepresentativeWebFixture creates a fixed multi-stage, non-root web-app fixture.
func WriteRepresentativeWebFixture(filename string) (retErr error) {
	return writeFixture(filename, representativeWebFixture)
}

func writeFixture(filename string, entries []struct {
	name string
	data []byte
}) (retErr error) {
	if !filepath.IsAbs(filename) || filepath.Clean(filename) != filename {
		return errors.New("fixture output path must be clean and absolute")
	}
	parent := filepath.Dir(filename)
	info, err := os.Lstat(parent)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o077 != 0 || !ownedByInvoker(info) {
		return errors.New("fixture output parent is unsafe")
	}
	file, err := os.OpenFile(filename, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return errors.New("create fixture archive failed")
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.Remove(filename)
		}
	}()
	encoder, err := zstd.NewWriter(file, zstd.WithEncoderConcurrency(1), zstd.WithEncoderCRC(true))
	if err != nil {
		_ = file.Close()
		return errors.New("initialize fixture compressor failed")
	}
	writer := tar.NewWriter(encoder)
	for _, entry := range entries {
		header := &tar.Header{
			Name: entry.name, Typeflag: tar.TypeReg, Mode: 0o644,
			Size: int64(len(entry.data)), ModTime: time.Unix(0, 0).UTC(),
			AccessTime: time.Unix(0, 0).UTC(), ChangeTime: time.Unix(0, 0).UTC(),
			Uid: 0, Gid: 0, Format: tar.FormatPAX,
		}
		if err := writer.WriteHeader(header); err != nil {
			_ = encoder.Close()
			_ = file.Close()
			return errors.New("write fixture archive header failed")
		}
		if _, err := writer.Write(entry.data); err != nil {
			_ = encoder.Close()
			_ = file.Close()
			return errors.New("write fixture archive content failed")
		}
	}
	if err := writer.Close(); err != nil {
		_ = encoder.Close()
		_ = file.Close()
		return errors.New("finalize fixture tar failed")
	}
	if err := encoder.Close(); err != nil {
		_ = file.Close()
		return errors.New("finalize fixture compression failed")
	}
	if err := file.Close(); err != nil {
		return errors.New("close fixture archive failed")
	}
	committed = true
	return nil
}
