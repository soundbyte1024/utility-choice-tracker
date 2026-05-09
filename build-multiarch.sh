#!/usr/bin/env bash
# build-multiarch.sh
# Builds and pushes a multi-architecture image to Docker Hub.
# Usage: ./build-multiarch.sh yourname/utility-choice-tracker 1.1.0

set -e

IMAGE=${1:-"yourname/utility-choice-tracker"}
TAG=${2:-"latest"}

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
echo "✅ Done! Image pushed:"
echo "   ${IMAGE}:${TAG}"
echo "   ${IMAGE}:latest"
echo ""
echo "Covers x86 servers and Raspberry Pi 4/5. Docker pulls the right"
echo "architecture automatically based on the host machine."
echo ""
echo "Run it with:"
echo "  docker run -d --name utility-choice-tracker --restart unless-stopped \\"
echo "    -p 8000:8000 \\"
echo "    -v /opt/utility-tracker/data:/data \\"
echo "    -v /opt/utility-tracker/uploads:/uploads \\"
echo "    -e TZ=America/New_York \\"
echo "    ${IMAGE}:latest"
