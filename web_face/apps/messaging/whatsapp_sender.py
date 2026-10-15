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


def copy_image_to_clipboard(image_path):
    """Backward compatibility alias for copy_file."""
    return copy_file(image_path)


def whatsupp_ready() -> bool:
    """
    Ensures WhatsApp Web window/tab is active, restored, and focused in the foreground.
    Does NOT minimize the browser or trigger conflicting OS window toggling.
    """
    if "test" in sys.argv:
        return True

    print("[whatsupp_ready] Checking Chrome and WhatsApp windows...")

    # 1. Check for standalone/app window with WhatsApp in title
    try:
        direct_whatsapp = [
            w for w in getAllWindows()
            if ("WhatsApp" in getattr(w, "title", "") or "واتساب" in getattr(w, "title", ""))
            and getattr(w, "visible", True) and getattr(w, "width", 0) > 200
        ]
        if direct_whatsapp:
            target = direct_whatsapp[0]
            if getattr(target, "isMinimized", False):
                target.restore()
            target.activate()
            sleep(0.8)
            print(f"[whatsupp_ready] Focused direct WhatsApp window: {target.title}")
            return True
    except Exception as e:
        print(f"[whatsupp_ready] Error checking direct WhatsApp: {e}")

    # 2. Check for Chrome/Edge/Browser windows
    try:
        all_windows = getAllWindows()
    except Exception:
        all_windows = []

    chrome_windows = [
        w for w in all_windows
        if ("Chrome" in getattr(w, "title", "") or "Edge" in getattr(w, "title", "") or "Brave" in getattr(w, "title", ""))
        and getattr(w, "visible", True) and getattr(w, "width", 0) > 200
    ]

    if not chrome_windows:
        chrome_windows = [w for w in all_windows if "Chrome" in getattr(w, "title", "")]

    if not chrome_windows:
        print("[whatsupp_ready] No Chrome window found. Launching WhatsApp Web...")
        Popen("start chrome https://web.whatsapp.com", shell=True)
        for _ in range(30):
            sleep(0.5)
            try:
                active_win = getActiveWindow()
                title = getattr(active_win, "title", "") or ""
                if "WhatsApp" in title or "واتساب" in title:
                    break
            except Exception:
                pass
    else:
        chrome = chrome_windows[0]
        if getattr(chrome, "isMinimized", False):
            chrome.restore()
        chrome.activate()
        sleep(0.8)

    # 3. Cycle tabs to ensure WhatsApp tab is active
    whats_tab_found = False
    for _ in range(25):
        try:
            active_win = getActiveWindow()
            active_title = getattr(active_win, "title", "") or ""
            print(f"[whatsupp_ready] Active window title: {active_title}")
            if "WhatsApp" in active_title or "واتساب" in active_title:
                print("[whatsupp_ready] Switched to WhatsApp tab.")
                whats_tab_found = True
                break
        except Exception:
            pass
        hotkey("ctrl", "tab")
        sleep(0.2)

    if whats_tab_found:
        print("[whatsupp_ready] WhatsApp tab is active.")
        return True

    # 4. If WhatsApp tab not open inside Chrome, launch it
    print("[whatsupp_ready] WhatsApp tab not found. Opening new one in Chrome...")
    Popen("start chrome https://web.whatsapp.com", shell=True)
    for _ in range(30):
        sleep(0.5)
        try:
            active_win = getActiveWindow()
            title = getattr(active_win, "title", "") or ""
            if "WhatsApp" in title or "واتساب" in title:
                break
        except Exception:
            pass

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
    Uses proven reliable search coordinates, file pasting, and search validation.
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
    print(f"[send_message] Sending to: {phone}")

    # 1. Focus WhatsApp and set keyboard layout
    whatsupp_ready()
    set_keyboard_layout_to_english()
    random_delay(0.2, 0.5)

    # 2. Click search box and search for contact
    human_move_to(x_search, y_search)
    pyautogui.click()
    random_delay(0.15, 0.3)

    hotkey("ctrl", "a")
    write(" ")
    write(phone)
    random_delay(0.8, 1.4)
    press("enter")
    random_delay(1.5, 2.5)

    # 3. Paste file / invoice attachment if present
    has_image = bool(image and isinstance(image, str) and os.path.exists(image))
    if has_image:
        print(f"[send_message] Attaching file/invoice: {image}")
        if copy_file(image):
            random_delay(0.3, 0.6)
            hotkey("ctrl", "v")
            # Wait for WhatsApp attachment preview modal (5 to 8s as proven)
            random_delay(5.0, 8.0)
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

    # 4. Verify chat opened by checking if search box still holds phone number
    human_move_to(x_search, y_search)
    pyautogui.click()
    hotkey("ctrl", "a")
    hotkey("ctrl", "c")
    random_delay(0.2, 0.4)
    search = paste()
    x = len(phone) + 1
    if search and search[0:x] == " " + phone:
        print(f"[send_message] Phone {phone} not found in WhatsApp (search box still holds number)")
        press("delete")
        if return_to_system:
            return_to_system_tab()
        return False

    press("delete")
    sleep(0.2)

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
