// Package lsfpush copies verified OCI blobs to Harbor without extracting image layers.
package lsfpush

import (
	"archive/tar"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"

	"github.com/AMD-SLAI/image-build-lsf/internal/ociarchive"
	"github.com/google/go-containerregistry/pkg/authn"
	"github.com/google/go-containerregistry/pkg/name"
	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/layout"
	"github.com/google/go-containerregistry/pkg/v1/remote"
)

var imagePattern = regexp.MustCompile(`^([a-zA-Z0-9][a-zA-Z0-9.-]*(?::[0-9]{1,5})?)/([a-z0-9][a-z0-9._-]*)/([a-z0-9][a-z0-9._-]*):(slai-sc-[0-9a-f]{40}-[1-9][0-9]*-[1-9][0-9]*)$`)
var digestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
var blobPattern = regexp.MustCompile(`^blobs/sha256/[0-9a-f]{64}$`)
var jobPattern = regexp.MustCompile(`^[0-9]{1,20}$`)

// Credentials are accepted through stdin at prepare time, never as flags or environment.
type Credentials struct {
	Location string `json:"location"`
	Username string `json:"username"`
	Password string `json:"password"`
}
type Request struct {
	BuildJobDir    string    `json:"build_job_dir"`
	Image          string    `json:"image"`
	ArtifactDigest string    `json:"artifact_digest"`
	ManifestDigest string    `json:"manifest_digest"`
	ArtifactBytes  int64     `json:"artifact_bytes"`
	CreatedAt      time.Time `json:"created_at"`
}
type Evidence struct {
	SchemaVersion  int    `json:"schema_version"`
	JobID          string `json:"lsf_job_id"`
	FullImage      string `json:"full_image"`
	ImageDigest    string `json:"image_digest"`
	ArtifactDigest string `json:"artifact_digest"`
}

func Destination(image string) (name.Tag, string, error) {
	m := imagePattern.FindStringSubmatch(image)
	if m == nil {
		return name.Tag{}, "", errors.New("expected fully qualified Harbor project/image:slai-sc-<sha>-<run>-<attempt>")
	}
	tag, err := name.NewTag(image, name.StrictValidation)
	if err != nil {
		return name.Tag{}, "", errors.New("invalid Harbor image")
	}
	return tag, m[1] + "/" + m[2], nil
}

// PrivatePath rejects links, foreign ownership, and non-private final paths.
func PrivatePath(path string, directory bool) error {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return errors.New("private path must be absolute and canonical")
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil || resolved != path {
		return errors.New("private path is unavailable or contains symlinks")
	}
	st, err := os.Lstat(path)
	if err != nil {
		return errors.New("private path is unavailable")
	}
	owner, ok := st.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != uint32(os.Geteuid()) || st.Mode().Perm()&0077 != 0 || (directory && !st.IsDir()) || (!directory && !st.Mode().IsRegular()) {
		return errors.New("path must be a private owner-controlled regular file or directory")
	}
	return nil
}

func readJSON(path string, value any) error {
	if err := PrivatePath(path, false); err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return errors.New("private input unavailable")
	}
	defer f.Close()
	decoder := json.NewDecoder(io.LimitReader(f, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return errors.New("private JSON input invalid")
	}
	if decoder.Decode(new(any)) != io.EOF {
		return errors.New("private JSON has trailing data")
	}
	return nil
}
func writeJSON(path string, value any) error {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return errors.New("private output already exists or cannot be created")
	}
	err = json.NewEncoder(f).Encode(value)
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		return errors.New("private output write failed")
	}
	return nil
}

func ReadBuild(job string) (Request, error) {
	for _, p := range []string{job, filepath.Join(job, "output")} {
		if err := PrivatePath(p, true); err != nil {
			return Request{}, err
		}
	}
	// Build evidence contains additional fields, so decode it with an explicit size bound.
	path := filepath.Join(job, "output", "success.json")
	if err := PrivatePath(path, false); err != nil {
		return Request{}, err
	}
	data, err := os.ReadFile(path)
	if err != nil || len(data) > 64<<10 {
		return Request{}, errors.New("build evidence unavailable")
	}
	var e struct {
		Schema         int    `json:"schema_version"`
		JobID          string `json:"lsf_job_id"`
		Profile        string `json:"profile"`
		Platform       string `json:"platform"`
		Probe          int    `json:"probe_status"`
		ArtifactDigest string `json:"artifact_digest"`
		ManifestDigest string `json:"manifest_digest"`
		ArtifactBytes  int64  `json:"artifact_bytes"`
	}
	if json.Unmarshal(data, &e) != nil || e.Schema != 1 || !jobPattern.MatchString(e.JobID) || e.Profile != "slai-web-app-v1" || e.Platform != "linux/amd64" || e.Probe != 200 || !digestPattern.MatchString(e.ArtifactDigest) || !digestPattern.MatchString(e.ManifestDigest) || e.ArtifactBytes < 1 || e.ArtifactBytes > 20<<30 {
		return Request{}, errors.New("build evidence does not satisfy the verified SLAI web-app contract")
	}
	archive := filepath.Join(job, "output", "result.oci.tar")
	if err := PrivatePath(archive, false); err != nil {
		return Request{}, err
	}
	st, err := os.Stat(archive)
	if err != nil || st.Size() != e.ArtifactBytes {
		return Request{}, errors.New("archive length mismatch")
	}
	verified, err := ociarchive.Verify(archive)
	if err != nil || verified.TransportDigest != e.ArtifactDigest || verified.ManifestDigest != e.ManifestDigest {
		return Request{}, errors.New("archive verification failed")
	}
	return Request{BuildJobDir: job, ArtifactDigest: e.ArtifactDigest, ManifestDigest: e.ManifestDigest, ArtifactBytes: e.ArtifactBytes, CreatedAt: time.Now().UTC()}, nil
}

func Prepare(buildJob, image, parent string, input io.Reader) (string, error) {
	_, location, err := Destination(image)
	if err != nil {
		return "", err
	}
	request, err := ReadBuild(buildJob)
	if err != nil {
		return "", err
	}
	request.Image = image
	var creds Credentials
	decoder := json.NewDecoder(io.LimitReader(input, 64<<10))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&creds) != nil || decoder.Decode(new(any)) != io.EOF || creds.Location != location || !strings.HasPrefix(creds.Username, "robot$") || creds.Password == "" || strings.ContainsAny(creds.Username+creds.Password, "\r\n\x00") {
		return "", errors.New("expected developer robot credentials bound to the selected Harbor registry/project")
	}
	if err := PrivatePath(parent, true); err != nil {
		return "", err
	}
	dir, err := os.MkdirTemp(parent, "push.")
	if err != nil {
		return "", errors.New("cannot create private push job")
	}
	keep := false
	defer func() {
		if !keep {
			_ = os.RemoveAll(dir)
		}
	}()
	if err := os.Mkdir(filepath.Join(dir, "output"), 0700); err != nil {
		return "", err
	}
	if err := writeJSON(filepath.Join(dir, "request.json"), request); err != nil {
		return "", err
	}
	if err := writeJSON(filepath.Join(dir, "credentials.json"), creds); err != nil {
		return "", err
	}
	keep = true
	return dir, nil
}

// hostTransport restricts registry and token requests to HTTPS at the selected Harbor.
// It also prevents the registry client from silently falling back to cleartext HTTP.
type hostTransport struct {
	base http.RoundTripper
	host string
}

func (t hostTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	if r.URL.Scheme != "https" || r.URL.Host != t.host {
		return nil, errors.New("registry request must stay on selected HTTPS Harbor host")
	}
	return t.base.RoundTrip(r)
}

// materialize writes OCI metadata/blob files as the caller. It never extracts a layer.
func materialize(archive, dir string) error {
	f, err := os.Open(archive)
	if err != nil {
		return errors.New("archive unavailable")
	}
	defer f.Close()
	tr := tar.NewReader(f)
	for {
		h, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return errors.New("invalid OCI tar")
		}
		if h.Typeflag == tar.TypeDir {
			continue
		}
		if h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeRegA {
			return errors.New("unsupported OCI entry type")
		}
		if h.Name != "index.json" && h.Name != "oci-layout" && !blobPattern.MatchString(h.Name) {
			return errors.New("unexpected OCI entry")
		}
		target := filepath.Join(dir, h.Name)
		if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			return errors.New("duplicate or invalid OCI entry")
		}
		n, copyErr := io.Copy(out, tr)
		closeErr := out.Close()
		if copyErr != nil || closeErr != nil || n != h.Size {
			return errors.New("OCI blob copy failed")
		}
	}
}

// Upload uses exact manifest/blob bytes and then reads the destination tag back.
func Upload(ctx context.Context, dir, image, expected string, creds Credentials, transport http.RoundTripper) error {
	tag, location, err := Destination(image)
	if err != nil || creds.Location != location {
		return errors.New("credential destination mismatch")
	}
	hash, err := v1.NewHash(expected)
	if err != nil {
		return errors.New("invalid expected manifest digest")
	}
	img, err := layout.Path(dir).Image(hash)
	if err != nil {
		return errors.New("OCI layout image unavailable")
	}
	raw, err := img.RawManifest()
	sum := sha256.Sum256(raw)
	if err != nil || "sha256:"+hex.EncodeToString(sum[:]) != expected {
		return errors.New("source manifest mismatch")
	}
	options := []remote.Option{remote.WithContext(ctx), remote.WithAuth(&authn.Basic{Username: creds.Username, Password: creds.Password}), remote.WithTransport(transport), remote.WithJobs(1)}
	if err := remote.Write(tag, img, options...); err != nil {
		return errors.New("Harbor upload failed; details withheld")
	}
	observed, err := remote.Get(tag, options...)
	if err != nil {
		return errors.New("Harbor manifest read-back failed; details withheld")
	}
	sum = sha256.Sum256(observed.Manifest)
	if "sha256:"+hex.EncodeToString(sum[:]) != expected || observed.Digest.String() != expected {
		return errors.New("Harbor manifest digest differs from verified archive")
	}
	return nil
}

func Run(ctx context.Context, job, jobID, tempParent string) (e Evidence, retErr error) {
	if !jobPattern.MatchString(jobID) {
		return e, errors.New("LSF push requires numeric LSB_JOBID")
	}
	if err := PrivatePath(job, true); err != nil {
		return e, err
	}
	if err := PrivatePath(filepath.Join(job, "output"), true); err != nil {
		return e, err
	}
	// Once a worker starts, its staged credential is consumed even on failure.
	defer func() {
		_ = os.Remove(filepath.Join(job, "credentials.json"))
		if retErr != nil {
			_ = writeJSON(filepath.Join(job, "output", "failure.json"), map[string]string{"stage": "push", "category": "publication_failed"})
		}
		for _, n := range []string{"lsf.stdout", "lsf.stderr"} {
			p := filepath.Join(job, "output", n)
			if PrivatePath(p, false) == nil {
				_ = os.Chmod(p, 0600)
			}
		}
	}()
	var request Request
	if err := readJSON(filepath.Join(job, "request.json"), &request); err != nil {
		return e, err
	}
	age := time.Since(request.CreatedAt)
	if age < 0 || age > 2*time.Hour {
		return e, errors.New("push request expired; submit with fresh credentials")
	}
	_, location, err := Destination(request.Image)
	if err != nil {
		return e, err
	}
	var creds Credentials
	if err := readJSON(filepath.Join(job, "credentials.json"), &creds); err != nil {
		return e, err
	}
	if creds.Location != location || !strings.HasPrefix(creds.Username, "robot$") || creds.Password == "" {
		return e, errors.New("invalid developer robot credentials")
	}
	if err := os.Remove(filepath.Join(job, "credentials.json")); err != nil {
		return e, errors.New("cannot consume staged credentials")
	}
	root, err := os.MkdirTemp(tempParent, "oci-push-lsf-"+jobID+"-")
	if err != nil {
		return e, errors.New("local push workspace unavailable")
	}
	defer os.RemoveAll(root)
	// Copy the archive first, then verify this exact local copy before using credentials.
	source := filepath.Join(request.BuildJobDir, "output", "result.oci.tar")
	if err := PrivatePath(source, false); err != nil {
		return e, err
	}
	in, err := os.Open(source)
	if err != nil {
		return e, errors.New("archive unavailable")
	}
	defer in.Close()
	local := filepath.Join(root, "result.oci.tar")
	out, err := os.OpenFile(local, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return e, err
	}
	n, copyErr := io.Copy(out, io.LimitReader(in, request.ArtifactBytes+1))
	closeErr := out.Close()
	if copyErr != nil || closeErr != nil || n != request.ArtifactBytes {
		return e, errors.New("archive copy length mismatch")
	}
	verified, err := ociarchive.Verify(local)
	if err != nil || verified.TransportDigest != request.ArtifactDigest || verified.ManifestDigest != request.ManifestDigest || verified.OS+"/"+verified.Architecture != "linux/amd64" {
		return e, errors.New("local archive verification failed")
	}
	dir := filepath.Join(root, "layout")
	if err := os.Mkdir(dir, 0700); err != nil {
		return e, err
	}
	if err := materialize(local, dir); err != nil {
		return e, err
	}
	tag, _, _ := Destination(request.Image)
	transport := hostTransport{base: remote.DefaultTransport, host: tag.RegistryStr()}
	if err := Upload(ctx, dir, request.Image, request.ManifestDigest, creds, transport); err != nil {
		return e, err
	}
	e = Evidence{SchemaVersion: 1, JobID: jobID, FullImage: request.Image, ImageDigest: request.ManifestDigest, ArtifactDigest: request.ArtifactDigest}
	if err := writeJSON(filepath.Join(job, "output", "success.json"), e); err != nil {
		return e, err
	}
	return e, nil
}

func Result(job string) (Evidence, error) {
	var e Evidence
	var request Request
	if err := PrivatePath(job, true); err != nil {
		return e, err
	}
	if err := PrivatePath(filepath.Join(job, "output"), true); err != nil {
		return e, err
	}
	if err := readJSON(filepath.Join(job, "request.json"), &request); err != nil {
		return e, err
	}
	if err := readJSON(filepath.Join(job, "output", "success.json"), &e); err != nil {
		return e, errors.New("push success evidence unavailable; inspect output/failure.json or wait for LSF")
	}
	if e.SchemaVersion != 1 || !jobPattern.MatchString(e.JobID) || e.FullImage != request.Image || !digestPattern.MatchString(e.ImageDigest) || e.ImageDigest != request.ManifestDigest || e.ArtifactDigest != request.ArtifactDigest {
		return e, errors.New("push evidence mismatch")
	}
	if _, _, err := Destination(e.FullImage); err != nil {
		return e, err
	}
	return e, nil
}
