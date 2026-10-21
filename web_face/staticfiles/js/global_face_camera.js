/**
 * HULK GYM - Global Face Recognition & Independent Camera Manager
 * Connects to the continuous independent backend camera service.
 * Operates seamlessly across page switches WITHOUT restarting the webcam hardware.
 * Displays real-time full-screen entry alerts, plays chimes, and powers the mini dock preview.
 */

(function () {
  'use strict';

  let isOverlayActive = false;
  let overlayTimer = null;
  let audioCtx = null;
  let eventPollInterval = null;
  let lastEventTimestamp = 0;

  // Global variables shared across page scripts (e.g., face enrollment modal)
  window.isGlobalCameraActive = true;
  window.isEnrollModalOpen = false;

  // Persistent Cooldown Manager using localStorage to strictly enforce > 1 minute debounce across page switches
  function getMemberCooldowns() {
    try {
      const raw = localStorage.getItem('hulk_gym_member_overlay_cooldowns');
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function setMemberCooldown(memberId) {
    try {
      const cooldowns = getMemberCooldowns();
      cooldowns[String(memberId)] = Date.now();
      localStorage.setItem('hulk_gym_member_overlay_cooldowns', JSON.stringify(cooldowns));
    } catch (e) {}
  }

  function isMemberInCooldown(memberId) {
    const cooldowns = getMemberCooldowns();
    const lastTime = cooldowns[String(memberId)] || 0;
    // Enforce strict 65-second (more than 1 minute) cooldown
    return (Date.now() - lastTime) < 65000;
  }

  // Sound synthesis using Web Audio API (100% offline, zero audio files needed)
  function getAudioContext() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) audioCtx = new AudioContext();
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playSuccessChime() {
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const now = ctx.currentTime;
      // Dual-tone harmonic chime
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'triangle';
      osc1.frequency.setValueAtTime(523.25, now); // C5
      osc1.frequency.exponentialRampToValueAtTime(659.25, now + 0.12); // E5
      osc1.frequency.exponentialRampToValueAtTime(783.99, now + 0.28); // G5

      osc2.frequency.setValueAtTime(261.63, now); // C4
      osc2.frequency.exponentialRampToValueAtTime(392.00, now + 0.25);

      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.65);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 0.7);
      osc2.stop(now + 0.7);
    } catch (e) {
      console.warn("Audio chime error:", e);
    }
  }

  function playAlertChime() {
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const now = ctx.currentTime;
      // Urgent double beep
      for (let i = 0; i < 2; i++) {
        const start = now + (i * 0.16);
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(349.23, start); // F4
        osc.frequency.exponentialRampToValueAtTime(220.00, start + 0.12); // A3

        gain.gain.setValueAtTime(0.28, start);
        gain.gain.exponentialRampToValueAtTime(0.001, start + 0.13);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(start);
        osc.stop(start + 0.14);
      }
    } catch (e) {
      console.warn("Audio chime error:", e);
    }
  }

  function updateStatusPill(status, text) {
    const dot = document.getElementById('globalCamDot');
    const label = document.getElementById('globalCamText');
    if (!dot || !label) return;

    if (status === 'active') {
      dot.style.background = '#10b981';
      dot.style.boxShadow = '0 0 10px #10b981';
      label.textContent = text || 'الكاميرا المستقلة نشطة';
      label.style.color = '#10b981';
    } else if (status === 'loading') {
      dot.style.background = '#38bdf8';
      dot.style.boxShadow = '0 0 10px #38bdf8';
      label.textContent = text || 'جاري تشغيل الكاميرا...';
      label.style.color = '#38bdf8';
    } else if (status === 'paused') {
      dot.style.background = '#f59e0b';
      dot.style.boxShadow = '0 0 8px #f59e0b';
      label.textContent = text || 'الكاميرا متوقفة مؤقتاً';
      label.style.color = '#f59e0b';
    } else if (status === 'error') {
      dot.style.background = '#ef4444';
      dot.style.boxShadow = '0 0 8px #ef4444';
      label.textContent = text || 'خطأ في الكاميرا';
      label.style.color = '#ef4444';
    }
  }

  /**
   * Starts listening to the independent background camera events.
   * Runs smoothly without browser getUserMedia() calls, preventing restarts on page navigation.
   */
  function startIndependentCameraListener() {
    if (eventPollInterval) clearInterval(eventPollInterval);

    // Initial check: show loading state smoothly
    updateStatusPill('loading', 'جاري تشغيل الكاميرا...');

    eventPollInterval = setInterval(async () => {
      // Don't poll if overlay is already active or tab is hidden
      if (isOverlayActive || document.hidden) {
        return;
      }

      try {
        const res = await fetch(`/face/api/live-events/?since=${lastEventTimestamp}`);
        if (!res.ok) return;
        const data = await res.json();

        // On first response, sync timestamp with server to prevent past event replay
        if (lastEventTimestamp === 0 && data.server_time) {
          lastEventTimestamp = data.server_time;
        }

        if (data.camera_running !== undefined) {
          if (data.camera_running) {
            updateStatusPill('active', 'الكاميرا المستقلة نشطة');
          } else if (data.camera_starting) {
            updateStatusPill('loading', 'جاري تشغيل الكاميرا...');
          } else if (data.camera_error) {
            updateStatusPill('error', 'تنبيه: ' + data.camera_error.substring(0, 25));
          } else {
            updateStatusPill('paused', 'الكاميرا متوقفة');
          }
        }

        if (data.has_event && data.event) {
          const ev = data.event;
          lastEventTimestamp = ev.timestamp;

          const m = ev.member;
          const mId = m.id;

          // Strict > 1 Minute cooldown check across all page switches and tabs
          if (isMemberInCooldown(mId)) {
            return;
          }

          setMemberCooldown(mId);

          // Suppress visual overlay takeover during WhatsApp sending to prevent interrupting message flow
          if (data.whatsapp_sending || window.isWhatsAppSending || (window.whatsappQueueRunner && window.whatsappQueueRunner.isRunning)) {
            console.log("[FaceID] Silent check-in completed for #" + mId + " (overlay suppressed during WhatsApp dispatch)");
            return;
          }

          showFullscreenNotification(m, ev.score, ev.gate_opened);
        }
      } catch (e) {
        // Silent catch for background polling
      }
    }, 380);
  }

  function showFullscreenNotification(m, score, gateOpened) {
    if (isOverlayActive) return;
    isOverlayActive = true;

    const overlay = document.getElementById('fullscreen-result-overlay');
    const card = document.getElementById('fullscreen-result-card');
    const badge = document.getElementById('fs-status-badge');
    const icon = document.getElementById('fs-status-icon');
    const title = document.getElementById('fs-status-title');
    const avatarImg = document.getElementById('fs-avatar-img');
    const avatarPlaceholder = document.getElementById('fs-avatar-placeholder');
    const avatarBox = document.getElementById('fs-avatar-container');
    const nameEl = document.getElementById('fs-member-name');
    const idEl = document.getElementById('fs-member-id');
    const planEl = document.getElementById('fs-plan-name');
    const infoBox = document.getElementById('fs-info-box');
    const dateLabel = document.getElementById('fs-date-label');
    const dateVal = document.getElementById('fs-date-value');
    const daysLabel = document.getElementById('fs-days-label');
    const daysVal = document.getElementById('fs-days-value');
    const debtNotice = document.getElementById('fs-debt-notice');
    const gateNotice = document.getElementById('fs-gate-notice');
    const alertInstruction = document.getElementById('fs-alert-instruction');
    const progressFill = document.getElementById('fs-progress-fill');

    if (!overlay) return;

    nameEl.textContent = m.name || 'عضو غير مسمى';
    idEl.textContent = '#' + (m.member_id || '---');
    planEl.textContent = m.plan || 'باقة أساسية';

    if (m.photo_url) {
      avatarImg.src = m.photo_url;
      avatarImg.style.display = 'block';
      avatarPlaceholder.style.display = 'none';
    } else {
      avatarImg.style.display = 'none';
      avatarPlaceholder.style.display = 'block';
    }

    if (m.has_debt) {
      debtNotice.style.display = 'block';
      document.getElementById('fs-debt-amount').textContent = m.remaining + ' ج.م';
    } else {
      debtNotice.style.display = 'none';
    }

    const durationMs = m.is_active ? 3500 : 4500;

    if (m.is_active) {
      // Emerald Green Active Theme
      card.style.background = 'linear-gradient(145deg, #062419 0%, #03140d 100%)';
      card.style.border = '3px solid #10b981';
      card.style.boxShadow = '0 0 80px rgba(16, 185, 129, 0.4), inset 0 0 40px rgba(16, 185, 129, 0.15)';
      avatarBox.style.borderColor = '#10b981';
      avatarBox.style.boxShadow = '0 0 35px rgba(16, 185, 129, 0.5)';

      badge.style.background = 'rgba(16, 185, 129, 0.2)';
      badge.style.border = '2px solid #10b981';
      badge.style.color = '#34d399';
      icon.innerHTML = '<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981;"></span>';

      infoBox.style.background = 'rgba(16, 185, 129, 0.1)';
      infoBox.style.border = '1px solid rgba(16, 185, 129, 0.25)';

      dateLabel.textContent = 'تاريخ نهاية الاشتراك';
      dateLabel.style.color = '#a7f3d0';
      dateVal.textContent = m.end_date || 'غير محدد';
      dateVal.style.color = '#6ee7b7';

      if (m.window_hours_left !== undefined && m.window_hours_left !== null) {
        daysLabel.textContent = 'نافذة اليوم المتبقية';
        daysLabel.style.color = '#a7f3d0';
        daysVal.textContent = m.window_hours_left + ' ساعة';
        daysVal.style.color = '#38bdf8';
        title.textContent = `مسموح بالدخول — نافذة التمرين (${m.window_hours_left} س)`;
      } else {
        daysLabel.textContent = 'الأيام المتبقية';
        daysLabel.style.color = '#a7f3d0';
        daysVal.textContent = (m.days_left || 0) + ' يوم';
        daysVal.style.color = '#34d399';
        title.textContent = 'مسموح بالدخول — مرحباً بك!';
      }

      gateNotice.style.display = 'block';
      alertInstruction.style.display = 'none';
      progressFill.style.background = '#10b981';

      playSuccessChime();
    } else {
      // Crimson Red Expired / Denied Theme
      card.style.background = 'linear-gradient(145deg, #2b0b10 0%, #150508 100%)';
      card.style.border = '3px solid #f43f5e';
      card.style.boxShadow = '0 0 80px rgba(244, 63, 94, 0.45), inset 0 0 40px rgba(244, 63, 94, 0.2)';
      avatarBox.style.borderColor = '#f43f5e';
      avatarBox.style.boxShadow = '0 0 35px rgba(244, 63, 94, 0.5)';

      badge.style.background = 'rgba(244, 63, 94, 0.22)';
      badge.style.border = '2px solid #f43f5e';
      badge.style.color = '#fda4af';
      icon.innerHTML = '<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#f43f5e; box-shadow:0 0 8px #f43f5e;"></span>';

      infoBox.style.background = 'rgba(244, 63, 94, 0.12)';
      infoBox.style.border = '1px solid rgba(244, 63, 94, 0.3)';

      if (m.deny_code === 'consecutive_day_blocked') {
        title.textContent = 'غير مسموح بالدخول — باقة يوم ويوم (سجلت حضوراً بالأمس)';
        dateLabel.textContent = 'نظام الباقة';
        dateLabel.style.color = '#fecdd3';
        dateVal.textContent = m.plan || 'يوم ويوم';
        dateVal.style.color = '#f87171';

        daysLabel.textContent = 'حضور الأمس';
        daysLabel.style.color = '#fecdd3';
        daysVal.textContent = 'مسجل حضور بالأمس';
        daysVal.style.color = '#fb7185';

        alertInstruction.textContent = m.deny_reason || 'عفواً، باقتك بنظام (يوم ويوم) ولا يُسمح بالدخول يومين متتاليين.';
      } else if (m.deny_code === 'daily_window_expired') {
        title.textContent = 'غير مسموح بالدخول — انتهت نافذة الـ 4 ساعات اليوم';
        dateLabel.textContent = 'أول دخول اليوم';
        dateLabel.style.color = '#fecdd3';
        dateVal.textContent = m.first_entry_time_str || 'اليوم';
        dateVal.style.color = '#f87171';

        daysLabel.textContent = 'نافذة اليوم';
        daysLabel.style.color = '#fecdd3';
        daysVal.textContent = 'انتهت (4 ساعات)';
        daysVal.style.color = '#fb7185';

        alertInstruction.textContent = m.deny_reason || 'عفواً، انتهت نافذة التمرين اليومية المسموحة (4 ساعات من أول دخول).';
      } else {
        title.textContent = 'غير مسموح بالدخول — الاشتراك منتهي!';
        dateLabel.textContent = 'انتهى بتاريخ';
        dateLabel.style.color = '#fecdd3';
        dateVal.textContent = m.end_date || 'منتهي مسبقاً';
        dateVal.style.color = '#f87171';

        daysLabel.textContent = 'مدة الانتهاء';
        daysLabel.style.color = '#fecdd3';
        const expDays = m.expired_days || 0;
        daysVal.textContent = expDays > 0 ? ('منتهي منذ ' + expDays + ' يوم') : 'منتهي اليوم';
        daysVal.style.color = '#fb7185';

        alertInstruction.textContent = m.deny_reason || 'يرجى مراجعة موظف الاستقبال لتجديد الاشتراك وتحديث العضوية.';
      }

      gateNotice.style.display = 'none';
      alertInstruction.style.display = 'block';
      progressFill.style.background = '#f43f5e';

      playAlertChime();
    }

    // Reset and trigger countdown bar
    progressFill.style.transition = 'none';
    progressFill.style.width = '100%';
    overlay.style.display = 'flex';
    overlay.style.opacity = '1';

    setTimeout(() => {
      progressFill.style.transition = `width ${durationMs}ms linear`;
      progressFill.style.width = '0%';
    }, 40);

    if (overlayTimer) clearTimeout(overlayTimer);
    overlayTimer = setTimeout(() => {
      hideFullscreenNotification();
    }, durationMs);
  }

  function hideFullscreenNotification() {
    const overlay = document.getElementById('fullscreen-result-overlay');
    if (!overlay) return;

    overlay.style.opacity = '0';
    setTimeout(() => {
      overlay.style.display = 'none';
      isOverlayActive = false;
    }, 200);
  }

  // Toggle mini docked preview window
  window.toggleCameraDockPreview = function () {
    const dock = document.getElementById('globalCamDock');
    if (!dock) return;
    const dockImg = document.getElementById('dockPreviewImg');
    if (dock.style.display === 'none' || !dock.style.display) {
      dock.style.display = 'block';
      if (dockImg) {
        dockImg.style.display = 'block';
        const streamUrl = dockImg.getAttribute('data-src') || '/face/video-feed/';
        dockImg.src = streamUrl + '?t=' + Date.now();
      }
    } else {
      dock.style.display = 'none';
      if (dockImg) {
        dockImg.src = ''; // disconnect stream to free browser HTTP connection and thread
        dockImg.style.display = 'none';
      }
    }
  };

  // Open independent camera floating window
  window.openIndependentCameraWindow = function () {
    const w = 820;
    const h = 600;
    const left = (screen.width - w) / 2;
    const top = (screen.height - h) / 2;
    window.open('/face/camera-window/', 'HulkGymCamera', `width=${w},height=${h},top=${top},left=${left},resizable=yes,scrollbars=no`);
  };

  window.closeFullscreenOverlay = hideFullscreenNotification;

  // Auto-start listener on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    startIndependentCameraListener();
  });

})();
