from apps.core.models import GymProfile


def gym_context(request):
    try:
        profile = GymProfile.get_solo()
    except Exception:
        profile = None
    return {
        "gym_profile": profile,
    }
