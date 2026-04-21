#!/usr/bin/env bash
set -euo pipefail

REGISTRY="${REGISTRY:-localhost:5000}"
IMAGE_NAME="${IMAGE_NAME:-aippt}"
TAG="${TAG:-latest}"

FULL_TAG="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo "Building ${FULL_TAG} ..."
docker build -t "${FULL_TAG}" .

echo "Pushing ${FULL_TAG} ..."
docker push "${FULL_TAG}"

echo "Done: ${FULL_TAG}"
