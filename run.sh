#!/bin/bash

docker_cmd() {
  if docker ps >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

if [ -f .env ]; then
    source .env
else
    echo "Warning: .env file not found."
fi

case "$1" in
  build)
    echo "Building Docker image..."
    docker_cmd build \
      -t "$IMAGE_NAME" .
    docker_cmd compose up -d
    ;;
  up)
    echo "Starting container..."
    docker_cmd compose up -d
    ;;
  down)
    echo "Stopping container..."
    docker_cmd stop "$CONTAINER_NAME"
    ;;
  remove)
    echo "Removing the container..."
    docker_cmd rm "$CONTAINER_NAME"
    ;;
  sh)
    echo "Entering container shell..."
    docker_cmd exec -it "$CONTAINER_NAME" bash
    ;;
  virtualenv)
    echo "Starting virtual environment..."
    virtualenv space_venv --python=python3.12
    source space_venv/bin/activate
    ;;
  *)
    echo "Usage: $0 {build|up|down}"
    exit 1
    ;;
esac
