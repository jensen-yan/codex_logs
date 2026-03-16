#!/usr/bin/env python3
"""Export a Codex session JSONL file to a shareable Markdown transcript."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


LOCAL_TZ = ZoneInfo("Asia/Shanghai") if ZoneInfo else None


@dataclass
class Entry:
    role: str
    timestamp: str
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_jsonl", type=Path, nargs="?")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output markdown path. Defaults to <date>-<session_id[:8]>.md in cwd.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for exported markdown files.",
    )
    parser.add_argument(
        "--recent",
        type=int,
        help="Export the most recent N session files from --sessions-root.",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=Path.home() / ".codex" / "sessions",
        help="Codex sessions root used together with --recent.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def iso_to_local(iso_ts: str) -> datetime | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if LOCAL_TZ is not None:
        return dt.astimezone(LOCAL_TZ)
    return dt


def time_label(iso_ts: str) -> str:
    dt = iso_to_local(iso_ts)
    if dt is None:
        return ""
    return dt.strftime("%H:%M")


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in {"input_text", "output_text"}:
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
    return "\n\n".join(parts).strip()


def compact_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def render_tool_call(name: str, arguments: str) -> str:
    try:
        parsed = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        parsed = arguments

    if name == "exec_command" and isinstance(parsed, dict):
        lines = ["[Tool: exec_command]"]
        cmd = str(parsed.get("cmd", "")).strip()
        if cmd:
            lines.append("")
            lines.append("```bash")
            lines.append(cmd)
            lines.append("```")
        workdir = parsed.get("workdir")
        if workdir:
            lines.append(f"workdir: `{workdir}`")
        return "\n".join(lines).strip()

    if name == "write_stdin" and isinstance(parsed, dict):
        session_id = parsed.get("session_id", "")
        chars = str(parsed.get("chars", "")).strip()
        if not chars:
            return ""
        lines = [f"[Tool: write_stdin] session `{session_id}`"]
        if chars:
            lines.extend(["", "```text", chars, "```"])
        return "\n".join(lines).strip()

    if name == "update_plan" and isinstance(parsed, dict):
        plan = parsed.get("plan", [])
        lines = ["[Tool: update_plan]"]
        for item in plan:
            if not isinstance(item, dict):
                continue
            status = item.get("status", "unknown")
            step = item.get("step", "")
            lines.append(f"- [{status}] {step}")
        return "\n".join(lines).strip()

    if name == "spawn_agent" and isinstance(parsed, dict):
        lines = ["[Tool: spawn_agent]"]
        agent_type = parsed.get("agent_type")
        if agent_type:
            lines.append(f"agent_type: `{agent_type}`")
        message = str(parsed.get("message", "")).strip()
        if message:
            lines.extend(["", message])
        return "\n".join(lines).strip()

    if name == "send_input" and isinstance(parsed, dict):
        lines = ["[Tool: send_input]"]
        agent_id = parsed.get("id")
        if agent_id:
            lines.append(f"agent: `{agent_id}`")
        message = str(parsed.get("message", "")).strip()
        if message:
            lines.extend(["", message])
        return "\n".join(lines).strip()

    if name == "wait" and isinstance(parsed, dict):
        ids = parsed.get("ids", [])
        return f"[Tool: wait] {compact_json(ids)}"

    return "[Tool: {}]\n\n```json\n{}\n```".format(name, compact_json(parsed))


def render_web_call(payload: dict[str, Any]) -> str:
    action = payload.get("action", {})
    if not isinstance(action, dict):
        return "[Tool: web]"

    action_type = action.get("type")
    if action_type == "search":
        query = action.get("query", "")
        return f"[Tool: web.search] `{query}`"
    if action_type == "open_page":
        return "[Tool: web.open_page]"
    return f"[Tool: web] `{action_type}`"


def collect_entries(rows: list[dict[str, Any]]) -> tuple[list[Entry], dict[str, Any]]:
    entries: list[Entry] = []
    meta: dict[str, Any] = {}

    for row in rows:
        row_type = row.get("type")
        payload = row.get("payload", {})
        timestamp = str(row.get("timestamp", ""))

        if row_type == "session_meta":
            if not meta and isinstance(payload, dict):
                meta = payload
            continue

        if row_type == "event_msg" and isinstance(payload, dict):
            if payload.get("type") == "user_message":
                text = str(payload.get("message", "")).strip()
                if text:
                    entries.append(Entry(role="user", timestamp=timestamp, text=text))
            continue

        if row_type == "response_item" and isinstance(payload, dict):
            payload_type = payload.get("type")
            if payload_type == "message":
                role = payload.get("role")
                if role != "assistant":
                    continue
                text = extract_message_text(payload.get("content"))
                if text:
                    entries.append(Entry(role=role, timestamp=timestamp, text=text))
                continue

            if payload_type == "function_call":
                name = str(payload.get("name", "tool"))
                arguments = str(payload.get("arguments", ""))
                text = render_tool_call(name, arguments)
                if text:
                    entries.append(
                        Entry(role="assistant", timestamp=timestamp, text=text)
                    )
                continue

            if payload_type == "web_search_call":
                entries.append(
                    Entry(
                        role="assistant",
                        timestamp=timestamp,
                        text=render_web_call(payload),
                    )
                )
                continue

    return entries, meta


def session_id_from_meta(meta: dict[str, Any], session_path: Path) -> str:
    session_id = str(meta.get("id", "")).strip()
    if session_id:
        return session_id
    stem = session_path.stem
    parts = stem.split("-")
    if len(parts) >= 3:
        return parts[-1]
    return stem


def session_slug(session_id: str) -> str:
    compact = session_id.replace("-", "")
    if len(compact) <= 16:
        return compact
    return f"{compact[:8]}-{compact[-8:]}"


def output_path_for(session_path: Path, meta: dict[str, Any], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit

    session_id = session_id_from_meta(meta, session_path)
    started_at = iso_to_local(str(meta.get("timestamp", "")))
    if started_at is None:
        started_at = datetime.fromtimestamp(session_path.stat().st_mtime, tz=LOCAL_TZ)
    name = f"{started_at:%Y%m%d}-{session_slug(session_id)}.md"
    return Path.cwd() / name


def default_output_name(session_path: Path, meta: dict[str, Any]) -> str:
    session_id = session_id_from_meta(meta, session_path)
    started_at = iso_to_local(str(meta.get("timestamp", "")))
    if started_at is None:
        started_at = datetime.fromtimestamp(session_path.stat().st_mtime, tz=LOCAL_TZ)
    return f"{started_at:%Y%m%d}-{session_slug(session_id)}.md"


def write_markdown(
    entries: list[Entry], meta: dict[str, Any], session_path: Path, output_path: Path
) -> None:
    session_id = session_id_from_meta(meta, session_path)
    started_at = iso_to_local(str(meta.get("timestamp", "")))
    exported_at = datetime.now(tz=LOCAL_TZ) if LOCAL_TZ is not None else datetime.now()

    lines: list[str] = []
    lines.append(f"# Conversation {session_id[:8]}")
    lines.append("")
    if started_at is not None:
        lines.append(f"- Date: {started_at:%Y-%m-%d}")
        lines.append(f"- Started: {started_at:%Y-%m-%d %H:%M %Z}")
    lines.append(f"- Session: `{session_id}`")
    lines.append(f"- Source: `{session_path}`")
    lines.append(f"- Messages: {len(entries)}")
    lines.append(f"- Exported: {exported_at:%Y-%m-%d %H:%M %Z}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for entry in entries:
        role_label = "User" if entry.role == "user" else "Assistant"
        header = f"## {role_label}"
        label = time_label(entry.timestamp)
        if label:
            header += f" ({label})"
        lines.append(header)
        lines.append("")
        lines.append(entry.text.strip())
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def export_one(session_path: Path, output_path: Path | None, output_dir: Path | None) -> Path:
    rows = load_jsonl(session_path)
    entries, meta = collect_entries(rows)
    if not entries:
        raise SystemExit(f"No shareable user/assistant entries found in {session_path}.")

    if output_path is not None:
        target = output_path
    elif output_dir is not None:
        target = output_dir / default_output_name(session_path, meta)
    else:
        target = output_path_for(session_path, meta, None)

    write_markdown(entries, meta, session_path, target)
    return target


def recent_session_files(root: Path, limit: int) -> list[Path]:
    files = sorted(root.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    chosen: list[Path] = []
    seen: set[str] = set()

    for path in files:
        try:
            rows = load_jsonl(path)
        except json.JSONDecodeError:
            continue
        meta = {}
        if rows and rows[0].get("type") == "session_meta":
            payload = rows[0].get("payload", {})
            if isinstance(payload, dict):
                meta = payload
        slug = session_slug(session_id_from_meta(meta, path))
        if slug in seen:
            continue
        seen.add(slug)
        chosen.append(path)
        if len(chosen) >= limit:
            break

    return chosen


def main() -> None:
    args = parse_args()
    if args.recent is not None:
        if args.recent <= 0:
            raise SystemExit("--recent must be positive.")
        if args.output is not None:
            raise SystemExit("--output cannot be used together with --recent.")
        target_dir = args.output_dir or Path.cwd()
        for session_path in recent_session_files(args.sessions_root, args.recent):
            print(export_one(session_path, None, target_dir))
        return

    if args.session_jsonl is None:
        raise SystemExit("session_jsonl is required unless --recent is used.")

    print(export_one(args.session_jsonl, args.output, args.output_dir))


if __name__ == "__main__":
    main()
