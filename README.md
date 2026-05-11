# Running the agent

The BOM agent (`agent.py`) talks to **Apache Jena Fuseki** for SPARQL and an LLM (via LiteLLM). You need Fuseki reachable with dataset **`apex-bom`** and Turtle data loaded before asking questions.

<a id="llm-config"></a>
### Environment (USE_OLLAMA and LLM_MODEL)

Before running **`agent.py`**, configure how the agent reaches the language model. Set these in **`.env`** (recommended) or in the shell / Compose **`environment:`** block:

| Ollama required variables | OpenAI required variables |
|--------------------------|---------------------------|
| `USE_OLLAMA=true` | `USE_OLLAMA=false` |
| `LLM_MODEL` (e.g. `llama3.1:8b`) | `LLM_MODEL` (e.g. `gpt-4o-mini`) |
| `FUSEKI_HOST` | `FUSEKI_HOST` |
| `FUSEKI_PORT` | `FUSEKI_PORT` |
| `OLLAMA_HOST` | `OPENAI_API_KEY` |
| `OLLAMA_PORT` | - |

If **`USE_OLLAMA`** is unset, the agent defaults to **`true`**. If **`LLM_MODEL`** is unset, defaults are **`llama3.1:8b`** (Ollama path) or **`gpt-4o-mini`** (non-Ollama path). You should still set **`USE_OLLAMA`** and **`LLM_MODEL`** explicitly so runs match your machine (wrong defaults cause confusing connection or auth errors).

**Examples (`.env`):**

```bash
# Local Ollama
USE_OLLAMA=true
LLM_MODEL=llama3.1:8b
FUSEKI_HOST=host.docker.internal
FUSEKI_PORT=3030
# Required when running agent in Docker and Ollama on host
OLLAMA_HOST=host.docker.internal
OLLAMA_PORT=11434
```

```bash
# OpenAI
USE_OLLAMA=false
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-key-here
FUSEKI_HOST=host.docker.internal
FUSEKI_PORT=3030
```

## Running with Docker Compose

### Prerequisites

- Docker and Docker Compose v2 (`docker compose`)
- Optional: **OpenAI API key** if you use a cloud model (e.g. `gpt-4o-mini`). For **Ollama** on the host, install it and pull a model such as `llama3.1:8b`.

### 1. Start Fuseki

From the repository root:

```bash
docker compose up -d fuseki
```

Fuseki listens on [http://localhost:3030](http://localhost:3030). Log in with **`admin`** / **`admin`** (see `docker-compose.yaml`), and ensure the dataset **`apex-bom`** exists (create it once in the UI if it is missing).

Alternatively, with **`FUSEKI_HOST`** and **`FUSEKI_PORT`** set (e.g. **`localhost`** and **`3030`** when Fuseki is mapped on the host), you can create the dataset programmatically:

```bash
python3 fuseki-utilities/setup_fuseki.py
```

### 2. Build and run the agent container

Build the agent image:

```bash
docker compose build agent
```

Start an interactive REPL ( stdin/tty ). The container entrypoint (`docker-entrypoint.sh`) waits briefly, runs **`generate_bom.py`** and **`load_ttl.py`** to refresh **`apex_bom.ttl`** and load it into Fuseki, then starts **`agent.py`**:

```bash
docker compose run --rm -it agent
```

Use **`quit`** to leave the REPL.

### Compose networking

The **`agent`** service is configured with **`FUSEKI_HOST=host.docker.internal`** and **`FUSEKI_PORT=3030`**, so the agent reaches Fuseki through the host-mapped port **`3030`** (same as `fuseki`’s `ports:` mapping). **`extra_hosts`** supplies `host.docker.internal` on Linux.

### LLM configuration (Compose)

Pass **`USE_OLLAMA`**, **`LLM_MODEL`**, Fuseki, and provider credentials when you run the container, or add them under **`agent.environment`** / a root **`.env`** file consumed by Compose (see [LLM configuration](#llm-config) above).

Inside the **agent** container, **`127.0.0.1`** is the container itself—so **Ollama on your Mac** must be reached via **`host.docker.internal`** (Compose already adds **`extra_hosts`** for this on Linux; Docker Desktop provides it on macOS).

Use one of these Compose runs:

| Backend | Command |
|--------|---------|
| OpenAI | `docker compose run --rm -it -e USE_OLLAMA=false -e LLM_MODEL=gpt-4o-mini -e OPENAI_API_KEY=\"your-openai-key-here\" -e FUSEKI_HOST=host.docker.internal -e FUSEKI_PORT=3030 agent` |
| Ollama (host) | `docker compose run --rm -it -e USE_OLLAMA=true -e LLM_MODEL=llama3.1:8b -e OLLAMA_HOST=host.docker.internal -e OLLAMA_PORT=11434 -e FUSEKI_HOST=host.docker.internal -e FUSEKI_PORT=3030 agent` |

Other OpenAI chat models work the same way: set **`LLM_MODEL`** to e.g. **`gpt-4o`** or **`gpt-4o-mini`**.

(`OLLAMA_*` is ignored when **`USE_OLLAMA=false`**.)

**Shortcut:** put variables in a repo **`.env`** and run:

```bash
docker compose run --rm -it --env-file .env agent
```

---

## Running in a dev container

This repository includes a VS Code **Dev Container** (`.devcontainer/devcontainer.json`) based on **Python 3.11**. Dependencies install on container create via **`postCreateCommand`**.

### Prerequisites

- Docker on the machine that hosts the dev container
- **Fuseki** running so the dev container can reach it. Easiest: from the repo on the host, run **`docker compose up -d fuseki`** and publish **`3030`** as in `docker-compose.yaml`.

### Environment

The dev container is started with **`--env-file=${localWorkspaceFolder}/.env`**. Create a **`.env`** at the repo root (do not commit secrets) with at least:

```bash
FUSEKI_HOST=host.docker.internal
FUSEKI_PORT=3030

USE_OLLAMA=true
LLM_MODEL=llama3.1:8b
OLLAMA_HOST=host.docker.internal
OLLAMA_PORT=11434
# Or OpenAI: USE_OLLAMA=false, LLM_MODEL=gpt-4o-mini, OPENAI_API_KEY=...
```

Also set **`OPENAI_API_KEY`** when **`USE_OLLAMA=false`**, and **`OLLAMA_HOST`** / **`OLLAMA_PORT`** if Ollama is not on **`127.0.0.1:11434`**. See [LLM configuration](#llm-config) and **`.devcontainer/devcontainer.env.example`**.

**`host.docker.internal`:** The dev container adds **`--add-host=host.docker.internal:host-gateway`** so Linux resolves the host gateway; Fuseki on the host at port **3030** is reachable as **`http://host.docker.internal:3030`**.

### Load data and start the agent

In the dev container terminal, from the repo root:

1. Ensure Fuseki dataset **`apex-bom`** exists. Create it in the Fuseki UI, or run **`python fuseki-utilities/setup_fuseki.py`** (uses **`FUSEKI_HOST`** / **`FUSEKI_PORT`** from **`.env`**).

2. Ensure **`apex_bom.ttl`** exists (generate below if needed).

3. Generate and load the graph (or reuse an existing TTL):

   ```bash
   python generate_bom.py
   python fuseki-utilities/load_ttl.py
   ```

4. Run the agent:

   ```bash
   python agent.py
   ```

If **`FUSEKI_HOST`** / **`FUSEKI_PORT`** are unset, **`skills.py`** will fail at import time—keep them in **`.env`** for the dev container.

### VS Code tasks for dataset lifecycle

From VS Code, run **Terminal → Run Task...** and use these built-in tasks:

- **`1. Setup Fuseki Dataset`**: creates the `apex-bom` dataset (if missing).
- **`2. Clear DB`**: clears the current dataset graph in Fuseki.
- **`3. Generate BOM TTL`**: regenerates `apex_bom.ttl`.
- **`4. Load TTL to Fuseki`**: loads `apex_bom.ttl` into Fuseki.
- **`Run Full BOM Pipeline`**: runs setup → clear → generate → load in sequence (full re-seed).
