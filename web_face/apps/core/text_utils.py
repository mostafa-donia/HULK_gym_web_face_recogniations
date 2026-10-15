"""
Text utility functions for Arabic shaping, BiDi reordering, and image generation.
"""

def reshape_arabic(text: str) -> str:
    """
    Properly reshapes Arabic characters into their connected forms and applies
    the BiDi algorithm for correct right-to-left visual rendering in PIL/Pillow.
    """
    if not text:
        return ""
    text_str = str(text)
    # Check if string contains any Arabic characters
    has_arabic = any(
        "\u0600" <= c <= "\u06FF"
        or "\u0750" <= c <= "\u077F"
        or "\u08A0" <= c <= "\u08FF"
        or "\uFB50" <= c <= "\uFDFF"
        or "\uFE70" <= c <= "\uFEFF"
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
