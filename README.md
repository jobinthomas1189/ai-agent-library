# Dallas Agent Workshop (Notebook-first)

This repo is designed for a ~50-person hands-on meetup.

## Quick start

### 1) Create venv + install
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure Environment

#### Set GCP Credentials (for Secret Manager)
Source the local GCP environment script to set `GOOGLE_APPLICATION_CREDENTIALS`:
```bash
source scripts/local_gcp_env.sh
```

#### Copy env template for optional settings:
```bash
cp .env.example .env
```

Set:
- `OPENROUTER_MODEL` (default: `arcee-ai/trinity-large-preview:free`)

**API Keys:** Both `OPENROUTER_API_KEY` and `TAVILY_API_KEY` are retrieved from Google Cloud Secret Manager by default (using keys `openrouter-api-key` and `tavily`). If GCP credentials aren't available, set them as environment variables:
```bash
export OPENROUTER_API_KEY=your_key_here
export TAVILY_API_KEY=your_tavily_key_here
```

### 3) Run notebook
```bash
jupyter lab
```

Open: `workshop.ipynb`

## Preflight Check
```bash
python test_model.py
```

Expected output:

```
MODEL WORKING
```

### Research Agent

**Motivation:**
Current workshop is developer-centric (code execution). This adds an applied use case (research/competitive intelligence) that's more broadly relatable.

A multi-step agent that:
1. Plans search queries based on your question
2. Searches the web via Tavily API
3. Synthesizes findings into a structured report

**Setup:**
- Ensure GCP credentials are configured (`source scripts/local_gcp_env.sh`)
- The Tavily API key is automatically retrieved from Secret Manager (key: `tavily`)
- The Open Router API key is automatically retrieved from Secret Manager (key: `openrouter-api-key`)
- Run section 4 in the notebook

**Example questions:**
- "What are the latest trends in AI agents?"
- "Compare the top 3 cloud providers for ML workloads"
- "What's the competitive landscape for vector databases?"
```

## Troubleshooting:
- Regenerate your OpenRouter key if you see a 401 error.
- Restart your notebook kernel after updating `.env`.
- If `python test_model.py` works but the notebook still gets 401, you likely have a stale shell env var. Before starting Jupyter, run: `unset OPENROUTER_API_KEY OPENROUTER_MODEL`.

## Notes
- Agent runs locally on your laptop.
- Model calls go to OpenRouter.
- The Python execution tool is **not** a hardened sandbox.
