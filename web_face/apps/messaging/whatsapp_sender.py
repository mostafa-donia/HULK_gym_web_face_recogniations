from collections import deque
from subprocess import Popen
from time import sleep
import ctypes
import io
import os
import random
import sys
import time

import pyautogui
pyautogui.FAILSAFE = False
import win32clipboard
from PIL import Image
from pyautogui import hotkey, press, write
from pygetwindow import getAllWindows, getActiveWindow
from pyperclip import copy, paste

sent = []
unsent = []

MESSAGE_SEND_MODE = "paste"
MESSAGE_CHAR_DELAY = 0.02


def apply_send_settings(settings=None):
    """Apply the configured WhatsApp sending mode and per-character delay."""
    global MESSAGE_SEND_MODE, MESSAGE_CHAR_DELAY
    if settings is None:
        return
    mode = str(settings.get("whatsapp_send_mode", "paste") or "paste").strip().lower()
    if mode not in {"typing", "paste"}:
        mode = "paste"
    try:
        delay = float(settings.get("whatsapp_letter_delay", MESSAGE_CHAR_DELAY) or MESSAGE_CHAR_DELAY)
    except (TypeError, ValueError):
        delay = MESSAGE_CHAR_DELAY
    MESSAGE_SEND_MODE = mode
    MESSAGE_CHAR_DELAY = max(0.0, min(delay, 0.5))
    return {"mode": MESSAGE_SEND_MODE, "char_delay": MESSAGE_CHAR_DELAY}


def random_delay(min_seconds: float = 0.25, max_seconds: float = 1.2) -> float:
    """Sleep for a random duration while preserving human-like flow."""
    delay = random.uniform(min_seconds, max_seconds)
    sleep(delay)
    return delay


def human_move_to(x: float, y: float, duration_range: tuple = (0.35, 0.5), jitter: int = 18) -> None:
    """Move the mouse in a slightly human-like, imperfect path."""
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


def set_keyboard_layout_to_english():
    """Detect current Windows keyboard language and switch to English (US) once if needed."""
    try:
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
        if current_lang == "en-US":
            return

        pyautogui.hotkey("alt", "shift")
        sleep(0.25)
    except Exception as e:
        print(f"[set_keyboard_layout_to_english] Warning: {e}")


def copy_file(file_path: str) -> bool:
    """
    Copy image (via CF_DIB) or file/document (via CF_HDROP) to Windows clipboard.
    Supports images, HTML invoices, PDF documents, and brochures.
    """
    if not file_path:
        return False

    abs_path = os.path.abspath(str(file_path))
    stem, ext = os.path.splitext(abs_path)
    if ext.lower() in [".html", ".htm"] and os.path.exists(stem + ".png"):
        abs_path = stem + ".png"

    if not os.path.exists(abs_path):
        print(f"[copy_file] File not found: {abs_path}")
        return False

    # 1. Try raster image via CF_DIB (JPG, PNG, BMP, WEBP, etc.)
    try:
        img = Image.open(abs_path)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]  # Remove BMP header
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        print(f"[copy_file] Copied image via CF_DIB: {abs_path}")
        return True
    except Exception:
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
        print(f"[copy_file] Copied file via CF_HDROP: {abs_path}")
        return True
    except Exception as e:
        print(f"[copy_file] Error copying file to clipboard: {e}")
        return False


def is_whatsapp_desktop_installed() -> tuple:
    """
    Checks if WhatsApp Desktop is installed on the Windows system.
    Supports:
    1. Microsoft Store WhatsApp Desktop (UWP / WindowsApps)
    2. Registry protocol (whatsapp://)
    3. Standalone executable paths
    4. Currently running WhatsApp desktop processes
    Returns: (is_installed: bool, message: str, details: dict)
    """
    details = {
        "store_app": False,
        "win32_exe": False,
        "protocol_registered": False,
        "running_process": False,
    }

    # 1. Check running processes
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            pname = (p.info.get("name") or "").lower()
            if "whatsapp" in pname:
                details["running_process"] = True
                break
    except Exception:
        pass

    # 2. Check Registry for whatsapp:// protocol
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp") as key:
            winreg.QueryValueEx(key, "URL Protocol")
            details["protocol_registered"] = True
    except Exception:
        pass

    # 3. Check App execution alias and Win32 executable locations
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
    app_data = os.environ.get("APPDATA", "")

    candidates = [
        os.path.join(local_app_data, "Microsoft", "WindowsApps", "WhatsApp.exe"),
        os.path.join(local_app_data, "WhatsApp", "WhatsApp.exe"),
        os.path.join(prog_files, "WhatsApp", "WhatsApp.exe"),
        os.path.join(prog_files_x86, "WhatsApp", "WhatsApp.exe"),
        os.path.join(app_data, "WhatsApp", "WhatsApp.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            details["win32_exe"] = True
            break

    # 4. Check WindowsApps directory patterns
    try:
        import glob
        matches = glob.glob(r"C:\Program Files\WindowsApps\*WhatsApp*")
        if matches:
            details["store_app"] = True
    except Exception:
        pass

    installed = details["protocol_registered"] or details["running_process"] or details["store_app"] or details["win32_exe"]
    if installed:
        msg = "تطبيق واتساب للكمبيوتر (WhatsApp Desktop) مثبت وجاهز للاستخدام."
    else:
        msg = "تطبيق واتساب للكمبيوتر (WhatsApp Desktop) غير مثبت على هذا الجهاز. يرجى تثبيته من Microsoft Store."

    return installed, msg, details


def copy_image_to_clipboard(image_path):
    """Backward compatibility alias for copy_file."""
    return copy_file(image_path)


def whatsupp_ready() -> bool:
    """
    Ensures WhatsApp Desktop (native Windows application) is installed, running, restored,
    and active in the foreground.
    Strictly works on WhatsApp Desktop ONLY (no Chrome or WhatsApp Web).
    """
    if "test" in sys.argv:
        return True

    installed, msg, _ = is_whatsapp_desktop_installed()
    if not installed:
        print(f"[whatsupp_ready] ERROR: {msg}")
        return False

    print("[whatsupp_ready] Checking for WhatsApp Desktop window...")

    def find_whatsapp_window():
        try:
            from pygetwindow import getAllWindows
            all_win = getAllWindows()
        except Exception:
            all_win = []

        matching = []
        for w in all_win:
            title = getattr(w, "title", "") or ""
            # Must contain WhatsApp or واتساب, and NOT belong to a browser
            if ("WhatsApp" in title or "واتساب" in title) and not any(
                b in title for b in ["Chrome", "Edge", "Firefox", "Brave", "Opera"]
            ):
                matching.append(w)
        return matching

    whatsapp_windows = find_whatsapp_window()

    # If not running / not opened, launch WhatsApp Desktop via whatsapp: protocol
    if not whatsapp_windows:
        print("[whatsupp_ready] WhatsApp Desktop is not running. Launching via 'start whatsapp:' ...")
        Popen("start whatsapp:", shell=True)
        # Wait up to 15 seconds for WhatsApp window to appear
        for _ in range(30):
            sleep(0.5)
            whatsapp_windows = find_whatsapp_window()
            if whatsapp_windows:
                break

    if not whatsapp_windows:
        print("[whatsupp_ready] Could not find or open WhatsApp Desktop window.")
        return False

    target = whatsapp_windows[0]
    hwnd = getattr(target, "_hWnd", None)

    # Restore if minimized and bring to foreground reliably via Win32 API
    try:
        if hwnd:
            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5
            user32.SetForegroundWindow(hwnd)
        else:
            if getattr(target, "isMinimized", False):
                target.restore()
            target.activate()
    except Exception as e:
        print(f"[whatsupp_ready] Focus warning: {e}")

    sleep(0.8)
    print(f"[whatsupp_ready] WhatsApp Desktop is focused: {getattr(target, 'title', 'WhatsApp')}")
    return True


def return_to_system_tab() -> bool:
    """
    Seamlessly switches focus back to the previously active system window using Alt+Tab.
    """
    print("[return_to_system_tab] Returning focus via Alt+Tab...")
    sleep(0.3)
    try:
        hotkey("alt", "tab")
        sleep(0.3)
        return True
    except Exception as e:
        print(f"[return_to_system_tab] Error: {e}")
        return False


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


def send_message(
    phone: str,
    message: str = "",
    image: str = None,
    x_search: int = 300,
    y_search: int = 190,
    return_to_system: bool = False,
    topic: str = None,
    message_bank: dict = None,
    context: dict = None,
) -> bool:
    """
    Sends a WhatsApp message and/or file attachment (invoice, report, image) to the specified phone.
    Works strictly on WhatsApp Desktop.
    """
    global sent, unsent
    if "test" in sys.argv:
        return True

    if isinstance(message, dict):
        message_bank = message
        topic = topic or random.choice(list(message_bank.keys())) if isinstance(message_bank, dict) and message_bank else None
        message = choose_message_for_group(message_bank, topic) if topic else ""
    elif isinstance(message_bank, dict):
        chosen_topic = topic or random.choice(list(message_bank.keys()))
        message = choose_message_for_group(message_bank, chosen_topic)

    if context and isinstance(context, dict):
        try:
            message = message.format(**context)
        except Exception:
            pass

    phone = str(phone).strip()
    print(f"[send_message] Sending to: {phone} via WhatsApp Desktop")

    # 1. Focus WhatsApp Desktop and switch keyboard layout
    if not whatsupp_ready():
        print(f"[send_message] WhatsApp Desktop could not be focused for {phone}")
        return False

    set_keyboard_layout_to_english()
    random_delay(0.2, 0.4)

    # 2. Focus search in WhatsApp Desktop (Ctrl+F is native search in WhatsApp Desktop)
    hotkey("ctrl", "f")
    random_delay(0.2, 0.3)

    if x_search and y_search:
        try:
            human_move_to(x_search, y_search)
            pyautogui.click()
            random_delay(0.15, 0.25)
        except Exception:
            pass

    # Clear previous search content
    hotkey("ctrl", "a")
    press("backspace")
    random_delay(0.1, 0.2)

    # Paste phone number to avoid keyboard layout discrepancies
    copy(phone)
    hotkey("ctrl", "v")
    random_delay(1.2, 1.8)
    press("enter")
    random_delay(1.8, 2.8)

    # 3. Paste file / invoice attachment if present
    # Check if image path exists (or if .html has a matching .png)
    target_img = None
    if image and isinstance(image, str):
        if os.path.exists(image):
            target_img = image
        else:
            stem, ext = os.path.splitext(image)
            if ext.lower() == ".html" and os.path.exists(stem + ".png"):
                target_img = stem + ".png"

    if target_img:
        print(f"[send_message] Attaching file/invoice image: {target_img}")
        if copy_file(target_img):
            random_delay(0.4, 0.7)
            hotkey("ctrl", "v")
            # Wait for WhatsApp Desktop attachment preview modal to appear
            random_delay(2.5, 3.8)
            if message:
                copy(message)
                random_delay(0.3, 0.6)
                hotkey("ctrl", "v")
                random_delay(0.4, 0.8)
            press("enter")
            random_delay(1.5, 2.5)
        else:
            print("[send_message] copy_file failed, falling back to message text")
            if message:
                copy(message)
                random_delay(0.3, 0.6)
                hotkey("ctrl", "v")
                random_delay(0.3, 0.6)
                press("enter")
                random_delay(1.2, 2.0)
    else:
        if message:
            copy(message)
            random_delay(0.3, 0.6)
            hotkey("ctrl", "v")
            random_delay(0.3, 0.6)
            press("enter")
            random_delay(1.2, 2.0)

    # 4. Clean search bar without destructive coordinate clicks
    try:
        hotkey("ctrl", "f")
        random_delay(0.15, 0.25)
        hotkey("ctrl", "a")
        press("backspace")
        press("esc")
    except Exception:
        pass

    if return_to_system:
        return_to_system_tab()

    return True


def sending(
    phones: list,
    messages: list,
    groups: list = None,
    image: str = None,
    progress_callback=None,
    contexts: list = None,
    x_search: int = 300,
    y_search: int = 190,
):
    global sent, unsent
    sent = []
    unsent = []

    set_keyboard_layout_to_english()
    random_delay(0.2, 0.8)

    if not phones or not messages:
        print("[sending] No phones or messages to send")
        return "No phones or messages to send"

    # Support dictionary of messages with groups/topics
    if isinstance(messages, dict):
        if groups is not None:
            if len(groups) != len(phones):
                raise ValueError("The groups list must match the phones list length.")
            selected_groups = groups
        else:
            selected_groups = [random.choice(list(messages.keys())) for _ in phones]

        total_count = len(phones)
        processed = 0

        for i, phone in enumerate(phones):
            if i == 0:
                whatsupp_ready()
            topic = selected_groups[i]
            context = contexts[i] if contexts and i < len(contexts) else None
            msg_text = choose_message_for_group(messages, topic)
            res = send_message(phone, msg_text, image=image, context=context, x_search=x_search, y_search=y_search)
            if res:
                sent.append(phone)
            else:
                unsent.append(phone)
            processed += 1
            if progress_callback:
                try:
                    progress_callback(processed, total_count)
                except Exception:
                    pass
            sleep(0.5)

        return_to_system_tab()
        return f"total: {len(phones)}, Sent: {len(sent)}, Unsent: {len(unsent)}"

    if len(phones) != len(messages) and len(messages) != 1:
        print("[sending] Number of phones and messages must be the same")
        return "Number of phones and messages must be the same"

    total_count = len(phones)
    processed = 0

    if len(messages) == 1:
        message = messages[0]
        for i, phone in enumerate(phones):
            if i == 0:
                whatsupp_ready()
            res = send_message(phone, message, image=image, x_search=x_search, y_search=y_search)
            if res:
                sent.append(phone)
            else:
                unsent.append(phone)
            processed += 1
            if progress_callback:
                try:
                    progress_callback(processed, total_count)
                except Exception:
                    pass
            sleep(0.5)
    else:
        for i, phone in enumerate(phones):
            if i == 0:
                whatsupp_ready()
            res = send_message(phone, str(messages[i]), image=image, x_search=x_search, y_search=y_search)
            if res:
                sent.append(phone)
            else:
                unsent.append(phone)
            processed += 1
            if progress_callback:
                try:
                    progress_callback(processed, total_count)
                except Exception:
                    pass
            sleep(0.5)

    return_to_system_tab()
    return f"""
    total: {len(phones)}
    Sent: {len(sent)}
    Unsent: {len(unsent)}
    Unsent numbers: {unsent}
    """


if __name__ == "__main__":
    phones = ["01080922432"]
    messages = ["صلي علي سيدنا محمد صلي الله عليه وسلم"]
    image = r"logo.png"
    result = sending(phones, messages, image=image, y_search=200)
    print(result)
