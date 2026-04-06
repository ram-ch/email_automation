"""Interactive CLI for testing the hotel email agent.

Usage: uv run python cli.py
"""
from app.agent.react_agent import process_email
from app.config import Settings
from app.services.pms import PMS


def main():
    settings = Settings(simulated_today="2025-04-15")
    pms = PMS(settings.data_path)

    print("=" * 60)
    print("  Grand Oslo Hotel — AI Email Agent (Interactive CLI)")
    print("=" * 60)
    print(f"  Mode: {settings.approval_mode}")
    print(f"  Model: {settings.model}")
    print(f"  Simulated date: 2025-04-15")
    print()
    print("  Commands:")
    print("    /mode auto     — switch to autonomous mode")
    print("    /mode human    — switch to human approval mode")
    print("    /approve       — approve pending actions")
    print("    /reset         — reset PMS to fresh state")
    print("    /quit          — exit")
    print("=" * 60)

    pending_result = None

    while True:
        print()
        sender = input("From (email): ").strip()
        if not sender:
            continue
        if sender.startswith("/"):
            cmd = sender
        else:
            print("Email body (type your message, then press Enter twice to send):")
            lines = []
            while True:
                line = input()
                if line == "":
                    if lines:
                        break
                    continue
                lines.append(line)
            email_body = "\n".join(lines)
            cmd = None

        if cmd:
            if cmd == "/quit":
                print("Goodbye!")
                break
            elif cmd == "/reset":
                pms = PMS(settings.data_path)
                pending_result = None
                print("  PMS reset to fresh state.")
                continue
            elif cmd == "/mode auto":
                settings = Settings(
                    anthropic_api_key=settings.anthropic_api_key,
                    approval_mode="autonomous",
                    simulated_today="2025-04-15",
                )
                print("  Switched to autonomous mode.")
                continue
            elif cmd == "/mode human":
                settings = Settings(
                    anthropic_api_key=settings.anthropic_api_key,
                    approval_mode="human_approval",
                    simulated_today="2025-04-15",
                )
                print("  Switched to human approval mode.")
                continue
            elif cmd == "/approve":
                if pending_result and hasattr(pending_result, "execute_pending") and callable(pending_result.execute_pending):
                    pending_result.execute_pending(pms)
                    print("  Actions executed successfully!")
                    pending_result = None
                else:
                    print("  No pending actions to approve.")
                continue
            else:
                print(f"  Unknown command: {cmd}")
                continue

        print()
        print("  Processing...")
        print()

        result = process_email(
            email_body=email_body,
            sender_email=sender,
            pms=pms,
            settings=settings,
        )

        # Show action plan if any
        if result.action_plan:
            print("--- Action Plan ---")
            for i, step in enumerate(result.action_plan, 1):
                print(f"  {i}. [{step.status}] {step.description}")
            print()

        # Show risk flag if any
        if result.risk_flag:
            print(f"--- Escalated ---")
            print(f"  {result.risk_flag}")
            print()

        # Show draft reply
        print("--- Draft Reply ---")
        print(result.draft_reply)
        print()

        # Approval status
        if result.requires_approval:
            print("--- Requires Approval ---")
            print("  Type /approve to execute pending actions.")
            pending_result = result
        else:
            pending_result = None


if __name__ == "__main__":
    main()
