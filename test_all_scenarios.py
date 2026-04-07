"""Run all 12 test scenarios against the FastAPI endpoint and print results.

Usage:
  1. Start the server:  uv run uvicorn app.main:app --reload
  2. Run scenarios:      uv run python test_all_scenarios.py

TIP: Set approval_mode = "autonomous" in config.toml so scenarios
     run without blocking for approval. Risky requests will still
     escalate (no PMS writes) as expected.
"""
import re
import sys
import httpx

BASE_URL = "http://localhost:8000"

SCENARIOS = [
    {
        "id": 1,
        "title": "Multi-booking in one email",
        "sender_email": "newguest@test.com",
        "body": "I'd like to book 2 rooms for April 24-26 -- one Standard Double for my wife and me, and one Standard Single for my mother. Breakfast for all. My name is Lisa Berg, phone +47 555 1234, Norwegian.",
    },
    {
        "id": 2,
        "title": "Modify a non-refundable booking",
        "sender_email": "yuki.tanaka@email.com",
        "body": "Can I change my reservation to April 21-23 instead?",
    },
    {
        "id": 3,
        "title": "Booking dates outside availability range",
        "sender_email": "someone@test.com",
        "body": "Do you have rooms available May 1-3?",
    },
    {
        "id": 4,
        "title": "Check-in date in the past",
        "sender_email": "erik.hansen@email.com",
        "body": "I'd like to book a Standard Single for April 10-12.",
    },
    {
        "id": 5,
        "title": "Ambiguous cancel - multiple reservations",
        "sender_email": "erik.hansen@email.com",
        "body": "Please cancel my booking.",
    },
    {
        "id": 6,
        "title": "Upgrade request (room type change)",
        "sender_email": "erik.hansen@email.com",
        "body": "Can you upgrade my April 20-23 reservation to a Junior Suite?",
    },
    {
        "id": 7,
        "title": "Unauthorized cancellation attempt",
        "sender_email": "unknown@random.com",
        "body": "Cancel reservation RES001.",
    },
    {
        "id": 8,
        "title": "Booking with zero availability + alternatives",
        "sender_email": "anna.berg@email.com",
        "body": "I want to book a Standard Double for April 26-27.",
    },
    {
        "id": 9,
        "title": "Rate plan math",
        "sender_email": "erik.hansen@email.com",
        "body": "How much would a Junior Suite cost for April 24-26 with the Non-Refundable Saver rate?",
    },
    {
        "id": 10,
        "title": "Policy question with a twist (15kg dog)",
        "sender_email": "james.smith@email.com",
        "body": "I have a 15kg dog. Can I bring it to the hotel?",
    },
    {
        "id": 11,
        "title": "Cancellation policy calculation",
        "sender_email": "james.smith@email.com",
        "body": "What's the cancellation fee if I cancel my April 25-27 reservation today?",
    },
    {
        "id": 12,
        "title": "Non-existent room type",
        "sender_email": "someone@test.com",
        "body": "I'd like to book a Presidential Suite for April 20-22.",
    },
]


def extract_reply_text(html: str) -> str:
    """Extract plain text from the email HTML body."""
    match = re.search(r'line-height:1\.7;">\s*(.*?)\s*</td>', html, re.DOTALL)
    if not match:
        return "(could not extract reply)"
    text = re.sub(r'<br>\n?', '\n', match.group(1))
    return text.strip()


def print_result(scenario: dict, data: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"  SCENARIO {scenario['id']}: {scenario['title']}")
    print(f"  From: {scenario['sender_email']}")
    print(f"  Message: {scenario['body']}")
    print(f"{'=' * 70}")

    if data.get("action_plan"):
        print("\n--- Action Plan ---")
        for step in data["action_plan"]:
            print(f"  {step['step']}. {step['description']}")
    else:
        print("\n--- Action Plan ---")
        print("  (No actions)")

    if data.get("risk_flag"):
        print(f"\n--- Risk Flag ---\n  {data['risk_flag']}")

    print(f"\n--- Status: {data['status']} | Mode: {data['mode']} ---")

    reply_text = extract_reply_text(data.get("email_html", ""))
    print(f"\n--- Draft Reply ---\n{reply_text}")
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
    print("=" * 70)
    print("  Grand Oslo Hotel — All 12 Test Scenarios")
    print("=" * 70)

    passed = 0
    failed = 0

    for scenario in SCENARIOS:
        try:
            resp = httpx.post(
                BASE_URL + "/process-email",
                json={
                    "sender_email": scenario["sender_email"],
                    "body": scenario["body"],
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            print_result(scenario, data)
            passed += 1
        except httpx.ReadTimeout:
            print(f"\n{'=' * 70}")
            print(f"  SCENARIO {scenario['id']}: {scenario['title']} — TIMEOUT")
            print(f"  (Waiting for approval in server terminal?)")
            print(f"{'=' * 70}")
            failed += 1
        except Exception as e:
            print(f"\n{'=' * 70}")
            print(f"  SCENARIO {scenario['id']}: {scenario['title']} — ERROR")
            print(f"  {type(e).__name__}: {e}")
            print(f"{'=' * 70}")
            failed += 1

    print()
    print("=" * 70)
    print(f"  Results: {passed} completed, {failed} failed/timed out")
    print("=" * 70)


if __name__ == "__main__":
    main()
