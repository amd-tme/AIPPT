package lsfbuild

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/AMD-SLAI/image-build-lsf/internal/sourcebundle"
)

func TestValidateContainerfileAcceptsLSFWebSubset(t *testing.T) {
	filename := writeContainerfile(t, "FROM example.invalid/build@sha256:"+strings.Repeat("a", 64)+" AS build\nRUN true\nFROM scratch\nCOPY --from=build /server /server\nENTRYPOINT [\"/server\"]\n")
	if err := ValidateContainerfile(filename); err != nil {
		t.Fatalf("compatible Containerfile rejected: %v", err)
	}
}

func TestValidateContainerfileRejectsUnsupportedConstructs(t *testing.T) {
	tests := []struct{ name, content, category string }{
		{"unpinned", "FROM alpine:3.20\n", "unpinned_base"},
		{"user", "FROM scratch\nUSER 65534\n", "image_user_unsupported"},
		{"copy-chown", "FROM scratch\nCOPY --chown=1:1 x /x\n", "image_ownership_unsupported"},
		{"run-chown", "FROM scratch\nRUN chown 1:1 /x\n", "image_ownership_unsupported"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := ValidateContainerfile(writeContainerfile(t, test.content))
			var stageErr *StageError
			if !errors.As(err, &stageErr) || stageErr.Stage != "policy" || stageErr.Category != test.category {
				t.Fatalf("unexpected result: %#v", err)
			}
		})
	}
}

func TestPodmanEnvironmentDoesNotInheritCredentials(t *testing.T) {
	root := t.TempDir()
	environment := podmanEnvironment(root)
	output, err := runCommand(context.Background(), environment, "/usr/bin/env")
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"AWS_", "MINIO_", "REGISTRY_", "DOCKER_", "SECRET", "TOKEN"} {
		if strings.Contains(output, forbidden) {
			t.Fatalf("isolated environment leaked %q: %s", forbidden, output)
		}
	}
	for _, required := range []string{"HOME=" + filepath.Join(root, "home"), "XDG_RUNTIME_DIR=" + filepath.Join(root, "runtime"), "TMPDIR=" + filepath.Join(root, "tmp")} {
		if !strings.Contains(output, required+"\n") {
			t.Fatalf("isolated environment lacks %q: %s", required, output)
		}
	}
}

func TestClassifyOutputDistinguishesDockerfileStepFromRuntimeSetup(t *testing.T) {
	if got := classifyOutput(&commandError{output: `Error: error building at STEP "RUN go build": error while running runtime: exit status 1`}); got != "build_step" {
		t.Fatalf("Dockerfile command failure classified as %q", got)
	}
	if got := classifyOutput(&commandError{output: "error creating container: exit status 126"}); got != "runtime" {
		t.Fatalf("container runtime failure classified as %q", got)
	}
}

func TestPodmanBaseFallsBackToSingleMappingVFS(t *testing.T) {
	root := t.TempDir()
	config := Config{FuseOverlayFS: filepath.Join(root, "missing-fuse-overlayfs")}
	arguments := strings.Join(podmanBase(config, root), " ")
	if !strings.Contains(arguments, "--storage-driver vfs") || !strings.Contains(arguments, "vfs.ignore_chown_errors=true") {
		t.Fatalf("VFS fallback is incomplete: %s", arguments)
	}
	if strings.Contains(arguments, "overlay.mount_program") {
		t.Fatalf("VFS fallback retained overlay configuration: %s", arguments)
	}
}

func TestCopyAtomicRefusesOverwriteAndLeavesNoPartial(t *testing.T) {
	root := t.TempDir()
	source, target := filepath.Join(root, "source"), filepath.Join(root, "target")
	if err := os.WriteFile(source, []byte("artifact"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := copyAtomic(source, target); err != nil {
		t.Fatal(err)
	}
	if err := copyAtomic(source, target); err == nil {
		t.Fatal("overwrite was accepted")
	}
	if _, err := os.Stat(target + ".partial"); !os.IsNotExist(err) {
		t.Fatalf("partial result retained: %v", err)
	}
}

func TestCleanupJobRemovesOnlyExactOwnedJobRoots(t *testing.T) {
	parent := t.TempDir()
	podman := filepath.Join(parent, "podman")
	fuse := filepath.Join(parent, "fuse-overlayfs")
	for _, executable := range []string{podman, fuse} {
		if err := os.WriteFile(executable, []byte("#!/bin/sh\nexit 0\n"), 0o700); err != nil {
			t.Fatal(err)
		}
	}
	target := filepath.Join(parent, "oci-build-lsf-12345-abcdef")
	other := filepath.Join(parent, "oci-build-lsf-123456-abcdef")
	if err := os.Mkdir(target, 0o700); err != nil {
		t.Fatal(err)
	}
	locked := filepath.Join(target, "locked")
	if err := os.Mkdir(locked, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(locked, "state"), []byte("x"), 0o000); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(locked, 0o000); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(other, 0o700); err != nil {
		t.Fatal(err)
	}
	removed, err := CleanupJob(context.Background(), Config{TempParent: parent, Podman: podman, FuseOverlayFS: fuse}, "12345")
	if err != nil || removed != 1 {
		t.Fatalf("cleanup result: removed=%d err=%v", removed, err)
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Fatalf("exact target remains: %v", err)
	}
	if _, err := os.Stat(other); err != nil {
		t.Fatalf("non-target was removed: %v", err)
	}
}

func TestRunCleansLocalWorkspaceAfterBuildFailure(t *testing.T) {
	root := t.TempDir()
	jobDir := filepath.Join(root, "job")
	outputDir := filepath.Join(jobDir, "output")
	if err := os.Mkdir(jobDir, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(outputDir, 0o700); err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(jobDir, "source.tar.zst")
	if err := sourcebundle.WriteScratchFixture(archive); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(archive)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(data)
	if err := os.WriteFile(filepath.Join(jobDir, "source.sha256"), []byte("sha256:"+hex.EncodeToString(digest[:])+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	logPath := filepath.Join(root, "podman.log")
	podman := filepath.Join(root, "podman")
	script := "#!/bin/sh\nprintf '%s\\n' \"$*\" >>'" + logPath + "'\ncase \" $* \" in *' build '*) echo 'controlled build diagnostic' >&2; exit 1;; esac\nexit 0\n"
	if err := os.WriteFile(podman, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	fuse := filepath.Join(root, "fuse-overlayfs")
	self := filepath.Join(root, "worker")
	for _, executable := range []string{fuse, self} {
		if err := os.WriteFile(executable, []byte("#!/bin/sh\nexit 0\n"), 0o700); err != nil {
			t.Fatal(err)
		}
	}
	_, err = Run(context.Background(), Config{JobDir: jobDir, Podman: podman, FuseOverlayFS: fuse, Self: self, JobID: "12345", Profile: "oci-build-v1", BuildContext: ".", Dockerfile: "Containerfile", BuildNetwork: "none", TempParent: root})
	var stageErr *StageError
	if !errors.As(err, &stageErr) || stageErr.Stage != "build" {
		t.Fatalf("unexpected run result: %v", err)
	}
	matches, globErr := filepath.Glob(filepath.Join(root, "oci-build-lsf-12345-*"))
	if globErr != nil || len(matches) != 0 {
		t.Fatalf("failed build retained local roots: matches=%v err=%v", matches, globErr)
	}
	failure, readErr := os.ReadFile(filepath.Join(outputDir, "failure.json"))
	if readErr != nil || !strings.Contains(string(failure), `"category":"build_command"`) {
		t.Fatalf("failure evidence missing: %q err=%v", failure, readErr)
	}
	diagnostic, readErr := os.ReadFile(filepath.Join(outputDir, "build.log"))
	if readErr != nil || !strings.Contains(string(diagnostic), "build") {
		t.Fatalf("owner-only failure diagnostic missing: %q err=%v", diagnostic, readErr)
	}
	if info, statErr := os.Stat(filepath.Join(outputDir, "build.log")); statErr != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("failure diagnostic permissions are unsafe: info=%v err=%v", info, statErr)
	}
	commands, readErr := os.ReadFile(logPath)
	if readErr != nil || !strings.Contains(string(commands), "system migrate") || !strings.Contains(string(commands), "system reset --force") {
		t.Fatalf("isolated Podman namespace/storage teardown was not attempted: %q err=%v", commands, readErr)
	}
}

func TestValidateConfigAcceptsSLAIBuildInputsAndRejectsEscapes(t *testing.T) {
	root := t.TempDir()
	executable := filepath.Join(root, "executable")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	valid := Config{JobDir: root, Podman: executable, FuseOverlayFS: executable, Self: executable,
		JobID: "123", Profile: "slai-web-app-v1", BuildContext: "web", Dockerfile: "web/Dockerfile",
		BuildNetwork: "host", ProbePort: 8080, ProbePath: "/healthz", TempParent: root}
	if err := validateConfig(valid); err != nil {
		t.Fatalf("SLAI build inputs rejected: %v", err)
	}
	for name, mutate := range map[string]func(*Config){
		"context traversal":          func(c *Config) { c.BuildContext = "../web" },
		"dockerfile outside context": func(c *Config) { c.Dockerfile = "Dockerfile" },
		"unknown network":            func(c *Config) { c.BuildNetwork = "bridge" },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := valid
			mutate(&candidate)
			if err := validateConfig(candidate); err == nil {
				t.Fatal("invalid build input accepted")
			}
		})
	}
}

func writeContainerfile(t *testing.T, content string) string {
	t.Helper()
	filename := filepath.Join(t.TempDir(), "Containerfile")
	if err := os.WriteFile(filename, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return filename
}

func TestFirstExecutableUsesSupportedPrecedence(t *testing.T) {
	root := t.TempDir()
	unavailable := filepath.Join(root, "unavailable")
	first := filepath.Join(root, "first")
	second := filepath.Join(root, "second")
	if err := os.WriteFile(first, []byte("#!/bin/sh\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(second, []byte("#!/bin/sh\n"), 0700); err != nil {
		t.Fatal(err)
	}
	if got := firstExecutable([]string{unavailable, root, first, second}); got != second {
		t.Fatalf("non-executable candidate selected: %s", got)
	}
	if err := os.Chmod(first, 0700); err != nil {
		t.Fatal(err)
	}
	if got := firstExecutable([]string{first, second}); got != first {
		t.Fatalf("precedence changed: %s", got)
	}
}

func TestCustomPodmanRetainsHelperConfiguration(t *testing.T) {
	args := strings.Join(podmanBase(Config{Podman: "/custom/podman"}, t.TempDir()), " ")
	for _, flag := range []string{"--conmon", "--runtime", "--network-cmd-path"} {
		if strings.Contains(args, flag) {
			t.Fatalf("custom runtime configuration overwritten: %s", args)
		}
	}
}
