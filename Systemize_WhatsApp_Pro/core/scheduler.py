import time
import random
from datetime import datetime
from typing import List, Optional
from PySide6.QtCore import QThread, Signal

from core.contact_manager import Contact
from core.whatsapp_engine import WhatsAppEngine, WhatsAppKillSwitchTriggered


class DispatchWorker(QThread):
    """
    Background dispatch worker thread.
    Executes the campaign safely with randomized timing, human movements,
    and live real-time signals to both the main window and the mini overlay HUD.
    """
    progress_updated = Signal(int, int, int, str, str)  # sent, total, remaining, name, phone
    countdown_tick = Signal(float)  # seconds left until next send
    status_updated = Signal(str, bool)  # text, is_active
    contact_completed = Signal(object, bool, str)  # contact, success, message
    batch_finished = Signal(int, int)  # total_sent, total_failed
    emergency_stopped = Signal(str)  # reason

    def __init__(
        self,
        contacts: List[Contact],
        engine: WhatsAppEngine,
        template_text: str = "",
        attachment_path: Optional[str] = None,
        schedule_time: Optional[datetime] = None,
        parent=None
    ):
        super().__init__(parent)
        self.contacts = contacts
        self.engine = engine
        self.template_text = template_text
        self.attachment_path = attachment_path
        self.schedule_time = schedule_time

        self._is_running = True
        self._is_paused = False

    def pause(self):
        self._is_paused = True
        self.status_updated.emit("⏸️ تم الإيقاف المؤقت", False)

    def resume(self):
        self._is_paused = False
        self.status_updated.emit("🟢 جاري الاستئناف...", True)

    def stop(self):
        self._is_running = False
        self.engine.kill_switch_requested = True
        self.status_updated.emit("⏹️ تم الإيقاف", False)

    def run(self):
        self.engine.reset_kill_switch()
        self._is_running = True
        self._is_paused = False

        total = len(self.contacts)
        sent_count = 0
        failed_count = 0

        # 1. Scheduled dispatch wait loop if scheduled for later
        if self.schedule_time and self.schedule_time > datetime.now():
            self.status_updated.emit(f"📅 مجدول للبدء في: {self.schedule_time.strftime('%Y-%m-%d %I:%M %p')}", True)
            while self._is_running and datetime.now() < self.schedule_time:
                remaining_sec = (self.schedule_time - datetime.now()).total_seconds()
                self.countdown_tick.emit(remaining_sec)
                self.status_updated.emit(f"⏳ بدء مجدول بعد: {int(remaining_sec)} ثانية", True)

                # Sleep in short increments to remain responsive
                time.sleep(min(1.0, max(0.1, remaining_sec)))
                try:
                    self.engine.check_kill_switch()
                except WhatsAppKillSwitchTriggered as e:
                    self.emergency_stopped.emit(str(e))
                    return

            if not self._is_running:
                self.batch_finished.emit(sent_count, failed_count)
                return

        # 2. Main Dispatch Loop
        for idx, contact in enumerate(self.contacts):
            if not self._is_running:
                break

            # Handle Pause
            while self._is_paused and self._is_running:
                time.sleep(0.2)
                try:
                    self.engine.check_kill_switch()
                except WhatsAppKillSwitchTriggered as e:
                    self._is_running = False
                    self.emergency_stopped.emit(str(e))
                    return

            if not self._is_running:
                break

            contact.status = "جاري الإرسال"
            remaining = total - sent_count - failed_count
            self.progress_updated.emit(sent_count, total, remaining, contact.name, contact.phone)

            # Personalize message template tags
            personalized_msg = self._render_template(self.template_text, contact)

            # Attempt sending via engine
            try:
                def on_engine_status(txt):
                    self.status_updated.emit(txt, True)

                ok, msg = self.engine.send_single_message(
                    phone=contact.phone,
                    message=personalized_msg,
                    attachment_path=self.attachment_path,
                    on_status_update=on_engine_status
                )

                if ok:
                    contact.status = "تم الإرسال"
                    contact.sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sent_count += 1
                else:
                    contact.status = "فشل الإرسال"
                    contact.error_message = msg
                    failed_count += 1

                self.contact_completed.emit(contact, ok, msg)

            except WhatsAppKillSwitchTriggered as exc:
                contact.status = "فشل (طوارئ)"
                contact.error_message = str(exc)
                failed_count += 1
                self.contact_completed.emit(contact, False, str(exc))
                self.emergency_stopped.emit(str(exc))
                break
            except Exception as exc:
                contact.status = "فشل"
                contact.error_message = str(exc)
                failed_count += 1
                self.contact_completed.emit(contact, False, str(exc))

            # Update progress counts
            remaining = total - sent_count - failed_count
            self.progress_updated.emit(sent_count, total, remaining, contact.name, contact.phone)

            # 3. Inter-message randomized delay with live countdown
            if idx < total - 1 and self._is_running:
                delay = random.uniform(self.engine.min_delay, self.engine.max_delay)
                end_wait = time.time() + delay

                while time.time() < end_wait and self._is_running:
                    # While paused, pause the countdown
                    if self._is_paused:
                        time.sleep(0.2)
                        continue

                    left = max(0.0, end_wait - time.time())
                    self.countdown_tick.emit(left)
                    self.status_updated.emit(f"⏱️ استراحة أمان ({left:.1f}s) لمنع حظر الرقم", True)

                    time.sleep(min(0.08, left))
                    try:
                        self.engine.check_kill_switch()
                    except WhatsAppKillSwitchTriggered as e:
                        self._is_running = False
                        self.emergency_stopped.emit(str(e))
                        return

        self.countdown_tick.emit(0.0)
        self.status_updated.emit(f"✓ اكتملت الحملة! تم إرسال {sent_count} من {total}", False)
        self.batch_finished.emit(sent_count, failed_count)

    def _render_template(self, template: str, contact: Contact) -> str:
        """Replaces placeholders like {name}, {phone}, {category}, {time}, {notes}."""
        if not template:
            return ""

        rendered = template
        now = datetime.now()

        # Standard placeholders
        replacements = {
            "{name}": contact.name,
            "{الاسم}": contact.name,
            "{phone}": contact.phone,
            "{الهاتف}": contact.phone,
            "{category}": contact.category,
            "{التصنيف}": contact.category,
            "{notes}": contact.notes,
            "{الملاحظات}": contact.notes,
            "{time}": now.strftime("%I:%M %p"),
            "{الوقت}": now.strftime("%I:%M %p"),
            "{date}": now.strftime("%Y-%m-%d"),
            "{التاريخ}": now.strftime("%Y-%m-%d"),
        }

        # Custom column placeholders from Excel
        for k, v in contact.custom_data.items():
            replacements[f"{{{k}}}"] = str(v)

        for placeholder, val in replacements.items():
            rendered = rendered.replace(placeholder, str(val))

        return rendered
