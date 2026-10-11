"""Send new live listings for one syllabus, once a day (Feature 54).

    .venv/bin/python scripts/daily_alert.py fixtures/syllabi/vtu_cse_sem4_dbms.txt --semester 4
    .venv/bin/python scripts/daily_alert.py my_syllabus.pdf --semester 3 --dry-run

Runs the full pipeline, compares the live listings with the ones already
sent, and sends only the new ones. With TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID in .env it sends a Telegram message; otherwise it prints.

Credits: a run costs what one click in the app costs (8 to 10 searches),
under the same S2S_CREDIT_CAP. The cache TTL is cut to 20 hours so a daily
run searches again, and at most once a day. On the free plan (250 searches a
month), one syllabus a day uses most of the quota - use --every 2 or more.

Example cron line (08:00 every day):

    0 8 * * * cd /path/to/repo && .venv/bin/python scripts/daily_alert.py syllabus.pdf --semester 4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s2s import pipeline                      # noqa: E402
from s2s.analyze import alerts                # noqa: E402
from s2s.config import ROOT_DIR, Settings     # noqa: E402
from s2s.ingest import loader                 # noqa: E402

STATE_DIR = ROOT_DIR / ".cache" / "alerts"

#: A daily run must search again; a 72-hour cache would replay yesterday.
ALERT_CACHE_TTL_HOURS = 20


def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    import requests

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
        return response.status_code == 200
    except Exception as exc:
        print(f"Telegram send failed: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("syllabus", help="PDF, DOCX or TXT syllabus")
    parser.add_argument("--semester", type=int, default=None)
    parser.add_argument("--every", type=int, default=1,
                        help="run only if this many days passed since the last run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the message, send nothing, save nothing")
    args = parser.parse_args()

    path = Path(args.syllabus)
    syllabus = loader.from_bytes(path.read_bytes(), path.name)

    key = hashlib.sha256(syllabus.text.encode("utf-8")).hexdigest()[:16]
    state_path = STATE_DIR / f"{key}.json"
    state = {"seen": [], "last_run": 0.0}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    days = (time.time() - state.get("last_run", 0.0)) / 86400
    if days < args.every - 0.05:                 # small slack for cron drift
        print(f"Last run {days:.1f} days ago; --every {args.every}. Nothing to do.")
        return 0

    settings = Settings.load()
    settings.cache_ttl_hours = ALERT_CACHE_TTL_HOURS
    if not settings.has_serpapi and not settings.demo_mode:
        print("ERROR: no SERPAPI_API_KEY in .env.")
        return 1

    result = pipeline.run(syllabus, settings, semester=args.semester)
    print(f"{result.ledger.summary()} · {len(result.live)} live")

    new = alerts.new_live(result.opportunities, set(state.get("seen", [])))
    text = alerts.message(new)
    if not text:
        print("No new live listings.")
    else:
        print(text)

    if args.dry_run:
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if text and token and chat_id:
        if not _send_telegram(token, chat_id, text):
            # Not marked as seen, so the next run tries again.
            return 1
        print("Sent to Telegram.")

    state["seen"] = sorted(set(state.get("seen", [])) | {o.url for o in new})
    state["last_run"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
