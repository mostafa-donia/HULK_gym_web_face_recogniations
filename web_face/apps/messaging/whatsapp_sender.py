from collections import deque
from subprocess import Popen
from time import sleep
import ctypes
import io
import os
import random
import time

import pyautogui
import win32clipboard
from PIL import Image
from pyautogui import hotkey, press, write
from pygetwindow import getAllWindows, getActiveWindow
from pyperclip import copy, paste

sent = []
unsent = []

MESSAGE_SEND_MODE = "typing"
MESSAGE_CHAR_DELAY = 0.02


def apply_send_settings(settings=None):
    """Apply the configured WhatsApp sending mode and per-character delay."""
    global MESSAGE_SEND_MODE, MESSAGE_CHAR_DELAY
    if settings is None:
        return
    mode = str(settings.get("whatsapp_send_mode", "typing") or "typing").strip().lower()
    if mode not in {"typing", "paste"}:
        mode = "typing"
    try:
        delay = float(settings.get("whatsapp_letter_delay", MESSAGE_CHAR_DELAY) or MESSAGE_CHAR_DELAY)
    except (TypeError, ValueError):
        delay = MESSAGE_CHAR_DELAY
    MESSAGE_SEND_MODE = mode
    MESSAGE_CHAR_DELAY = max(0.0, min(delay, 0.5))
    return {"mode": MESSAGE_SEND_MODE, "char_delay": MESSAGE_CHAR_DELAY}


def write_message(message: str, char_delay: float = None, use_paste_mode: bool = False):
    if not message:
        return

    if use_paste_mode:
        try:
            copy(message)
            random_delay(3, 5)
            pyautogui.hotkey('ctrl', 'v')
            random_delay(2,3)
            return
        except Exception:
            pass

    hotkey('win', 'space')
    random_delay(0.5, 1)

    effective_delay = MESSAGE_CHAR_DELAY if char_delay is None else max(0.0, float(char_delay))

    arabic_keys = {
    '|': 'p\\',
    'ذ': '`',
    'ض': 'q',
    'ص': 'w',
    'ث': 'e',
    'ق': 'r',
    'ف': 't',
    'غ': 'y',
    'ع': 'u',
    'ه': 'i',
    'خ': 'o',
    'ح': 'p',
    'ج': '[',
    'د': ']',

    'ش': 'a',
    'س': 's',
    'ي': 'd',
    'ب': 'f',
    'ل': 'g',
    'ا': 'h',
    'ت': 'j',
    'ن': 'k',
    'م': 'l',
    'ك': ';',
    'ط': "'",
    '/': '/l',
    ':': '/;',
    '.': '/.',

    'ئ': 'z',
    'ء': 'x',
    'ؤ': 'c',
    'ر': 'v',
    'ى': 'n',
    'ة': 'm',
    'و': ',',
    'ز': '.',
    'ظ': '/',
'أ': 'h',
'إ': 'h',
'آ': 'h',
',': '/,'
}


    for char in message :
        if char == ' ':
            pyautogui.write(' ')
        elif char in arabic_keys.keys():
            key = arabic_keys[char]
            if len(key) == 1 :
                pyautogui.press(key)
            else :
                random_delay(0.1,0.25)
                pyautogui.hotkey('shift',key[1])
                random_delay(0.1,0.25)       
        elif char == '\n':
            hotkey('shift','enter')
        else :
            pyautogui.write(char)

        if effective_delay > 0:
            sleep(effective_delay)


def random_delay(min_seconds: float = 0.25, max_seconds: float = 1.2) -> float:
    """Sleep for a random duration while preserving the original flow."""
    delay = random.uniform(min_seconds, max_seconds)
    sleep(delay)
    return delay


def human_move_to(x: float, y: float, duration_range: tuple = (0.35, 1.1), jitter: int = 18) -> None:
    """Move the mouse in a slightly human-like, imperfect path"""
    start_x, start_y = pyautogui.position()
    x = int(x)
    y = int(y)
    steps = max(6, int(random.uniform(8, 16)))
    points = []
    for i in range(steps + 1):
        t = i / steps
        px = start_x + (x - start_x) * t + random.uniform(-jitter, jitter)
        py = start_y + (y - start_y) * t + random.uniform(-jitter, jitter)
        points.append((px, py))
    duration = random.uniform(*duration_range)
    per_step = duration / max(len(points) - 1, 1)
    for px, py in points[1:]:
        pyautogui.moveTo(px, py, duration=max(per_step * 0.6, 0.05), tween=pyautogui.easeOutQuad)
    pyautogui.moveTo(x, y, duration=random.uniform(0.08, 0.2), tween=pyautogui.easeInOutQuad)


def pick_random_message(messages):
    """Pick one random message from a dict of categories or a plain list of variants."""
    if isinstance(messages, dict):
        if not messages:
            raise ValueError("Message dict is empty.")
        key = random.choice(list(messages.keys()))
        options = messages[key]
        options = options if isinstance(options, (list, tuple)) else [options]
        options = [str(item) for item in options if str(item).strip()]
        if not options:
            return str(key)
        return random.choice(options)

    if isinstance(messages, (list, tuple)):
        options = [str(item) for item in messages if str(item).strip()]
        if not options:
            return ""
        return random.choice(options)

    return str(messages)


def choose_message_for_send(messages, category=None):
    """Pick a random message from a single category or from a messages dictionary."""
    if isinstance(messages, dict):
        if category is not None:
            options = messages.get(category, [])
            if isinstance(options, (list, tuple)):
                options = [str(item) for item in options if str(item).strip()]
                return random.choice(options) if options else str(category)
            return str(options)
        return pick_random_message(messages)

    if isinstance(messages, (list, tuple)):
        options = [str(item) for item in messages if str(item).strip()]
        return random.choice(options) if options else ""

    return str(messages)


def choose_message_for_group(messages, group_name):
    """Select a random message from the specific selected group for a phone."""
    if not isinstance(messages, dict):
        return str(messages)
    options = messages.get(group_name, [])
    if isinstance(options, (list, tuple)):
        options = [str(item) for item in options if str(item).strip()]
        if not options:
            return str(group_name)
        return random.choice(options)
    return str(options)


def build_message_variants(messages):
    """Compatibility wrapper for callers expecting a flat list of variant messages."""
    if not isinstance(messages, dict):
        return messages

    final_messages = []
    for key, variants in messages.items():
        variant_list = variants if isinstance(variants, (list, tuple)) else [variants]
        variant_list = [str(item) for item in variant_list if str(item).strip()]
        if not variant_list:
            variant_list = [str(key)]
        final_messages.extend(variant_list)
    return final_messages


class WhatsAppRateLimiter:
    """Prevent WhatsApp automation from exceeding safe sending thresholds."""

    def __init__(self, limit_per_minute: int = 20, limit_per_hour: int = 120) -> None:
        self.limit_per_minute = limit_per_minute
        self.limit_per_hour = limit_per_hour
        self.minute_window = deque()
        self.hour_window = deque()

    def _prune(self, window: deque, seconds: int, now: float) -> None:
        while window and now - window[0] >= seconds:
            window.popleft()

    def allow_send(self) -> bool:
        now = time.monotonic()
        self._prune(self.minute_window, 60, now)
        self._prune(self.hour_window, 3600, now)
        if len(self.minute_window) >= self.limit_per_minute:
            return False
        if len(self.hour_window) >= self.limit_per_hour:
            return False
        self.minute_window.append(now)
        self.hour_window.append(now)
        return True

    def _confirm_timeout(self, elapsed: float, next_wait: float, max_wait: float) -> bool:
        print(f"[rate-limit] Next wait is {next_wait:.1f}s and total wait would exceed {max_wait:.0f}s.")
        answer = input("Continue waiting or stop sending? [y/N]: ").strip().lower()
        return answer in ("y", "yes")

    def wait_until_allowed(self, pause_between_checks: float = 1.0, max_wait: float = 60.0) -> bool:
        started = time.monotonic()
        while not self.allow_send():
            now = time.monotonic()
            self._prune(self.minute_window, 60, now)
            self._prune(self.hour_window, 3600, now)
            minute_wait = 0.0
            hour_wait = 0.0
            if len(self.minute_window) >= self.limit_per_minute and self.minute_window:
                minute_wait = 60 - (now - self.minute_window[0])
            if len(self.hour_window) >= self.limit_per_hour and self.hour_window:
                hour_wait = 3600 - (now - self.hour_window[0])
            wait_seconds = max(minute_wait, hour_wait, 0.0) + 0.2
            elapsed = now - started
            if elapsed + wait_seconds > max_wait:
                if not self._confirm_timeout(elapsed, wait_seconds, max_wait):
                    print("[rate-limit] Aborting send process by user request.")
                    return False
                started = time.monotonic()
            print(f"[rate-limit] Pausing for {wait_seconds:.1f}s to stay under the safe WhatsApp limits.")
            sleep(max(wait_seconds, pause_between_checks))
        return True

def set_keyboard_layout_to_english():
    """Detect current Windows keyboard language and switch to English (US) once if needed."""
    hkl = ctypes.windll.user32.GetKeyboardLayout(0)
    lang_id = hkl & 0xFFFF
    language_map = {
        0x0409: "en-US",
        0x0809: "en-GB",
        0x0407: "de-DE",
        0x040C: "fr-FR",
        0x0410: "it-IT",
        0x0412: "ko-KR",
        0x0411: "ja-JP",
        0x0804: "zh-CN",
        0x0404: "zh-TW",
        0x0413: "nl-NL",
        0x0416: "pt-BR",
    }
    current_lang = language_map.get(lang_id, f"0x{lang_id:04X}")
    print(f"[set_keyboard_layout_to_english_once] Current keyboard language: {current_lang}")

    if current_lang == "en-US":
        print("[set_keyboard_layout_to_english_once] Already English (US). No switch needed.")
        return

    print("[set_keyboard_layout_to_english_once] Sending Alt+Shift once to switch layout.")
    pyautogui.hotkey("alt", "shift")
    sleep(0.25)

    hkl_after = ctypes.windll.user32.GetKeyboardLayout(0)
    current_lang_after = language_map.get(hkl_after & 0xFFFF, f"0x{(hkl_after & 0xFFFF):04X}")
    print(f"[set_keyboard_layout_to_english_once] After switch, current keyboard language: {current_lang_after}")
    
def copy_file(file_path: str) -> bool:
    """
    Copy image (via CF_DIB) or document/file (via CF_HDROP) to Windows clipboard.
    Allows pasting images, HTML files, PDF documents, or brochures into WhatsApp Web with Ctrl+V.
    """
    if not file_path:
        return False

    abs_path = os.path.abspath(str(file_path))
    if not os.path.exists(abs_path):
        print(f"[copy_file] File not found: {abs_path}")
        return False

    # 1. Try Image CF_DIB format (for JPG, PNG, WebP, BMP, etc.)
    try:
        img = Image.open(abs_path)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]  # Remove BMP 14-byte file header
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        print(f"[copy_file] Image copied to clipboard as CF_DIB: {abs_path}")
        return True
    except Exception:
        # Not a standard raster image or is a document (HTML, PDF, DOCX, etc.)
        pass

    # 2. CF_HDROP Windows Shell File Drop Format (for HTML, PDF, and general documents)
    try:
        from ctypes import wintypes

        class DROPFILES(ctypes.Structure):
            _fields_ = [
                ("pFiles", wintypes.DWORD),
                ("pt", wintypes.POINT),
                ("fNC", wintypes.BOOL),
                ("fWide", wintypes.BOOL),
            ]

        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        offset = ctypes.sizeof(DROPFILES)
        file_bytes = (abs_path + "\0\0").encode("utf-16le")
        total_size = offset + len(file_bytes)

        GHND = 0x0042  # GMEM_MOVEABLE | GMEM_ZEROINIT
        h_global = kernel32.GlobalAlloc(GHND, total_size)
        if not h_global:
            print("[copy_file] GlobalAlloc failed.")
            return False

        ptr = kernel32.GlobalLock(h_global)
        if not ptr:
            print("[copy_file] GlobalLock failed.")
            return False

        df = DROPFILES(pFiles=offset, pt=wintypes.POINT(0, 0), fNC=False, fWide=True)
        ctypes.memmove(ptr, ctypes.byref(df), offset)
        ctypes.memmove(ptr + offset, file_bytes, len(file_bytes))
        kernel32.GlobalUnlock(h_global)

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(15, h_global)  # 15 = CF_HDROP
        win32clipboard.CloseClipboard()
        print(f"[copy_file] Document file copied to clipboard as CF_HDROP: {abs_path}")
        return True
    except Exception as e:
        print(f"[copy_file] Error copying file to clipboard: {e}")
        return False


def copy_image_to_clipboard(image_path):
    """Backward compatibility alias for copy_file."""
    return copy_file(image_path)

    
    
def prepare_phones(phones:str):
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩","0123456789")
    phones = phones.translate(table)
    phones = list(phones)
    phone_list =""
    for i,c in enumerate(phones) :
        if c == "," and i + 1 < len(phones) and phones[i+1] == ",":
            phones.pop(i+1)
        phone_list+=(c)
    phone_list = phone_list.split(",")
    corrected_phone_list = []
    for i in phone_list :
        if len(i)>10 and len(i)<12 :
            corrected_phone_list.append(i)
        elif len(i)== 10 and i[0] == "1" :
            corrected_phone_list.append("0"+i)
        elif len(i)== 12 and i[0] =="2" :
            i = i.replace("2","",1)
            corrected_phone_list.append(i)
    return corrected_phone_list

def prepare_messages(messages:str):
    messages = list(messages)
    message_list =""
    for i,c in enumerate(messages) :
        if c == "," and i + 1 < len(messages) and messages[i+1] == ",":
            messages.pop(i+1)
        message_list+=(c)
    message_list = message_list.split(",")
    return message_list

WHATSAPP_TITLE_KEYWORDS = [
    "whatsapp", "واتساب", "واتس اب", "واتس", "web.whatsapp"
]

BROWSER_TITLE_KEYWORDS = [
    "chrome", "edge", "msedge", "brave", "firefox", "opera"
]


def is_whatsapp_title(title: str) -> bool:
    if not title:
        return False
    t = str(title).lower()
    return any(k in t for k in ["whatsapp", "web.whatsapp"]) or any(k in str(title) for k in ["واتساب", "واتس اب", "واتس"])


def is_browser_title(title: str) -> bool:
    if not title:
        return False
    t = str(title).lower()
    return any(k in t for k in BROWSER_TITLE_KEYWORDS)


def activate_window_safely(win) -> bool:
    """
    Safely restores and brings a window to the foreground on Windows,
    handling minimized windows and OS foreground locks.
    """
    if not win:
        return False
    try:
        if hasattr(win, "isMinimized") and win.isMinimized:
            win.restore()
            sleep(0.2)
    except Exception:
        pass

    try:
        hwnd = getattr(win, "_hWnd", None)
        if hwnd:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            SW_RESTORE = 9
            user32.ShowWindowAsync(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_RESTORE)

            current_thread = kernel32.GetCurrentThreadId()
            fg_hwnd = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
            if fg_thread != current_thread:
                user32.AttachThreadInput(current_thread, fg_thread, True)
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
                user32.AttachThreadInput(current_thread, fg_thread, False)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
    except Exception as e:
        print(f"[activate_window_safely] Win32 error: {e}")

    try:
        win.activate()
    except Exception:
        pass

    sleep(0.3)
    return True


def is_system_title(title: str) -> bool:
    if not title:
        return False
    t = str(title).lower()
    system_keywords = [
        "hulk", "gym", "نظام", "إدارة", "8000", "127.0.0.1", "localhost",
        "طابور", "رسائل", "مشترك", "أعضاء", "لوحة", "فاتورة", "إيصال",
        "dashboard", "members", "payments", "messaging"
    ]
    return any(k in t for k in system_keywords) and not is_whatsapp_title(title)


def return_to_system_tab() -> bool:
    """
    After finishing WhatsApp message dispatch, seamlessly switches focus back
    to the HULK GYM system browser tab/window.
    """
    print("[return_to_system_tab] Returning focus to HULK GYM system tab/window...")
    sleep(0.4)

    try:
        cur = getActiveWindow()
    except Exception:
        cur = None

    # 1. First, check if the current active window is a browser (where WhatsApp was just active).
    # Step backward across browser tabs to return to the HULK GYM tab.
    if cur and is_browser_title(cur.title):
        for _ in range(25):
            hotkey("ctrl", "shift", "tab")
            sleep(0.18)
            try:
                active = getActiveWindow()
                title = str(active.title or "").strip()
                if is_system_title(title):
                    print(f"[return_to_system_tab] Successfully switched back to system tab: {title}")
                    return True
            except Exception:
                pass

    # 2. Check all open windows to find a dedicated window running the system
    try:
        all_windows = getAllWindows()
    except Exception:
        all_windows = []

    for w in all_windows:
        title = str(w.title or "").strip()
        if is_system_title(title):
            print(f"[return_to_system_tab] Found system window: {title}. Activating...")
            activate_window_safely(w)
            return True

    # 3. Fallback: single Ctrl+Shift+Tab
    try:
        hotkey("ctrl", "shift", "tab")
        sleep(0.2)
    except Exception:
        pass

    return False


def whatsupp_ready() -> bool:
    """
    Ensures WhatsApp Web or WhatsApp Desktop window/tab is active,
    restored, and focused in the foreground.
    Supports Chrome, Edge, Brave, Firefox, and native WhatsApp app.
    """
    print("[whatsupp_ready] Checking for active WhatsApp window...")

    # 1. Check if current active window is already WhatsApp
    try:
        active = getActiveWindow()
        if active and is_whatsapp_title(active.title):
            print(f"[whatsupp_ready] WhatsApp is already active: {active.title}")
            return True
    except Exception:
        pass

    # 2. Check all open windows to see if a WhatsApp window already exists
    try:
        all_windows = getAllWindows()
    except Exception:
        all_windows = []

    whatsapp_windows = [w for w in all_windows if is_whatsapp_title(w.title)]
    if whatsapp_windows:
        target = whatsapp_windows[0]
        print(f"[whatsupp_ready] Found existing WhatsApp window: {target.title}. Bringing to foreground...")
        activate_window_safely(target)
        sleep(0.6)
        return True

    # 3. Check browser windows (Chrome, Edge, Brave, etc.) and cycle tabs to find WhatsApp
    browser_windows = [w for w in all_windows if is_browser_title(w.title)]
    for b_win in browser_windows:
        print(f"[whatsupp_ready] Inspecting browser window: {b_win.title}")
        activate_window_safely(b_win)
        sleep(0.5)

        for _ in range(25):
            try:
                cur = getActiveWindow()
                if cur and is_whatsapp_title(cur.title):
                    print(f"[whatsupp_ready] Found WhatsApp tab: {cur.title}")
                    return True
            except Exception:
                pass
            hotkey("ctrl", "tab")
            sleep(0.18)

    # 4. If not found in any running window or tab, launch WhatsApp Web
    print("[whatsupp_ready] WhatsApp not found. Launching WhatsApp Web...")
    import webbrowser
    launched = False
    try:
        Popen("start chrome https://web.whatsapp.com", shell=True)
        launched = True
    except Exception:
        pass

    if not launched:
        try:
            Popen("start msedge https://web.whatsapp.com", shell=True)
            launched = True
        except Exception:
            pass

    if not launched:
        webbrowser.open("https://web.whatsapp.com")

    # Wait for the browser window and WhatsApp page to load
    print("[whatsupp_ready] Waiting for WhatsApp Web window to initialize...")
    for _ in range(25):
        sleep(0.5)
        try:
            active = getActiveWindow()
            if active and is_whatsapp_title(active.title):
                print(f"[whatsupp_ready] WhatsApp is now active: {active.title}")
                return True

            for w in getAllWindows():
                if is_whatsapp_title(w.title):
                    activate_window_safely(w)
                    print(f"[whatsupp_ready] WhatsApp window detected: {w.title}")
                    return True
        except Exception:
            pass

    return True


def send_message(phone: str, message: str = "", image: str = None, topic: str = None, message_bank: dict = None, context: dict = None, return_to_system: bool = False) -> bool:
    if isinstance(message, dict):
        message_bank = message
        topic = topic or random.choice(list(message_bank.keys())) if isinstance(message_bank, dict) and message_bank else None
        message = choose_message_for_group(message_bank, topic) if topic else ""
    elif isinstance(message_bank, dict):
        chosen_topic = topic or random.choice(list(message_bank.keys()))
        message = choose_message_for_group(message_bank, chosen_topic)

    # Format message with context data (placeholders like {name}, {end_date}, etc.)
    if context and isinstance(context, dict):
        try:
            message = message.format(**context)
        except KeyError as e:
            print(f"[send_message] Missing context key: {e}, sending unformatted message")
        except Exception as exc:
            print(f"[send_message] Error formatting message: {exc}")

    # Ensure WhatsApp window is active and in foreground
    whatsupp_ready()

    set_keyboard_layout_to_english()
    random_delay(0.35, 0.8)
    set_keyboard_layout_to_english()

    print("[send_message] Sending to:", phone)
    press("esc")
    random_delay(0.25, 0.5)

    # Focus search box (Ctrl+Alt+/ in WhatsApp Web, plus fallback click)
    hotkey("ctrl", "alt", "/")
    random_delay(0.25, 0.4)
    human_move_to(300, 198, duration_range=(0.35, 0.8), jitter=16)
    pyautogui.click(300, 198)
    random_delay(0.3, 0.6)

    hotkey("ctrl", "a")
    random_delay(0.2, 0.4)
    press("backspace")
    random_delay(0.2, 0.4)

    write(phone, interval=0.08)
    random_delay(2.5, 4.0)

    press("enter")
    random_delay(2.0, 3.2)

    # 1. If file / image attachment is provided, copy to clipboard and paste
    if image and isinstance(image, str) and os.path.exists(image):
        print(f"[send_message] Attaching file/image: {image}")
        if copy_file(image):
            random_delay(0.6, 1.2)
            hotkey("ctrl", "v")
            random_delay(3.5, 5.5)  # Wait for WhatsApp attachment preview dialog
            if message:
                copy(message)
                random_delay(0.4, 0.8)
                hotkey("ctrl", "v")
                random_delay(0.4, 0.8)
            press("enter")
            random_delay(1.8, 2.8)
            print(f"[send_message] Attached file and message delivered successfully to {phone}")
            if return_to_system:
                return_to_system_tab()
            return True
        else:
            print(f"[send_message] Failed to copy attachment to clipboard, falling back to text only")

    # 2. Text-only message delivery
    if message:
        write_message(message, use_paste_mode=(MESSAGE_SEND_MODE == "paste"), char_delay=MESSAGE_CHAR_DELAY)
        random_delay(1.5, 3.0)
        press("enter")
        random_delay(1.2, 2.2)

    print(f"[send_message] Message delivered successfully to {phone}")
    if return_to_system:
        return_to_system_tab()
    return True


def sending(phones: list, messages: list, groups: list = None, image: str = None, progress_callback=None, contexts: list = None):
    global sent, unsent

    if isinstance(messages, dict):
        if groups is not None:
            if len(groups) != len(phones):
                raise ValueError("The groups list must match the phones list length.")
            selected_groups = groups
        else:
            selected_groups = [random.choice(list(messages.keys())) for _ in phones]

        if not messages:
            return "No messages available"

        set_keyboard_layout_to_english()
        random_delay(1.5, 2.8)
        print(f"[sending] Called with {len(phones)} phones, {len(selected_groups)} topics")
        for i, phone in enumerate(phones):
            print(f"[sending]   Phone {i}: {phone} | topic={selected_groups[i]}")

        if len(phones) == 0:
            print("[sending] ERROR: No phones to send")
            return "No phones to send"

        total_count = len(phones)
        processed = 0

        def emit_progress():
            if progress_callback is None:
                return
            try:
                progress_callback(processed, total_count)
            except Exception:
                pass

        rate_limiter = WhatsAppRateLimiter(limit_per_minute=20, limit_per_hour=120)
        whatsupp_ready()

        for i, phone in enumerate(phones):
            topic = selected_groups[i]
            context = contexts[i] if contexts and i < len(contexts) else None
            print(f"[sending] Sending with topic '{topic}' to {phone}")
            if not rate_limiter.wait_until_allowed(max_wait=60.0):
                break
            try:
                send_message(phone, messages, topic=topic, image=image, context=context)
                sent.append(phone)
            except Exception:
                unsent.append(phone)
                raise
            finally:
                processed += 1
                emit_progress()
            random_delay(0.7, 1.3)

        return_to_system_tab()
        return "ok"

    set_keyboard_layout_to_english()
    random_delay(1.5, 2.8)
    print(f"[sending] Called with {len(phones)} phones, {len(messages)} messages")
    for i, phone in enumerate(phones):
        print(f"[sending]   Phone {i}: {phone}")
    for i, msg in enumerate(messages):
        print(f"[sending]   Message {i}: len={len(str(msg))} content_sample={str(msg)[:50]!r}")
    if len(phones) == 0 or len(messages) == 0:
        print("[sending] ERROR: No phones or messages to send")
        return "No phones or messages to send"
    if len(phones) != len(messages) and len(messages) != 1:
        print(f"[sending] ERROR: Mismatch - {len(phones)} phones vs {len(messages)} messages")
        return "Number of phones and messages must be the same"

    total_count = len(phones)
    processed = 0

    def emit_progress():
        if progress_callback is None:
            return
        try:
            progress_callback(processed, total_count)
        except Exception:
            pass

    rate_limiter = WhatsAppRateLimiter(limit_per_minute=20, limit_per_hour=120)
    if len(messages) == 1:
        message = messages[0]
        print(f"[sending] Single message mode: {len(message)} chars")
        set_keyboard_layout_to_english()
        whatsupp_ready()
        for phone in phones:
            print(f"[sending] Sending to {phone}")
            if not rate_limiter.wait_until_allowed(max_wait=60.0):
                break
            try:
                send_message(phone, message, image)
                sent.append(phone)
            except Exception:
                unsent.append(phone)
                raise
            finally:
                processed += 1
                emit_progress()
            random_delay(0.7, 1.3)
    else:
        print(f"[sending] Multiple messages mode: {len(phones)} messages")
        whatsupp_ready()
        for i, phone in enumerate(phones):
            print(f"[sending] Sending message {i} ({len(messages[i])} chars) to {phone}")
            if not rate_limiter.wait_until_allowed(max_wait=60.0):
                break
            try:
                send_message(phone, str(messages[i]), image)
                sent.append(phone)
            except Exception:
                unsent.append(phone)
                raise
            finally:
                processed += 1
                emit_progress()
            random_delay(0.7, 1.3)

    return_to_system_tab()

if __name__ == "__main__":
    sent = []
    unsent = []
                

    image = "whatsapp_sender\image copy.png"
    sending(["01080922432"],["صلي علي سيدنا محمد صلي الله عليه وسلم"])
    #pyautogui.mouseInfo()
    print(f"total: {len(numbers)}")
    print(f"Sent: {len(sent)}")
    print(f"Unsent: {len(unsent)}")
    print(f"\n\nSent numbers: {sent}")
    print(f"\n\nUnsent numbers: {unsent}")
    ## TODO count send and unsent 
    ## TODO attach files
    ## TODO not get blocked
    ## TODO ENTRY
