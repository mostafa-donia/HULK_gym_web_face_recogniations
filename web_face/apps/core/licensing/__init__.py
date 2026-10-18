try:
    from .hwid import get_hardware_fingerprint
    from .crypto import (
        generate_offline_license_token,
        verify_offline_license_token,
    )
    try:
        from .engine import (
            get_or_create_system_license,
            validate_system_license,
            activate_offline_token,
        )
    except Exception:
        pass
except ImportError:
    from apps.core.licensing.hwid import get_hardware_fingerprint
    from apps.core.licensing.crypto import (
        generate_offline_license_token,
        verify_offline_license_token,
    )
    try:
        from apps.core.licensing.engine import (
            get_or_create_system_license,
            validate_system_license,
            activate_offline_token,
        )
    except Exception:
        pass

__all__ = [
    "get_hardware_fingerprint",
    "get_or_create_system_license",
    "validate_system_license",
    "activate_offline_token",
    "generate_offline_license_token",
    "verify_offline_license_token",
]
