"""
Text utility functions for Arabic shaping, BiDi reordering, and image generation.
"""
import os
import re
from PIL import ImageFont


# Comprehensive regex matching emojis, symbols, and variation selectors that cause hollow boxes in PIL
EMOJI_PATTERN = re.compile(
    "["
    "\U00010000-\U0010ffff"  # Emojis (SMP: faces, gestures, food, objects)
    "\u2600-\u27bf"          # Miscellaneous symbols & dingbats (e.g. ⚡, ✈, ✉, ✌, etc.)
    "\u2300-\u23ff"          # Miscellaneous technical
    "\u2b50-\u2b55"          # Star, circle symbols
    "\ufe00-\ufe0f"          # Variation selectors
    "\u200d"                 # Zero-width joiner
    "\u200b-\u200f"          # Zero-width spaces and bidi marks
    "\u202a-\u202e"          # Directional formatting characters
    "]+",
    flags=re.UNICODE
)


def reshape_arabic(text: str) -> str:
    """
    Properly reshapes Arabic characters into their connected forms and applies
    the BiDi algorithm for correct right-to-left visual rendering in PIL/Pillow.
    Eliminates hollow boxes by filtering emojis and unsupported dingbats.
    """
    if not text:
        return ""
    text_str = str(text)

    # Clean emojis and unsupported dingbat characters to prevent hollow boxes (□)
    text_str = EMOJI_PATTERN.sub("", text_str)
    for ch in ["✓", "✔", "•", "▪", "●", "◆", "★", "⚡", "🤖", "🏋️‍♂️", "🏋️", "♂️", "🚨", "📊", "💰", "📉", "💵", "🎁", "📝", "👤", "👋", "📄", "💪"]:
        text_str = text_str.replace(ch, "")
    text_str = " ".join(text_str.split()).strip()

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
        return get_display(reshaped, base_dir='R')
    except Exception:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text_str), base_dir='R')
        except Exception:
            return text_str


def get_arabic_font(size: int = 18, bold: bool = False):
    """
    Returns an ImageFont instance that renders connected Arabic text beautifully in PIL.
    Prioritizes Arial Bold / Arial and Tahoma which natively bundle full Arabic cursive OpenType glyph tables.
    """
    safe_size = max(16, int(size))
    candidates = []
    if bold:
        candidates = [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\tahomabd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            "arialbd.ttf",
            "tahomabd.ttf",
            "segoeuib.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            "arial.ttf",
            "tahoma.ttf",
            "segoeui.ttf",
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
