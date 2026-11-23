package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/AMD-SLAI/image-build-lsf/internal/lsfbuild"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	fuseOverlayFS := os.Getenv("OCI_LSF_FUSE_OVERLAYFS")
	if fuseOverlayFS == "" {
		fuseOverlayFS = "/bin/fuse-overlayfs"
	}
	if len(os.Args) > 1 && os.Args[1] == "probe-helper" {
		flags := flag.NewFlagSet("probe-helper", flag.ContinueOnError)
		var port int
		var path string
		flags.IntVar(&port, "port", 0, "fixed loopback port")
		flags.StringVar(&path, "path", "", "fixed health path")
		if err := flags.Parse(os.Args[2:]); err != nil || flags.NArg() != 0 {
			return errors.New("invalid probe-helper arguments")
		}
		return lsfbuild.Probe(port, path)
	}
	if len(os.Args) > 1 && os.Args[1] == "cleanup-job" {
		flags := flag.NewFlagSet("cleanup-job", flag.ContinueOnError)
		config := lsfbuild.Config{Podman: "/tool/pandora64/bin/podman", FuseOverlayFS: fuseOverlayFS, TempParent: "/tmp"}
		var jobID string
		flags.StringVar(&jobID, "job-id", "", "exact numeric LSF job ID")
		flags.StringVar(&config.Podman, "podman", config.Podman, "absolute Podman executable")
		flags.StringVar(&config.FuseOverlayFS, "fuse-overlayfs", config.FuseOverlayFS, "absolute fuse-overlayfs executable")
		flags.StringVar(&config.TempParent, "temp-parent", config.TempParent, "host-local temporary parent")
		if err := flags.Parse(os.Args[2:]); err != nil || flags.NArg() != 0 {
			return errors.New("invalid cleanup-job arguments")
		}
		removed, err := lsfbuild.CleanupJob(context.Background(), config, jobID)
		if err != nil {
			return err
		}
		fmt.Fprintf(os.Stdout, "removed=%d\n", removed)
		return nil
	}
	flags := flag.NewFlagSet("run", flag.ContinueOnError)
	config := lsfbuild.Config{Podman: "/tool/pandora64/bin/podman", FuseOverlayFS: fuseOverlayFS, Profile: "slai-web-app-v1", BuildContext: ".", Dockerfile: "Dockerfile", BuildNetwork: "none", ProbePort: 8080, ProbePath: "/healthz", TempParent: "/tmp"}
	flags.StringVar(&config.JobDir, "job-dir", "", "owner-only NFS job directory")
	flags.StringVar(&config.Podman, "podman", config.Podman, "absolute Podman executable")
	flags.StringVar(&config.FuseOverlayFS, "fuse-overlayfs", config.FuseOverlayFS, "absolute fuse-overlayfs executable")
	flags.StringVar(&config.Self, "self", "", "absolute static worker executable")
	flags.StringVar(&config.Profile, "profile", config.Profile, "oci-build-v1 or slai-web-app-v1")
	flags.StringVar(&config.BuildContext, "build-context", config.BuildContext, "clean repository-relative build context")
	flags.StringVar(&config.Dockerfile, "dockerfile", config.Dockerfile, "Dockerfile path relative to repository root and inside build context")
	flags.StringVar(&config.BuildNetwork, "build-network", config.BuildNetwork, "none or host; host is only for reviewed dependency downloads")
	flags.IntVar(&config.ProbePort, "probe-port", config.ProbePort, "web profile loopback port")
	flags.StringVar(&config.ProbePath, "probe-path", config.ProbePath, "web profile health path")
	flags.StringVar(&config.TempParent, "temp-parent", config.TempParent, "host-local temporary parent")
	if err := flags.Parse(os.Args[1:]); err != nil || flags.NArg() != 0 {
		return errors.New("invalid LSF worker arguments")
	}
	config.JobID = os.Getenv("LSB_JOBID")
	if config.Self == "" {
		var err error
		config.Self, err = os.Executable()
		if err != nil {
			return errors.New("worker executable path is unavailable")
		}
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)
	defer stop()
	evidence, err := lsfbuild.Run(ctx, config)
	if err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(evidence)
}
