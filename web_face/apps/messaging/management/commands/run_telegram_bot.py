import time
import logging
from django.core.management.base import BaseCommand
from apps.messaging.telegram_bot import (
    get_telegram_config,
    get_bot_info,
    delete_telegram_webhook,
    make_telegram_api_call,
    handle_telegram_update,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Runs the Telegram Bot long-polling daemon for local/offline gym environments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Poll once and exit (useful for health checks).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Telegram Bot Runner..."))
        enabled, token, mgr_chat, profile = get_telegram_config()

        if not token or "Placeholder" in token:
            self.stdout.write(
                self.style.WARNING(
                    "Warning: Telegram Bot Token is not configured or is a placeholder. "
                    "Please update it from the Settings page."
                )
            )

        # Check bot identity
        bot_info = get_bot_info(token=token)
        if not bot_info.get("ok"):
            self.stdout.write(
                self.style.ERROR(
                    f"Failed to connect to Telegram API: {bot_info.get('description')}"
                )
            )
            if options.get("once"):
                return

        bot_user = bot_info.get("result", {})
        bot_name = bot_user.get("first_name", "Bot")
        bot_username = bot_user.get("username", "Unknown")
        self.stdout.write(
            self.style.SUCCESS(
                f"Connected to Telegram Bot: {bot_name} (@{bot_username})"
            )
        )

        # Clear webhook so getUpdates works cleanly
        delete_telegram_webhook(token=token)

        offset = None
        self.stdout.write(self.style.SUCCESS("Bot is now listening for messages and button clicks. Press Ctrl+C to stop."))

        while True:
            try:
                enabled, token, mgr_chat, profile = get_telegram_config()
                if not enabled:
                    self.stdout.write("Telegram Bot is disabled in Gym Settings. Sleeping for 10s...")
                    time.sleep(10)
                    continue

                params = {"timeout": 20, "allowed_updates": ["message", "callback_query"]}
                if offset:
                    params["offset"] = offset

                res = make_telegram_api_call("getUpdates", params, token=token)
                if res.get("ok"):
                    updates = res.get("result", [])
                    for u in updates:
                        u_id = u.get("update_id")
                        offset = u_id + 1
                        try:
                            handle_telegram_update(u)
                        except Exception as e:
                            logger.exception("Error handling telegram update: %s", e)

                if options.get("once"):
                    break

            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS("\nTelegram Bot Runner stopped."))
                break
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"Polling loop error: {exc}"))
                time.sleep(3)
