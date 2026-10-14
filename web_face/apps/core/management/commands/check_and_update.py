import sys
from django.core.management.base import BaseCommand
from apps.core.updater import check_for_updates, perform_system_update, get_current_version_info

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class Command(BaseCommand):
    help = "Checks GitHub for updates and applies updates safely with automatic database backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if updates are available on GitHub without applying them.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the latest updates immediately (pull, backup, migrate, refresh cache).",
        )

    def safe_print(self, msg, style_fn=None):
        out = style_fn(msg) if style_fn else msg
        try:
            self.stdout.write(out)
        except UnicodeEncodeError:
            clean = msg.encode("ascii", errors="replace").decode("ascii")
            self.stdout.write(style_fn(clean) if style_fn else clean)

    def handle(self, *args, **options):
        self.safe_print("=== HULK GYM System Updater ===", self.style.MIGRATE_HEADING)
        info = get_current_version_info()
        self.safe_print(f"Current Version: {info.get('version_tag', 'v2.1.0')} ({info.get('commit', 'unknown')})")
        self.safe_print(f"Active Branch  : {info.get('branch', 'main')}")
        self.safe_print(f"Last Commit    : {info.get('date', '')} - {info.get('message', '')}\n")

        if options["check"]:
            self.safe_print("Checking GitHub for updates...")
            res = check_for_updates()
            if not res.get("success"):
                self.safe_print(f"Error checking updates: {res.get('message')}", self.style.ERROR)
                sys.exit(1)

            if res.get("update_available"):
                self.safe_print(f"[!] New updates found! ({res.get('commits_behind', 1)} commits behind)", self.style.SUCCESS)
                for c in res.get("commits_list", []):
                    self.safe_print(f"  * {c}")
                self.safe_print("\nRun 'python manage.py check_and_update --apply' to update now.", self.style.WARNING)
            else:
                self.safe_print("[OK] System is fully up to date!", self.style.SUCCESS)
            return

        if options["apply"]:
            self.safe_print("Applying update from GitHub...")
            res = perform_system_update()
            for log_line in res.get("logs", []):
                self.safe_print(log_line)

            if res.get("success"):
                self.safe_print(f"\n{res.get('message')}", self.style.SUCCESS)
            else:
                self.safe_print(f"\n{res.get('message')}", self.style.ERROR)
                sys.exit(1)
            return

        # Default: Check first, if update available ask or show status
        self.safe_print("Checking GitHub for updates...")
        res = check_for_updates()
        if res.get("update_available"):
            self.safe_print(f"[!] New updates found! ({res.get('commits_behind', 1)} commits behind)", self.style.SUCCESS)
            for c in res.get("commits_list", []):
                self.safe_print(f"  * {c}")
            self.safe_print("\nApplying update now...")
            update_res = perform_system_update()
            for log_line in update_res.get("logs", []):
                self.safe_print(log_line)
            if update_res.get("success"):
                self.safe_print(f"\n{update_res.get('message')}", self.style.SUCCESS)
            else:
                self.safe_print(f"\n{update_res.get('message')}", self.style.ERROR)
                sys.exit(1)
        else:
            self.safe_print("[OK] System is already up to date with GitHub!", self.style.SUCCESS)
