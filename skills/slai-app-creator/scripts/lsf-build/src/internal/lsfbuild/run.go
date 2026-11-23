package lsfbuild

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"

	"github.com/AMD-SLAI/image-build-lsf/internal/ociarchive"
	"github.com/AMD-SLAI/image-build-lsf/internal/sourcebundle"
)

const maxCommandOutput = 1 << 20

var (
	jobIDPattern  = regexp.MustCompile(`^[0-9]{1,20}$`)
	digestPattern = regexp.MustCompile(`^sha256:([0-9a-f]{64})\n?$`)
)

type Config struct {
	JobDir, Podman, FuseOverlayFS, Self, JobID string
	Profile                                    string
	BuildContext                               string
	Dockerfile                                 string
	BuildNetwork                               string
	ProbePort                                  int
	ProbePath                                  string
	TempParent                                 string
}

type Evidence struct {
	SchemaVersion  int    `json:"schema_version"`
	JobID          string `json:"lsf_job_id"`
	Profile        string `json:"profile"`
	BuildContext   string `json:"build_context"`
	Dockerfile     string `json:"dockerfile"`
	BuildNetwork   string `json:"build_network"`
	StorageDriver  string `json:"storage_driver"`
	SourceDigest   string `json:"source_digest"`
	ArtifactDigest string `json:"artifact_digest"`
	ManifestDigest string `json:"manifest_digest"`
	Platform       string `json:"platform"`
	ArtifactBytes  int64  `json:"artifact_bytes"`
	ProbeStatus    int    `json:"probe_status,omitempty"`
}

type StageError struct {
	Stage, Category string
}

func (e *StageError) Error() string {
	return e.Stage + " failed with category " + e.Category + "; output withheld"
}

func Run(ctx context.Context, config Config) (evidence Evidence, retErr error) {
	if err := validateConfig(config); err != nil {
		return Evidence{}, err
	}
	if err := validateJobDir(config.JobDir); err != nil {
		return Evidence{}, err
	}
	defer protectLSFLogs(config.JobDir)
	expectedDigest, err := readExpectedDigest(filepath.Join(config.JobDir, "source.sha256"))
	if err != nil {
		return Evidence{}, err
	}

	localRoot, err := os.MkdirTemp(config.TempParent, "oci-build-lsf-"+config.JobID+"-")
	if err != nil {
		return Evidence{}, errors.New("create local build root failed")
	}
	if err := os.Chmod(localRoot, 0o700); err != nil {
		_ = os.RemoveAll(localRoot)
		return Evidence{}, errors.New("protect local build root failed")
	}
	tag := "localhost/oci-build-lsf:" + config.JobID
	containerName := "oci-build-lsf-probe-" + config.JobID
	base := podmanBase(config, localRoot)
	commandEnv := podmanEnvironment(localRoot)
	commandArgs := func(extra ...string) []string {
		return append(append([]string{}, base...), extra...)
	}
	defer func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		_, _ = runCommand(cleanupCtx, commandEnv, config.Podman, commandArgs("rm", "--force", "--ignore", containerName)...)
		_, _ = runCommand(cleanupCtx, commandEnv, config.Podman, commandArgs("rmi", "--force", tag)...)
		_, _ = runCommand(cleanupCtx, commandEnv, config.Podman, commandArgs("system", "migrate")...)
		_, _ = runCommand(cleanupCtx, commandEnv, config.Podman, commandArgs("system", "reset", "--force")...)
		_ = makeTreeRemovable(localRoot)
		if err := os.RemoveAll(localRoot); err != nil {
			retErr = &StageError{Stage: "cleanup", Category: "local_workspace"}
		}
		if retErr != nil {
			_ = writeFailure(config.JobDir, retErr)
		}
	}()

	for _, name := range []string{"home/.config/containers", "runtime", "storage", "runroot", "tmp", "source", "result"} {
		if err := os.MkdirAll(filepath.Join(localRoot, name), 0o700); err != nil {
			return Evidence{}, &StageError{Stage: "prepare", Category: "local_workspace"}
		}
	}
	policy := []byte("{\"default\":[{\"type\":\"insecureAcceptAnything\"}]}\n")
	if err := os.WriteFile(filepath.Join(localRoot, "home/.config/containers/policy.json"), policy, 0o600); err != nil {
		return Evidence{}, &StageError{Stage: "prepare", Category: "container_policy"}
	}
	localSource := filepath.Join(localRoot, "source.tar.zst")
	digest, err := copyAndHash(filepath.Join(config.JobDir, "source.tar.zst"), localSource, 64<<20)
	if err != nil || digest != expectedDigest {
		return Evidence{}, &StageError{Stage: "source", Category: "digest_or_copy"}
	}
	extracted := filepath.Join(localRoot, "source-tree")
	policyBounds := sourcebundle.Policy{MaxArchiveBytes: 64 << 20, MaxExpandedBytes: 2 << 30, MaxEntries: 100000, MaxPathBytes: 512, MaxDepth: 32, MaxExpansion: 100}
	if _, err := sourcebundle.ExtractTarZstd(localSource, extracted, policyBounds); err != nil {
		return Evidence{}, &StageError{Stage: "source", Category: "extraction"}
	}
	contextDir := filepath.Join(extracted, filepath.FromSlash(config.BuildContext))
	dockerfilePath := filepath.Join(extracted, filepath.FromSlash(config.Dockerfile))
	if err := validateBuildInputs(extracted, contextDir, dockerfilePath); err != nil {
		return Evidence{}, err
	}
	if err := ValidateContainerfile(dockerfilePath); err != nil {
		return Evidence{}, err
	}

	buildArgs := commandArgs(
		"build", "--format", "oci", "--platform", "linux/amd64", "--no-cache", "--layers=false",
		"--network", config.BuildNetwork, "--cap-drop", "all",
		"--force-rm", "--rm", "--file", dockerfilePath, "--tag", tag, contextDir,
	)
	if _, err := runCommand(ctx, commandEnv, config.Podman, buildArgs...); err != nil {
		_ = writeCommandDiagnostic(config.JobDir, "build.log", err)
		return Evidence{}, &StageError{Stage: "build", Category: classifyOutput(err)}
	}
	probeStatus := 0
	if config.Profile == "slai-web-app-v1" {
		runArgs := commandArgs("run", "--detach", "--pull", "never", "--name", containerName,
			"--network", "none", "--cap-drop", "all", "--security-opt", "no-new-privileges", tag)
		if _, err := runCommand(ctx, commandEnv, config.Podman, runArgs...); err != nil {
			return Evidence{}, &StageError{Stage: "probe_start", Category: classifyOutput(err)}
		}
		if _, err := runCommand(ctx, commandEnv, config.Podman, commandArgs("cp", config.Self, containerName+":/.__oci_build_http_probe")...); err != nil {
			return Evidence{}, &StageError{Stage: "probe_copy", Category: classifyOutput(err)}
		}
		probeArgs := commandArgs("exec", "--user", "0", containerName, "/.__oci_build_http_probe",
			"probe-helper", "--port", fmt.Sprint(config.ProbePort), "--path", config.ProbePath)
		if _, err := runCommand(ctx, commandEnv, config.Podman, probeArgs...); err != nil {
			return Evidence{}, &StageError{Stage: "probe_http", Category: classifyOutput(err)}
		}
		probeStatus = http.StatusOK
	}
	localResult := filepath.Join(localRoot, "result", "image.oci.tar")
	if _, err := runCommand(ctx, commandEnv, config.Podman, commandArgs("save", "--format", "oci-archive", "--output", localResult, tag)...); err != nil {
		return Evidence{}, &StageError{Stage: "export", Category: classifyOutput(err)}
	}
	verified, err := ociarchive.Verify(localResult)
	if err != nil {
		return Evidence{}, &StageError{Stage: "verify", Category: "invalid_oci"}
	}
	info, err := os.Stat(localResult)
	if err != nil || info.Size() < 1 {
		return Evidence{}, &StageError{Stage: "verify", Category: "invalid_result"}
	}
	outDir := filepath.Join(config.JobDir, "output")
	if err := validateOutputDir(outDir); err != nil {
		return Evidence{}, err
	}
	if err := copyAtomic(localResult, filepath.Join(outDir, "result.oci.tar")); err != nil {
		return Evidence{}, &StageError{Stage: "publish", Category: "nfs_copy"}
	}
	evidence = Evidence{SchemaVersion: 1, JobID: config.JobID, Profile: config.Profile,
		BuildContext: config.BuildContext, Dockerfile: config.Dockerfile, BuildNetwork: config.BuildNetwork,
		StorageDriver: storageDriver(config),
		SourceDigest:  expectedDigest, ArtifactDigest: verified.TransportDigest,
		ManifestDigest: verified.ManifestDigest, Platform: verified.OS + "/" + verified.Architecture,
		ArtifactBytes: info.Size(), ProbeStatus: probeStatus}
	for _, name := range []string{"source.tar.zst", "source.sha256", "packaging.json"} {
		if err := os.Remove(filepath.Join(config.JobDir, name)); err != nil && !errors.Is(err, os.ErrNotExist) {
			_ = os.Remove(filepath.Join(outDir, "result.oci.tar"))
			return Evidence{}, &StageError{Stage: "publish", Category: "source_cleanup"}
		}
	}
	if err := writeJSONAtomic(filepath.Join(outDir, "success.json"), evidence); err != nil {
		_ = os.Remove(filepath.Join(outDir, "result.oci.tar"))
		return Evidence{}, &StageError{Stage: "publish", Category: "evidence"}
	}
	return evidence, nil
}

func protectLSFLogs(jobDir string) {
	for _, name := range []string{"lsf.stdout", "lsf.stderr"} {
		path := filepath.Join(jobDir, "output", name)
		info, err := os.Lstat(path)
		if err == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 && owned(info) {
			_ = os.Chmod(path, 0o600)
		}
	}
}

// CleanupJob removes only owner-controlled local roots for one exact numeric LSF job ID.
// It is the recovery path for an earlier worker that could not run or finish its defer.
func CleanupJob(ctx context.Context, config Config, jobID string) (int, error) {
	if !jobIDPattern.MatchString(jobID) || !filepath.IsAbs(config.TempParent) || !filepath.IsAbs(config.Podman) || !filepath.IsAbs(config.FuseOverlayFS) {
		return 0, errors.New("cleanup configuration is invalid")
	}
	matches, err := filepath.Glob(filepath.Join(config.TempParent, "oci-build-lsf-"+jobID+"-*"))
	if err != nil {
		return 0, errors.New("cleanup target enumeration failed")
	}
	removed := 0
	for _, root := range matches {
		info, statErr := os.Lstat(root)
		if statErr != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o077 != 0 || !owned(info) {
			return removed, errors.New("cleanup target is unsafe")
		}
		base := podmanBase(config, root)
		environment := podmanEnvironment(root)
		migrateArgs := append(append([]string{}, base...), "system", "migrate")
		_, _ = runCommand(ctx, environment, config.Podman, migrateArgs...)
		resetArgs := append(append([]string{}, base...), "system", "reset", "--force")
		_, _ = runCommand(ctx, environment, config.Podman, resetArgs...)
		_ = makeTreeRemovable(root)
		if err := os.RemoveAll(root); err != nil {
			return removed, errors.New("cleanup target removal failed")
		}
		removed++
	}
	return removed, nil
}

func makeTreeRemovable(root string) error {
	if err := os.Chmod(root, 0o700); err != nil {
		return err
	}
	return filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return nil
		}
		mode := os.FileMode(0o600)
		if entry.IsDir() {
			mode = 0o700
		}
		return os.Chmod(path, mode)
	})
}

func ValidateContainerfile(filename string) error {
	data, err := os.ReadFile(filename)
	if err != nil || len(data) == 0 || len(data) > 1<<20 {
		return &StageError{Stage: "policy", Category: "containerfile_unavailable"}
	}
	for _, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Fields(line)
		instruction := strings.ToUpper(fields[0])
		switch instruction {
		case "FROM":
			image := ""
			for _, field := range fields[1:] {
				if !strings.HasPrefix(field, "--") {
					image = field
					break
				}
			}
			if image != "scratch" && !regexp.MustCompile(`@sha256:[0-9a-f]{64}$`).MatchString(image) {
				return &StageError{Stage: "policy", Category: "unpinned_base"}
			}
		case "USER":
			return &StageError{Stage: "policy", Category: "image_user_unsupported"}
		case "COPY", "ADD":
			if strings.Contains(strings.ToLower(line), "--chown") {
				return &StageError{Stage: "policy", Category: "image_ownership_unsupported"}
			}
		case "RUN":
			if regexp.MustCompile(`(^|[^a-z0-9_])chown([^a-z0-9_]|$)`).MatchString(strings.ToLower(line)) {
				return &StageError{Stage: "policy", Category: "image_ownership_unsupported"}
			}
		}
	}
	return nil
}

func Probe(port int, path string) error {
	if port < 1 || port > 65535 || path == "" || path[0] != '/' || strings.ContainsAny(path, "?#\r\n") {
		return errors.New("probe configuration is invalid")
	}
	client := &http.Client{Timeout: 2 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }, Transport: &http.Transport{Proxy: nil}}
	endpoint := fmt.Sprintf("http://127.0.0.1:%d%s", port, path)
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		response, err := client.Get(endpoint)
		if err == nil {
			_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
			_ = response.Body.Close()
			if response.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(250 * time.Millisecond)
	}
	return errors.New("probe did not observe exact status 200")
}

func podmanBase(config Config, root string) []string {
	base := []string{"--root", filepath.Join(root, "storage"), "--runroot", filepath.Join(root, "runroot"),
		"--tmpdir", filepath.Join(root, "tmp"), "--storage-driver", storageDriver(config)}
	// A custom Podman executable may manage its own helper configuration.
	if config.Podman == "/tool/pandora64/bin/podman" {
		for _, helper := range []struct {
			flag  string
			paths []string
		}{
			{"--conmon", []string{"/tool/pandora64/bin/conmon", "/usr/bin/conmon", "/usr/libexec/podman/conmon"}},
			{"--runtime", []string{"/tool/pandora64/bin/runc", "/usr/bin/runc", "/usr/bin/crun"}},
			{"--network-cmd-path", []string{"/usr/bin/slirp4netns", "/bin/slirp4netns", "/tool/pandora64/bin/slirp4netns"}},
		} {
			if path := firstExecutable(helper.paths); path != "" {
				base = append(base, helper.flag, path)
			}
		}
	}
	if storageDriver(config) == "overlay" {
		base = append(base, "--storage-opt", "overlay.mount_program="+config.FuseOverlayFS,
			"--storage-opt", "overlay.ignore_chown_errors=true")
	} else {
		base = append(base, "--storage-opt", "vfs.ignore_chown_errors=true")
	}
	return append(base, "--cgroup-manager", "cgroupfs", "--events-backend", "file")
}

func storageDriver(config Config) string {
	info, err := os.Stat(config.FuseOverlayFS)
	if err == nil && info.Mode().IsRegular() && info.Mode()&0o111 != 0 {
		return "overlay"
	}
	return "vfs"
}

type commandError struct{ output string }

func (e *commandError) Error() string { return "command failed; output withheld" }

func podmanEnvironment(root string) []string {
	return []string{
		"HOME=" + filepath.Join(root, "home"),
		"XDG_CONFIG_HOME=" + filepath.Join(root, "home/.config"),
		"XDG_RUNTIME_DIR=" + filepath.Join(root, "runtime"),
		"TMPDIR=" + filepath.Join(root, "tmp"),
		"PATH=/tool/pandora64/bin:/usr/bin:/bin",
		"LANG=C",
		"LC_ALL=C",
	}
}

func runCommand(ctx context.Context, environment []string, path string, args ...string) (string, error) {
	command := exec.CommandContext(ctx, path, args...)
	var output boundedBuffer
	command.Stdout, command.Stderr = &output, &output
	command.Env = append([]string{}, environment...)
	if err := command.Run(); err != nil {
		return "", &commandError{output: output.String()}
	}
	return output.String(), nil
}

type boundedBuffer struct{ bytes.Buffer }

func (b *boundedBuffer) Write(value []byte) (int, error) {
	n := len(value)
	if remaining := maxCommandOutput - b.Len(); remaining > 0 {
		if len(value) > remaining {
			value = value[:remaining]
		}
		_, _ = b.Buffer.Write(value)
	}
	return n, nil
}

func classifyOutput(err error) string {
	var commandErr *commandError
	if !errors.As(err, &commandErr) {
		return "execution"
	}
	lower := strings.ToLower(commandErr.output)
	classifications := []struct {
		category string
		needles  []string
	}{
		{"permission", []string{"permission denied", "operation not permitted", "insufficient uids or gids", "lchown"}},
		{"resource", []string{"no space left", "cannot allocate memory", "resource temporarily unavailable"}},
		{"network", []string{"network is unreachable", "temporary failure in name resolution", "connection timed out", "could not resolve host"}},
		{"containerfile", []string{"unknown instruction", "parse error", "no from statement"}},
		{"runtime", []string{"creating container", "executable file not found", "exit status 126"}},
		{"build_step", []string{"error building at step", "did not complete successfully"}},
	}
	for _, classification := range classifications {
		for _, needle := range classification.needles {
			if strings.Contains(lower, needle) {
				return classification.category
			}
		}
	}
	return "command"
}

func validateConfig(c Config) error {
	if !jobIDPattern.MatchString(c.JobID) || !filepath.IsAbs(c.JobDir) || !filepath.IsAbs(c.Podman) || !filepath.IsAbs(c.FuseOverlayFS) || !filepath.IsAbs(c.Self) || !filepath.IsAbs(c.TempParent) {
		return errors.New("LSF build configuration is invalid")
	}
	if c.Profile != "oci-build-v1" && c.Profile != "slai-web-app-v1" {
		return errors.New("LSF build profile is invalid")
	}
	if !safeRelativePath(c.BuildContext) || !safeRelativePath(c.Dockerfile) || (c.BuildNetwork != "none" && c.BuildNetwork != "host") {
		return errors.New("LSF build input policy is invalid")
	}
	contextPrefix := c.BuildContext + "/"
	if c.BuildContext != "." && c.Dockerfile != c.BuildContext && !strings.HasPrefix(c.Dockerfile, contextPrefix) {
		return errors.New("LSF Dockerfile must be inside the build context")
	}
	if c.Profile == "slai-web-app-v1" && (c.ProbePort < 1 || c.ProbePort > 65535 || c.ProbePath == "" || c.ProbePath[0] != '/') {
		return errors.New("LSF web probe is invalid")
	}
	for _, path := range []string{c.Podman, c.Self} {
		info, err := os.Stat(path)
		if err != nil || !info.Mode().IsRegular() || info.Mode()&0o111 == 0 {
			return errors.New("LSF build executable is unavailable")
		}
	}
	if info, err := os.Stat(c.FuseOverlayFS); err == nil && (!info.Mode().IsRegular() || info.Mode()&0o111 == 0) {
		return errors.New("LSF fuse-overlayfs path is unsafe")
	} else if err != nil && !errors.Is(err, os.ErrNotExist) {
		return errors.New("LSF fuse-overlayfs path is unavailable")
	}
	return nil
}

func safeRelativePath(value string) bool {
	return value != "" && value != ".." && !filepath.IsAbs(value) && filepath.Clean(value) == value &&
		!strings.Contains(value, "\\") && !strings.HasPrefix(value, "../")
}

func validateBuildInputs(extracted, contextDir, dockerfilePath string) error {
	contextInfo, contextErr := os.Lstat(contextDir)
	dockerfileInfo, dockerfileErr := os.Lstat(dockerfilePath)
	contextRel, contextRelErr := filepath.Rel(extracted, contextDir)
	dockerfileRel, dockerfileRelErr := filepath.Rel(contextDir, dockerfilePath)
	if contextErr != nil || dockerfileErr != nil || contextRelErr != nil || dockerfileRelErr != nil ||
		!contextInfo.IsDir() || contextInfo.Mode()&os.ModeSymlink != 0 ||
		!dockerfileInfo.Mode().IsRegular() || dockerfileInfo.Mode()&os.ModeSymlink != 0 ||
		contextRel == ".." || strings.HasPrefix(contextRel, ".."+string(filepath.Separator)) ||
		dockerfileRel == ".." || strings.HasPrefix(dockerfileRel, ".."+string(filepath.Separator)) {
		return &StageError{Stage: "policy", Category: "build_input_unavailable"}
	}
	return nil
}

func validateJobDir(path string) error {
	info, err := os.Lstat(path)
	resolved, resolveErr := filepath.EvalSymlinks(path)
	if err != nil || resolveErr != nil || resolved != filepath.Clean(path) || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o077 != 0 || !owned(info) {
		return errors.New("LSF job directory is unsafe")
	}
	return nil
}

func validateOutputDir(path string) error {
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o077 != 0 || !owned(info) {
		return errors.New("LSF output directory is unsafe")
	}
	return nil
}

func owned(info os.FileInfo) bool {
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(stat.Uid) == os.Geteuid()
}

func readExpectedDigest(path string) (string, error) {
	data, err := os.ReadFile(path)
	match := digestPattern.FindSubmatch(data)
	if err != nil || match == nil {
		return "", errors.New("source digest record is invalid")
	}
	return "sha256:" + string(match[1]), nil
}

func copyAndHash(source, target string, max int64) (string, error) {
	info, err := os.Lstat(source)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o077 != 0 || !owned(info) || info.Size() < 1 || info.Size() > max {
		return "", errors.New("source snapshot is unsafe")
	}
	in, err := os.Open(source)
	if err != nil {
		return "", err
	}
	defer in.Close()
	out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	hash := sha256.New()
	written, copyErr := io.Copy(io.MultiWriter(out, hash), io.LimitReader(in, max+1))
	closeErr := out.Close()
	if copyErr != nil || closeErr != nil || written != info.Size() {
		_ = os.Remove(target)
		return "", errors.New("source snapshot copy failed")
	}
	return "sha256:" + hex.EncodeToString(hash.Sum(nil)), nil
}

func copyAtomic(source, target string) error {
	if _, err := os.Lstat(target); err == nil || !errors.Is(err, os.ErrNotExist) {
		return errors.New("result target already exists")
	}
	temporary := target + ".partial"
	in, err := os.Open(source)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(temporary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(out, in)
	syncErr := out.Sync()
	closeErr := out.Close()
	if copyErr != nil || syncErr != nil || closeErr != nil {
		_ = os.Remove(temporary)
		return errors.New("result copy failed")
	}
	return os.Rename(temporary, target)
}

func writeJSONAtomic(path string, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	temporary := path + ".partial"
	file, err := os.OpenFile(temporary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	_, writeErr := file.Write(data)
	syncErr := file.Sync()
	closeErr := file.Close()
	if writeErr != nil || syncErr != nil || closeErr != nil {
		_ = os.Remove(temporary)
		return errors.New("evidence write failed")
	}
	return os.Rename(temporary, path)
}

func writeFailure(jobDir string, failure error) error {
	category := "internal"
	var stageErr *StageError
	if errors.As(failure, &stageErr) {
		category = stageErr.Stage + "_" + stageErr.Category
	}
	return writeJSONAtomic(filepath.Join(jobDir, "output", "failure.json"), map[string]any{"schema_version": 1, "category": category})
}

func writeCommandDiagnostic(jobDir, name string, failure error) error {
	var commandErr *commandError
	if !errors.As(failure, &commandErr) || commandErr.output == "" || name != "build.log" {
		return nil
	}
	path := filepath.Join(jobDir, "output", name)
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	data := []byte(commandErr.output)
	if len(data) > maxCommandOutput {
		data = data[:maxCommandOutput]
	}
	if len(data) == 0 || data[len(data)-1] != '\n' {
		data = append(data, '\n')
	}
	_, writeErr := file.Write(data)
	syncErr := file.Sync()
	closeErr := file.Close()
	if writeErr != nil || syncErr != nil || closeErr != nil {
		_ = os.Remove(path)
		return errors.New("diagnostic write failed")
	}
	return nil
}

func firstExecutable(paths []string) string {
	for _, path := range paths {
		info, err := os.Stat(path)
		if err == nil && info.Mode().IsRegular() && info.Mode().Perm()&0111 != 0 {
			return path
		}
	}
	return ""
}
