import json
import os
from datetime import datetime, timezone

from config import LOG_FILE, LLM_MODEL

QUESTION_MAX = 300       # truncate logged question to this many chars
RESPONSE_PREVIEW_MAX = 200  # truncate logged response preview to this many chars
_CONSOLE_QUESTION_MAX = 60  # clip for the one-line terminal summary only


def log_interaction(question: str, tier: str, response: str) -> None:
    """
    Append a structured record of this interaction to the audit log.

    Writes one JSON object per line (.jsonl) to LOG_FILE. The question is
    truncated to 300 chars and the response preview to 200 chars; the full
    response length is preserved separately. Creates the logs/ directory if it
    doesn't exist, and prints a one-line terminal summary after each write.

    Logged fields:
      - timestamp        : ISO 8601 UTC datetime (…Z)
      - tier             : safety tier assigned to this question
      - question         : user's question, truncated to 300 chars
      - response_preview : first 200 chars of the response
      - model            : LLM model id that produced the response
      - response_length  : full char length of the response before truncation

    Returns None — side effects only (writes to file, prints to terminal).
    """
    question = question or ""
    response = response or ""

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tier": tier,
        "question": question[:QUESTION_MAX],
        "response_preview": response[:RESPONSE_PREVIEW_MAX],
        "model": LLM_MODEL,
        "response_length": len(response),
    }

    # Ensure logs/ exists before writing. exist_ok=True is a safe no-op once
    # created, so logging "just works" on first run in any environment.
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # One record, one line — json.dumps (not json.dump with indent=), then "\n".
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # One-line terminal summary: [LOGGED] tier=X | "question…" → N chars
    console_q = question[:_CONSOLE_QUESTION_MAX]
    if len(question) > _CONSOLE_QUESTION_MAX:
        console_q += "…"
    summary = f'[LOGGED] tier={tier} | "{console_q}" → {len(response)} chars'
    try:
        print(summary)
    except UnicodeEncodeError:
        # Some consoles (e.g. Windows cp1252) can't encode "→"/"…"; degrade to
        # ASCII so a console-encoding quirk can never crash the pipeline.
        print(summary.replace("→", "->").replace("…", "...").encode(
            "ascii", "replace").decode("ascii"))
