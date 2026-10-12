"""Append-only audit trail: output/audit_trail.json.

One record per agent loop (every boss run and every delegated specialist run).
Each record holds who ran, for which ticket, who delegated to it (parent run and
chain), the exact task it was given, every step of its loop (model text, tool
calls with full arguments, tool results, retries, delegations), why it stopped,
its structured output, and token usage.

The file is a JSON array that only ever grows. A new record is appended by
replacing the closing "]" in place, so earlier records are never rewritten,
reordered, or removed, and the file is never wiped (not even by a database reset).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
MAX_TEXT = 2000  # long enough to keep every tool argument and nearly every result whole
_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def clip(value: Any, limit: int = MAX_TEXT) -> Any:
    """Keep JSON values as-is when small; stringify and trim anything very long."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return value if not isinstance(value, str) else text
    return text[: limit - 1] + "…"


def _stamp(obj) -> str | None:
    ts = getattr(obj, "timestamp", None)
    return ts.isoformat(timespec="milliseconds") if ts else None


def steps_from_messages(messages: list[ModelMessage]) -> list[dict]:
    """Turn new agent-loop messages into audit steps, in order."""
    steps: list[dict] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            stamp = _stamp(msg)
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    if part.tool_name.startswith("final_result"):
                        steps.append({"time": stamp, "type": "final_output", "output": clip(part.args_as_dict())})
                    elif part.tool_name == "delegate":
                        args = part.args_as_dict()
                        steps.append({"time": stamp, "type": "delegate", "to": args.get("to"),
                                      "task": clip(args.get("task", "")), "tool_call_id": part.tool_call_id})
                    else:
                        steps.append({"time": stamp, "type": "tool_call", "tool": part.tool_name,
                                      "args": part.args_as_dict(), "tool_call_id": part.tool_call_id})
                elif isinstance(part, TextPart) and part.content.strip():
                    steps.append({"time": stamp, "type": "model_text", "text": clip(part.content)})
                elif isinstance(part, ThinkingPart) and part.content.strip():
                    steps.append({"time": stamp, "type": "model_thinking", "text": clip(part.content, 600)})
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and not part.tool_name.startswith("final_result"):
                    kind = "delegate_result" if part.tool_name == "delegate" else "tool_result"
                    steps.append({"time": _stamp(part), "type": kind, "tool": part.tool_name,
                                  "tool_call_id": part.tool_call_id, "result": clip(part.content)})
                elif isinstance(part, RetryPromptPart):
                    reason = part.content if isinstance(part.content, str) else json.dumps(part.content, default=str)
                    steps.append({"time": _stamp(part), "type": "retry", "tool": part.tool_name,
                                  "reason": clip(reason, 800)})
    return steps


def append_record(record: dict, path: Path | None = None) -> None:
    """Append one record to the JSON array without rewriting earlier records."""
    path = path or AUDIT_PATH
    data = json.dumps(record, ensure_ascii=False, default=str, indent=2)
    data = "\n".join("  " + line for line in data.splitlines())
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text("[\n" + data + "\n]\n", encoding="utf-8")
            return
        with open(path, "rb+") as f:
            # Only the closing "]" (and whitespace around it) at the very end is replaced.
            f.seek(0, 2)
            end = f.tell()
            start = max(0, end - 256)
            f.seek(start)
            tail = f.read()
            close = tail.rfind(b"]")
            if close == -1:
                raise RuntimeError(f"{path} is not a JSON array; refusing to modify it")
            before = tail[:close].rstrip()
            last = before[-1:]  # b"[" for an empty array, b"}" after a record
            f.seek(start + len(before))
            f.truncate()
            f.write((b"\n" if last == b"[" else b",\n") + data.encode("utf-8") + b"\n]\n")
