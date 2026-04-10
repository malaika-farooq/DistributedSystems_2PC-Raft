#!/bin/bash
# Run this instead of plain "docker compose up" to ensure 2PC changes take effect.
# The --no-cache flag forces Docker to recompile all proto files fresh.
echo "Stopping any running containers..."
docker compose down

echo "Rebuilding all images (no cache)..."
docker compose build --no-cache

echo "Starting all services..."
docker compose up
