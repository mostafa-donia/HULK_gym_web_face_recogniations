import os
import io
import time
import base64
import threading
import ssl
import urllib.request
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
        self.last_detected_manager: Optional[dict] = None
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

    def ensure_models_loaded(self, timeout: float = 6.0) -> bool:
        """Waits for asynchronous model loading thread to complete if still in progress."""
        if self.is_ready:
            return True
        start_t = time.time()
        while getattr(self, "models_loading", False) and (time.time() - start_t < timeout):
            time.sleep(0.1)
        return self.is_ready

    def decode_image(self, image_data: Any) -> Optional[np.ndarray]:
        """Accepts raw bytes, base64 data string, or numpy array and returns BGR image with correct EXIF orientation."""
        if image_data is None:
            return None
        if isinstance(image_data, np.ndarray):
            mat = image_data
        else:
            raw_bytes = None
            if isinstance(image_data, str):
                image_str = image_data.strip()
                if "base64," in image_str:
                    image_str = image_str.split("base64,")[1]
                image_str = image_str.replace(" ", "+")
                try:
                    raw_bytes = base64.b64decode(image_str)
                except Exception:
                    raw_bytes = None
            elif isinstance(image_data, (bytes, bytearray)):
                raw_bytes = bytes(image_data)

            if not raw_bytes:
                return None

            mat = None
            # 1. Try decoding with PIL to respect EXIF orientation (e.g. mobile selfies)
            try:
                from PIL import Image, ImageOps
                import io
                pil_img = Image.open(io.BytesIO(raw_bytes))
                pil_img = ImageOps.exif_transpose(pil_img)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                mat = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                mat = None

            # 2. Fallback to direct OpenCV imdecode
            if mat is None:
                try:
                    arr = np.frombuffer(raw_bytes, np.uint8)
                    mat = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                except Exception:
                    return None

        if mat is None or mat.size == 0:
            return None

        # 3. Downscale if image is too large (> 1280px) to prevent YuNet anchor failure
        h, w = mat.shape[:2]
        max_dim = max(h, w)
        if max_dim > 1280:
            scale = 1280.0 / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            mat = cv2.resize(mat, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return mat

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
        if not self.ensure_models_loaded(timeout=5.0):
            return False, None, None, "محرك الذكاء الاصطناعي ونماذج الوجه قيد التهيئة."

        mat = self.decode_image(frame)
        if mat is None or mat.size == 0:
            return False, None, None, "الصورة غير صالحة أو تعذر فك تشفيرها."

        faces = self.detect_faces(mat, score_threshold=score_threshold)
        if not faces and score_threshold > 0.40:
            faces = self.detect_faces(mat, score_threshold=0.40)
        if not faces and score_threshold > 0.30:
            faces = self.detect_faces(mat, score_threshold=0.30)

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
        cosine_threshold: float = 0.65
    ) -> Tuple[Optional[int], float]:
        """
        Calculates cosine similarity with two-phase fast-path optimization:
        Phase 1: Search ACTIVE members first using vectorized BLAS dot product. If matched >= threshold, return IMMEDIATELY.
        Phase 2: If no active match found, search INACTIVE/EXPIRED members (to trigger expired entry alerts).
        Supports cosine_threshold passed as decimal (e.g. 0.65) or percentage integer (e.g. 65).
        """
        if cosine_threshold > 1.0:
            cosine_threshold = cosine_threshold / 100.0
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

    def trigger_gate_relay(self, profile=None, sync_execute: bool = False) -> tuple[bool, str]:
        """
        Triggers turnstile / door electronic lock relay pulse for automatic gate entry.
        Supports:
          1. LAN Local IP via HTTP GET/POST (e.g. http://192.168.1.50:80/open or http://192.168.1.50/relay/0?turn=on)
          2. LAN Local IP via raw TCP Socket (e.g. 192.168.1.50:5000 with payload 'OPEN' or hex bytes)
          3. Legacy Serial USB COM Port (e.g. COM3)
        When called during face verification, runs asynchronously in a daemon thread.
        When sync_execute=True (e.g. test button), executes and returns (success, message).
        """
        if profile is None:
            try:
                from apps.core.models import GymProfile
                profile = GymProfile.get_solo()
            except Exception:
                profile = None

        relay_type = getattr(profile, "gate_relay_type", "lan_http") if profile else "lan_http"
        ip_addr = (getattr(profile, "gate_ip_address", "") or "192.168.1.50").strip() if profile else "192.168.1.50"
        port_num = getattr(profile, "gate_ip_port", 80) if profile else 80
        http_path = (getattr(profile, "gate_http_path", "") or "/open").strip() if profile else "/open"
        http_method = getattr(profile, "gate_http_method", "GET") if profile else "GET"
        tcp_payload = (getattr(profile, "gate_tcp_payload", "") or "OPEN").strip() if profile else "OPEN"
        pulse_sec = float(getattr(profile, "gate_pulse_seconds", 2.5) or 2.5) if profile else 2.5
        com_port = (getattr(profile, "gate_relay_port", "") or "COM3").strip() if profile else "COM3"

        def _do_trigger() -> tuple[bool, str]:
            # 1. LAN HTTP Trigger
            if relay_type == "lan_http" or (ip_addr and not ip_addr.upper().startswith("COM")):
                clean_ip = ip_addr
                if not clean_ip.startswith("http://") and not clean_ip.startswith("https://"):
                    path = http_path if http_path.startswith("/") else f"/{http_path}"
                    target_url = f"http://{clean_ip}:{port_num}{path}"
                else:
                    target_url = clean_ip

                print(f"[Gate Trigger LAN] Sending {http_method} request to gate at: {target_url}")
                try:
                    import urllib.request
                    data_bytes = b"" if http_method.upper() == "POST" else None
                    req = urllib.request.Request(
                        target_url,
                        data=data_bytes,
                        headers={"User-Agent": "Systemize-AccessGate/2.0"},
                        method=http_method.upper()
                    )
                    ssl_ctx = ssl._create_unverified_context()
                    with urllib.request.urlopen(req, context=ssl_ctx, timeout=2.5) as resp:
                        code = resp.getcode()
                        msg = f"تم إرسال إشارة فتح البوابة عبر الشبكة المحلية إلى ({target_url}) بنجاح (كود الاستجابة: {code})."
                        print(f"[Gate Trigger LAN] SUCCESS: {msg}")
                        return True, msg
                except Exception as ex:
                    msg = f"تعذر الاتصال بالبوابة على العنوان {target_url} ({ex})"
                    print(f"[Gate Trigger LAN Error] {msg}")
                    return False, msg

            # 2. LAN TCP Direct Socket Trigger
            elif relay_type == "lan_tcp":
                print(f"[Gate Trigger TCP] Connecting to gate socket at {ip_addr}:{port_num}...")
                try:
                    import socket
                    with socket.create_connection((ip_addr, int(port_num)), timeout=2.5) as s:
                        if tcp_payload.startswith("0x") or "\\x" in tcp_payload or " " in tcp_payload:
                            try:
                                hex_clean = tcp_payload.replace("0x", "").replace("\\x", "").replace(" ", "")
                                p_bytes = bytes.fromhex(hex_clean)
                            except Exception:
                                p_bytes = tcp_payload.encode("utf-8")
                        else:
                            p_bytes = (tcp_payload + "\r\n").encode("utf-8")

                        s.sendall(p_bytes)
                        msg = f"تم إرسال أمر الفتح عبر مقبس TCP إلى {ip_addr}:{port_num} بنجاح ({len(p_bytes)} بايت)."
                        print(f"[Gate Trigger TCP] SUCCESS: {msg}")
                        if pulse_sec > 0:
                            time.sleep(pulse_sec)
                        return True, msg
                except Exception as ex:
                    msg = f"فشل الاتصال بمقبس TCP للبوابة على {ip_addr}:{port_num} ({ex})"
                    print(f"[Gate Trigger TCP Error] {msg}")
                    return False, msg

            # 3. Serial USB Relay (COM Port)
            elif relay_type == "serial_com" or com_port.upper().startswith("COM"):
                try:
                    import serial
                    with serial.Serial(com_port, 9600, timeout=1) as ser:
                        ser.write(b"\xA0\x01\x01\xA2")
                        time.sleep(pulse_sec)
                        ser.write(b"\xA0\x01\x00\xA1")
                    msg = f"تم إرسال نبضة فتح البوابة عبر منفذ السيريال {com_port} بنجاح."
                    print(f"[Gate Relay Serial] SUCCESS: {msg}")
                    return True, msg
                except Exception as ex:
                    msg = f"خطأ في منفذ السيريال {com_port} ({ex})"
                    print(f"[Gate Relay Serial Error] {msg}")
                    return False, msg

            return False, "نوع اتصال البوابة غير محدد."

        if sync_execute:
            return _do_trigger()
        else:
            threading.Thread(target=_do_trigger, daemon=True).start()
            return True, "جاري إرسال إشارة فتح البوابة في الخلفية."

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
            # Prioritize DirectShow (CAP_DSHOW) on Windows to eliminate MSMF error -1072873822
            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_MSMF]
            for backend in backends:
                try:
                    c = cv2.VideoCapture(self.camera_index, backend)
                    if c and c.isOpened():
                        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        c.set(cv2.CAP_PROP_FPS, 30)
                        ret, test_frame = c.read()
                        if ret and test_frame is not None and test_frame.size > 0:
                            self.cap = c
                            break
                        else:
                            c.release()
                except Exception:
                    continue

            if not self.cap or not self.cap.isOpened():
                self.camera_error = f"تعذر فتح الكاميرا رقم {self.camera_index}. تأكد من توصيل الكاميرا بالجهاز."
                print(f"[FaceEngine] {self.camera_error}")
                self.camera_running = False
                self.camera_starting = False
                return

            self.camera_error = None
            self.camera_running = True
            self.camera_starting = False
            print(f"[FaceEngine] Independent Camera #{self.camera_index} is active and running in background via DirectShow.")

            frame_count = 0
            consecutive_failures = 0
            while self.camera_running:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        # Attempt soft auto-reconnect via DirectShow
                        time.sleep(1.0)
                        try:
                            self.cap.release()
                            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            consecutive_failures = 0
                        except Exception:
                            pass
                    time.sleep(0.03)
                    continue

                consecutive_failures = 0
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

            det_thresh = max(float(getattr(profile, "face_min_confidence", 0.55) or 0.55), 0.50)
            thresh = profile.face_match_threshold_ratio
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

                # 1. Check if face belongs to the Gym Manager
                is_manager = False
                best_mgr_score = -1.0
                if profile.manager_face_enrolled and profile.manager_face_embeddings:
                    emb_arr = np.array(emb, dtype=np.float32)
                    emb_norm = np.linalg.norm(emb_arr)
                    if emb_norm > 0:
                        emb_arr = emb_arr / emb_norm
                    for m_emb in profile.manager_face_embeddings:
                        m_vec = np.array(m_emb, dtype=np.float32)
                        m_n = np.linalg.norm(m_vec)
                        if m_n > 0:
                            m_vec = m_vec / m_n
                        sc = float(np.dot(emb_arr, m_vec))
                        if sc > best_mgr_score:
                            best_mgr_score = sc

                    mgr_target_thresh = min(0.58, max(0.50, thresh - 0.06))
                    if best_mgr_score >= mgr_target_thresh:
                        is_manager = True

                if is_manager:
                    # Draw vibrant green box for Manager with crown label
                    mgr_color = (34, 197, 94)
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), mgr_color, 3)
                    mgr_label = f"👑 المدير ({round(best_mgr_score * 100)}%)"
                    cv2.putText(annotated, mgr_label, (x, max(28, y - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, mgr_color, 2, cv2.LINE_AA)
                    with self.frame_lock:
                        self.last_detected_manager = {
                            "matched": True,
                            "score": best_mgr_score,
                            "box": [x, y, w, h],
                            "timestamp": time.time(),
                        }
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
                            self.trigger_gate_relay(profile=profile)

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
                else:
                    color = (0, 0, 230)
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
                    score_pct = round(match_score * 100)
                    status_txt = f"غير مسجل ({score_pct}%)"
                    cv2.putText(annotated, status_txt, (x, max(25, y - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)

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
        cv2.putText(img, "SYSTEMIZE - INDEPENDENT CAMERA", (80, 220),
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
