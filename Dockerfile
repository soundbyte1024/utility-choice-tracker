FROM python:3.12-slim

# Supported platforms:
#   linux/amd64       — x86_64 servers and desktops
#   linux/arm64       — Raspberry Pi 4, Pi 5, Pi 400, CM4, Zero 2 W (64-bit OS), Apple Silicon
#
# Note: Raspberry Pi 1, 2, 3, Pi Zero, and Pi Zero W are not supported.
#       Pi 3 users can run a 64-bit OS to use the arm64 image.
#
# Single-arch local build:  docker compose up -d
# Multi-arch push to hub:   ./build-multiarch.sh yourname/utility-choice-tracker 1.1.0

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
# --prefer-binary: use pre-built wheels instead of compiling from source (critical for arm/v6 cross-compilation)
# --timeout 120:   QEMU emulation of armv6 is slow; longer timeout prevents false failures
RUN pip install --no-cache-dir --prefer-binary --timeout 120 -r requirements.txt

COPY backend/ .

# Copy frontend into static directory served by FastAPI
RUN mkdir -p /app/static
COPY frontend/index.html /app/static/index.html

RUN chmod +x /app/entrypoint.sh

VOLUME ["/data", "/uploads"]

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
