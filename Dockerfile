FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY aippt/ aippt/
COPY aippt.py .
COPY pyproject.toml .
COPY dirs.yaml .

# Build Sphinx docs (if docs/ exists)
COPY docs/ docs/
RUN if [ -f docs/Makefile ]; then \
      apt-get update && apt-get install -y --no-install-recommends make && \
      rm -rf /var/lib/apt/lists/* && \
      pip install --no-cache-dir sphinx sphinx-rtd-theme && \
      make -C docs html; \
    fi

# Create non-root user and data directories
RUN useradd -m appuser && \
    mkdir -p uploads images backups && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["python", "aippt.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
