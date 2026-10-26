import os
import io
import re
import sys
import time
import math
import random
import ctypes
from ctypes import wintypes
from subprocess import Popen
from typing import Optional, Tuple, Dict, Any, Callable

import pyautogui
pyautogui.FAILSAFE = False

try:
    import win32clipboard
    import win32gui
except ImportError:
    win32clipboard = None
    win32gui = None

from PIL import Image
from pyperclip import copy, paste


class WhatsAppKillSwitchTriggered(Exception):
    """Raised immediately when the emergency hotkey is detected during WhatsApp dispatch."""
    pass


class WhatsAppEngine:
    def __init__(self):
        self.kill_switch_requested = False
        self.kill_switch_hotkey = "ctrl+k"
        self.search_x = 300
        self.search_y = 190
        self.send_mode = "paste"  # "typing" or "paste"
        self.letter_delay = 0.02
        self.min_delay = 6.0
        self.max_delay = 14.0
        self.human_mouse = True
        self.original_window_hwnd = None
        self.is_sending = False

    def reset_kill_switch(self):
        self.kill_switch_requested = False

    def check_kill_switch(self):
        """
        Non-blocking physical key check using GetAsyncKeyState across the entire OS.
        Triggers instantly if user presses the kill switch (default: Ctrl+K).
        """
        if self.kill_switch_requested:
            raise WhatsAppKillSwitchTriggered(f"تم إيقاف الإرسال فوراً بواسطة زر الطوارئ ({self.kill_switch_hotkey})")

        user32 = ctypes.windll.user32
        hotkey_str = self.kill_switch_hotkey.lower().strip()
        keys = [k.strip() for k in hotkey_str.split("+")]

        vk_map = {
            "ctrl": 0x11, "control": 0x11,
            "shift": 0x10,
            "alt": 0x12,
            "esc": 0x1B, "escape": 0x1B,
            "space": 0x20,
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
            "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
            "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
        }

        all_pressed = True
        for k in keys:
            if k in vk_map:
                vk = vk_map[k]
            elif len(k) == 1 and k.isalnum():
                vk = ord(k.upper())
            else:
                all_pressed = False
                break

            if not (user32.GetAsyncKeyState(vk) & 0x8000):
                all_pressed = False
                break

        if all_pressed:
            self.kill_switch_requested = True
            raise WhatsAppKillSwitchTriggered(f"تم إيقاف الإرسال فوراً بواسطة زر الطوارئ ({self.kill_switch_hotkey})")

    def safe_delay(self, seconds: float, step: float = 0.05):
        """Sleeps safely while continuously listening for the kill switch."""
        end_time = time.time() + seconds
        while time.time() < end_time:
            self.check_kill_switch()
            time.sleep(min(step, max(0.001, end_time - time.time())))

    def random_delay(self, min_sec: Optional[float] = None, max_sec: Optional[float] = None) -> float:
        min_s = min_sec if min_sec is not None else self.min_delay
        max_s = max_sec if max_sec is not None else self.max_delay
        actual = random.uniform(min_s, max_s)
        self.safe_delay(actual)
        return actual

    def human_move_to(self, target_x: int, target_y: int, duration: float = 0.35):
        """Moves mouse naturally using a smooth easing curve and subtle random jitter."""
        if not self.human_mouse:
            pyautogui.moveTo(target_x, target_y)
            return

        start_x, start_y = pyautogui.position()
        dist = math.hypot(target_x - start_x, target_y - start_y)
        if dist < 10:
            pyautogui.moveTo(target_x, target_y)
            return

        steps = max(12, int(dist / 25))
        step_time = max(0.008, duration / steps)

        for i in range(1, steps + 1):
            self.check_kill_switch()
            t = i / steps
            # Smooth ease-out quad
            ease = -t * (t - 2.0)
            cur_x = int(start_x + (target_x - start_x) * ease + random.uniform(-1.5, 1.5))
            cur_y = int(start_y + (target_y - start_y) * ease + random.uniform(-1.5, 1.5))
            pyautogui.moveTo(cur_x, cur_y)
            time.sleep(step_time)

        pyautogui.moveTo(target_x, target_y)

    def set_keyboard_layout_to_english(self):
        """Switches Windows keyboard layout to English (0x0409) to prevent Arabic layout issues."""
        try:
            user32 = ctypes.windll.user32
            HWND_BROADCAST = 0xFFFF
            WM_INPUTLANGCHANGEREQUEST = 0x0050
            hkl = user32.LoadKeyboardLayoutW("00000409", 1)
            user32.PostMessageW(HWND_BROADCAST, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
        except Exception:
            pass

    def copy_file_to_clipboard(self, file_path: str) -> bool:
        """
        Copies any file (image, PDF, excel, docx) to clipboard with CF_HDROP (15) and CF_DIB (if image)
        so WhatsApp Desktop accepts it via Ctrl+V.
        """
        if not win32clipboard:
            return False

        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return False

        try:
            class DROPFILES(ctypes.Structure):
                _fields_ = [
                    ("pFiles", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                    ("fNC", wintypes.BOOL),
                    ("fWide", wintypes.BOOL),
                ]

            kernel32 = ctypes.windll.kernel32
            offset = ctypes.sizeof(DROPFILES)
            file_bytes = (abs_path + "\0\0").encode("utf-16le")
            total_size = offset + len(file_bytes)

            GHND = 0x0042
            h_global = kernel32.GlobalAlloc(GHND, total_size)
            if not h_global:
                return False

            ptr = kernel32.GlobalLock(h_global)
            if not ptr:
                return False

            df = DROPFILES(pFiles=offset, pt=wintypes.POINT(0, 0), fNC=False, fWide=True)
            ctypes.memmove(ptr, ctypes.byref(df), offset)
            ctypes.memmove(ptr + offset, file_bytes, len(file_bytes))
            kernel32.GlobalUnlock(h_global)

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()

            # CF_HDROP (15)
            win32clipboard.SetClipboardData(15, h_global)

            # Secondary CF_DIB if image for web/legacy fallback
            try:
                img = Image.open(abs_path)
                output = io.BytesIO()
                img.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]  # Strip BMP header
                output.close()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            except Exception:
                pass

            win32clipboard.CloseClipboard()
            return True
        except Exception as e:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return False

    def find_whatsapp_window(self) -> Optional[int]:
        """Finds WhatsApp Desktop window HWND."""
        user32 = ctypes.windll.user32
        if not win32gui:
            hwnd = user32.FindWindowW(None, "WhatsApp")
            return hwnd if hwnd and user32.IsWindow(hwnd) else None

        candidates = []
        def enum_cb(h, _):
            if not win32gui.IsWindow(h):
                return
            cls = (win32gui.GetClassName(h) or "").strip()
            title = (win32gui.GetWindowText(h) or "").strip().lower()
            if any(b in title for b in ["chrome", "edge", "firefox", "brave", "visual studio", "systemize"]):
                return
            if cls == "WinUIDesktopWin32WindowClass":
                candidates.append((h, 10))
            elif "whatsapp" in title or "واتساب" in title:
                w = 5 + (3 if win32gui.IsWindowVisible(h) else 0)
                candidates.append((h, w))

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        hwnd = user32.FindWindowW(None, "WhatsApp")
        return hwnd if hwnd and user32.IsWindow(hwnd) else None

    def ensure_whatsapp_focused(self) -> bool:
        """Launches / Maximizes and focuses WhatsApp Desktop."""
        hwnd = self.find_whatsapp_window()
        if not hwnd:
            Popen("start whatsapp:", shell=True)
            for _ in range(25):
                time.sleep(0.4)
                hwnd = self.find_whatsapp_window()
                if hwnd:
                    break

        if not hwnd:
            return False

        try:
            user32 = ctypes.windll.user32
            # Maximize and bring to foreground
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.6)
            return True
        except Exception:
            return False

    def send_single_message(
        self,
        phone: str,
        message: str = "",
        attachment_path: Optional[str] = None,
        on_status_update: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Sends a single WhatsApp message and/or file attachment to a contact.
        Returns: (success: bool, status_message: str)
        """
        self.is_sending = True
        try:
            self.check_kill_switch()
            clean_phone = re.sub(r"[^\d+]", "", str(phone).strip())
            if not clean_phone:
                return False, "رقم الهاتف فارغ أو غير صالح."

            if on_status_update:
                on_status_update(f"⏳ جاري التركيز على واتساب للرقم: {clean_phone}...")

            # 1. Focus WhatsApp Desktop
            if not self.ensure_whatsapp_focused():
                return False, "تعذر فتح تطبيق WhatsApp Desktop. يرجى التأكد من تشغيله."

            self.set_keyboard_layout_to_english()
            self.safe_delay(0.2)

            # 2. Click Search Bar
            if on_status_update:
                on_status_update(f"🔍 البحث عن جهة الاتصال ({clean_phone})...")

            pyautogui.press("esc")
            self.safe_delay(0.15)
            self.human_move_to(self.search_x, self.search_y)
            pyautogui.click()
            self.safe_delay(0.2)

            # Clear search box and paste phone
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            self.safe_delay(0.1)

            copy(clean_phone)
            pyautogui.hotkey("ctrl", "v")
            self.safe_delay(0.9)
            pyautogui.press("enter")
            self.safe_delay(1.2)

            # 3. Focus Chat input area
            w_hwnd = self.find_whatsapp_window()
            if w_hwnd and win32gui:
                rect = win32gui.GetWindowRect(w_hwnd)
                w_width = rect[2] - rect[0]
                w_height = rect[3] - rect[1]
                chat_x = rect[0] + int(w_width * 0.65)
                chat_y = rect[1] + int(w_height - 45)
                self.human_move_to(chat_x, chat_y)
                pyautogui.click()
                self.safe_delay(0.3)

            # 4. Attach File / Image if provided
            if attachment_path and os.path.exists(attachment_path):
                if on_status_update:
                    on_status_update(f"📎 جاري لصق المرفق ({os.path.basename(attachment_path)})...")

                copied = self.copy_file_to_clipboard(attachment_path)
                if copied:
                    pyautogui.hotkey("ctrl", "v")
                    self.safe_delay(1.5)  # Wait for WhatsApp media preview to load
                else:
                    print(f"[WhatsAppEngine] Failed to copy file {attachment_path} to clipboard.")

            # 5. Type or Paste Message
            if message and message.strip():
                if on_status_update:
                    on_status_update("✍️ كتابة وإرسال نص الرسالة...")

                if self.send_mode == "typing":
                    # Human typing simulation
                    for ch in message:
                        self.check_kill_switch()
                        if ch == "\n":
                            pyautogui.hotkey("shift", "enter")
                        else:
                            # Use clipboard for complex arabic unicode chars
                            copy(ch)
                            pyautogui.hotkey("ctrl", "v")
                        time.sleep(self.letter_delay + random.uniform(0.005, 0.02))
                else:
                    # Fast clipboard paste mode
                    copy(message)
                    pyautogui.hotkey("ctrl", "v")
                    self.safe_delay(0.3)

            self.safe_delay(0.4)
            pyautogui.press("enter")
            self.safe_delay(0.8)

            if on_status_update:
                on_status_update("✓ تم الإرسال بنجاح!")

            return True, "تم الإرسال بنجاح ✓"

        except WhatsAppKillSwitchTriggered as e:
            return False, str(e)
        except Exception as e:
            return False, f"خطأ أثناء الإرسال: {str(e)}"
        finally:
            self.is_sending = False
