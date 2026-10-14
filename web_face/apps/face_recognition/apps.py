from django.apps import AppConfig


class FaceRecognitionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.face_recognition'
    verbose_name = 'التعرف بالوجه وبوابات الدخول'

    def ready(self):
        import os
        import sys
        if "runserver" not in sys.argv or os.environ.get("RUN_MAIN") != "true":
            return

        def _auto_start():
            try:
                from apps.core.models import GymProfile
                from apps.face_recognition.engine import get_face_engine
                profile = GymProfile.get_solo()
                if profile.face_camera_enabled:
                    get_face_engine()
            except Exception:
                pass

        import threading
        threading.Thread(target=_auto_start, daemon=True).start()
