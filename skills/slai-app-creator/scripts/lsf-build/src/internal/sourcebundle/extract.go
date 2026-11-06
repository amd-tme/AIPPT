package sourcebundle

import (
	"archive/tar"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/klauspost/compress/zstd"
)

type Policy struct {
	MaxArchiveBytes  int64
	MaxExpandedBytes int64
	MaxEntries       int
	MaxPathBytes     int
	MaxDepth         int
	MaxExpansion     int64
}

type Result struct {
	Files         int   `json:"files"`
	ExpandedBytes int64 `json:"expanded_bytes"`
}

// ExtractTarZstd extracts one verified source object into a new directory. The
// prototype intentionally accepts only ASCII regular files and directories; links and
// special files are rejected rather than interpreted.
func ExtractTarZstd(archivePath, destination string, policy Policy) (result Result, retErr error) {
	if err := validatePolicy(policy); err != nil {
		return Result{}, err
	}
	archiveInfo, err := os.Lstat(archivePath)
	if err != nil || !archiveInfo.Mode().IsRegular() || archiveInfo.Mode()&os.ModeSymlink != 0 || archiveInfo.Mode().Perm()&0o077 != 0 || !ownedByInvoker(archiveInfo) || archiveInfo.Size() < 1 || archiveInfo.Size() > policy.MaxArchiveBytes {
		return Result{}, errors.New("source archive is not a bounded regular file")
	}
	if !filepath.IsAbs(destination) || filepath.Clean(destination) != destination {
		return Result{}, errors.New("source destination must be a clean absolute path")
	}
	if _, err := os.Lstat(destination); err == nil || !errors.Is(err, os.ErrNotExist) {
		return Result{}, errors.New("source destination already exists or cannot be inspected")
	}
	parent := filepath.Dir(destination)
	parentInfo, err := os.Lstat(parent)
	resolvedParent, resolveErr := filepath.EvalSymlinks(parent)
	if err != nil || resolveErr != nil || resolvedParent != parent || !parentInfo.IsDir() || parentInfo.Mode()&os.ModeSymlink != 0 || parentInfo.Mode().Perm()&0o077 != 0 || !ownedByInvoker(parentInfo) {
		return Result{}, errors.New("source destination parent is unsafe")
	}

	staging := destination + ".extracting"
	if _, err := os.Lstat(staging); err == nil || !errors.Is(err, os.ErrNotExist) {
		return Result{}, errors.New("source extraction staging path already exists or cannot be inspected")
	}
	if err := os.Mkdir(staging, 0o700); err != nil {
		return Result{}, errors.New("create source extraction staging directory failed")
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.RemoveAll(staging)
		}
	}()

	archive, err := os.Open(archivePath)
	if err != nil {
		return Result{}, errors.New("open source archive failed")
	}
	defer archive.Close()
	decoder, err := zstd.NewReader(archive,
		zstd.WithDecoderConcurrency(1),
		zstd.WithDecoderMaxMemory(uint64(policy.MaxExpandedBytes)),
	)
	if err != nil {
		return Result{}, errors.New("initialize source decompressor failed")
	}
	defer decoder.Close()

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
		folded := strings.ToLower(name)
		if _, duplicate := seen[folded]; duplicate {
			return Result{}, errors.New("source archive contains a duplicate or case-colliding path")
		}
		if header.Mode&0o7000 != 0 {
			return Result{}, errors.New("source archive contains prohibited mode bits")
		}
		target := filepath.Join(staging, filepath.FromSlash(name))
		if !within(staging, target) {
			return Result{}, errors.New("source archive path escapes extraction root")
		}

		switch header.Typeflag {
		case tar.TypeDir:
			if err := createParents(staging, filepath.Dir(target), seen, policy.MaxEntries); err != nil {
				return Result{}, err
			}
			if len(seen) >= policy.MaxEntries {
				return Result{}, errors.New("source archive exceeds entry-count limit")
			}
			if err := os.Mkdir(target, 0o700); err != nil {
				return Result{}, errors.New("create source directory failed")
			}
			seen[folded] = tar.TypeDir
		case tar.TypeReg, tar.TypeRegA:
			if header.Size < 0 || header.Size > policy.MaxExpandedBytes-result.ExpandedBytes {
				return Result{}, errors.New("source archive exceeds expanded-byte limit")
			}
			if policy.MaxExpansion > 0 && result.ExpandedBytes+header.Size > archiveInfo.Size()*policy.MaxExpansion {
				return Result{}, errors.New("source archive exceeds expansion-ratio limit")
			}
			if err := createParents(staging, filepath.Dir(target), seen, policy.MaxEntries); err != nil {
				return Result{}, err
			}
			if len(seen) >= policy.MaxEntries {
				return Result{}, errors.New("source archive exceeds entry-count limit")
			}
			file, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
			if err != nil {
				return Result{}, errors.New("create extracted source file failed")
			}
			written, copyErr := io.Copy(file, io.LimitReader(reader, header.Size+1))
			closeErr := file.Close()
			if copyErr != nil || closeErr != nil || written != header.Size {
				return Result{}, errors.New("write extracted source file failed")
			}
			mode := os.FileMode(header.Mode) & 0o777
			mode &^= 0o022
			if err := os.Chmod(target, mode); err != nil {
				return Result{}, errors.New("set extracted source file mode failed")
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
	if err := os.Rename(staging, destination); err != nil {
		return Result{}, errors.New("commit extracted source failed")
	}
	committed = true
	return result, nil
}

func validateTrailingArchiveData(reader io.Reader) error {
	const maxPadding = 10 << 10
	padding, err := io.ReadAll(io.LimitReader(reader, maxPadding+1))
	if err != nil {
		return errors.New("read source archive trailer failed")
	}
	if len(padding) > maxPadding {
		return errors.New("source archive contains excessive trailing data")
	}
	for _, value := range padding {
		if value != 0 {
			return errors.New("source archive contains non-padding trailing data")
		}
	}
	return nil
}

func validatePolicy(policy Policy) error {
	if policy.MaxArchiveBytes <= 0 || policy.MaxExpandedBytes <= 0 || policy.MaxEntries <= 0 || policy.MaxPathBytes <= 0 || policy.MaxDepth <= 0 || policy.MaxExpansion <= 0 {
		return errors.New("source extraction policy must use positive bounds")
	}
	return nil
}

func safeName(name string, policy Policy) (string, error) {
	if name == "" || len(name) > policy.MaxPathBytes || strings.IndexByte(name, 0) >= 0 || strings.Contains(name, "\\") || strings.HasPrefix(name, "/") || path.Clean(name) != name || name == "." {
		return "", errors.New("source archive contains an unsafe path")
	}
	parts := strings.Split(name, "/")
	if len(parts) > policy.MaxDepth {
		return "", errors.New("source archive path exceeds depth limit")
	}
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return "", errors.New("source archive contains an unsafe path component")
		}
		for _, character := range []byte(part) {
			if character < 0x20 || character > 0x7e {
				return "", errors.New("source archive prototype paths must be printable ASCII")
			}
		}
	}
	return name, nil
}

func createParents(root, parent string, seen map[string]byte, maxEntries int) error {
	relative, err := filepath.Rel(root, parent)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return errors.New("source archive parent escapes extraction root")
	}
	if relative == "." {
		return nil
	}
	current := root
	for _, component := range strings.Split(filepath.ToSlash(relative), "/") {
		current = filepath.Join(current, component)
		folded, err := filepath.Rel(root, current)
		if err != nil {
			return errors.New("source archive parent path is invalid")
		}
		folded = strings.ToLower(filepath.ToSlash(folded))
		if kind, exists := seen[folded]; exists && kind != tar.TypeDir {
			return errors.New("source archive parent collides with a file")
		}
		if _, err := os.Lstat(current); errors.Is(err, os.ErrNotExist) {
			if len(seen) >= maxEntries {
				return errors.New("source archive exceeds entry-count limit")
			}
			if err := os.Mkdir(current, 0o700); err != nil {
				return errors.New("create source parent directory failed")
			}
			seen[folded] = tar.TypeDir
		} else if err != nil {
			return errors.New("inspect source parent directory failed")
		}
	}
	return nil
}

func ownedByInvoker(info os.FileInfo) bool {
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(stat.Uid) == os.Geteuid()
}

func within(root, candidate string) bool {
	relative, err := filepath.Rel(filepath.Clean(root), filepath.Clean(candidate))
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

func (result Result) String() string {
	return fmt.Sprintf("%d files, %d bytes", result.Files, result.ExpandedBytes)
}
