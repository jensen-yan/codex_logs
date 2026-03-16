# codex_logs

This repository stores shareable Codex chat transcripts exported from local
session JSONL files.

## Layout

- `talk/`: exported Markdown conversations, one file per session
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

## 示例
[talk/20260310-019cd710-fca1d5f3.md](talk/20260310-019cd710-fca1d5f3.md)
记录了我在设计upper Bound tage 时候的沟通记录。
User 部分是我的提示词；
Assistant 部分是Codex 的回复。