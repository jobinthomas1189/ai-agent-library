from __future__ import annotations

import os
from typing import Any, Dict, Optional, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from prompts import SYSTEM
from tools import run_python


class AgentState(TypedDict):
    task: str
    plan: Optional[str]
    code: Optional[str]
    last_run: Optional[Dict[str, Any]]
    attempts: int
    done: bool


def make_client():
    from openai import OpenAI

    api_key = os.environ["OPENROUTER_API_KEY"].strip()
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:8888",
            "X-Title": "Dallas Agent Workshop",
        },
    )


def llm_chat(client, model: str, user_msg: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def planner_node(state: AgentState) -> AgentState:
    client = make_client()
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
    task = state["task"]

    prompt = f"""Task:
{task}

You must generate Python code that EXECUTES and PRINTS the final answer.

STRICT REQUIREMENTS:
- The code MUST call print() on the final result.
- The code MUST be executable immediately.
- Do NOT define a function without calling it.
- Do NOT leave expressions unused.

Return EXACTLY in this format:

Plan:
<brief plan>

```python
# executable Python code
# must include print(...)
"""
    text = llm_chat(client, model, prompt)

    code = ""
    if "```" in text:
        parts = text.split("```")
        for i in range(len(parts) - 1):
            if "python" in parts[i].lower():
                code = parts[i + 1]
                break
        if not code and len(parts) >= 3:
            code = parts[1]

    code = (code or "").strip()
    # If we extracted from ```python fences via naive splitting, the first line may be "python".
    lines = [ln.rstrip() for ln in code.splitlines()]
    if lines and lines[0].strip().lower() in ("python", "py"):
        code = "\n".join(lines[1:]).lstrip()

    return {
        **state,
        "plan": text,
        "code": code,
        "attempts": state["attempts"] + 1,
    }


def exec_node(state: AgentState) -> AgentState:
    code = (state.get("code") or "").strip()

    if code and "print(" not in code:
        lines = [ln for ln in code.splitlines() if ln.strip()]

        if len(lines) == 1 and not lines[0].startswith(("def ", "class ", "import ", "from ")):
            code = f"print({lines[0]})"

    print("=== GENERATED CODE ===")
    print(code)
    print("======================")

    result = run_python(code, timeout_s=3)
    return {**state, "last_run": result}


def decide_node(state: AgentState) -> str:
    result = state.get("last_run") or {}
    if bool(result.get("ok")):
        return "finish"
    if state["attempts"] >= 3:
        return "finish"
    return "fix"


def fixer_node(state: AgentState) -> AgentState:
    client = make_client()
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

    task = state["task"]
    code = state.get("code") or ""
    last = state.get("last_run") or {}
    stderr = last.get("stderr", "")
    stdout = last.get("stdout", "")

    prompt = f"""Task:
{task}

Your previous code:
```python
{code}
```

Execution stdout:
{stdout}

Execution stderr:
{stderr}

Fix the code. Return ONLY a Python code block in triple backticks.
"""
    text = llm_chat(client, model, prompt)

    new_code = ""
    if "```" in text:
        parts = text.split("```")
        new_code = (parts[1] if len(parts) >= 2 else "").strip()

    new_lines = [ln.rstrip() for ln in new_code.splitlines()]
    if new_lines and new_lines[0].strip().lower() in ("python", "py"):
        new_code = "\n".join(new_lines[1:]).lstrip()

    return {**state, "code": new_code, "attempts": state["attempts"] + 1}


def finish_node(state: AgentState) -> AgentState:
    return {**state, "done": True}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", planner_node)
    g.add_node("exec", exec_node)
    g.add_node("fix", fixer_node)
    g.add_node("finish", finish_node)

    g.set_entry_point("plan")
    g.add_edge("plan", "exec")
    g.add_conditional_edges("exec", decide_node, {"fix": "fix", "finish": "finish"})
    g.add_edge("fix", "exec")
    g.add_edge("finish", END)
    return g.compile()


def run_task(task: str) -> Dict[str, Any]:
    load_dotenv(dotenv_path=".env", override=False)
    graph = build_graph()
    state: AgentState = {
        "task": task,
        "plan": None,
        "code": None,
        "last_run": None,
        "attempts": 0,
        "done": False,
    }
    out = graph.invoke(state)
    return out
