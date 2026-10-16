from collections import deque
from subprocess import Popen
from time import sleep
import ctypes
from ctypes import wintypes
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
from pyperclip import copy, paste

sent = []
unsent = []

MESSAGE_SEND_MODE = "paste"
MESSAGE_CHAR_DELAY = 0.02

ORIGINAL_BROWSER_HWND = None


def ensure_desktop_attached():
    """Ensure process and thread are attached to interactive desktop WinSta0\\Default."""
    try:
        user32 = ctypes.windll.user32
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as e:
        print(f"[ensure_desktop_attached] Warning: {e}")


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
    Copy image (via CF_DIB + CF_HDROP) or file/document (via CF_HDROP) to Windows clipboard.
    Supports images, HTML invoices, PDF documents, and brochures.
    """
    if not file_path:
        return False

    abs_path = os.path.abspath(str(file_path))
    # If not found directly, check MEDIA_ROOT
    if not os.path.exists(abs_path):
        try:
            from django.conf import settings
            cand = os.path.join(settings.MEDIA_ROOT, str(file_path))
            if os.path.exists(cand):
                abs_path = os.path.abspath(cand)
        except Exception:
            pass

    stem, ext = os.path.splitext(abs_path)
    # If HTML invoice, prefer companion PNG image if available
    if ext.lower() in [".html", ".htm"]:
        if os.path.exists(stem + ".png"):
            abs_path = stem + ".png"
            stem, ext = os.path.splitext(abs_path)
        else:
            try:
                from django.conf import settings
                cand_png = os.path.join(settings.MEDIA_ROOT, "invoices", os.path.basename(stem) + ".png")
                if os.path.exists(cand_png):
                    abs_path = os.path.abspath(cand_png)
                    stem, ext = os.path.splitext(abs_path)
            except Exception:
                pass

    if not os.path.exists(abs_path):
        print(f"[copy_file] File not found: {abs_path}")
        return False

    # Universal 64-bit safe CF_HDROP and CF_DIB clipboard placement
    try:
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

        # 1. Primary format: CF_HDROP (15) so WhatsApp Desktop (UWP/WinUI 3) accepts the file/image directly
        win32clipboard.SetClipboardData(15, h_global)

        # 2. Secondary format: CF_DIB if image for legacy or browser paste compatibility
        try:
            img = Image.open(abs_path)
            output = io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]  # Remove BMP header
            output.close()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        except Exception:
            pass

        win32clipboard.CloseClipboard()
        print(f"[copy_file] Copied file to clipboard (CF_HDROP + CF_DIB): {abs_path}")
        return True
    except Exception as e:
        print(f"[copy_file] Error copying file to clipboard: {e}")
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False


def copy_image_to_clipboard(image_path):
    """Backward compatibility alias for copy_file."""
    return copy_file(image_path)


def is_whatsapp_desktop_installed() -> tuple:
    """
    Checks if WhatsApp Desktop is installed on the Windows system.
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


def is_whatsapp_desktop_window(hwnd) -> bool:
    """Checks if the given HWND is the native WhatsApp Desktop app (not a web browser)."""
    if not hwnd:
        return False
    try:
        import win32gui
        cls_name = (win32gui.GetClassName(hwnd) or "")
        title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
        if cls_name == "WinUIDesktopWin32WindowClass":
            return True
        if title in ("whatsapp", "واتساب"):
            return True
        if ("whatsapp" in title or "واتساب" in title) and not any(
            b in title for b in ["google chrome", "chrome", "edge", "firefox", "brave", "opera", "hulk", "gym", "cina"]
        ):
            return True
    except Exception:
        pass
    return False


def find_system_browser_hwnd():
    """Finds the existing browser window running the gym system without opening any new tabs."""
    try:
        import win32gui
        tier1 = []  # Browser window with Gym System title
        tier2 = []  # Any Google Chrome / Edge / Brave / Firefox window

        def enum_cb(h, _):
            if win32gui.IsWindowVisible(h) and not is_whatsapp_desktop_window(h):
                t = (win32gui.GetWindowText(h) or "").lower()
                if not t:
                    return True
                is_browser = any(b in t for b in ["google chrome", "microsoft​ edge", "edge", "firefox", "brave", "opera"])
                is_gym = any(k in t for k in ["hulk", "gym", "cina", "127.0.0.1", "localhost", "الرئيسية", "لوحة", "إيصالات", "تذكيرات"])
                if is_browser and is_gym:
                    tier1.append(h)
                elif is_gym and "chrome" in (win32gui.GetClassName(h) or "").lower():
                    tier1.append(h)
                elif is_browser:
                    tier2.append(h)
            return True

        win32gui.EnumWindows(enum_cb, None)
        if tier1:
            return tier1[0]
        if tier2:
            return tier2[0]
    except Exception as e:
        print(f"[find_system_browser_hwnd] Warning: {e}")
    return None


def force_activate_window(hwnd, maximize: bool = False) -> bool:
    """
    Reliably brings the specified HWND to the foreground on Windows,
    bypassing ForegroundLockTimeout restrictions by attaching thread input
    from the current thread and foreground thread.
    If maximize=True, guarantees the window is maximized to full screen (SW_MAXIMIZE = 3).
    """
    if not hwnd:
        return False
    try:
        ensure_desktop_attached()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        import win32gui

        if not win32gui.IsWindow(hwnd):
            return False

        fore_hwnd = user32.GetForegroundWindow()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
        cur_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)

        # Unlock Windows foreground lock timeout
        user32.SystemParametersInfoW(0x2001, 0, 0, 3)

        if fore_thread and fore_thread != cur_thread:
            user32.AttachThreadInput(fore_thread, cur_thread, True)
        if target_thread and target_thread != cur_thread:
            user32.AttachThreadInput(target_thread, cur_thread, True)

        try:
            user32.keybd_event(0x12, 0, 0, 0)  # Alt key down
            if maximize:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE first if minimized
                    sleep(0.15)
                user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE (full screen window)
            else:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                else:
                    placement = win32gui.GetWindowPlacement(hwnd)
                    if placement and placement[1] == 3:
                        user32.ShowWindow(hwnd, 3)  # Preserve maximized state
                    else:
                        user32.ShowWindow(hwnd, 5)  # SW_SHOW
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SwitchToThisWindow(hwnd, True)
        finally:
            user32.keybd_event(0x12, 0, 2, 0)  # Alt key up
            if fore_thread and fore_thread != cur_thread:
                user32.AttachThreadInput(fore_thread, cur_thread, False)
            if target_thread and target_thread != cur_thread:
                user32.AttachThreadInput(target_thread, cur_thread, False)

        sleep(0.15)
        return True
    except Exception as e:
        print(f"[force_activate_window] Warning: {e}")
        return False


def remember_current_window():
    """Remember the foreground browser/system window HWND before activating WhatsApp Desktop."""
    global ORIGINAL_BROWSER_HWND
    try:
        ensure_desktop_attached()
        user32 = ctypes.windll.user32
        import win32gui

        hwnd = user32.GetForegroundWindow()
        if hwnd and not is_whatsapp_desktop_window(hwnd):
            title = (win32gui.GetWindowText(hwnd) or "").lower()
            is_browser = any(b in title for b in ["google chrome", "edge", "firefox", "brave", "opera", "hulk", "gym", "cina", "127.0.0.1", "localhost"])
            if is_browser:
                ORIGINAL_BROWSER_HWND = hwnd
                safe_title = title.encode("ascii", "replace").decode("ascii")
                print(f"[remember_current_window] Saved active system browser HWND: {hwnd} ({safe_title})")
                return

        if not ORIGINAL_BROWSER_HWND or not win32gui.IsWindow(ORIGINAL_BROWSER_HWND) or is_whatsapp_desktop_window(ORIGINAL_BROWSER_HWND):
            found_hwnd = find_system_browser_hwnd()
            if found_hwnd:
                ORIGINAL_BROWSER_HWND = found_hwnd
                print(f"[remember_current_window] Located system browser HWND: {found_hwnd}")
    except Exception as e:
        print(f"[remember_current_window] Warning: {e}")


def whatsupp_ready() -> bool:
    """
    Ensures WhatsApp Desktop (native Windows application) is installed, running,
    MAXIMIZED to full screen, and active in the foreground.
    """
    ensure_desktop_attached()
    installed, msg, _ = is_whatsapp_desktop_installed()
    if not installed:
        print(f"[whatsupp_ready] ERROR: {msg}")
        return False

    # Save active browser window before WhatsApp steals focus
    remember_current_window()

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "WhatsApp")
    if not hwnd:
        hwnd = user32.FindWindowW("WinUIDesktopWin32WindowClass", None)

    if not hwnd:
        print("[whatsupp_ready] WhatsApp Desktop is not visible. Launching via 'start whatsapp:' ...")
        Popen("start whatsapp:", shell=True)
        for _ in range(20):
            sleep(0.5)
            hwnd = user32.FindWindowW(None, "WhatsApp") or user32.FindWindowW("WinUIDesktopWin32WindowClass", None)
            if hwnd:
                break

    if not hwnd:
        print("[whatsupp_ready] Could not find or open WhatsApp Desktop window.")
        return False

    # Activate and MAXIMIZE WhatsApp Desktop to full screen (SW_MAXIMIZE = 3)
    force_activate_window(hwnd, maximize=True)
    user32.ShowWindow(hwnd, 3)

    sleep(0.8)
    print(f"[whatsupp_ready] WhatsApp Desktop maximized and focused: HWND={hwnd}")
    return True


def get_browser_executable() -> str:
    """Finds Google Chrome or Microsoft Edge executable on Windows."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "chrome"


def return_to_system_window(url: str = "http://127.0.0.1:8000/messaging/") -> bool:
    """
    Seamlessly brings the original Google Chrome / browser window back to the foreground
    WITHOUT opening any new tabs.
    """
    global ORIGINAL_BROWSER_HWND
    try:
        ensure_desktop_attached()
        import win32gui

        target_hwnd = ORIGINAL_BROWSER_HWND
        if not target_hwnd or not win32gui.IsWindow(target_hwnd) or is_whatsapp_desktop_window(target_hwnd):
            target_hwnd = find_system_browser_hwnd()

        if target_hwnd and win32gui.IsWindow(target_hwnd):
            force_activate_window(target_hwnd, maximize=False)
            print(f"[return_to_system_window] Restored and focused original browser HWND: {target_hwnd} (no new tab opened)")
            return True

        # Fallback only if no browser window is open at all on the system
        browser_exe = get_browser_executable()
        if os.path.isabs(browser_exe):
            Popen([browser_exe, url])
        else:
            Popen(f'start "" "{browser_exe}" "{url}"', shell=True)
        return True
    except Exception as e:
        print(f"[return_to_system_window] Warning: {e}")
        return False


def return_to_system_tab() -> bool:
    """Backward compatibility alias for return_to_system_window."""
    return return_to_system_window()


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
    x_search: int = None,
    y_search: int = None,
    return_to_system: bool = False,
    topic: str = None,
    message_bank: dict = None,
    context: dict = None,
) -> bool:
    """
    Sends a WhatsApp message and/or file attachment (invoice, report, image) to the specified phone.
    Works strictly on WhatsApp Desktop using user-configured search bar coordinates.
    """
    global sent, unsent

    # Retrieve coordinates from GymProfile if not explicitly provided
    if x_search is None or y_search is None:
        try:
            from apps.core.models import GymProfile
            prof = GymProfile.get_solo()
            x_search = prof.whatsapp_search_x if prof.whatsapp_search_x is not None else 300
            y_search = prof.whatsapp_search_y if prof.whatsapp_search_y is not None else 190
        except Exception:
            x_search = x_search or 300
            y_search = y_search or 190

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
    print(f"[send_message] Sending to: {phone} (search coords: x={x_search}, y={y_search})")

    # 1. Focus WhatsApp Desktop and switch keyboard layout
    if not whatsupp_ready():
        print(f"[send_message] WhatsApp Desktop could not be focused for {phone}")
        return False

    set_keyboard_layout_to_english()
    random_delay(0.2, 0.4)

    # 2. Focus the search bar via coordinates
    human_move_to(x_search, y_search)
    pyautogui.click()
    random_delay(0.15, 0.25)

    # Clear previous search content cleanly and type space then phone
    hotkey("ctrl", "a")
    write(" ")
    write(phone)
    random_delay(0.8, 1.2)
    press("enter")
    random_delay(1.2, 1.6)

    # Calculate chat message input area coordinates dynamically from WhatsApp window
    chat_input_x = None
    chat_input_y = None
    try:
        user32 = ctypes.windll.user32
        import win32gui
        w_hwnd = user32.FindWindowW(None, "WhatsApp") or user32.FindWindowW("WinUIDesktopWin32WindowClass", None)
        if w_hwnd:
            rect = win32gui.GetWindowRect(w_hwnd)
            w_width = rect[2] - rect[0]
            w_height = rect[3] - rect[1]
            chat_input_x = rect[0] + int(w_width * 0.65)
            chat_input_y = rect[1] + int(w_height - 45)
    except Exception:
        pass

    # Click in the chat message input box to ensure chat input has focus
    if chat_input_x and chat_input_y:
        human_move_to(chat_input_x, chat_input_y)
        pyautogui.click()
        random_delay(0.25, 0.45)

    # 3. Paste file / invoice attachment if present
    target_img = None
    if image and isinstance(image, str):
        if os.path.exists(image):
            target_img = image
        else:
            try:
                from django.conf import settings
                cand = os.path.join(settings.MEDIA_ROOT, image)
                if os.path.exists(cand):
                    target_img = cand
            except Exception:
                pass

        if not target_img:
            stem, ext = os.path.splitext(image)
            if ext.lower() in [".html", ".htm"]:
                if os.path.exists(stem + ".png"):
                    target_img = stem + ".png"
                else:
                    try:
                        from django.conf import settings
                        cand_png = os.path.join(settings.MEDIA_ROOT, stem + ".png")
                        if os.path.exists(cand_png):
                            target_img = cand_png
                    except Exception:
                        pass

    if target_img and os.path.exists(target_img):
        print(f"[send_message] Attaching file/invoice: {target_img}")
        if copy_file(target_img):
            random_delay(0.35, 0.6)
            hotkey("ctrl", "v")
            # Wait 3.5 to 5.0 seconds for WhatsApp attachment preview to fully render
            random_delay(3.5, 5.0)
            if message:
                copy(message)
                random_delay(0.25, 0.4)
                hotkey("ctrl", "v")
                random_delay(0.25, 0.4)
            press("enter")
            random_delay(1.5, 2.5)
        else:
            print("[send_message] copy_file failed, falling back to message text")
            if message:
                copy(message)
                random_delay(0.25, 0.4)
                hotkey("ctrl", "v")
                random_delay(0.25, 0.4)
                press("enter")
                random_delay(1.0, 1.8)
    else:
        if message:
            copy(message)
            random_delay(0.25, 0.4)
            hotkey("ctrl", "v")
            random_delay(0.25, 0.4)
            press("enter")
            random_delay(1.0, 1.8)

    # 4. Verification Check: Check if search still contains the typed phone
    human_move_to(x_search, y_search)
    pyautogui.click()
    hotkey("ctrl", "a")
    hotkey("ctrl", "c")
    random_delay(0.25, 0.45)
    search = paste()
    x = len(phone) + 1
    if search and search[0:x] == " " + phone:
        print(f"[send_message] Target contact {phone} was NOT found on WhatsApp.")
        hotkey("ctrl", "a")
        press("backspace")
        press("esc")
        if return_to_system:
            return_to_system_window()
        return False

    # Clear search bar cleanly
    hotkey("ctrl", "a")
    press("backspace")
    press("esc")

    # 5. Return focus to browser if requested
    if return_to_system:
        return_to_system_window()

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

            result = send_message(
                phone,
                msg_text,
                image,
                x_search=x_search,
                y_search=y_search,
                return_to_system=False,
                context=context,
            )
            processed += 1
            if result:
                sent.append(phone)
            else:
                unsent.append(phone)

            if progress_callback:
                progress_callback(processed, total_count, phone, result)
            sleep(0.5)

    elif len(messages) == 1:
        message = messages[0]
        total_count = len(phones)
        for i, phone in enumerate(phones):
            if i == 0:
                whatsupp_ready()
            context = contexts[i] if contexts and i < len(contexts) else None
            result = send_message(
                phone,
                message,
                image,
                x_search=x_search,
                y_search=y_search,
                return_to_system=False,
                context=context,
            )
            if result:
                sent.append(phone)
            else:
                unsent.append(phone)

            if progress_callback:
                progress_callback(i + 1, total_count, phone, result)
            sleep(0.5)
    else:
        if len(phones) != len(messages):
            print("[sending] Number of phones and messages must be the same")
            return "Number of phones and messages must be the same"

        total_count = len(phones)
        for i, phone in enumerate(phones):
            if i == 0:
                whatsupp_ready()
            context = contexts[i] if contexts and i < len(contexts) else None
            result = send_message(
                phone,
                messages[i],
                image,
                x_search=x_search,
                y_search=y_search,
                return_to_system=False,
                context=context,
            )
            if result:
                sent.append(phone)
            else:
                unsent.append(phone)

            if progress_callback:
                progress_callback(i + 1, total_count, phone, result)
            sleep(0.5)

    return_to_system_window()
    return f"""
    total: {len(phones)}
    Sent: {len(sent)}
    Unsent: {len(unsent)}
    Unsent numbers: {unsent}
    """
