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
    print("  Commands: /mode auto, /mode human, /approve, /reset, /debug, /quit")
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
            elif cmd.startswith("/debug"):
                parts = cmd.split()
                if len(parts) == 1:
                    print("  /debug guests     — list all guests")
                    print("  /debug res        — list all reservations")
                    print("  /debug avail DATE — availability for a date (e.g. /debug avail 2025-04-25)")
                elif parts[1] == "guests":
                    for g in pms._data["guests"]:
                        print(f"  {g['id']}: {g['first_name']} {g['last_name']} ({g['email']})")
                elif parts[1] == "res":
                    for r in pms._data["reservations"]:
                        room = pms.get_room_type(r["room_type_id"])
                        room_name = room.name if room else r["room_type_id"]
                        print(f"  {r['id']}: {r['guest_id']} | {room_name} | {r['check_in']} to {r['check_out']} | {r['status']} | {r['total_amount']} NOK")
                elif parts[1] == "avail" and len(parts) == 3:
                    date_str = parts[2]
                    avail = pms._data["availability"].get(date_str, {})
                    if avail:
                        for rt_id, count in avail.items():
                            room = pms.get_room_type(rt_id)
                            name = room.name if room else rt_id
                            print(f"  {name} ({rt_id}): {count} room(s)")
                    else:
                        print(f"  No availability data for {date_str}")
                else:
                    print(f"  Unknown debug command: {cmd}")
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
                print(f"  {i}. {step.description}")
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
