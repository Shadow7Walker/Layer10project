# Layer10 Grounded Memory Graph Take-Home

This project is a complete pipeline for extracting, deduplicating, storing, and visualizing a grounded long-term memory graph from unstructured corpora (like GitHub issues).

## Requirements

1. **Python 3.10+**
2. **`uv`** (Fast Python package and project manager)
   - If you don't have `uv` installed, you can install it via:
     - **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
     - **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
     - Or simply: `pip install uv`

## Local Model Setup (Ollama)

This project relies on a local LLM to execute structured extraction of entities and claims smoothly. Before running the extraction pipeline, you must have Ollama running:

1. Download and install [Ollama](https://ollama.com).
2. Open a terminal and start the server with the `llama3` model:
   ```bash
   ollama run llama3
   ```
   *Keep this terminal window open/running while you execute the data pipeline below.*

## Running the Pipeline

You can run the entire data ingestion, extraction, and deduplication pipeline via the unified Python runner.

1. Clone or extract this repository and navigate into the project directory:
   ```bash
   cd layer10-takehome
   ```

2. Initialize dependencies using `uv` (this reads from `uv.lock`/`pyproject.toml`):
   ```bash
   uv sync
   ```

3. Run the complete pipeline targeting an open-source repository (defaulting to fetching 10 issues from `facebook/react`):
   ```bash
   uv run python run.py --owner facebook --repo react --count 10
   ```

   *Optional: Provide a `--query` flag to automatically run a context retrieval test at the end of the pipeline:*
   ```bash
   uv run python run.py --owner facebook --repo react --count 10 --query bug
   ```

## Launching the Visualization Explorer

Once the pipeline has completed and generated the SQLite memory graph (`data/memory_graph.db`), you can launch the Streamlit frontend to interactively explore Entities, Claims, and Grounding Evidence:

```bash
uv run streamlit run src/app.py
```

This will automatically open the dashboard in your default web browser at `http://localhost:8501`.

## Documentation

For a detailed breakdown of the system architecture, ontology, edge-case handling, and how this pipeline adapts to Layer10's enterprise environments (Slack, Jira, etc.), please read the included `layer10_writeup.md`.
