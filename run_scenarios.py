"""Live demo runner — executes the 3 required scenarios against real Claude.

Usage: uv run python run_scenarios.py
Set ANTHROPIC_API_KEY in .env or environment before running.
"""
from app.agent.react_agent import process_email
from app.config import Settings
from app.services.pms import PMS


def print_result(title: str, result):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    if result.action_plan:
        print("\n--- Action Plan ---")
        for i, step in enumerate(result.action_plan, 1):
            print(f"  {i}. [{step.status}] {step.description}")

    if result.risk_flag:
        print(f"\n--- Risk Flag ---\n  {result.risk_flag}")

    print(f"\n--- Approval Required: {result.requires_approval} ---")

    print(f"\n--- Draft Reply ---\n{result.draft_reply}")
    print()


def main():
    settings = Settings()
    pms = PMS(settings.data_path)

    # Scenario 1: Read-only lookup
    print_result(
        "Scenario 1: Read-Only Lookup",
        process_email(
            email_body="Do you have any available rooms April 20th-22nd?",
            sender_email="someone@email.com",
            pms=pms,
            settings=settings,
        ),
    )

    # Scenario 2: Booking action (human approval mode)
    pms_booking = PMS(settings.data_path)  # Fresh state
    result = process_email(
        email_body=(
            "Hi, we'd like to book a double room with breakfast for 2 adults "
            "for April 24th-26th. My name is Erik Hansen."
        ),
        sender_email="erik.hansen@email.com",
        pms=pms_booking,
        settings=Settings(anthropic_api_key=settings.anthropic_api_key, approval_mode="human_approval"),
    )
    print_result("Scenario 2: Booking (Human Approval Mode)", result)

    if result.requires_approval and hasattr(result, "execute_pending") and callable(result.execute_pending):
        print("  >> Simulating approval... executing pending actions.")
        result.execute_pending(pms_booking)
        print("  >> Actions executed. Reservation created.\n")

    # Scenario 3: Ambiguous/risky request
    pms_escalation = PMS(settings.data_path)
    print_result(
        "Scenario 3: Ambiguous/Risky Request (Autonomous Mode)",
        process_email(
            email_body="I want a refund on my non-refundable booking.",
            sender_email="maria.gonzalez@email.com",
            pms=pms_escalation,
            settings=Settings(anthropic_api_key=settings.anthropic_api_key, approval_mode="autonomous"),
        ),
    )


if __name__ == "__main__":
    main()
