import os
import io
import time
import base64
import threading
from typing import Optional, Tuple, List, Dict, Any
import numpy as np
import cv2
from django.conf import settings


class FaceEngine:
    """
    High-performance, CPU-optimized Face Recognition & Detection Service.
    Powered by OpenCV DNN:
      - YuNet: Ultra-fast real-time face detection & 5-point landmark alignment.
      - SFace: 128-D Deep facial feature embedding with Cosine Similarity metric.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FaceEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.models_dir = os.path.join(settings.BASE_DIR, "models")
        self.yunet_path = os.path.join(self.models_dir, "face_detection_yunet_2023mar.onnx")
        self.sface_path = os.path.join(self.models_dir, "face_recognition_sface_2021dec.onnx")

        self.detector = None
        self.recognizer = None
        self.last_input_size = (640, 480)
        self.inference_lock = threading.RLock()

        # In-memory cached embeddings for sub-millisecond 1:N vector matching:
        # {member_id: [np.ndarray(128,), ...]}
        self.cache_lock = threading.RLock()
        self.embeddings_cache: Dict[int, List[np.ndarray]] = {}
        self.active_embeddings_cache: Dict[int, List[np.ndarray]] = {}
        self.inactive_embeddings_cache: Dict[int, List[np.ndarray]] = {}
        self.active_matrix: Optional[np.ndarray] = None
        self.active_ids: Optional[np.ndarray] = None
        self.inactive_matrix: Optional[np.ndarray] = None
        self.inactive_ids: Optional[np.ndarray] = None
        self.cache_timestamp = 0

        # Persistent Independent Background Camera Worker State
        self.camera_lock = threading.RLock()
        self.frame_lock = threading.RLock()
        self.event_lock = threading.RLock()
        self.cap = None
        self.camera_running = False
        self.camera_index = 0
        self.camera_thread = None
        self.camera_error = None

        self.current_raw_frame = None
        self.annotated_frame = None
        self.latest_jpeg_bytes = None
        self.latest_event = None
        self.last_event_time = 0
        self.member_last_overlay_time: Dict[int, float] = {}
        self.camera_starting = False
        self._placeholder_jpeg = None
        self._create_placeholder_jpeg()

        # Asynchronously initialize models so server boot and HTTP requests are never delayed
        self.models_loading = True
        threading.Thread(target=self._init_models_worker, daemon=True).start()
        self._initialized = True

    def _init_models_worker(self):
        try:
            self._init_models()
        finally:
            self.models_loading = False

    def _init_models(self):
        with self.inference_lock:
            if os.path.exists(self.yunet_path) and os.path.getsize(self.yunet_path) > 100000:
                try:
                    self.detector = cv2.FaceDetectorYN.create(
                        model=self.yunet_path,
                        config="",
                        input_size=self.last_input_size,
                        score_threshold=0.55,
                        nms_threshold=0.30,
                        top_k=10,
                        backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                        target_id=cv2.dnn.DNN_TARGET_CPU
                    )
                except Exception as e:
                    print(f"Error initializing YuNet face detector: {e}")
                    self.detector = None
            else:
                print(f"YuNet ONNX model not found at {self.yunet_path}")

            if os.path.exists(self.sface_path) and os.path.getsize(self.sface_path) > 10000000:
                try:
                    self.recognizer = cv2.FaceRecognizerSF.create(
                        model=self.sface_path,
                        config="",
                        backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                        target_id=cv2.dnn.DNN_TARGET_CPU
                    )
                except Exception as e:
                    print(f"Error initializing SFace face recognizer: {e}")
                    self.recognizer = None
            else:
                print(f"SFace ONNX model not found at {self.sface_path}")

    @property
    def is_ready(self) -> bool:
        return self.detector is not None and self.recognizer is not None

    def decode_image(self, image_data: Any) -> Optional[np.ndarray]:
        """Accepts raw bytes, base64 data string, or numpy array and returns BGR image."""
        if image_data is None:
            return None
        if isinstance(image_data, np.ndarray):
            return image_data

        if isinstance(image_data, str):
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]
            try:
                raw_bytes = base64.b64decode(image_data)
                arr = np.frombuffer(raw_bytes, np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                return None

        if isinstance(image_data, (bytes, bytearray)):
            try:
                arr = np.frombuffer(image_data, np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                return None

        return None

    def detect_faces(self, frame: np.ndarray, score_threshold: float = 0.55) -> List[np.ndarray]:
        """Detects faces in frame and returns list of face bounding/landmark arrays."""
        if not self.is_ready or frame is None:
            return []

        h, w = frame.shape[:2]
        with self.inference_lock:
            if (w, h) != self.last_input_size:
                self.detector.setInputSize((w, h))
                self.last_input_size = (w, h)
            self.detector.setScoreThreshold(score_threshold)
            ret, faces = self.detector.detect(frame)

        if ret is None or faces is None:
            return []
        return [f for f in faces]

    def extract_embedding_and_crop(
        self,
        frame: np.ndarray,
        score_threshold: float = 0.55
    ) -> Tuple[bool, Optional[List[float]], Optional[bytes], str]:
        """
        Detects the most prominent face in the frame, extracts the 128-D SFace embedding,
        and returns a clean JPEG thumbnail crop.
        """
        if not self.is_ready:
            return False, None, None, "محرك الذكاء الاصطناعي ونماذج الوجه غير محملة."

        mat = self.decode_image(frame)
        if mat is None or mat.size == 0:
            return False, None, None, "الصورة غير صالحة أو تعذر فك تشفيرها."

        faces = self.detect_faces(mat, score_threshold=score_threshold)
        if not faces:
            return False, None, None, "لم يتم العثور على أي وجه واضح في الصورة. يرجى النظر إلى الكاميرا مباشرة."

        # Pick the largest face (highest width * height)
        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        primary_face = faces_sorted[0]

        with self.inference_lock:
            try:
                # 1. Align and crop face to standard 112x112 via landmarks
                aligned_face = self.recognizer.alignCrop(mat, primary_face)
                # 2. Extract 128-D deep feature vector
                feature = self.recognizer.feature(aligned_face)
                norm_feat = feature.flatten()
                norm = np.linalg.norm(norm_feat)
                if norm > 0:
                    norm_feat = norm_feat / norm
                embedding_list = [float(x) for x in norm_feat]
            except Exception as e:
                return False, None, None, f"فشل استخراج بصمة الوجه: {str(e)}"

        # 3. Create square avatar crop for UI thumbnail
        h, w = mat.shape[:2]
        fx, fy, fw, fh = map(int, primary_face[:4])
        pad = int(max(fw, fh) * 0.25)
        x1 = max(0, fx - pad)
        y1 = max(0, fy - pad)
        x2 = min(w, fx + fw + pad)
        y2 = min(h, fy + fh + pad)
        crop_img = mat[y1:y2, x1:x2]

        crop_jpeg = None
        if crop_img.size > 0:
            crop_resized = cv2.resize(crop_img, (200, 200), interpolation=cv2.INTER_AREA)
            ret, buf = cv2.imencode(".jpg", crop_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if ret:
                crop_jpeg = buf.tobytes()

        return True, embedding_list, crop_jpeg, "تم استخراج بصمة الوجه بنجاح."

    def extract_embedding_for_face(self, mat: np.ndarray, face_data: np.ndarray) -> Optional[List[float]]:
        """Extracts normalized 128-D embedding from an aligned face box & landmarks."""
        if not self.is_ready:
            return None
        with self.inference_lock:
            try:
                aligned = self.recognizer.alignCrop(mat, face_data)
                feat = self.recognizer.feature(aligned)
                norm_feat = feat.flatten()
                norm = np.linalg.norm(norm_feat)
                if norm > 0:
                    norm_feat = norm_feat / norm
                return [float(x) for x in norm_feat]
            except Exception:
                return None

    def refresh_cache(self, force: bool = False):
        """
        Pre-loads enrolled member embeddings into partitioned fast numpy vector matrices:
          - active_matrix / active_ids: members with an active valid subscription today.
          - inactive_matrix / inactive_ids: expired or pending members.
        Enables ultra-high-performance vectorized BLAS searching (active members matched first).
        """
        now = time.time()
        if not force and (now - self.cache_timestamp < 10):
            return

        from apps.members.models import Member
        from datetime import date

        today = date.today()

        with self.cache_lock:
            new_active = {}
            new_inactive = {}
            active_vec_list = []
            active_id_list = []
            inactive_vec_list = []
            inactive_id_list = []

            qs = Member.objects.filter(has_face_enrolled=True).only("id", "face_embeddings", "last_subscription_end")
            for m in qs:
                embs = m.face_embeddings or []
                vecs = []
                for e in embs:
                    if isinstance(e, list) and len(e) == 128:
                        arr = np.array(e, dtype=np.float32)
                        n = np.linalg.norm(arr)
                        if n > 0:
                            arr = arr / n
                        vecs.append(arr)
                if vecs:
                    is_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
                    if is_active:
                        new_active[m.id] = vecs
                        for v in vecs:
                            active_vec_list.append(v)
                            active_id_list.append(m.id)
                    else:
                        new_inactive[m.id] = vecs
                        for v in vecs:
                            inactive_vec_list.append(v)
                            inactive_id_list.append(m.id)

            self.active_embeddings_cache = new_active
            self.inactive_embeddings_cache = new_inactive
            self.embeddings_cache = {**new_active, **new_inactive}

            if active_vec_list:
                self.active_matrix = np.vstack(active_vec_list).astype(np.float32)
                self.active_ids = np.array(active_id_list, dtype=np.int64)
            else:
                self.active_matrix = None
                self.active_ids = None

            if inactive_vec_list:
                self.inactive_matrix = np.vstack(inactive_vec_list).astype(np.float32)
                self.inactive_ids = np.array(inactive_id_list, dtype=np.int64)
            else:
                self.inactive_matrix = None
                self.inactive_ids = None

            self.cache_timestamp = now

    def match_face_vector(
        self,
        query_embedding: List[float],
        cosine_threshold: float = 0.363
    ) -> Tuple[Optional[int], float]:
        """
        Calculates cosine similarity with two-phase fast-path optimization:
        Phase 1: Search ACTIVE members first using vectorized BLAS dot product. If matched >= threshold, return IMMEDIATELY.
        Phase 2: If no active match found, search INACTIVE/EXPIRED members (to trigger expired entry alerts).
        """
        self.refresh_cache()
        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        with self.cache_lock:
            act_mat = self.active_matrix
            act_ids = self.active_ids
            inact_mat = self.inactive_matrix
            inact_ids = self.inactive_ids

        # ==========================================================
        # PHASE 1: FAST-PATH SEARCH ACTIVE MEMBERS FIRST (Instant Matrix SIMD)
        # ==========================================================
        best_active_id = None
        best_active_score = -1.0

        if act_mat is not None and act_mat.size > 0:
            act_scores = np.dot(act_mat, q_vec)
            best_idx = int(np.argmax(act_scores))
            best_active_score = float(act_scores[best_idx])
            if best_active_score >= cosine_threshold:
                best_active_id = int(act_ids[best_idx])
                # MATCH FOUND IN ACTIVE MEMBERS! Return immediately without touching inactive faces:
                return best_active_id, best_active_score

        # ==========================================================
        # PHASE 2: SEARCH INACTIVE/EXPIRED MEMBERS ONLY IF NO ACTIVE MATCH
        # ==========================================================
        best_inactive_id = None
        best_inactive_score = -1.0

        if inact_mat is not None and inact_mat.size > 0:
            inact_scores = np.dot(inact_mat, q_vec)
            best_idx = int(np.argmax(inact_scores))
            best_inactive_score = float(inact_scores[best_idx])
            if best_inactive_score >= cosine_threshold:
                best_inactive_id = int(inact_ids[best_idx])
                return best_inactive_id, best_inactive_score

        top_score = max(best_active_score, best_inactive_score, 0.0)
        return None, top_score

    def trigger_gate_relay(self, port: str = "COM3"):
        """Triggers turnstile / door electric lock relay pulse for automatic gate entry."""
        def _relay_worker():
            try:
                import serial
                with serial.Serial(port, 9600, timeout=1) as ser:
                    # Standard USB Relay ON command (Channel 1 ON)
                    ser.write(b"\xA0\x01\x01\xA2")
                    time.sleep(2.5)  # Open turnstile for 2.5 seconds
                    # Standard USB Relay OFF command (Channel 1 OFF)
                    ser.write(b"\xA0\x01\x00\xA1")
            except Exception as e:
                # Silently catch if serial hardware is simulated or not plugged in
                print(f"[Gate Relay Signal] Turnstile trigger on {port} (Hardware message: {e})")

        threading.Thread(target=_relay_worker, daemon=True).start()

    def start_camera(self, camera_index: int = 0):
        """Starts the persistent independent camera capture thread."""
        import sys
        if any(cmd in sys.argv for cmd in ["test", "migrate", "makemigrations"]):
            return

        with self.camera_lock:
            if self.camera_running or self.camera_starting:
                return
            self.stop_camera()
            self.camera_index = camera_index
            self.camera_starting = True
            self.camera_running = False
            self.camera_thread = threading.Thread(target=self._capture_worker, daemon=True)
            self.camera_thread.start()

    def stop_camera(self):
        """Stops the persistent background camera."""
        self.camera_running = False
        self.camera_starting = False
        with self.frame_lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    def _capture_worker(self):
        try:
            self.cap = None
            backends = [cv2.CAP_MSMF, cv2.CAP_ANY, cv2.CAP_DSHOW]
            for backend in backends:
                try:
                    c = cv2.VideoCapture(self.camera_index, backend)
                    if c and c.isOpened():
                        self.cap = c
                        break
                except Exception:
                    continue

            if not self.cap or not self.cap.isOpened():
                self.camera_error = f"تعذر فتح الكاميرا رقم {self.camera_index}. تأكد من توصيل الكاميرا بالجهاز."
                print(f"[FaceEngine] {self.camera_error}")
                self.camera_running = False
                self.camera_starting = False
                return

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.camera_error = None
            self.camera_running = True
            self.camera_starting = False
            print(f"[FaceEngine] Independent Camera #{self.camera_index} is active and running in background.")

            frame_count = 0
            while self.camera_running:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    time.sleep(0.03)
                    continue

                with self.frame_lock:
                    self.current_raw_frame = frame.copy()

                frame_count += 1
                # Run recognition roughly 6 times per second (every 5 frames at 30 FPS)
                if frame_count % 5 == 0:
                    self._process_recognition_frame(frame)

                display_frame = self.annotated_frame if self.annotated_frame is not None else frame
                ret_jpg, buf = cv2.imencode(".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ret_jpg:
                    with self.frame_lock:
                        self.latest_jpeg_bytes = buf.tobytes()

                time.sleep(0.02)
        except Exception as e:
            self.camera_error = str(e)
            print(f"[FaceEngine] Camera worker exception: {e}")
        finally:
            with self.frame_lock:
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None
            self.camera_running = False
            self.camera_starting = False

    def _process_recognition_frame(self, frame: np.ndarray):
        if not self.is_ready:
            return

        from django.db import connection
        try:
            from apps.core.models import GymProfile
            from apps.members.models import Member, CheckInEvent
            from django.utils import timezone
            from datetime import timedelta

            profile = GymProfile.get_solo()
            if not profile.face_camera_enabled:
                self.annotated_frame = frame
                return

            det_thresh = max(float(profile.face_min_confidence or 0.68), 0.65)
            thresh = max(float(profile.face_match_threshold or 0.45), 0.42)
            debounce_sec = max(int(profile.face_debounce_seconds or 60), 60)

            faces = self.detect_faces(frame, score_threshold=det_thresh)
            if not faces:
                self.annotated_frame = frame
                return

            annotated = frame.copy()
            for face in faces:
                x, y, w, h = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                # Filter out background noise, artifacts, and tiny blurry detections (min 70x70)
                if w < 70 or h < 70:
                    continue
                # Aspect ratio check: face bounding box must be plausible (0.7 to 1.85)
                aspect = float(h) / max(float(w), 1.0)
                if aspect < 0.7 or aspect > 1.85:
                    continue
                # YuNet confidence score check
                face_conf = float(face[14]) if len(face) > 14 else 1.0
                if face_conf < det_thresh:
                    continue

                emb = self.extract_embedding_for_face(frame, face)
                if not emb:
                    continue

                member_id, match_score = self.match_face_vector(emb, cosine_threshold=thresh)
                if member_id:
                    member = Member.objects.filter(id=member_id).first()
                    if member:
                        member.refresh_status()
                        eligibility = member.check_access_eligibility()
                        access_allowed = eligibility["allowed"]
                        is_active = access_allowed

                        color = (34, 197, 94) if is_active else (239, 68, 68)
                        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)

                        status_txt = f"{member.name} ({round(match_score * 100)}%)"
                        cv2.putText(annotated, status_txt, (x, max(25, y - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)

                        # Strict 1-Minute (or configured debounce) Cooldown Check
                        now = timezone.now()
                        now_ts = time.time()
                        last_overlay_ts = self.member_last_overlay_time.get(member.id, 0.0)

                        if (now_ts - last_overlay_ts) < debounce_sec:
                            # Already notified and logged recently - suppress duplicate overlay!
                            continue

                        cutoff = now - timedelta(seconds=debounce_sec)
                        recent_checkin = CheckInEvent.objects.filter(
                            member=member,
                            checked_in_at__gte=cutoff
                        ).first()

                        if access_allowed and not recent_checkin:
                            CheckInEvent.objects.create(
                                member=member,
                                method="face",
                                confidence=match_score,
                                status_snapshot=member.current_status,
                                days_left_snapshot=member.days_left,
                                debt_snapshot=member.current_remaining,
                            )

                        gate_opened = bool(access_allowed and profile.gate_relay_enabled)
                        if gate_opened:
                            self.trigger_gate_relay(port=profile.gate_relay_port or "COM3")

                        today = timezone.localdate()
                        expired_days = (today - member.last_subscription_end).days if (member.last_subscription_end and not member.is_active) else 0
                        end_date_str = member.last_subscription_end.strftime("%d/%m/%Y") if member.last_subscription_end else "غير محدد"

                        event_data = {
                            "id": str(now_ts),
                            "timestamp": now_ts,
                            "score": round(match_score * 100, 1),
                            "gate_opened": gate_opened,
                            "access_allowed": access_allowed,
                            "deny_reason": eligibility["reason"] if not access_allowed else None,
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
                            }
                        }

                        # Record overlay timestamp to enforce the > 1 minute debounce strictly
                        self.member_last_overlay_time[member.id] = now_ts

                        with self.event_lock:
                            self.latest_event = event_data
                            self.last_event_time = now_ts
                else:
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (160, 160, 160), 1)

            self.annotated_frame = annotated
        except Exception as e:
            if "table is locked" not in str(e):
                print(f"[FaceEngine] Recognition frame info: {e}")
        finally:
            connection.close()

    def get_latest_jpeg(self) -> bytes:
        """Returns the latest JPEG frame from the continuous camera feed."""
        with self.frame_lock:
            if self.latest_jpeg_bytes:
                return self.latest_jpeg_bytes
        if self._placeholder_jpeg is None:
            self._create_placeholder_jpeg()
        return self._placeholder_jpeg

    def _create_placeholder_jpeg(self):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        for y in range(480):
            img[y, :, :] = (int(10 + y * 0.02), int(16 + y * 0.03), int(24 + y * 0.04))
        cv2.putText(img, "HULK GYM - INDEPENDENT CAMERA", (80, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (16, 185, 129), 2, cv2.LINE_AA)
        cv2.putText(img, "INITIALIZING STREAM...", (180, 270),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1, cv2.LINE_AA)
        ret, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ret:
            self._placeholder_jpeg = buf.tobytes()

    def get_latest_event(self) -> Optional[dict]:
        """Returns the most recent face recognition event if fresh (within 3.5 seconds)."""
        with self.event_lock:
            if self.latest_event:
                if (time.time() - float(self.latest_event.get("timestamp", 0))) > 3.5:
                    self.latest_event = None
            return self.latest_event

    def capture_current_frame(self) -> Tuple[bool, Optional[str], str]:
        """Returns base64 JPEG data URL of the latest frame from the independent camera."""
        with self.frame_lock:
            frame = self.current_raw_frame.copy() if self.current_raw_frame is not None else None
        if frame is None:
            return False, None, "لا يوجد إطار متاح من الكاميرا حالياً."
        ret, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ret:
            return False, None, "فشل ترميز الصورة."
        b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
        return True, f"data:image/jpeg;base64,{b64}", "تم التقاط الإطار بنجاح."


# Global Singleton accessor
def get_face_engine() -> FaceEngine:
    engine = FaceEngine()
    if not engine.camera_running and not engine.camera_starting:
        try:
            from apps.core.models import GymProfile
            profile = GymProfile.get_solo()
            if profile.face_camera_enabled:
                engine.start_camera(camera_index=0)
        except Exception:
            pass
    return engine
