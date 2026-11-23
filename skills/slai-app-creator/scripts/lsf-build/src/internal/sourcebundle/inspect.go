package sourcebundle

import (
	"archive/tar"
	"bytes"
	"errors"
	"io"
	"os"
	"path"
	"strings"

	"github.com/klauspost/compress/zstd"
)

var prohibitedContentMarkers = [][]byte{
	[]byte("-----BEGIN " + "PRIVATE KEY-----"),
	[]byte("-----BEGIN " + "RSA PRIVATE KEY-----"),
	[]byte("-----BEGIN " + "EC PRIVATE KEY-----"),
	[]byte("-----BEGIN " + "OPENSSH PRIVATE KEY-----"),
	[]byte("X-Amz-Signature="),
	[]byte("github_pat_"),
	[]byte("ghp_"),
}

// InspectTarZstd parses a source archive without extracting it. It applies the same
// path, type, mode, entry-count, expansion, and trailer bounds as extraction and adds
// defense-in-depth checks for prohibited secret-bearing paths and credential markers.
func InspectTarZstd(archivePath string, policy Policy) (Result, error) {
	if err := validatePolicy(policy); err != nil {
		return Result{}, err
	}
	info, err := os.Lstat(archivePath)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Size() < 1 || info.Size() > policy.MaxArchiveBytes {
		return Result{}, errors.New("source archive is not a bounded regular file")
	}
	archive, err := os.Open(archivePath)
	if err != nil {
		return Result{}, errors.New("open source archive failed")
	}
	defer archive.Close()
	decoder, err := zstd.NewReader(archive, zstd.WithDecoderConcurrency(1), zstd.WithDecoderMaxMemory(uint64(policy.MaxExpandedBytes)))
	if err != nil {
		return Result{}, errors.New("initialize source decompressor failed")
	}
	defer decoder.Close()

	result := Result{}
	seen := make(map[string]byte)
	reader := tar.NewReader(decoder)
	for {
		header, err := reader.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return Result{}, errors.New("read source archive failed")
		}
		name, err := safeName(header.Name, policy)
		if err != nil {
			return Result{}, err
		}
		if prohibitedSourcePath(name) {
			return Result{}, errors.New("source archive contains a prohibited secret-bearing path")
		}
		folded := strings.ToLower(name)
		if _, duplicate := seen[folded]; duplicate {
			return Result{}, errors.New("source archive contains a duplicate or case-colliding path")
		}
		if header.Mode&0o7000 != 0 {
			return Result{}, errors.New("source archive contains prohibited mode bits")
		}
		if err := addMetadataParents(seen, name, policy.MaxEntries); err != nil {
			return Result{}, err
		}
		if len(seen) >= policy.MaxEntries {
			return Result{}, errors.New("source archive exceeds entry-count limit")
		}
		switch header.Typeflag {
		case tar.TypeDir:
			seen[folded] = tar.TypeDir
		case tar.TypeReg, tar.TypeRegA:
			if header.Size < 0 || header.Size > policy.MaxExpandedBytes-result.ExpandedBytes {
				return Result{}, errors.New("source archive exceeds expanded-byte limit")
			}
			if result.ExpandedBytes+header.Size > info.Size()*policy.MaxExpansion {
				return Result{}, errors.New("source archive exceeds expansion-ratio limit")
			}
			if err := scanRegularFile(reader, header.Size); err != nil {
				return Result{}, err
			}
			seen[folded] = tar.TypeReg
			result.Files++
			result.ExpandedBytes += header.Size
		default:
			return Result{}, errors.New("source archive contains a link or special entry")
		}
	}
	if err := validateTrailingArchiveData(decoder); err != nil {
		return Result{}, err
	}
	if result.Files == 0 {
		return Result{}, errors.New("source archive contains no regular files")
	}
	return result, nil
}

func addMetadataParents(seen map[string]byte, name string, maxEntries int) error {
	parent := path.Dir(name)
	if parent == "." {
		return nil
	}
	current := ""
	for _, component := range strings.Split(parent, "/") {
		if current == "" {
			current = component
		} else {
			current += "/" + component
		}
		folded := strings.ToLower(current)
		if kind, exists := seen[folded]; exists {
			if kind != tar.TypeDir {
				return errors.New("source archive parent collides with a file")
			}
			continue
		}
		if len(seen) >= maxEntries {
			return errors.New("source archive exceeds entry-count limit")
		}
		seen[folded] = tar.TypeDir
	}
	return nil
}

func prohibitedSourcePath(name string) bool {
	parts := strings.Split(strings.ToLower(name), "/")
	for _, component := range parts {
		if component == ".git" || component == ".netrc" || component == "id_rsa" || component == "id_ed25519" || component == "credentials" {
			return true
		}
		if component == ".env" || (strings.HasPrefix(component, ".env.") && component != ".env.example" && component != ".env.sample" && component != ".env.template") {
			return true
		}
		for _, suffix := range []string{".pem", ".key", ".p12", ".pfx"} {
			if strings.HasSuffix(component, suffix) {
				return true
			}
		}
	}
	return false
}

func scanRegularFile(reader io.Reader, size int64) error {
	const chunkSize = 32 << 10
	maxMarker := 0
	for _, marker := range prohibitedContentMarkers {
		if len(marker) > maxMarker {
			maxMarker = len(marker)
		}
	}
	buffer := make([]byte, chunkSize)
	tail := make([]byte, 0, maxMarker-1)
	remaining := size
	for remaining > 0 {
		want := int64(len(buffer))
		if remaining < want {
			want = remaining
		}
		n, err := io.ReadFull(reader, buffer[:want])
		if err != nil {
			return errors.New("read source archive file failed")
		}
		window := append(tail, buffer[:n]...)
		for _, marker := range prohibitedContentMarkers {
			if bytes.Contains(window, marker) {
				return errors.New("source archive contains a prohibited credential marker")
			}
		}
		keep := maxMarker - 1
		if keep > len(window) {
			keep = len(window)
		}
		tail = append(tail[:0], window[len(window)-keep:]...)
		remaining -= int64(n)
	}
	return nil
}
