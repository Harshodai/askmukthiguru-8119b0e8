import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATE_FILE = BASE_DIR / "transcripts" / "_state.json"


def main():
    if not STATE_FILE.exists():
        print(f"❌ State file not found at: {STATE_FILE}")
        return

    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)

    failed_count = len(state.get("failed", []))
    if failed_count == 0:
        print("✅ No failed videos to reset in transcripts/_state.json.")
        return

    print(
        f"🔄 Found {failed_count} failed videos in transcripts/_state.json. Clearing list to queue them for retry..."
    )
    state["failed"] = []

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print("✅ Reset complete. All previously failed videos are now queued for extraction.")


if __name__ == "__main__":
    main()
