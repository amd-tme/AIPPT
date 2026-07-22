# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────────────────────
# Stage: docs — build the Sphinx HTML site.
# docs/_build/ is gitignored, so the built artifact does not exist on a clean
# checkout/CI. Build it here instead of COPYing a local artifact; the runtime
# image then serves it at /docs (app.py mounts docs/_build/html when present).
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS docs

# Same AMD CA handling as the runtime stage: pip verifies against its own certifi
# bundle, so build a combined bundle (public roots + AMD root) and point pip at it.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/ca/amd-root-ca.pem /usr/local/share/ca-certificates-extra/amd-root-ca.pem
RUN cat /etc/ssl/certs/ca-certificates.crt \
        /usr/local/share/ca-certificates-extra/amd-root-ca.pem \
        > /etc/ssl/certs/ca-bundle-with-amd.pem

WORKDIR /build
COPY docs/requirements.txt docs/requirements.txt
RUN PIP_CERT=/etc/ssl/certs/ca-bundle-with-amd.pem \
        pip install --no-cache-dir -r docs/requirements.txt
COPY docs/ docs/
# docs/conf.py does `from aippt import __version__` (after adding the repo root
# to sys.path), so the package must be importable here. __init__.py is trivial
# and there are no autodoc directives, so the source tree alone suffices — no
# runtime deps needed in this stage.
COPY aippt/ aippt/
RUN sphinx-build -b html docs docs/_build/html


# ─────────────────────────────────────────────────────────────────────────────
# Stage: runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies:
#  - poppler-utils (pdftoppm): used by the SharePoint/Graph render pipeline
#    (PPTX -> Graph -> PDF -> pdftoppm -> PNG; see aippt/render.py) for Linux
#    image export. The live preview pipeline no longer needs it — PptxViewJS
#    renders the generated .pptx in the browser (see aippt/preview.py), so
#    LibreOffice/soffice and its metric-compatible font substitutes have been
#    dropped from the image.
#  - ca-certificates: base trust store extended with the AMD root below.
# Node.js is deliberately NOT installed from apt here — see the COPY --from=node
# block below for why (bookworm's Node 18 predates the render sandbox flag).
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js 24 for the slides-as-code (.mjs/pptxgenjs) preview engine. Copied from
# the official Node image rather than Debian apt: bookworm ships Node 18, but the
# render sandbox in aippt/preview.py invokes node with the *stable* --permission
# flag, which only exists from Node 23.5+ (it was --experimental-permission on
# Node 20-22 LTS, and absent on Node 18). Node 24 is the current LTS. Both images
# are Debian bookworm, so the binary is glibc-compatible with python:3.11-slim.
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Bake the AMD Corporate PKI chain into a combined CA bundle so minio-py (and
# npm, below) can verify TLS under readOnlyRootFilesystem. The manifest points
# MINIO_CA_BUNDLE at this file. These are public CA certs, not secrets.
COPY deploy/ca/amd-root-ca.pem /usr/local/share/ca-certificates-extra/amd-root-ca.pem
RUN cat /etc/ssl/certs/ca-certificates.crt \
        /usr/local/share/ca-certificates-extra/amd-root-ca.pem \
        > /etc/ssl/certs/ca-bundle-with-amd.pem

WORKDIR /app

# Install Python dependencies. On AMD-network build hosts, egress to pypi is
# TLS-intercepted by the AMD Corporate Root CA; pip verifies against its own
# bundled certifi store (not the system trust), so point it at the combined
# bundle baked above (public roots + AMD Corporate Root + issuing CA).
COPY requirements.txt .
RUN PIP_CERT=/etc/ssl/certs/ca-bundle-with-amd.pem pip install --no-cache-dir -r requirements.txt

# Install Node dependencies for the slides-as-code preview engine. createRequire()
# in lib/*.mjs resolves these from /app/node_modules. npm verifies the registry
# TLS against its own store too, so hand it the AMD bundle via NODE_EXTRA_CA_CERTS.
# Note: `sharp` pulls a prebuilt libvips binary at install time — the build host
# needs egress to its CDN. If that is blocked, add build-essential + python3 and
# let sharp compile from source.
COPY package.json package-lock.json ./
RUN NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle-with-amd.pem npm ci --omit=dev

# Copy application code (world-readable; ownership enforced by K8s securityContext)
COPY aippt/ aippt/
COPY aippt.py .
COPY pyproject.toml .
COPY dirs.yaml .
COPY gateway.yaml gateway.yaml
COPY models.yaml models.yaml
COPY templates.yaml templates.yaml

# Slides-as-code assets read by the preview render pipeline:
#  - lib/      pptxgenjs helper modules imported by the scripts
#  - themes/   theme YAML + logo/image assets the helpers read from disk
#  - examples/ bundled demo decks, previewable via the default output/+examples/
#              allow-list
COPY lib/ lib/
COPY themes/ themes/
COPY examples/ examples/

# Built HTML docs from the docs stage; app.py mounts these at /docs so the
# in-UI "Docs" link resolves.
COPY --from=docs /build/docs/_build/html /app/docs/_build/html

# Create data directory for SQLite, uploads, and images (writable via fsGroup)
RUN mkdir -p /app/data/uploads /app/data/images /app/data/backups && \
    chmod -R 0755 /app/data

EXPOSE 8000

ENTRYPOINT ["python", "aippt.py", "serve", "--host", "0.0.0.0", "--port", "8000", "--db", "/app/data/slides.db", "--uploads-dir", "/app/data/uploads", "--images-dir", "/app/data/images", "--data-dir", "/app/data", "--preview-out-dir", "/app/data/.preview"]
