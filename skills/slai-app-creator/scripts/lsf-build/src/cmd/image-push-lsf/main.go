package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"github.com/AMD-SLAI/image-build-lsf/internal/lsfpush"
	"io"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)
	defer stop()
	if err := run(ctx, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run(ctx context.Context, args []string) error {
	if len(args) < 1 {
		return errors.New("usage: image-push-lsf prepare|run|result")
	}
	flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var job, build, image, parent string
	flags.StringVar(&job, "job-dir", "", "private push job directory")
	switch args[0] {
	case "prepare":
		flags.StringVar(&build, "build-job-dir", "", "verified build job directory")
		flags.StringVar(&image, "image", "", "fully qualified Harbor tag")
		flags.StringVar(&parent, "parent", "", "private NFS push-job parent")
	case "run":
	case "result":
	default:
		return errors.New("unknown image-push-lsf command")
	}
	if flags.Parse(args[1:]) != nil || flags.NArg() != 0 {
		return errors.New("invalid image-push-lsf arguments")
	}
	switch args[0] {
	case "prepare":
		dir, err := lsfpush.Prepare(build, image, parent, os.Stdin)
		if err != nil {
			return err
		}
		fmt.Fprintln(os.Stdout, dir)
	case "run":
		ctx, cancel := context.WithTimeout(ctx, 25*time.Minute)
		defer cancel()
		e, err := lsfpush.Run(ctx, job, os.Getenv("LSB_JOBID"), "/tmp")
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(e)
	case "result":
		e, err := lsfpush.Result(job)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(e)
	}
	return nil
}
