"""
Text utility functions for Arabic shaping, BiDi reordering, and image generation.
"""
import os
from PIL import ImageFont


def reshape_arabic(text: str) -> str:
    """
    Properly reshapes Arabic characters into their connected forms and applies
    the BiDi algorithm for correct right-to-left visual rendering in PIL/Pillow.
    Idempotent: will not double-reshape already shaped presentation forms.
    """
    if not text:
        return ""
    text_str = str(text)

    # Remove symbols/emojis not supported by standard Windows fonts to prevent hollow boxes (□)
    for unsupported in ["✓", "✔", "🏋️‍♂️", "🏋️", "♂️", "🚨", "📊", "💰", "📉", "💵", "🎁", "📝", "👤", "👋", "📄", "💪", "\ufe0f", "\u200d"]:
        if unsupported in text_str:
            text_str = text_str.replace(unsupported, "")
    text_str = text_str.strip()

    # If already reshaped into Arabic Presentation Forms, do not reshape/reverse again
    already_shaped = any("\uFB50" <= c <= "\uFDFF" or "\uFE70" <= c <= "\uFEFF" for c in text_str)
    if already_shaped:
        return text_str

    # Check if string contains any base Arabic characters
    has_arabic = any(
        "\u0600" <= c <= "\u06FF"
        or "\u0750" <= c <= "\u077F"
        or "\u08A0" <= c <= "\u08FF"
        for c in text_str
    )
    if not has_arabic:
        return text_str

    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        configuration = {
            "delete_harakat": False,
            "support_ligatures": True,
        }
        reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
        reshaped = reshaper.reshape(text_str)
        return get_display(reshaped)
    except Exception:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text_str))
        except Exception:
            return text_str


def get_arabic_font(size: int = 18, bold: bool = False):
    """
    Returns an ImageFont instance that renders connected Arabic text beautifully in PIL.
    Prioritizes Segoe UI Bold / Segoe UI (Windows standard modern font with native Arabic cursive linking),
    then Arial Bold / Arial.
    Avoids Tahoma at sizes <= 16pt which causes broken/disconnected Arabic letters in FreeType.
    """
    safe_size = max(16, int(size))
    candidates = []
    if bold:
        candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            "segoeuib.ttf",
            "arialbd.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "segoeui.ttf",
            "arial.ttf",
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, safe_size)
        except Exception:
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return None
