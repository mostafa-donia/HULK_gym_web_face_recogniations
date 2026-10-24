import json
import time
from datetime import timedelta
from decimal import Decimal
import numpy as np
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.files.base import ContentFile

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile
from apps.members.models import Member, CheckInEvent
from apps.face_recognition.engine import get_face_engine


def face_kiosk_view(request):
    """
    Live Face Recognition Attendance Kiosk & Gate Control.
    Can be run full-screen on a tablet, reception display, or turnstile terminal.
    """
    profile = GymProfile.get_solo()
    recent_events = CheckInEvent.objects.select_related("member").order_by("-checked_in_at")[:12]
    context = {
        "profile": profile,
        "recent_events": recent_events,
        "enrolled_count": Member.objects.filter(has_face_enrolled=True).count(),
        "today_checkins_count": CheckInEvent.objects.filter(checked_in_at__date=timezone.localdate()).count(),
    }
    return render(request, "face_recognition/kiosk.html", context)


@csrf_exempt
def api_face_verify(request):
    """
    Real-time face verification endpoint called by the camera gate / kiosk.
    Receives webcam image base64, recognizes member in <1ms, registers attendance,
    and triggers electronic gate relay if member is active.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required."}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = {}

    image_b64 = body.get("image_base64")
    if not image_b64:
        return JsonResponse({"success": False, "message": "No image data provided."}, status=400)

    engine = get_face_engine()
    if not engine.is_ready:
        return JsonResponse({"success": False, "message": "نماذج الذكاء الاصطناعي غير محملة."}, status=503)

    profile = GymProfile.get_solo()
    thresh = profile.face_match_threshold_ratio
    det_thresh = max(float(profile.face_min_confidence or 0.55), 0.50)

    success, emb, crop_bytes, msg = engine.extract_embedding_and_crop(image_b64, score_threshold=det_thresh)
    if not success or not emb:
        return JsonResponse({"success": False, "matched": False, "message": msg})

    member_id, score = engine.match_face_vector(emb, cosine_threshold=thresh)
    if not member_id:
        # Check if the detected face belongs to the Gym Manager
        if profile.manager_face_unlock_enabled and profile.manager_face_enrolled and profile.manager_face_embeddings:
            q_vec = np.array(emb, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm > 0:
                q_vec = q_vec / q_norm
            mgr_best = -1.0
            for m_emb in profile.manager_face_embeddings:
                m_vec = np.array(m_emb, dtype=np.float32)
                m_norm = np.linalg.norm(m_vec)
                if m_norm > 0:
                    m_vec = m_vec / m_norm
                s = float(np.dot(q_vec, m_vec))
                if s > mgr_best:
                    mgr_best = s
            if mgr_best >= thresh:
                request.session["manager_page_unlocked"] = True
                request.session["settings_page_unlocked"] = True
                request.session["trainers_page_unlocked"] = True
                request.session["retention_page_unlocked"] = True
                request.session["reports_page_unlocked"] = True
                request.session["developer_options_unlocked"] = False
                request.session.modified = True
                request.session.save()
                return JsonResponse({
                    "success": True,
                    "matched": True,
                    "is_manager": True,
                    "score": round(mgr_best * 100, 1),
                    "member_name": "المدير العام (Manager)",
                    "status": "مدير النظام",
                    "photo_url": profile.manager_face_photo.url if profile.manager_face_photo else None,
                    "message": "✓ تم التعرف على وجه مدير الصالة بنجاح. أهلاً بك!",
                })

        return JsonResponse({
            "success": True,
            "matched": False,
            "score": round(score * 100, 1),
            "required_score": profile.face_match_threshold_percent,
            "message": f"وجه غير مسجل في النظام (نسبة التطابق {round(score * 100)}% أقل من المعيار المطلوب {profile.face_match_threshold_percent}%).",
        })

    member = Member.objects.filter(id=member_id).first()
    if not member:
        return JsonResponse({"success": False, "matched": False, "message": "العضو غير موجود."})

    # Update active/expired status against today
    member.refresh_status()

    # Check access eligibility (active status + day-on-day-off rules)
    eligibility = member.check_access_eligibility()
    access_allowed = eligibility["allowed"]

    # Debounce check (prevent duplicate logs within debounce window)
    debounce_sec = profile.face_debounce_seconds or 60
    cutoff = timezone.now() - timedelta(seconds=debounce_sec)
    recent_checkin = CheckInEvent.objects.filter(member=member, checked_in_at__gte=cutoff).first()

    logged_new = False
    if access_allowed and not recent_checkin:
        CheckInEvent.objects.create(
            member=member,
            method="face",
            confidence=score,
            status_snapshot=member.current_status,
            days_left_snapshot=member.days_left,
            debt_snapshot=member.current_remaining,
        )
        logged_new = True

        # Trigger physical turnstile / magnetic lock gate relay
        if profile.gate_relay_enabled:
            engine.trigger_gate_relay(profile=profile)

    today = timezone.localdate()
    expired_days = (today - member.last_subscription_end).days if (member.last_subscription_end and not member.is_active) else 0
    end_date_str = member.last_subscription_end.strftime("%d/%m/%Y") if member.last_subscription_end else "غير محدد"

    return JsonResponse({
        "success": True,
        "matched": True,
        "access_allowed": access_allowed,
        "deny_reason": eligibility["reason"] if not access_allowed else None,
        "logged_new": logged_new,
        "debounced": not logged_new and access_allowed,
        "score": round(score * 100, 1),
        "member": {
            "id": member.id,
            "name": member.name,
            "member_id": member.member_id,
            "is_active": access_allowed,
            "days_left": member.days_left,
            "end_date": end_date_str,
            "expired_days": expired_days,
            "has_debt": member.has_debt,
            "remaining": str(member.current_remaining),
            "plan": member.last_subscription_type or "باقة أساسية",
            "photo_url": member.face_photo.url if member.face_photo else None,
            "deny_reason": eligibility["reason"] if not access_allowed else None,
            "deny_code": eligibility.get("reason_code"),
            "window_hours_left": eligibility.get("window_hours_left"),
            "first_entry_time_str": eligibility.get("first_entry_time_str"),
            "is_alternate_days": member.is_alternate_days_subscription(),
        },
        "gate_opened": bool(access_allowed and profile.gate_relay_enabled and logged_new),
    })


@csrf_exempt
@login_required
def api_enroll_face(request, member_id):
    """
    Enrolls a member's face from the webcam wizard / member profile.
    Extracts 128-D embedding and stores official face crop thumbnail.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required."}, status=405)

    member = get_object_or_404(Member, id=member_id)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = {}

    poses = body.get("poses")
    image_b64 = body.get("image_base64")
    append_variant = bool(body.get("append_variant", False))

    if not poses and not image_b64:
        return JsonResponse({"success": False, "message": "لم يتم إرسال أي صور أو وضعيات للوجه."}, status=400)

    engine = get_face_engine()
    if not engine.is_ready:
        return JsonResponse({"success": False, "message": "نماذج الذكاء الاصطناعي غير متوفرة."}, status=503)

    profile = GymProfile.get_solo()
    det_thresh = float(profile.face_min_confidence or 0.55)

    # Normalize poses input into a list of (label, image_b64)
    pose_items = []
    if poses and isinstance(poses, list):
        for p in poses:
            if isinstance(p, dict) and p.get("image_base64"):
                pose_items.append((p.get("label", "variant"), p.get("image_base64")))
    elif image_b64:
        pose_items.append((body.get("label", "center" if not append_variant else "variant"), image_b64))

    if not pose_items:
        return JsonResponse({"success": False, "message": "لا توجد صور صالحة للمعالجة."}, status=400)

    extracted_embeddings = []
    primary_crop_bytes = None
    errors = []

    for label, img_str in pose_items:
        success, emb, crop_bytes, msg = engine.extract_embedding_and_crop(img_str, score_threshold=det_thresh)
        if success and emb:
            extracted_embeddings.append(emb)
            if (label == "center" or primary_crop_bytes is None) and crop_bytes:
                primary_crop_bytes = crop_bytes
        else:
            errors.append(f"الوضعية ({label}): {msg}")

    if not extracted_embeddings:
        err_msg = " | ".join(errors) if errors else "تعذر استخراج بصمة الوجه من الصور الملتقطة."
        return JsonResponse({"success": False, "message": err_msg}, status=400)

    # If appending variant: keep existing and add new (up to 10 max).
    # If standard 5-poses re-enrollment: replace or merge
    existing_embs = member.face_embeddings or [] if append_variant else []
    for new_emb in extracted_embeddings:
        existing_embs.append(new_emb)

    # Keep up to 10 pose/variant embeddings
    if len(existing_embs) > 10:
        existing_embs = existing_embs[-10:]

    member.face_embeddings = existing_embs
    member.has_face_enrolled = True
    member.face_enrolled_at = timezone.now()

    # Save photo crop if available
    if primary_crop_bytes:
        filename = f"face_{member.id}_{int(time.time())}.jpg"
        member.face_photo.save(filename, ContentFile(primary_crop_bytes), save=False)

    member.save()

    # Invalidate engine cache so new enrollment is recognized immediately
    engine.refresh_cache(force=True)

    mode_label = "إضافة وضعيات إضافية (Variants)" if append_variant else "تسجيل الوضعيات الـ 5"
    return JsonResponse({
        "success": True,
        "message": f"تم {mode_label} بنجاح ({len(existing_embs)} بصمة محفوظة للعضو {member.name})!",
        "photo_url": member.face_photo.url if member.face_photo else None,
        "samples_count": len(existing_embs),
    })


@csrf_exempt
@login_required
@manager_required
def api_delete_face(request, member_id):
    """Deletes face enrollment records for a member."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required."}, status=405)

    member = get_object_or_404(Member, id=member_id)
    member.has_face_enrolled = False
    member.face_embeddings = []
    member.face_enrolled_at = None
    if member.face_photo:
        try:
            member.face_photo.delete(save=False)
        except Exception:
            pass
        member.face_photo = None
    member.save()

    engine = get_face_engine()
    engine.refresh_cache(force=True)

    return JsonResponse({"success": True, "message": "تم حذف بصمة الوجه بنجاح."})


def api_kiosk_recent_checkins(request):
    """Returns recent check-in events formatted as JSON for live kiosk feed."""
    events = CheckInEvent.objects.select_related("member").order_by("-checked_in_at")[:10]
    data = []
    for ev in events:
        data.append({
            "id": ev.id,
            "member_id": ev.member.member_id,
            "name": ev.member.name,
            "time": ev.checked_in_at.strftime("%I:%M %p"),
            "status": ev.status_snapshot,
            "days_left": ev.days_left_snapshot,
            "debt": str(ev.debt_snapshot),
            "photo_url": ev.member.face_photo.url if ev.member.face_photo else None,
        })
    return JsonResponse({"success": True, "events": data})


def video_feed_view(request):
    """
    Streams continuous MJPEG video feed from the independent background camera.
    Does NOT restart when users switch pages.
    """
    engine = get_face_engine()

    def frame_generator():
        try:
            while True:
                frame_bytes = engine.get_latest_jpeg()
                if frame_bytes:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(0.035)
        except (GeneratorExit, BrokenPipeError, ConnectionResetError, Exception):
            pass

    return StreamingHttpResponse(frame_generator(), content_type='multipart/x-mixed-replace; boundary=frame')


def api_live_events_view(request):
    """
    Returns latest face recognition event for background polling across any page.
    Enables instant full-screen takeover overlay without camera restarts.
    """
    engine = get_face_engine()
    now_ts = time.time()
    try:
        since_ts = float(request.GET.get("since", 0))
    except (ValueError, TypeError):
        since_ts = 0.0

    camera_starting = getattr(engine, "camera_starting", False)
    is_wa_sending = False
    try:
        from apps.messaging import whatsapp_sender
        is_wa_sending = getattr(whatsapp_sender, "IS_WHATSAPP_SENDING", False)
    except Exception:
        pass

    # If initial poll from a newly loaded page (since_ts <= 0), synchronize timestamp and do not replay old past events
    if since_ts <= 0.0:
        return JsonResponse({
            "success": True,
            "has_event": False,
            "server_time": now_ts,
            "camera_running": engine.camera_running,
            "camera_starting": camera_starting,
            "camera_error": engine.camera_error,
            "whatsapp_sending": is_wa_sending,
        })

    event = engine.get_latest_event()
    if event and (event.get("timestamp", 0) > since_ts) and (now_ts - float(event.get("timestamp", 0)) <= 3.5):
        return JsonResponse({
            "success": True,
            "has_event": True,
            "server_time": now_ts,
            "camera_running": engine.camera_running,
            "camera_starting": camera_starting,
            "camera_error": engine.camera_error,
            "event": event,
            "whatsapp_sending": is_wa_sending,
        })

    return JsonResponse({
        "success": True,
        "has_event": False,
        "server_time": now_ts,
        "camera_running": engine.camera_running,
        "camera_starting": camera_starting,
        "camera_error": engine.camera_error,
        "whatsapp_sending": is_wa_sending,
    })


def api_capture_frame_view(request):
    """
    Captures a high-resolution base64 frame from the independent camera for enrollment.
    """
    engine = get_face_engine()
    if not engine.camera_running and not engine.camera_starting:
        engine.start_camera(camera_index=0)

    # Wait up to 2.5 seconds if camera was initializing
    for _ in range(25):
        if engine.current_raw_frame is not None:
            break
        time.sleep(0.1)

    success, b64_frame, msg = engine.capture_current_frame()
    if not success:
        return JsonResponse({"success": False, "message": msg}, status=503)
    return JsonResponse({"success": True, "image_base64": b64_frame, "message": msg})


@login_required
def independent_camera_window_view(request):
    """
    Renders the dedicated independent camera floating window for receptionist / second display.
    """
    profile = GymProfile.get_solo()
    context = {
        "profile": profile,
        "today_checkins_count": CheckInEvent.objects.filter(checked_in_at__date=timezone.localdate()).count(),
        "enrolled_count": Member.objects.filter(has_face_enrolled=True).count(),
    }
    return render(request, "face_recognition/camera_window.html", context)


@csrf_exempt
@login_required
def api_test_gate_trigger(request):
    """
    Test trigger endpoint for the electronic gate relay (LAN Local IP / Serial).
    Allows managers to test the gate connection from Settings or Kiosk.
    """
    profile = GymProfile.get_solo()
    engine = get_face_engine()

    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            body = {}
        ip_override = body.get("gate_ip_address") or request.POST.get("gate_ip_address")
        if ip_override:
            profile.gate_ip_address = ip_override.strip()
        port_override = body.get("gate_ip_port") or request.POST.get("gate_ip_port")
        if port_override:
            try:
                profile.gate_ip_port = int(port_override)
            except Exception:
                pass
        type_override = body.get("gate_relay_type") or request.POST.get("gate_relay_type")
        if type_override:
            profile.gate_relay_type = type_override.strip()
        path_override = body.get("gate_http_path") or request.POST.get("gate_http_path")
        if path_override:
            profile.gate_http_path = path_override.strip()

    success, msg = engine.trigger_gate_relay(profile=profile, sync_execute=True)
    return JsonResponse({
        "success": success,
        "message": msg,
        "gate_relay_type": profile.gate_relay_type,
        "gate_ip": f"{profile.gate_ip_address}:{profile.gate_ip_port}",
    })


@csrf_exempt
@login_required
def api_enroll_manager_face(request):
    """
    Enrolls the Gym Manager's official face embedding.
    Extracts 128-D SFace feature vectors and crops face thumbnail into GymProfile.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صالحة."}, status=405)

    profile = GymProfile.get_solo()
    raw_img = None
    if "image" in request.FILES:
        raw_img = request.FILES["image"].read()
    elif "image" in request.POST:
        raw_img = request.POST.get("image")
    elif request.body:
        try:
            body_str = request.body.decode("utf-8") if isinstance(request.body, bytes) else str(request.body)
            data = json.loads(body_str)
            raw_img = data.get("image") or data.get("image_base64")
        except Exception:
            pass

    engine = get_face_engine()
    if not engine.ensure_models_loaded(timeout=6.0):
        return JsonResponse({"success": False, "message": "محرك الذكاء الاصطناعي قيد التهيئة، يرجى المحاولة بعد لحظات."}, status=503)

    source = request.POST.get("source") or ""
    if not raw_img or source == "same":
        with engine.frame_lock:
            if engine.current_raw_frame is not None:
                raw_img = engine.current_raw_frame.copy()
            elif engine.latest_jpeg_bytes is not None:
                raw_img = engine.latest_jpeg_bytes

    if not raw_img:
        return JsonResponse({"success": False, "message": "لم يتم التقاط صورة من الكاميرا، يرجى التأكد من تشغيل الكاميرا."}, status=400)

    det_thresh = max(0.40, float(profile.face_min_confidence or 0.55) - 0.10)
    success, emb, crop_bytes, err = engine.extract_embedding_and_crop(raw_img, score_threshold=det_thresh)

    if not success or emb is None:
        return JsonResponse({"success": False, "message": err or "تعذر التعرف على وجه واضح في الصورة. يرجى النظر للكاميرا مع إضاءة جيدة."}, status=400)

    try:
        step = int(request.POST.get("step", 1) or 1)
    except (ValueError, TypeError):
        step = 1

    append_mode = str(request.POST.get("append", "false")).lower() in ["true", "1"] or (step > 1)
    current_embs = list(profile.manager_face_embeddings or []) if append_mode else []
    current_embs.append(emb.tolist() if hasattr(emb, "tolist") else emb)

    profile.manager_face_embeddings = current_embs
    profile.manager_face_enrolled = True
    profile.manager_face_unlock_enabled = True
    profile.manager_face_enrolled_at = timezone.now()

    if crop_bytes and (step == 1 or not profile.manager_face_photo or not append_mode):
        filename = f"manager_face_{int(time.time())}.jpg"
        if profile.manager_face_photo:
            try:
                profile.manager_face_photo.delete(save=False)
            except Exception:
                pass
        profile.manager_face_photo.save(filename, ContentFile(crop_bytes), save=False)

    profile.save()

    return JsonResponse({
        "success": True,
        "step": step,
        "total_steps": 5,
        "embeddings_count": len(current_embs),
        "message": f"✓ تم التقاط وحفظ الموضع ({step} من 5) بنجاح!",
        "photo_url": profile.manager_face_photo.url if profile.manager_face_photo else None,
        "enrolled_at": profile.manager_face_enrolled_at.strftime("%Y-%m-%d %H:%M"),
    })


@csrf_exempt
@login_required
def api_delete_manager_face(request):
    """
    Deletes the enrolled face records for the Gym Manager.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صالحة."}, status=405)

    profile = GymProfile.get_solo()
    profile.manager_face_enrolled = False
    profile.manager_face_embeddings = []
    profile.manager_face_enrolled_at = None
    if profile.manager_face_photo:
        try:
            profile.manager_face_photo.delete(save=False)
        except Exception:
            pass
        profile.manager_face_photo = None
    profile.save()

    return JsonResponse({
        "success": True,
        "message": "✓ تم حذف بصمة وجه المدير بنجاح.",
    })


@csrf_exempt
@login_required
def api_enroll_employee_face(request, employee_id):
    """
    Enrolls an employee's face embedding from webcam frame or photo upload.
    Stores multi-angle vectors and crops face thumbnail into Employee model.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صالحة."}, status=405)

    from apps.payroll.models import Employee
    employee = get_object_or_404(Employee, id=employee_id)

    raw_img = None
    if "image" in request.FILES:
        raw_img = request.FILES["image"].read()
    elif "image" in request.POST:
        raw_img = request.POST.get("image", "").strip()

    if not raw_img:
        return JsonResponse({"success": False, "message": "لم يتم إرسال أي صورة لتسجيل البصمة."}, status=400)

    engine = get_face_engine()
    if not engine.ensure_models_loaded(timeout=5.0):
        return JsonResponse({"success": False, "message": "نماذج الذكاء الاصطناعي قيد التحميل، يرجى الانتظار ثوانٍ."}, status=503)

    success, embs, crop_bytes, err_msg = engine.extract_face_and_embedding(raw_img)
    if not success or not embs:
        return JsonResponse({"success": False, "message": err_msg or "فشل في رصد الوجه. تأكد من إضاءة الغرفة ومواجهة الكاميرا مباشرة."}, status=422)

    step = int(request.POST.get("step", "1"))
    current_embs = employee.face_embeddings or []
    if step == 1 and not request.POST.get("append", ""):
        current_embs = []

    for vec in embs:
        if len(vec) == 128:
            current_embs.append(vec)

    employee.face_embeddings = current_embs[-5:]
    employee.face_enrolled = True
    employee.face_enrolled_at = timezone.now()

    if crop_bytes and (step == 1 or not employee.face_photo):
        filename = f"emp_{employee.id}_{int(time.time())}.jpg"
        employee.face_photo.save(filename, ContentFile(crop_bytes), save=False)

    employee.save()
    engine.refresh_cache(force=True)

    return JsonResponse({
        "success": True,
        "step": step,
        "total_steps": 5,
        "embeddings_count": len(employee.face_embeddings),
        "message": f"✓ تم التقاط وحفظ بصمة وجه {employee.name} بنجاح!",
        "photo_url": employee.face_photo.url if employee.face_photo else None,
        "enrolled_at": employee.face_enrolled_at.strftime("%Y-%m-%d %H:%M"),
    })


@csrf_exempt
@login_required
def api_delete_employee_face(request, employee_id):
    """Deletes face biometric records for an employee."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صالحة."}, status=405)

    from apps.payroll.models import Employee
    employee = get_object_or_404(Employee, id=employee_id)
    employee.face_enrolled = False
    employee.face_embeddings = []
    employee.face_enrolled_at = None
    if employee.face_photo:
        try:
            employee.face_photo.delete(save=False)
        except Exception:
            pass
        employee.face_photo = None
    employee.save()

    engine = get_face_engine()
    engine.refresh_cache(force=True)

    return JsonResponse({
        "success": True,
        "message": f"✓ تم حذف بصمة وجه {employee.name} بنجاح.",
    })


@csrf_exempt
def api_verify_manager_face_unlock(request):
    """
    Verifies live webcam frame against enrolled manager face embeddings.
    If matched >= threshold:
      - Sets manager_page_unlocked and settings_page_unlocked in session.
      - Returns success=True with redirect_url.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة الطلب غير صالحة."}, status=405)

    profile = GymProfile.get_solo()
    if not profile.manager_face_unlock_enabled:
        return JsonResponse({
            "success": False,
            "message": "خاصية فتح القفل ببصمة الوجه معطلة في إعدادات النظام.",
        }, status=403)

    if not profile.manager_face_enrolled or not profile.manager_face_embeddings:
        return JsonResponse({
            "success": False,
            "message": "لم يتم تسجيل بصمة وجه المدير في إعدادات المطور بعد.",
        }, status=400)

    raw_img = None
    target_url = request.POST.get("target_url") or "/manager/"

    if "image" in request.FILES:
        raw_img = request.FILES["image"].read()
    elif "image" in request.POST:
        raw_img = request.POST.get("image")
    elif request.body:
        try:
            data = json.loads(request.body)
            raw_img = data.get("image")
            if "target_url" in data:
                target_url = data["target_url"]
        except Exception:
            pass

    engine = get_face_engine()
    if not engine.ensure_models_loaded(timeout=6.0):
        return JsonResponse({"success": False, "message": "محرك الذكاء الاصطناعي قيد التحضير."}, status=503)

    source = request.POST.get("source") or request.GET.get("source") or ""

    # 1. Quick pickup from live background engine detection within last 3.5 seconds
    if source == "same" and getattr(engine, "last_detected_manager", None):
        last_m = engine.last_detected_manager
        if (time.time() - last_m.get("timestamp", 0)) <= 3.5 and last_m.get("matched"):
            pct_score = round(last_m["score"] * 100)
            request.session["manager_page_unlocked"] = True
            request.session["settings_page_unlocked"] = True
            request.session["trainers_page_unlocked"] = True
            request.session["retention_page_unlocked"] = True
            request.session["reports_page_unlocked"] = True
            request.session["developer_options_unlocked"] = False
            request.session.modified = True
            request.session.save()
            return JsonResponse({
                "success": True,
                "matched": True,
                "score": pct_score,
                "box": last_m.get("box"),
                "message": f"✓ تم التحقق بنجاح! مرحباً بالمدير (نسبة التطابق {pct_score}%).",
                "redirect_url": target_url,
            })

    if not raw_img or source == "same":
        # Shared system camera: grab current live frame directly from OpenCV engine
        with engine.frame_lock:
            if engine.current_raw_frame is not None:
                raw_img = engine.current_raw_frame.copy()
            elif engine.latest_jpeg_bytes is not None:
                raw_img = engine.latest_jpeg_bytes

    if raw_img is None:
        return JsonResponse({"success": False, "score": 0, "message": "لم يتم التقاط صورة من الكاميرا، وكاميرا النظام غير متصلة."}, status=200)

    det_thresh = max(0.40, float(profile.face_min_confidence or 0.55) - 0.10)
    success, query_emb, _, err = engine.extract_embedding_and_crop(raw_img, score_threshold=det_thresh)

    if not success or query_emb is None:
        return JsonResponse({
            "success": False,
            "matched": False,
            "score": 0,
            "message": "لم يتم اكتشاف وجه واضح أمام الكاميرا. يرجى النظر مباشرة إلى الكاميرا.",
        }, status=200)

    q_vec = np.array(query_emb, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm > 0:
        q_vec = q_vec / q_norm

    best_score = -1.0
    for emb in profile.manager_face_embeddings:
        m_vec = np.array(emb, dtype=np.float32)
        m_norm = np.linalg.norm(m_vec)
        if m_norm > 0:
            m_vec = m_vec / m_norm
        score = float(np.dot(q_vec, m_vec))
        if score > best_score:
            best_score = score

    # Threshold for manager unlock (with multi-angle embeddings)
    thresh = min(0.58, max(0.48, profile.face_match_threshold_ratio - 0.06))
    pct_score = round(max(0.0, best_score) * 100)

    if best_score >= thresh:
        request.session["manager_page_unlocked"] = True
        request.session["settings_page_unlocked"] = True
        request.session["trainers_page_unlocked"] = True
        request.session["retention_page_unlocked"] = True
        request.session["reports_page_unlocked"] = True
        # Developer settings requires developer password and is NOT unlocked by manager face
        request.session["developer_options_unlocked"] = False
        request.session.modified = True
        request.session.save()

        return JsonResponse({
            "success": True,
            "matched": True,
            "score": pct_score,
            "message": f"✓ تم التحقق بنجاح! مرحباً بالمدير (نسبة التطابق {pct_score}%).",
            "redirect_url": target_url,
        })
    else:
        return JsonResponse({
            "success": False,
            "matched": False,
            "score": pct_score,
            "message": f"الوجه قيد الفحص (نسبة التطابق {pct_score}%). يرجى النظر مباشرة للكاميرا.",
        }, status=200)



