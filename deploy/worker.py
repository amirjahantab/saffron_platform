"""Single scheduled-command process; commands also protect shared state in the DB."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal
import time
import logging
import django
from django.core.management import call_command
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django.setup()
running = True


def stop(*args):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
next_reminders = next_prune = 0
while running:
    for command in ["expire_overdue_orders"] + (["dispatch_notifications"] if settings.NOTIFICATIONS_ENABLED else []):
        try:
            call_command(command)
        except Exception:
            logging.error("Scheduled command failed: %s", command)  # No secret-bearing tracebacks.
    now = time.monotonic()
    for command, due in [("queue_abandoned_carts", next_reminders), ("prune_private_data", next_prune)]:
        if now >= due:
            try:
                call_command(command)
            except Exception:
                logging.error("Scheduled command failed: %s", command)
            if command == "queue_abandoned_carts":
                next_reminders = now+3600
            else:
                next_prune = now+86400
    for _ in range(30):
        if not running:
            break
        time.sleep(1)
