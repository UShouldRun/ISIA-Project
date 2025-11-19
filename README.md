# Multi-Agent Planetary Exploration and Resource Mapping System

## Objective

This project simulates a decentralized planetary exploration system using **SPADE**.  
Autonomous rovers and drones are deployed on a distant planet or moon to collaboratively explore terrain, map resources, and adapt to hazards in real-time—without centralized mission control.

The system focuses on:

- Autonomous navigation and resource detection (e.g., minerals, water ice).
- Peer-to-peer coordination to maximize coverage and reduce redundant exploration.
- Dynamic adaptation to hazards such as dust storms, obstacles, or equipment malfunctions.

---

## Requirements

- Python 3.12+
- Docker (for containerized setup)
- SPADE library
- Other dependencies listed in `requirements.txt` (or installed in the Docker container)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/UShouldRun/ISIA-Project.git
cd ISIA-Project
cp .env.example .env
````

Change the `.env` file if you want to.

### 2. Build the Docker container

```bash
./run.sh build
```

This will:

* Build the Docker image with all dependencies.
* Start the container with the environment ready for simulation.

### 3. Start the simulation

```bash
./run.sh up
```

* This starts the container and launches the visualization server.
* You can access the visualization at: `http://localhost:<CLIENT_PORT>/index.html` (configured in `.env`).

### 4. Stop and clean up

```bash
./run.sh down    # Stop the container
./run.sh remove  # Remove the container
```

---

## Configuration

Simulation settings are controlled via a JSON configuration file (passed as an argument to `main.py`):

```json
{
  "simulation": {
    "duration_seconds": 600,
    "tag": "mars"
  },
  "world": {
    "map_limit": [100, 100]
  },
  "bases": [
    {
      "jid": "base1",
      "name": "AlphaBase",
      "center": [50, 50],
      "radius": 50
    }
  ],
  "rovers": [
    {
      "jid": "rover1",
      "base": "AlphaBase",
      "position": "random_in_base",
      "assigned_drone": "drone1"
    }
  ],
  "drones": [
    {
      "jid": "drone1",
      "position": [10, 10],
      "known_bases": ["base1"]
    }
  ]
}
```

* You can configure multiple rovers, drones, and bases.
* Positions can be fixed coordinates or `"random_in_base"`.

---

## Generating Documentation

You can generate HTML docs using `pdoc` inside the Docker container:

```bash
./run.sh docs
```

* This will create the `docs/` folder locally containing the HTML documentation.
* You can view it in your browser:

```bash
./run.sh docs-open
```

---

## Running the Simulation Locally

If not using Docker:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=$(pwd)/src python src/main.py configs/config.json
```

---

## Features

* **Decentralized control**: Each agent makes independent decisions while communicating with peers.
* **Dynamic hazards**: Dust storms and obstacles affect exploration in real-time.
* **Resource mapping**: Agents detect and report resource locations.
* **Visualization**: Live web-based map showing agent positions and explored areas.

---

## License

MIT License

---

## Acknowledgements

This project uses:

* [SPADE](https://spade-mas.readthedocs.io/) for multi-agent system implementation.
* Python 3.12 for modern type hints and async support.
