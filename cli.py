"""Interactive CLI for testing the hotel email agent.

Usage: uv run python cli.py
"""
import sys
import threading
import time

from app.agent.react_agent import process_email, _execute_action_plan
from app.config import Settings, load_settings
from app.services.pms import PMS


def spinner(stop_event):
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r  {chars[i % len(chars)]} Thinking...")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()


def main():
    settings = load_settings(simulated_today="2025-04-15")
    pms = PMS(settings.data_path)
    sender = ""

    print()
    print("=" * 60)
    print("  Grand Oslo Hotel — AI Email Agent")
    print("=" * 60)
    print(f"  Mode: {settings.approval_mode} | Model: {settings.model}")
    print()
    print("  Commands: /mode auto, /mode human, /approve, /reset, /quit")
    print("=" * 60)

    pending_result = None

    while True:
        print()

        # Get sender email (remember last one)
        prompt = f"From [{sender}]: " if sender else "From (email): "
        new_sender = input(prompt).strip()
        if new_sender.startswith("/"):
            cmd = new_sender
        else:
            if new_sender:
                sender = new_sender
            if not sender:
                print("  Please enter an email address.")
                continue

            email_body = input("Message: ").strip()
            if not email_body:
                continue
            cmd = None

        # Handle commands
        if cmd:
            if cmd == "/quit":
                print("Goodbye!")
                break
            elif cmd == "/reset":
                pms = PMS(settings.data_path)
                pending_result = None
                print("  PMS reset to fresh state.")
            elif cmd == "/mode auto":
                settings.approval_mode = "autonomous"
                print("  Switched to autonomous mode.")
            elif cmd == "/mode human":
                settings.approval_mode = "human_approval"
                print("  Switched to human approval mode.")
            elif cmd == "/approve":
                if pending_result and pending_result.action_plan:
                    from app.models import SkillResult
                    skill_result = SkillResult(
                        skill_name="approved",
                        action_plan=pending_result.action_plan,
                        draft_reply=pending_result.draft_reply,
                    )
                    _execute_action_plan(skill_result, pms)
                    print("  Actions executed successfully!")
                    pending_result = None
                else:
                    print("  No pending actions to approve.")
            else:
                print(f"  Unknown command: {cmd}")
            continue

        # Process email with spinner
        stop = threading.Event()
        t = threading.Thread(target=spinner, args=(stop,))
        t.start()

        try:
            result = process_email(
                email_body=email_body,
                sender_email=sender,
                pms=pms,
                settings=settings,
            )
        finally:
            stop.set()
            t.join()

        # Show action plan
        if result.action_plan:
            print("--- Action Plan ---")
            for i, step in enumerate(result.action_plan, 1):
                print(f"  {i}. [{step.status}] {step.description}")
            print()

        # Show risk flag
        if result.risk_flag:
            print("--- Escalated ---")
            print(f"  {result.risk_flag}")
            print()

        # Show draft reply
        print("--- Draft Reply ---")
        print(result.draft_reply)

        # Approval status
        if result.requires_approval:
            print()
            print("--- Requires Approval: type /approve to execute ---")
            pending_result = result
        else:
            pending_result = None


if __name__ == "__main__":
    main()
