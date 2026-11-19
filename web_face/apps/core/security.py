import time
from typing import Optional
from apps.face_recognition.engine import get_face_engine


def is_manager_authorized(request) -> bool:
    """
    Checks if manager authorization should be automatically granted.
    Conditions that grant instant manager access without passwords:
    1. User is authenticated as Manager, Owner, or Superuser.
    2. Session is already unlocked via Face ID or password.
    3. The AI camera engine has detected the gym manager within the last 180 seconds.
    """
    # 1. Direct role check (Logged in as Manager / Owner / Superuser)
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        if getattr(user, "is_manager", False) or getattr(user, "is_owner", False) or user.is_superuser:
            unlock_all_manager_zones(request)
            return True

    # 2. Session flag check
    session = getattr(request, "session", None)
    if session and (
        session.get("manager_page_unlocked")
        or session.get("settings_page_unlocked")
        or session.get("trainers_page_unlocked")
    ):
        unlock_all_manager_zones(request)
        return True

    # 3. Live AI Camera Detection (Seen within last 180 seconds)
    try:
        engine = get_face_engine()
        last_m = getattr(engine, "last_detected_manager", None)
        if last_m and last_m.get("matched"):
            ts = last_m.get("timestamp", 0)
            if (time.time() - ts) <= 180.0:
                unlock_all_manager_zones(request)
                return True
    except Exception:
        pass

    return False


def unlock_all_manager_zones(request):
    """
    Sets all manager session access flags simultaneously so navigating between
    Manager Dashboard, Settings, Trainers, Reports, and Retention is seamless.
    (Developer Options remains strictly locked behind developer password).
    """
    session = getattr(request, "session", None)
    if session:
        session["manager_page_unlocked"] = True
        session["settings_page_unlocked"] = True
        session["trainers_page_unlocked"] = True
        session["retention_page_unlocked"] = True
        session["reports_page_unlocked"] = True
        session["developer_options_unlocked"] = False
        session.modified = True
        try:
            session.save()
        except Exception:
            pass
