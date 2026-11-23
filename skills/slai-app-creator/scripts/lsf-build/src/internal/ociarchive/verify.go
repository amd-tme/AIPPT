package ociarchive

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"regexp"
	"strings"
)

const (
	maxMetadataBytes   = 4 << 20
	maxCanaryScanBytes = 512 << 20
)

var digestPattern = regexp.MustCompile(`^sha256:([0-9a-f]{64})$`)

type Result struct {
	TransportDigest string `json:"transport_digest"`
	ManifestDigest  string `json:"manifest_digest"`
	OS              string `json:"os"`
	Architecture    string `json:"architecture"`
}

type descriptor struct {
	Digest   string `json:"digest"`
	Platform *struct {
		OS           string `json:"os"`
		Architecture string `json:"architecture"`
	} `json:"platform,omitempty"`
}

func Verify(filename string) (Result, error) {
	transport, err := hashFile(filename)
	if err != nil {
		return Result{}, err
	}
	f, err := os.Open(filename)
	if err != nil {
		return Result{}, err
	}
	defer f.Close()

	metadata := make(map[string][]byte)
	blobHashes := make(map[string]string)
	tr := tar.NewReader(f)
	for {
		h, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return Result{}, fmt.Errorf("read OCI tar: %w", err)
		}
		if !safeArchivePath(h.Name, h.Typeflag) {
			return Result{}, errors.New("unsafe OCI archive path")
		}
		if h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeRegA {
			continue
		}
		if h.Name == "index.json" || h.Name == "oci-layout" || strings.HasPrefix(h.Name, "blobs/sha256/") {
			if h.Size < 0 {
				return Result{}, errors.New("OCI metadata blob exceeds limit")
			}
			if strings.HasPrefix(h.Name, "blobs/sha256/") {
				expected := strings.TrimPrefix(h.Name, "blobs/sha256/")
				if !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(expected) {
					return Result{}, errors.New("invalid OCI blob path")
				}
				if _, duplicate := blobHashes[h.Name]; duplicate {
					return Result{}, errors.New("duplicate OCI archive entry")
				}
				hash := sha256.New()
				if h.Size > maxMetadataBytes {
					if _, err := io.Copy(hash, tr); err != nil {
						return Result{}, errors.New("truncated OCI blob")
					}
					actual := hex.EncodeToString(hash.Sum(nil))
					if actual != expected {
						return Result{}, errors.New("OCI blob digest mismatch")
					}
					blobHashes[h.Name] = actual
					continue
				}
				data, err := io.ReadAll(io.TeeReader(io.LimitReader(tr, maxMetadataBytes+1), hash))
				if err != nil || int64(len(data)) != h.Size {
					return Result{}, errors.New("truncated OCI metadata blob")
				}
				actual := hex.EncodeToString(hash.Sum(nil))
				if actual != expected {
					return Result{}, errors.New("OCI blob digest mismatch")
				}
				blobHashes[h.Name] = actual
				metadata[h.Name] = data
				continue
			}
			if h.Size > maxMetadataBytes {
				return Result{}, errors.New("OCI metadata blob exceeds limit")
			}
			data, err := io.ReadAll(io.LimitReader(tr, maxMetadataBytes+1))
			if err != nil || int64(len(data)) != h.Size {
				return Result{}, errors.New("truncated OCI metadata blob")
			}
			if _, duplicate := metadata[h.Name]; duplicate {
				return Result{}, errors.New("duplicate OCI archive entry")
			}
			metadata[h.Name] = data
		}
	}
	var layout struct {
		ImageLayoutVersion string `json:"imageLayoutVersion"`
	}
	if err := json.Unmarshal(metadata["oci-layout"], &layout); err != nil || layout.ImageLayoutVersion != "1.0.0" {
		return Result{}, errors.New("invalid OCI layout version")
	}

	var index struct {
		SchemaVersion int          `json:"schemaVersion"`
		Manifests     []descriptor `json:"manifests"`
	}
	if err := json.Unmarshal(metadata["index.json"], &index); err != nil || index.SchemaVersion != 2 || len(index.Manifests) != 1 {
		return Result{}, errors.New("OCI index must contain exactly one schema-2 manifest")
	}
	manifestDescriptor := index.Manifests[0]
	manifestBlob, err := blob(metadata, manifestDescriptor.Digest)
	if err != nil {
		return Result{}, fmt.Errorf("manifest: %w", err)
	}
	var manifest struct {
		SchemaVersion int          `json:"schemaVersion"`
		Config        descriptor   `json:"config"`
		Layers        []descriptor `json:"layers"`
	}
	if err := json.Unmarshal(manifestBlob, &manifest); err != nil || manifest.SchemaVersion != 2 {
		return Result{}, errors.New("invalid OCI manifest")
	}
	configBlob, err := blob(metadata, manifest.Config.Digest)
	if err != nil {
		return Result{}, fmt.Errorf("config: %w", err)
	}
	var config struct {
		OS           string `json:"os"`
		Architecture string `json:"architecture"`
	}
	if err := json.Unmarshal(configBlob, &config); err != nil {
		return Result{}, errors.New("invalid OCI config")
	}
	if config.OS != "linux" || config.Architecture != "amd64" {
		return Result{}, fmt.Errorf("unexpected platform %s/%s", config.OS, config.Architecture)
	}
	if manifestDescriptor.Platform != nil && (manifestDescriptor.Platform.OS != config.OS || manifestDescriptor.Platform.Architecture != config.Architecture) {
		return Result{}, errors.New("OCI index and config platform disagree")
	}
	for _, layer := range manifest.Layers {
		m := digestPattern.FindStringSubmatch(layer.Digest)
		if m == nil || blobHashes["blobs/sha256/"+m[1]] != m[1] {
			return Result{}, errors.New("referenced OCI layer missing or invalid")
		}
	}
	return Result{
		TransportDigest: "sha256:" + transport,
		ManifestDigest:  manifestDescriptor.Digest,
		OS:              config.OS,
		Architecture:    config.Architecture,
	}, nil
}

// VerifyValueAbsent scans regular OCI archive entries and gzip-compressed layer contents
// without returning the synthetic value in an error or retaining archive data.
func VerifyValueAbsent(filename string, value []byte) error {
	if len(value) < 16 || len(value) > 256 {
		return errors.New("prohibited canary length is outside the fixed bounds")
	}
	f, err := os.Open(filename)
	if err != nil {
		return err
	}
	defer f.Close()

	tr := tar.NewReader(f)
	for {
		h, err := tr.Next()
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return errors.New("read OCI archive during canary scan")
		}
		if !safeArchivePath(h.Name, h.Typeflag) {
			return errors.New("unsafe OCI archive path during canary scan")
		}
		if h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeRegA {
			continue
		}
		if h.Size < 0 || h.Size > maxCanaryScanBytes {
			return errors.New("OCI archive entry exceeds canary scan limit")
		}
		entry := bufio.NewReader(io.LimitReader(tr, h.Size))
		magic, _ := entry.Peek(2)
		rawScanner := newValueScanner(value)
		rawStream := io.TeeReader(entry, rawScanner)
		if len(magic) == 2 && magic[0] == 0x1f && magic[1] == 0x8b {
			gz, err := gzip.NewReader(rawStream)
			if err != nil {
				return errors.New("invalid gzip OCI layer during canary scan")
			}
			decodedScanner := newValueScanner(value)
			n, copyErr := io.Copy(decodedScanner, io.LimitReader(gz, maxCanaryScanBytes+1))
			closeErr := gz.Close()
			_, drainErr := io.Copy(io.Discard, rawStream)
			if copyErr != nil || closeErr != nil || drainErr != nil || n > maxCanaryScanBytes {
				return errors.New("bounded gzip OCI layer scan failed")
			}
			if decodedScanner.found {
				return errors.New("OCI archive contains prohibited canary")
			}
		} else if _, err := io.Copy(io.Discard, rawStream); err != nil {
			return errors.New("bounded OCI entry scan failed")
		}
		if rawScanner.found {
			return errors.New("OCI archive contains prohibited canary")
		}
	}
}

type valueScanner struct {
	value []byte
	tail  []byte
	found bool
}

func newValueScanner(value []byte) *valueScanner {
	return &valueScanner{value: append([]byte(nil), value...)}
}

func (s *valueScanner) Write(p []byte) (int, error) {
	n := len(p)
	if s.found || n == 0 {
		return n, nil
	}
	window := make([]byte, 0, len(s.tail)+n)
	window = append(window, s.tail...)
	window = append(window, p...)
	if bytes.Contains(window, s.value) {
		s.found = true
		return n, nil
	}
	keep := len(s.value) - 1
	if keep > len(window) {
		keep = len(window)
	}
	s.tail = append(s.tail[:0], window[len(window)-keep:]...)
	return n, nil
}

func safeArchivePath(name string, typeflag byte) bool {
	if name == "" || path.IsAbs(name) {
		return false
	}
	candidate := name
	if typeflag == tar.TypeDir {
		candidate = strings.TrimSuffix(candidate, "/")
	}
	clean := path.Clean(candidate)
	return candidate != "" && clean == candidate && clean != "." && clean != ".." && !strings.HasPrefix(clean, "../")
}

func blob(metadata map[string][]byte, digest string) ([]byte, error) {
	m := digestPattern.FindStringSubmatch(digest)
	if m == nil {
		return nil, errors.New("unsupported digest")
	}
	data, ok := metadata["blobs/sha256/"+m[1]]
	if !ok {
		return nil, errors.New("referenced blob missing")
	}
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != m[1] {
		return nil, errors.New("referenced blob digest mismatch")
	}
	return data, nil
}

func hashFile(filename string) (string, error) {
	f, err := os.Open(filename)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
