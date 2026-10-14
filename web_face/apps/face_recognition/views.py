import json
import time
from datetime import timedelta
from decimal import Decimal
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
    thresh = float(profile.face_match_threshold or 0.363)
    det_thresh = float(profile.face_min_confidence or 0.55)

    success, emb, crop_bytes, msg = engine.extract_embedding_and_crop(image_b64, score_threshold=det_thresh)
    if not success or not emb:
        return JsonResponse({"success": False, "matched": False, "message": msg})

    member_id, score = engine.match_face_vector(emb, cosine_threshold=thresh)
    if not member_id:
        return JsonResponse({
            "success": True,
            "matched": False,
            "score": round(score * 100, 1),
            "message": "وجه غير مسجل في النظام.",
        })

    member = Member.objects.filter(id=member_id).first()
    if not member:
        return JsonResponse({"success": False, "matched": False, "message": "العضو غير موجود."})

    # Update active/expired status against today
    member.refresh_status()

    # Debounce check (prevent duplicate logs within debounce window)
    debounce_sec = profile.face_debounce_seconds or 60
    cutoff = timezone.now() - timedelta(seconds=debounce_sec)
    recent_checkin = CheckInEvent.objects.filter(member=member, checked_in_at__gte=cutoff).first()

    logged_new = False
    if not recent_checkin:
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
        if member.is_active and profile.gate_relay_enabled:
            engine.trigger_gate_relay(port=profile.gate_relay_port or "COM3")

    today = timezone.localdate()
    expired_days = (today - member.last_subscription_end).days if (member.last_subscription_end and not member.is_active) else 0
    end_date_str = member.last_subscription_end.strftime("%d/%m/%Y") if member.last_subscription_end else "غير محدد"

    return JsonResponse({
        "success": True,
        "matched": True,
        "logged_new": logged_new,
        "debounced": not logged_new,
        "score": round(score * 100, 1),
        "member": {
            "id": member.id,
            "name": member.name,
            "member_id": member.member_id,
            "is_active": member.is_active,
            "days_left": member.days_left,
            "end_date": end_date_str,
            "expired_days": expired_days,
            "has_debt": member.has_debt,
            "remaining": str(member.current_remaining),
            "plan": member.last_subscription_type or "باقة أساسية",
            "photo_url": member.face_photo.url if member.face_photo else None,
        },
        "gate_opened": member.is_active and profile.gate_relay_enabled,
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
        while True:
            frame_bytes = engine.get_latest_jpeg()
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.035)

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

    # If initial poll from a newly loaded page (since_ts <= 0), synchronize timestamp and do not replay old past events
    if since_ts <= 0.0:
        return JsonResponse({
            "success": True,
            "has_event": False,
            "server_time": now_ts,
            "camera_running": engine.camera_running,
            "camera_error": engine.camera_error,
        })

    event = engine.get_latest_event()
    if event and (event.get("timestamp", 0) > since_ts) and (now_ts - float(event.get("timestamp", 0)) <= 3.5):
        return JsonResponse({
            "success": True,
            "has_event": True,
            "server_time": now_ts,
            "camera_running": engine.camera_running,
            "camera_error": engine.camera_error,
            "event": event,
        })

    return JsonResponse({
        "success": True,
        "has_event": False,
        "server_time": now_ts,
        "camera_running": engine.camera_running,
        "camera_error": engine.camera_error,
    })


def api_capture_frame_view(request):
    """
    Captures a high-resolution base64 frame from the independent camera for enrollment.
    """
    engine = get_face_engine()
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

