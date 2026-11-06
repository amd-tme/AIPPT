package sourcebundle

import (
	"archive/tar"
	"errors"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/klauspost/compress/zstd"
)

// PackFiles writes a deterministic tar.zst containing only the explicitly supplied,
// regular files beneath root. The caller is responsible for selecting an approved tree.
func PackFiles(root, output string, files []string) (retErr error) {
	if !filepath.IsAbs(root) || filepath.Clean(root) != root || !filepath.IsAbs(output) || filepath.Clean(output) != output || len(files) == 0 {
		return errors.New("source packaging paths are invalid")
	}
	rootInfo, err := os.Lstat(root)
	resolvedRoot, resolveErr := filepath.EvalSymlinks(root)
	if err != nil || resolveErr != nil || resolvedRoot != root || !rootInfo.IsDir() || rootInfo.Mode()&os.ModeSymlink != 0 {
		return errors.New("source packaging root is unsafe")
	}
	if _, err := os.Lstat(output); err == nil || !errors.Is(err, os.ErrNotExist) {
		return errors.New("source packaging refuses output overwrite")
	}
	ordered := append([]string(nil), files...)
	sort.Strings(ordered)
	seen := make(map[string]struct{}, len(ordered))
	archive, err := os.OpenFile(output, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return errors.New("source package output cannot be created")
	}
	committed := false
	defer func() {
		_ = archive.Close()
		if !committed {
			_ = os.Remove(output)
		}
	}()
	encoder, err := zstd.NewWriter(archive, zstd.WithEncoderConcurrency(1), zstd.WithEncoderCRC(true))
	if err != nil {
		return errors.New("source package compressor cannot be initialized")
	}
	w := tar.NewWriter(encoder)
	for _, name := range ordered {
		if name == "" || filepath.IsAbs(name) || filepath.Clean(name) != name || strings.Contains(name, "\\") || strings.HasPrefix(name, ".."+string(filepath.Separator)) {
			return errors.New("source package contains an unsafe selected path")
		}
		posixName := filepath.ToSlash(name)
		folded := strings.ToLower(posixName)
		if _, duplicate := seen[folded]; duplicate {
			return errors.New("source package contains duplicate or case-colliding paths")
		}
		seen[folded] = struct{}{}
		path := filepath.Join(root, name)
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return errors.New("source package selection contains a non-regular file")
		}
		mode := int64(0o644)
		if info.Mode()&0o111 != 0 {
			mode = 0o755
		}
		header := &tar.Header{Name: posixName, Typeflag: tar.TypeReg, Mode: mode, Size: info.Size(), ModTime: time.Unix(0, 0).UTC(), AccessTime: time.Unix(0, 0).UTC(), ChangeTime: time.Unix(0, 0).UTC(), Uid: 0, Gid: 0, Format: tar.FormatPAX}
		if err := w.WriteHeader(header); err != nil {
			return errors.New("source package header could not be written")
		}
		file, err := os.Open(path)
		if err != nil {
			return errors.New("source package input cannot be opened")
		}
		written, copyErr := io.Copy(w, file)
		closeErr := file.Close()
		if copyErr != nil || closeErr != nil || written != info.Size() {
			return errors.New("source package input could not be copied")
		}
	}
	if err := w.Close(); err != nil {
		return errors.New("source package tar could not be finalized")
	}
	if err := encoder.Close(); err != nil {
		return errors.New("source package compression could not be finalized")
	}
	if err := archive.Sync(); err != nil {
		return errors.New("source package output could not be synchronized")
	}
	if err := archive.Close(); err != nil {
		return errors.New("source package output could not be closed")
	}
	committed = true
	return nil
}
