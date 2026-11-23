package main

import (
	"reflect"
	"testing"
)

func TestSelectBuildContextFilesExcludesDeploymentAndCredentials(t *testing.T) {
	files := []string{
		"Dockerfile",
		"app/main.go",
		"deploy/secrets.enc.yaml",
		".github/workflows/build.yml",
		".env",
		"app/.npmrc",
	}
	want := []string{"Dockerfile", "app/main.go"}
	got, err := selectBuildContextFiles(files, ".")
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("selectBuildContextFiles() = %#v, want %#v", got, want)
	}
}
