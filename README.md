# codex_logs

This repository stores shareable Codex chat transcripts exported from local
session JSONL files.

## Layout

- `talk/`: exported Markdown conversations, one file per session
- `prompts/`: prompt-only Markdown files, one file per session
- `scripts/export_codex_session.py`: exporter for a single session or recent N sessions

## Usage

Export one session:

```bash
python3 scripts/export_codex_session.py \
  ~/.codex/sessions/2026/03/16/rollout-...jsonl \
  --output-dir talk
```

Export the most recent 30 sessions:

```bash
python3 scripts/export_codex_session.py \
  --recent 30 \
  --output-dir talk
```

Export only user prompts for the most recent 100 sessions:

```bash
python3 scripts/export_codex_session.py \
  --recent 100 \
  --roles user \
  --output-dir prompts
```
