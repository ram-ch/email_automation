"""Run the 3 required scenarios against the FastAPI endpoint.

Usage:
  1. Start the server:  uv run uvicorn app.main:app --reload
  2. Run scenarios:      uv run python run_scenarios.py

NOTE: In human_approval mode, the server terminal will prompt for
      approve/reject — switch to that terminal and type your decision.
      In autonomous mode, all non-risky requests complete immediately.
"""
import sys
import httpx

BASE_URL = "http://localhost:8000"

SCENARIOS = [
    {
        "id": 1,
        "title": "Read-Only Lookup",
        "description": "Guest asks about room availability — no PMS writes expected.",
        "sender_email": "someone@email.com",
        "body": "Do you have any available rooms April 20th-22nd?",
        "expected_status": "completed",
    },
    {
        "id": 2,
        "title": "Action + Write to PMS (Booking)",
        "description": "Guest books a room — action plan generated, PMS write on approval.",
        "sender_email": "erik.hansen@email.com",
        "body": "Hi, we'd like to book a double room with breakfast for 2 adults for April 24th-26th. My name is Erik Hansen.",
        "expected_status": None,  # depends on mode: "completed" (auto) or "approved"/"rejected" (human)
    },
    {
        "id": 3,
        "title": "Ambiguous / Risky Request",
        "description": "Non-refundable refund request — must be escalated, no PMS writes.",
        "sender_email": "maria.gonzalez@email.com",
        "body": "I want a refund on my non-refundable booking.",
        "expected_status": "escalated",
    },
]


def print_result(scenario: dict, data: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Scenario {scenario['id']}: {scenario['title']}")
    print(f"  {scenario['description']}")
    print(f"{'=' * 60}")
    print(f"  From: {scenario['sender_email']}")
    print(f"  Body: \"{scenario['body']}\"")
    print()

    if data.get("action_plan"):
        print("  --- Action Plan ---")
        for step in data["action_plan"]:
            print(f"    {step['step']}. {step['description']}")
    else:
        print("  --- Action Plan ---")
        print("    (No actions)")

    if data.get("risk_flag"):
        print(f"\n  --- Risk Flag ---")
        print(f"    {data['risk_flag']}")

    print(f"\n  --- Status: {data['status']} | Mode: {data['mode']} ---")

    # Print a snippet of the draft reply (strip HTML)
    html = data.get("email_html", "")
    # Quick-and-dirty: find text between body td tags
    import re
    body_match = re.search(r'line-height:1\.7;">\s*(.*?)\s*</td>', html, re.DOTALL)
    if body_match:
        text = re.sub(r'<br>\n?', '\n', body_match.group(1)).strip()
        print(f"\n  --- Draft Reply ---")
        for line in text.split('\n'):
            print(f"  {line}")
    print()


def main():
    # Check server is running
    try:
        httpx.get(BASE_URL + "/docs", timeout=3)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to {BASE_URL}")
        print(f"Start the server first:  uv run uvicorn app.main:app --reload")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Grand Oslo Hotel — Required Scenarios")
    print("=" * 60)

    for scenario in SCENARIOS:
        try:
            resp = httpx.post(
                BASE_URL + "/process-email",
                json={
                    "sender_email": scenario["sender_email"],
                    "body": scenario["body"],
                },
                timeout=120,  # long timeout for LLM + human approval
            )
            resp.raise_for_status()
            data = resp.json()
            print_result(scenario, data)
        except httpx.ReadTimeout:
            print(f"\n  Scenario {scenario['id']}: TIMEOUT (waiting for approval?)")
        except Exception as e:
            print(f"\n  Scenario {scenario['id']}: ERROR — {type(e).__name__}: {e}")

    print("=" * 60)
    print("  All scenarios complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
