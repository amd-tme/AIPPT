# Docker build service (optional; requires GitHub App)

**Assumption in this skill:** there is **no** GitHub App for **`repository_dispatch`** to the build service, so the **Request Docker build** workflow path is **not** the default. Use **`publish-image-harbor.sh`** (workstation) and/or **Deploy prod** (§1c) to build and push to Harbor.

**What the service is:** A separate repository (shared self-hosted runners) that can **build** and **push** images to Harbor when a caller sends **`repository_dispatch`**. The upstream design uses **`actions/create-github-app-token`** with secrets **`BUILD_APP_ID`** and **`BUILD_APP_PRIVATE_KEY`** on the **app repository** to mint a token and call the GitHub API. **Without** that app and secrets, the standard **reusable** caller workflow **cannot** run.

| Path (this skill — default) | How the image is built and pushed |
|-----------------------------|------------------------------------|
| **`publish-image-harbor.sh`** | **Docker** or **Podman** on a workstation; **Harbor CLI** login writes a short-lived robot to **`~/.config/harbor/credentials`**. |
| **Deploy prod** (§1c) | **GitHub Actions** `ubuntu-latest` + **Buildx** + your **HARBOR_*** in **Actions**; then manifest PR. |

| Path (only if your org onboards a Build App) | Notes |
|----------------------------------------------|--------|
| **Request Docker build** + **[`../assets/templates/request-docker-build.yml.example`](../assets/templates/request-docker-build.yml.example)** | Requires **`BUILD_APP_ID`**, **`BUILD_APP_PRIVATE_KEY`**, and service-team approval. See the **docker-build-service** repository (**`specs/06-caller-onboarding.md`**). Do **not** scaffold this in skill-driven flows unless the user says their org has the app. |

**Same `FULL_IMAGE` after any successful push:** **`${HARBOR_REGISTRY}/${HARBOR_PROJECT}/${IMAGE_NAME}:<tag>`** (defaults **`mkmhub.amd.com` / `hw-slaiapp-dev`**). **[`../assets/templates/stamp-harbor-last-image.sh.example`](../assets/templates/stamp-harbor-last-image.sh.example)** is still useful if you have a **tag** from another system and want **`.cache/harbor-last-image.env`** without running **`publish-image-harbor.sh`**.

**Further reading (maintainers):** **docker-build-service** `README`, **`request-build-reusable.yml`**, **`schemas/dispatch-payload.schema.json`**.
