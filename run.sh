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
    sleep 2  # wait for container to start

    echo "Starting SPADE server..."
    docker_cmd exec -d "$CONTAINER_NAME" spade run
    sleep 1  # wait for SPADE to initialize
    
    echo "Starting main.py..."
    docker_cmd exec -d "$CONTAINER_NAME" python3 src/main.py
    sleep 3  # wait for server to start
    
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open http://localhost:"$CLIENT_PORT"/index.html
    elif command -v open >/dev/null 2>&1; then
      open http://localhost:"${CLIENT_PORT}"/index.html
    fi
    echo -e "\033[32mRunning on http://localhost:"${CLIENT_PORT}"/index.html\033[0m"
    ;;
  up)
    echo "Starting container..."
    docker_cmd compose up -d
    sleep 2  # wait for container to start
    
    echo "Starting SPADE server..."
    docker_cmd exec -d "$CONTAINER_NAME" spade run
    sleep 1  # wait for SPADE to initialize
    
    echo "Starting main.py..."
    docker_cmd exec -d "$CONTAINER_NAME" python3 src/main.py
    sleep 3  # wait for server to start
    
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open http://localhost:"$CLIENT_PORT"/index.html
    elif command -v open >/dev/null 2>&1; then
      open http://localhost:"${CLIENT_PORT}"/index.html
    fi
    echo -e "\033[32mRunning on http://localhost:"${CLIENT_PORT}"/index.html\033[0m"
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
  kill)
    echo "Killing processes in container..."
    docker_cmd exec "$CONTAINER_NAME" pkill -f "spade run"
    docker_cmd exec "$CONTAINER_NAME" pkill -f "python3 src/main.py"
    echo -e "\033[32mProcesses killed\033[0m"
    ;;
  virtualenv)
    echo "Starting virtual environment..."
    virtualenv space_venv --python=python3.12
    source space_venv/bin/activate
    ;;
  docs)
    echo "Generating HTML docs inside the container..."
    docker_cmd exec -w /app -it "$CONTAINER_NAME" bash -c "cd src && PYTHONPATH=/app/src pdoc server.py agents world settings -o /app/docs"
    echo "Copying docs to local directory..."
    docker_cmd cp "$CONTAINER_NAME":/app/docs/. ./docs
    echo -e "\033[32mDocs copied to ./docs\033[0m"
    ;;
  docs-open)
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open ./docs/index.html
    elif command -v open >/dev/null 2>&1; then
      open ./docs/index.html
    else
      echo "Open ./docs/index.html manually in your browser."
    fi
    ;;
  logs)
      echo "Showing logs for all containers..."
      docker ps -a --format "table {{.Names}}\t{{.Status}}"  

      shift  # Remove the first argument ("logs") so $@ only contains container names

      if [ $# -eq 0 ]; then
          echo "No container names provided. Please specify at least one container."
          exit 1
      fi

      for container in "$@"; do
          echo -e "\n--- Logs for container: $container ---"
          docker logs -f "$container"
      done
      ;;
  *)
    echo "Usage: $0 {build|up|down|sh|kill|virtualenv|docs|docs-open|logs}"
    exit 1
    ;;
esac
