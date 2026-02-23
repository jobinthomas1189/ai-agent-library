# Dallas Agent Workshop (Notebook-first)

This repo is designed for a ~50-person hands-on meetup.

## Quick start

### 1) Create venv + install
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure OpenRouter
Copy env template and fill in your key:
```bash
cp .env.example .env
```

Set:
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (default: `arcee-ai/trinity-large-preview:free`)

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
1. Get free Tavily API key: https://tavily.com
2. Add to `.env`: `TAVILY_API_KEY=tvly-xxxxx`
3. Run section 4 in the notebook

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
