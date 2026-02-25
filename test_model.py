import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=".env", override=False)

model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

# Try to get API key from Google Cloud Secret Manager, fallback to env var
try:
    from secretgetter import secret_getter_cls
    sgc = secret_getter_cls()
    api_key = sgc.get_action('openrouter-api-key')
except Exception:
    # Fallback to environment variable if Secret Manager fails
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key.strip(),
    default_headers={
        "HTTP-Referer": "http://localhost:8888",
        "X-Title": "Dallas Agent Workshop",
    },
)

resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Reply with exactly: MODEL WORKING"}],
)

print(resp.choices[0].message.content)
