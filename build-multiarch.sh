#!/usr/bin/env bash
# build-multiarch.sh
# Builds and pushes a multi-architecture image to GitHub Container Registry (GHCR).
# Usage: ./build-multiarch.sh yourusername 1.1.0
#
# Prerequisites:
#   1. Create a GitHub PAT with write:packages scope at:
#      https://github.com/settings/tokens
#   2. Log in: echo YOUR_PAT | docker login ghcr.io -u yourusername --password-stdin

set -e

GITHUB_USER=${1:-"yourusername"}
TAG=${2:-"latest"}
IMAGE="ghcr.io/${GITHUB_USER}/utility-choice-tracker"

echo "Building multi-arch image: ${IMAGE}:${TAG}"
echo "Platforms:"
echo "  linux/amd64    — x86_64 servers and desktops"
echo "  linux/arm64    — Raspberry Pi 4, Pi 5, Pi 400, CM4, Zero 2 W (64-bit OS), Apple Silicon"
echo ""

# Ensure buildx builder with multi-arch support exists
if ! docker buildx inspect multiarch-builder &>/dev/null; then
  echo "Creating buildx builder..."
  docker buildx create --name multiarch-builder --use
  docker buildx inspect --bootstrap
else
  docker buildx use multiarch-builder
fi

# Build and push all platforms
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag "${IMAGE}:${TAG}" \
  --tag "${IMAGE}:latest" \
  --push \
  .

echo ""
echo "✅ Done! Image pushed to GHCR:"
echo "   ${IMAGE}:${TAG}"
echo "   ${IMAGE}:latest"
echo ""
echo "Pull it with:"
echo "  docker pull ${IMAGE}:latest"
echo ""
echo "Or use in docker-compose.yml:"
echo "  image: ${IMAGE}:latest"
