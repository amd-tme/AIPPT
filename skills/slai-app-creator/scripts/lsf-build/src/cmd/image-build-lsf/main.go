package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/AMD-SLAI/image-build-lsf/internal/ociarchive"
	"github.com/AMD-SLAI/image-build-lsf/internal/sourcebundle"
)

var (
	jobIDPattern  = regexp.MustCompile(`^[0-9]{1,20}$`)
	digestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

type evidence struct {
	SchemaVersion  int    `json:"schema_version"`
	JobID          string `json:"lsf_job_id"`
	ArtifactDigest string `json:"artifact_digest"`
	ManifestDigest string `json:"manifest_digest"`
	Platform       string `json:"platform"`
	ArtifactBytes  int64  `json:"artifact_bytes"`
}

func main() {
	if err := run(context.Background(), os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string) error {
	if len(args) < 2 {
		return usageError()
	}
	switch args[0] + " " + args[1] {
	case "source package":
		return packageSource(ctx, args[2:])
	case "result verify":
		return verifyResult(args[2:])
	default:
		return usageError()
	}
}

func usageError() error {
	return errors.New("usage: image-build-lsf source package ... | result verify ...")
}

func packageSource(ctx context.Context, args []string) error {
	flags := flag.NewFlagSet("source package", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var root, output, buildContext string
	flags.StringVar(&root, "root", ".", "clean Git worktree root")
	flags.StringVar(&output, "output", "", "new tar.zst output path")
	flags.StringVar(&buildContext, "build-context", ".", "repository-relative source subtree")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 || output == "" {
		return errors.New("usage: image-build-lsf source package --root REPOSITORY --output SOURCE.tar.zst [--build-context PATH]")
	}
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return errors.New("source repository path cannot be resolved")
	}
	rootAbs, err = filepath.EvalSymlinks(rootAbs)
	if err != nil {
		return errors.New("source repository path cannot be resolved")
	}
	outputAbs, err := filepath.Abs(output)
	if err != nil {
		return errors.New("source output path cannot be resolved")
	}
	files, err := cleanTrackedFiles(ctx, rootAbs)
	if err != nil {
		return err
	}
	files, err = selectBuildContextFiles(files, buildContext)
	if err != nil {
		return err
	}
	if err := sourcebundle.PackFiles(rootAbs, outputAbs, files); err != nil {
		return err
	}
	policy := sourcebundle.Policy{MaxArchiveBytes: 64 << 20, MaxExpandedBytes: 2 << 30, MaxEntries: 100000, MaxPathBytes: 512, MaxDepth: 32, MaxExpansion: 100}
	inspected, err := sourcebundle.InspectTarZstd(outputAbs, policy)
	if err != nil {
		_ = os.Remove(outputAbs)
		return err
	}
	info, digest, err := hashFile(outputAbs)
	if err != nil {
		_ = os.Remove(outputAbs)
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"file": outputAbs, "format": "tar.zst", "digest": digest, "size_bytes": info.Size(), "tracked_files": len(files), "inspected_files": inspected.Files, "build_context": buildContext})
}

func verifyResult(args []string) error {
	flags := flag.NewFlagSet("result verify", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var jobDir, field string
	flags.StringVar(&jobDir, "job-dir", "", "owner-only LSF job directory")
	flags.StringVar(&field, "field", "json", "json, job-id, artifact-digest, manifest-digest, or platform")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 || !filepath.IsAbs(jobDir) {
		return errors.New("usage: image-build-lsf result verify --job-dir ABSOLUTE_PATH [--field FIELD]")
	}
	data, err := os.ReadFile(filepath.Join(jobDir, "output", "success.json"))
	if err != nil {
		return errors.New("success evidence is unavailable")
	}
	var expected evidence
	if err := json.Unmarshal(data, &expected); err != nil || expected.SchemaVersion != 1 || !jobIDPattern.MatchString(expected.JobID) || !digestPattern.MatchString(expected.ArtifactDigest) || !digestPattern.MatchString(expected.ManifestDigest) || expected.Platform != "linux/amd64" || expected.ArtifactBytes < 1 {
		return errors.New("success evidence is invalid")
	}
	resultPath := filepath.Join(jobDir, "output", "result.oci.tar")
	info, err := os.Lstat(resultPath)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Size() != expected.ArtifactBytes {
		return errors.New("OCI result is unavailable or does not match evidence")
	}
	observed, err := ociarchive.Verify(resultPath)
	if err != nil || observed.TransportDigest != expected.ArtifactDigest || observed.ManifestDigest != expected.ManifestDigest || observed.OS+"/"+observed.Architecture != expected.Platform {
		return errors.New("OCI result verification failed")
	}
	switch field {
	case "json":
		return json.NewEncoder(os.Stdout).Encode(expected)
	case "job-id":
		fmt.Fprintln(os.Stdout, expected.JobID)
	case "artifact-digest":
		fmt.Fprintln(os.Stdout, expected.ArtifactDigest)
	case "manifest-digest":
		fmt.Fprintln(os.Stdout, expected.ManifestDigest)
	case "platform":
		fmt.Fprintln(os.Stdout, expected.Platform)
	default:
		return errors.New("result field is invalid")
	}
	return nil
}

func cleanTrackedFiles(ctx context.Context, root string) ([]string, error) {
	topCommand := exec.CommandContext(ctx, "git", "-C", root, "rev-parse", "--show-toplevel")
	topCommand.Stderr = io.Discard
	topData, err := topCommand.Output()
	if err != nil {
		return nil, errors.New("source root is not a Git worktree")
	}
	top, err := filepath.EvalSymlinks(strings.TrimSpace(string(topData)))
	if err != nil || top != root {
		return nil, errors.New("source root must be the Git worktree top level")
	}
	for _, arguments := range [][]string{{"-C", root, "diff", "--quiet", "HEAD", "--"}, {"-C", root, "diff", "--cached", "--quiet", "HEAD", "--"}} {
		command := exec.CommandContext(ctx, "git", arguments...)
		command.Stdout, command.Stderr = io.Discard, io.Discard
		if err := command.Run(); err != nil {
			return nil, errors.New("source repository tracked tree is dirty or unavailable")
		}
	}
	command := exec.CommandContext(ctx, "git", "-C", root, "ls-files", "-z", "--cached")
	command.Stderr = io.Discard
	data, err := command.Output()
	if err != nil || len(data) == 0 || data[len(data)-1] != 0 {
		return nil, errors.New("source repository tracked files cannot be enumerated")
	}
	parts := strings.Split(string(data[:len(data)-1]), "\x00")
	if len(parts) == 0 || len(parts) > 100000 {
		return nil, errors.New("source repository tracked-file count is invalid")
	}
	return parts, nil
}

func selectBuildContextFiles(files []string, buildContext string) ([]string, error) {
	if buildContext == "" || buildContext == ".." || filepath.IsAbs(buildContext) || filepath.Clean(buildContext) != buildContext || strings.Contains(buildContext, "\\") || strings.HasPrefix(buildContext, "../") {
		return nil, errors.New("source build context is invalid")
	}
	prefix := ""
	if buildContext != "." {
		prefix = filepath.ToSlash(buildContext) + "/"
	}
	selected := make([]string, 0, len(files))
	for _, name := range files {
		posixName := filepath.ToSlash(name)
		if prefix != "" && !strings.HasPrefix(posixName, prefix) {
			continue
		}
		if sourcePathExcluded(posixName, prefix) {
			continue
		}
		selected = append(selected, name)
	}
	if len(selected) == 0 {
		return nil, errors.New("source build context has no eligible tracked files")
	}
	return selected, nil
}

func sourcePathExcluded(name, contextPrefix string) bool {
	relative := strings.TrimPrefix(name, contextPrefix)
	parts := strings.Split(strings.ToLower(relative), "/")
	if len(parts) > 0 {
		switch parts[0] {
		case "deploy", ".github", ".gitlab", ".circleci":
			return true
		}
	}
	base := parts[len(parts)-1]
	if base == ".env" || strings.HasPrefix(base, ".env.") || base == ".npmrc" || base == ".pypirc" || base == ".netrc" || base == "auth.json" || base == "credentials" {
		return true
	}
	return strings.HasSuffix(base, ".raw.yaml") || strings.HasSuffix(base, ".enc.yaml")
}

func hashFile(filename string) (os.FileInfo, string, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, "", errors.New("source package cannot be opened")
	}
	hash := sha256.New()
	_, copyErr := io.Copy(hash, file)
	closeErr := file.Close()
	info, statErr := os.Stat(filename)
	if copyErr != nil || closeErr != nil || statErr != nil {
		return nil, "", errors.New("source package cannot be inspected")
	}
	return info, "sha256:" + hex.EncodeToString(hash.Sum(nil)), nil
}
