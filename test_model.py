import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=".env", override=False)

model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"].strip(),
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
