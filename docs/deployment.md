# Run TrialOps locally

TrialOps runs as a FastAPI backend on `127.0.0.1:8000` and a Streamlit frontend on `127.0.0.1:8501`. Python 3.11 is the tested runtime. Both local scripts and Compose bind published ports to the local machine by default.

## Windows PowerShell

Run these commands from the repository root. The existing `.venv` already has the dependencies in the development workspace. For a fresh checkout:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start and check both services:

```powershell
.\scripts\start.ps1
.\scripts\smoke.ps1
.\scripts\smoke.ps1 -Full
```

Open [TrialOps](http://127.0.0.1:8501) or the [API documentation](http://127.0.0.1:8000/docs). `-Full` also executes live extraction, comparison, synthetic-profile evaluation, hybrid retrieval with source-offset checks, and JSON/CSV/HTML exports. Full model checks require the pinned weights in `models/hf` or network access for their first download.

`start.ps1` uses the repository's `.venv\Scripts\python.exe`, sets absolute `DATA_DIR` and `TRIALOPS_MODEL_CACHE` paths, and sets the frontend's `API_BASE_URL`. It starts missing services in hidden windows, waits for health checks, and writes unique stdout/stderr logs under `reports/`. Healthy existing services are reused. A busy port whose service fails its health check produces an actionable error.

Stop processes launched by the script:

```powershell
.\scripts\stop.ps1
```

The saved `reports/server_state.json` records process IDs, creation times, executable paths and command lines. `stop.ps1` checks those identities again and stops matching service descendants. It leaves reused services that it did not launch running. Stop the tracked pair before changing ports; startup refuses to overwrite ownership of a running pair. Optional ports are available through `start.ps1 -BackendPort 8100 -FrontendPort 8601`; check them with `smoke.ps1 -ApiUrl http://127.0.0.1:8100 -UiUrl http://127.0.0.1:8601`.

The scripts do not automatically load `.env`. Set optional values in the PowerShell environment before starting, for example `$env:HF_HUB_OFFLINE = '1'` after downloading the weights. Generator selection defaults to local FLAN-T5-small; set `$env:GENERATOR_BACKEND = 'ollama'` and `$env:OLLAMA_MODEL` to use an existing local Ollama service instead.

## Docker Compose

The backend Dockerfile installs the pinned `requirements.txt`, first selecting the pinned CPU PyTorch wheel. The smaller frontend image installs pinned Streamlit, requests and pandas. Both images run as an unprivileged user and include HTTP health checks.

```powershell
New-Item -ItemType Directory -Path models/hf -Force
docker compose config --quiet
docker compose build
docker compose up -d --wait
.\scripts\smoke.ps1 -Full
docker compose down
```

Stop any local services using ports 8000/8501 before starting Compose. To keep local services running while trying Compose, select different host ports:

```powershell
$env:BACKEND_PORT = '8100'
$env:FRONTEND_PORT = '8601'
docker compose up -d --build --wait
.\scripts\smoke.ps1 -ApiUrl http://127.0.0.1:8100 -UiUrl http://127.0.0.1:8601
```

The frontend connects to `http://backend:8000` over the Compose network. Backend data, generated indexes and local reviews persist in the host's `data/` directory; model weights persist in `models/hf/`. `docker compose down` keeps these bind-mounted files. The first model request can download weights into the cache. Set `HF_HUB_OFFLINE=1` only when the required weights are already cached.

On a Linux host, set `TRIALOPS_UID` and `TRIALOPS_GID` to a user/group that can write the mounted `data/` and `models/hf/` directories. The defaults are UID/GID 10001. Compose reads optional overrides from `.env`; the sample file can be copied to `.env`. Ollama in another container or on the host needs a reachable `OLLAMA_URL` configured in the backend environment; container-local `127.0.0.1` addresses the backend container itself.

Inspect service health and logs with `docker compose ps` and `docker compose logs backend frontend`. Read `/health` for API readiness, `/_stcore/health` for Streamlit readiness, and `reports/deployment_smoke.json` for measured HTTP checks.

## Verified deployment status

On 18 October 2026, startup and reuse succeeded against the running Windows services, and the full HTTP smoke passed with 58 loaded public study records. Separate test services were started on 8100/8601, reused with ownership preserved, checked successfully, then stopped by verified process identity; both test ports closed and the original 8000/8501 services stayed healthy.

`docker compose config --quiet` passed. An actual `docker compose build` was attempted and exited with code 1 before building an image because Docker's Linux engine was unavailable:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

Docker CLI 29.7.2 and Compose v5.5.0 are installed. The executable is under `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe`. Starting the installed Docker Desktop hidden did not restore the engine: its backend log reported that `Docker/run/dockerInference` could not be renamed to `dockerInference.stale` because the file could not be accessed by the system. No image build or container startup has been verified on this machine. Resolve the Docker Desktop runtime failure, then rerun the Compose commands above. The working Python deployment remains available.

Machine-readable evidence is saved in `reports/deployment.json`, `reports/deployment_smoke.json`, and `reports/integration_smoke.json`.
