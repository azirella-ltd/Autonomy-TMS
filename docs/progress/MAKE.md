# Make Targets Overview

This project uses a Docker-based workflow for local development, remote deployment, and
model training. The tables below list every `make` target defined in the root
`Makefile` along with guidance on when to use them.

## Full stack orchestration

| Target | Description |
| --- | --- |
| `make up` | Build and start the proxy, frontend, backend, database, and seeding containers in CPU mode. Exposes HTTP on `http://localhost:8088`. |
| `make up-dev` | Same as `make up`, but layers in the overrides from `docker-compose.dev.yml`. |
| `make up-remote` | Launch the stack for remote access (HTTP on `http://172.29.20.187:8088`) using the default compose file plus dev overrides. |
| `make up-tls` | Start the stack with the TLS profile enabled (self-signed cert on `https://localhost:8443`). |
| `make up-remote-tls` | Start the TLS-enabled stack for remote access on `https://172.29.20.187:8443`. |
| `make up-tls-only` | Start only the TLS proxy (no HTTP proxy on port 8088). |
| `make gpu-up` | Prune dangling images, rebuild frontend/backend, and start the GPU stack (requires NVIDIA Docker). |
| `make gpu-up-dev` | Run `make up-dev` with GPU support forced on. |
| `make cpu-up` | Run `make up` with GPU support explicitly disabled. |
| `make cpu-up-dev` | Run `make up-dev` with GPU support explicitly disabled. |

## Image rebuild helpers

| Target | Description |
| --- | --- |
| `make rebuild-frontend` | Rebuild the frontend image using the dev overrides and restart the container. |
| `make rebuild-backend` | Rebuild the backend image (respecting `FORCE_GPU`) and restart the container. |

## Lifecycle, proxy, and administration utilities

| Target | Description |
| --- | --- |
| `make down` | Stop containers, keep volumes, and prune dangling Docker images. |
| `make ps` | Show the status of the running compose services. |
| `make logs` | Follow the combined logs (tail 200 lines) for all services. |
| `make proxy-up` | Restart only the proxy container without restarting dependencies. |
| `make proxy-recreate` | Force-rebuild the proxy container to pick up configuration or image changes. |
| `make proxy-logs` | Tail just the proxy container logs. |
| `make seed` | Seed default users via the `create-users` service. |
| `make seed-default-group` | Create the default Autonomy group, ensure its supply chain/game scaffolding, and assign Autonomy AI players (runs `make all_tbg`). |
| `make all_tbg` | Seed the Default TBG, Three FG TBG, and Variable TBG groups sequentially. |
| `make seed-default-tbg` | Seed only the Default TBG group/configs (includes Case, Six-Pack, Bottle variants). |
| `make seed-three-fg-tbg` | Seed only the Three FG TBG group (assumes Default TBG already exists). |
| `make seed-variable-tbg` | Seed only the Variable TBG group (assumes Default TBG already exists). |
| `make reset-admin` | Reset the SystemAdmin password to `Autonomy@2025`. |
| `make bootstrap-system` | Initialise the database, seed defaults, rebuild training data, and retrain the Autonomy GNN. |
| `make init-env` | Run the platform-specific environment setup script to generate `.env` files. |
| `make help` | Print an annotated list of all available targets. |
| `make rebuild-db` | Drop and recreate the database container/volume for a clean DB start. |
| `make reseed-db` | Reseed Autonomy defaults (skips dataset/training) once the backend is running. |

## OpenAI connectivity helpers

| Target | Description |
| --- | --- |
| `make openai-venv` | Create (or update) the lightweight `.venv-openai` environment used by helper scripts. |
| `make openai-check` | Ensure the helper venv exists, install `scripts/requirements.txt`, and run `backend/scripts/check_openai_connection.py`. |

## Training workflows

| Target | Description |
| --- | --- |
| `make train-setup` | Create a Python virtual environment under `backend/` and install training dependencies. |
| `make train-cpu` | Run the local training script in CPU mode. |
| `make train-gpu` | Run the local training script in GPU mode. |
| `make train-gnn` | Generate a Naive-agent dataset and train the temporal GNN inside the backend container. |
| `make remote-train` | Kick off remote training via `scripts/remote_train.sh` (requires `REMOTE=user@host`). |
| `make remote-train-dataset` | Remote training variant that also uploads a dataset (requires both `REMOTE` and `DATASET`). |

## Docker Compose Files

The Make targets wrap a small collection of Compose files so you can mix and match stacks
for development, production, or targeted services. Combine files with Docker's `-f`
flag as needed (the base `docker-compose.yml` is used automatically when you run
`docker-compose up`).

| File | Purpose | Example usage |
| --- | --- | --- |
| `docker-compose.yml` | Core development stack providing the nginx proxy, React frontend, FastAPI backend, MariaDB database, phpMyAdmin, and the `create-users` seeding container. Acts as the base file for overrides. | `docker compose up` or `make up` |
| `docker-compose.dev.yml` | Development overrides that pin the frontend API URLs to relative paths, expose an optional TLS proxy via the `tls` profile, and surface runtime hooks for GPU/CPU switching through `FORCE_GPU`. | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` |
| `docker-compose.gpu.yml` | Rebuilds the backend image with `Dockerfile.gpu`, enables the NVIDIA runtime, and requests a GPU device. Layer it on top of the base file when a GPU is available. | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up` |
| `docker-compose.prod.yml` | Minimal production deployment with MariaDB, a Gunicorn-backed backend built from `Dockerfile.prod`, and nginx serving the pre-built frontend. Used by `deploy-prod.sh`. | `docker compose -f docker-compose.prod.yml up -d` |
| `docker-compose.apps.yml` | Runs only the frontend and backend while expecting the `beer-game-network` and database to be provided externally—handy when pointing at a managed DB service. | `docker compose -f docker-compose.apps.yml up` |
| `docker-compose.db.yml` | Launches a standalone MariaDB instance with tuned performance flags on host port `3307` for local development or tooling that only needs the database. | `docker compose -f docker-compose.db.yml up` |

## GPU and CPU Controls

GPU builds can be toggled by passing `FORCE_GPU=1` to compatible targets:

```bash
make up FORCE_GPU=1
```

Helper aliases exist for convenience:

- `make gpu-up` and `make gpu-up-dev` force GPU mode.
- `make cpu-up` and `make cpu-up-dev` force CPU mode.

## Remote Training Commands

To run training jobs on a remote machine, provide the required `REMOTE` host and optional
parameters. Results are synced back to `backend/checkpoints/supply_chain_gnn.pth` by
default.

```bash
make remote-train REMOTE=user@host
make remote-train-dataset REMOTE=user@host DATASET=path/to/dataset
```

Available variables:

- `REMOTE_DIR` (default `~/beer-game`)
- `EPOCHS` (default `50`)
- `DEVICE` (default `cuda`)
- `WINDOW` (default `52`)
- `HORIZON` (default `1`)
- `NUM_RUNS` (default `128`)
- `T` (default `64`)
- `DATASET` (required for `remote-train-dataset`)
- `SAVE_LOCAL` (default `backend/checkpoints/supply_chain_gnn.pth`)

## Local Training Helpers

Set up and execute training locally from the `backend` directory:

```bash
make train-setup   # Create a Python venv and install training dependencies
make train-cpu     # Run CPU-based training
make train-gpu     # Run GPU-enabled training
```

## Environment Setup

`make init-env` runs either `scripts/setup_env.ps1` (Windows) or `scripts/setup_env.sh`
(Linux/macOS) to populate configuration files.

## Additional Tips

- Override the hostname printed in helper messages with `HOST=<ip-or-hostname>` when
  running locally (defaults to `localhost`).
- The Makefile auto-detects the Docker Compose V2 plugin. When it falls back to
  the legacy `docker-compose` binary it automatically pins
  `COMPOSE_API_VERSION=1.44` to avoid the `KeyError: 'ContainerConfig'` bug in
  new Docker Engine releases. If you run commands manually, either use the V2
  plugin (`docker compose`) or export the same environment variable yourself.
- Remote helper commands use `REMOTE_HOST=172.29.20.187` for status messages.
- The `help` target prints an annotated list of all commands if you need a quick
  reminder: `make help`.
