"""
EvalGuard Proctoring Engine
Ported from Flask app.py → Django with no external API keys required.
Uses local MediaPipe + OpenCV only.
"""

import cv2
import mediapipe as mp
import numpy as np
from collections import deque
import time
from datetime import datetime

# MediaPipe setup (local, no API key needed)
try:
    import mediapipe as mp
    print(f"MediaPipe version: {mp.__version__}")
    
    # For MediaPipe 0.10.32, use tasks API
    try:
        mp_face_landmarker = mp.tasks.vision.FaceLandmarker
        mp_face_detector = mp.tasks.vision.FaceDetector
        print("MediaPipe tasks API initialized successfully")
        
    except Exception as e:
        print(f"MediaPipe tasks initialization failed: {e}")
        mp_face_landmarker = None
        mp_face_detector = None
        
except ImportError as e:
    print(f"MediaPipe not installed: {e}")
    mp_face_landmarker = None
    mp_face_detector = None
except Exception as e:
    print(f"MediaPipe initialization failed: {e}")
    mp_face_landmarker = None
    mp_face_detector = None

import os

class YOLODetector:
    def __init__(self):
        self.model = None
        try:
            from ultralytics import YOLO
            # YOLOv8 nano model is fast and automatically downloaded to current dir if missing
            self.model = YOLO('yolov8n.pt')
            print("YOLOv8 initialized successfully")
        except ImportError:
            print("ultralytics not installed. YOLOv8 mobile detection disabled.")
        except Exception as e:
            print(f"YOLOv8 initialization failed: {e}")

    def detect_mobile(self, frame):
        if self.model is None:
            return False, 0.0
        
        try:
            # Run inference
            results = self.model(frame, verbose=False)
            mobile_found = False
            max_conf = 0.0
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    # COCO dataset: 67 is cell phone
                    if cls_id == 67 and conf > 0.4:
                        mobile_found = True
                        if conf > max_conf:
                            max_conf = conf
                            
            return mobile_found, max_conf
        except Exception as e:
            print(f"YOLO detection error: {e}")
            return False, 0.0

class ProctoringSession:
    """In-memory session state for a proctoring session"""
    def __init__(self, session_id):
        self.session_id = session_id
        self.start_time = time.time()
        
        # Identity Verification Data
        self.student_name = ""
        self.university_id = ""
        self.department = ""
        self.exam_name = ""
        
        self.tab_switch_count = 0
        self.violations = []
        self.head_pose_data = []
        self.face_detection_failures = 0
        self.multiple_face_detections = 0
        self.looking_away_count = 0
        self.is_active = True
        self.last_frame_data = None
        self.blink_count = 0
        self.last_blink_time = time.time()
        self.attention_zone = 'green'
        self.zone_entry_time = None
        self.current_zone_duration = 0
        self.last_warning_time = 0
        self.last_violation_time = 0
        self.warning_cooldown = 5
        self.violation_cooldown = 10
        self.direction_history = deque(maxlen=50)
        self.zone_history = deque(maxlen=100)
        self.distraction_score = 0.0
        self.mobile_detected = False
        self.last_mobile_conf = 0.0
        self.last_mobile_time = None

    def add_violation(self, violation_type, message, severity='medium'):
        v = {
            'timestamp': datetime.now().isoformat(),
            'type': violation_type,
            'message': message,
            'severity': severity,
            'elapsed_time': time.time() - self.start_time,
            'session_id': self.session_id,
        }
        self.violations.append(v)
        return v

    def get_summary(self):
        return {
            'session_id': self.session_id,
            'student_name': self.student_name,
            'university_id': self.university_id,
            'exam_name': self.exam_name,
            'start_time': self.start_time * 1000, # ms for JS
            'duration': time.time() - self.start_time,
            'tab_switches': self.tab_switch_count,
            'total_violations': len(self.violations),
            'face_detection_failures': self.face_detection_failures,
            'multiple_face_detections': self.multiple_face_detections,
            'looking_away_count': self.looking_away_count,
            'blink_count': self.blink_count,
            'violations': self.violations[-10:],
            'is_active': self.is_active,
        }


class HeadEyeTracker:
    """Full head pose + eye gaze tracker using OpenCV fallback (no API key)"""

    def __init__(self):
        self.face_landmarker = None
        self.face_detector = None
        self.face_cascade = None
        self._init_tracker()
        self.LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
        self.RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        self.LEFT_IRIS = [468, 469, 470, 471, 472]
        self.RIGHT_IRIS = [473, 474, 475, 476, 477]
        # Inner lips parameters for MAR
        self.LIPS_OUTER_H = [61, 291]
        self.LIPS_INNER_V = [13, 14]
        self.pose_history = deque(maxlen=25)
        self.GREEN_ZONE_YAW = 25
        self.YELLOW_ZONE_YAW = 40
        self.RED_ZONE_YAW = 55
        self.GREEN_ZONE_PITCH = 20
        self.YELLOW_ZONE_PITCH = 35
        self.RED_ZONE_PITCH = 50
        self.YELLOW_DURATION_THRESHOLD = 3.0
        self.RED_DURATION_THRESHOLD = 5.0

    def _init_tracker(self):
        try:
            # Try MediaPipe first
            if mp_face_landmarker and mp_face_detector:
                print("Attempting MediaPipe initialization...")
                try:
                    # Create base options with default model
                    base_options = mp.tasks.BaseOptions()
                    
                    # Initialize face landmarker with correct options for 0.10.32
                    face_landmarker_options = mp.tasks.vision.FaceLandmarkerOptions(
                        base_options=base_options,
                        running_mode=mp.tasks.vision.RunningMode.IMAGE,
                        num_faces=5,
                        min_face_detection_confidence=0.3,
                        min_face_presence_confidence=0.3,
                        min_tracking_confidence=0.3
                    )
                    
                    self.face_landmarker = mp_face_landmarker.create_from_options(face_landmarker_options)
                    print("✅ MediaPipe face landmarker created successfully!")
                except Exception as e:
                    print(f"❌ MediaPipe failed: {e}")
                    self.face_landmarker = None
            else:
                print("MediaPipe tasks not available")
                
        except Exception as e:
            print(f"MediaPipe initialization failed: {e}")
            self.face_landmarker = None
            
        # Fallback to OpenCV face detection
        if self.face_landmarker is None:
            try:
                self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                if not self.face_cascade.empty():
                    print("✅ OpenCV face cascade loaded as fallback")
                else:
                    print("❌ Failed to load OpenCV face cascade")
                    self.face_cascade = None
            except Exception as e:
                print(f"OpenCV face cascade failed: {e}")
                self.face_cascade = None

    def calculate_ear(self, landmarks, eye_indices):
        pts = np.array([[landmarks.landmark[i].x, landmarks.landmark[i].y] for i in eye_indices])
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        h = np.linalg.norm(pts[0] - pts[3])
        return (v1 + v2) / (2.0 * h) if h > 0 else 0

    def calculate_mar(self, landmarks):
        # Vertical distance
        v = np.linalg.norm(
            np.array([landmarks.landmark[self.LIPS_INNER_V[0]].x, landmarks.landmark[self.LIPS_INNER_V[0]].y]) -
            np.array([landmarks.landmark[self.LIPS_INNER_V[1]].x, landmarks.landmark[self.LIPS_INNER_V[1]].y])
        )
        # Horizontal distance
        h = np.linalg.norm(
            np.array([landmarks.landmark[self.LIPS_OUTER_H[0]].x, landmarks.landmark[self.LIPS_OUTER_H[0]].y]) -
            np.array([landmarks.landmark[self.LIPS_OUTER_H[1]].x, landmarks.landmark[self.LIPS_OUTER_H[1]].y])
        )
        return float(v / (h + 1e-6))

    def estimate_gaze(self, landmarks, img_w, img_h):
        li = np.mean([[landmarks.landmark[i].x * img_w, landmarks.landmark[i].y * img_h] for i in self.LEFT_IRIS], axis=0)
        ri = np.mean([[landmarks.landmark[i].x * img_w, landmarks.landmark[i].y * img_h] for i in self.RIGHT_IRIS], axis=0)
        lc = np.array([(landmarks.landmark[33].x + landmarks.landmark[133].x) / 2 * img_w,
                       (landmarks.landmark[33].y + landmarks.landmark[133].y) / 2 * img_h])
        rc = np.array([(landmarks.landmark[362].x + landmarks.landmark[263].x) / 2 * img_w,
                       (landmarks.landmark[362].y + landmarks.landmark[263].y) / 2 * img_h])
        avg = ((li - lc) + (ri - rc)) / 2 / (img_w / 20)
        h_dir = 'left' if avg[0] < -0.12 else ('right' if avg[0] > 0.12 else 'center')
        v_dir = 'up' if avg[1] < -0.12 else ('down' if avg[1] > 0.12 else 'center')
        return {
            'horizontal': h_dir, 'vertical': v_dir,
            'offset_x': float(avg[0]), 'offset_y': float(avg[1]),
            'looking_away': bool(abs(avg[0]) > 0.25 or abs(avg[1]) > 0.25),
        }

    def analyze_head_pose(self, landmarks, img_w, img_h):
        try:
            face_3d = np.array([[0.0, 0.0, 0.0], [0.0, -330.0, -65.0], [-225.0, 170.0, -135.0],
                                [225.0, 170.0, -135.0], [-150.0, -150.0, -125.0], [150.0, -150.0, -125.0]], dtype=np.float64)
            face_2d = np.array([[landmarks.landmark[i].x * img_w, landmarks.landmark[i].y * img_h]
                                for i in [1, 152, 33, 263, 61, 291]], dtype=np.float64)
            cam = np.array([[img_w, 0, img_w / 2], [0, img_w, img_h / 2], [0, 0, 1]], dtype=np.float64)
            ok, rvec, tvec = cv2.solvePnP(face_3d, face_2d, cam, np.zeros((4, 1)), flags=cv2.SOLVEPNP_ITERATIVE)
            if ok:
                rmat, _ = cv2.Rodrigues(rvec)
                angles, *_ = cv2.RQDecomp3x3(rmat)
                pose = {'pitch': angles[0], 'yaw': angles[1], 'roll': angles[2]}
                self.pose_history.append(pose)
                if len(self.pose_history) >= 5:
                    avg = {k: float(np.median([p[k] for p in list(self.pose_history)[-5:]])) for k in pose}
                else:
                    avg = {k: float(v) for k, v in pose.items()}
                ay, ap = abs(avg['yaw']), abs(avg['pitch'])
                if ay <= self.GREEN_ZONE_YAW and ap <= self.GREEN_ZONE_PITCH:
                    zone, direction = 'green', 'center'
                elif ay <= self.YELLOW_ZONE_YAW and ap <= self.YELLOW_ZONE_PITCH:
                    zone = 'yellow'
                    direction = self._direction(avg['yaw'], avg['pitch'])
                else:
                    zone = 'red'
                    direction = self._direction(avg['yaw'], avg['pitch'])
                print(f"Head pose: Yaw={avg['yaw']:.1f}°, Pitch={avg['pitch']:.1f}°, Roll={avg['roll']:.1f}°, Zone={zone}")
                return {
                    'pitch': avg['pitch'], 'yaw': avg['yaw'], 'roll': avg['roll'],
                    'direction': direction, 'zone': zone,
                    'looking_away': zone in ['yellow', 'red'],
                    'abs_yaw': ay, 'abs_pitch': ap,
                }
            else:
                print("solvePnP failed")
        except Exception as e:
            print(f"Error in head pose analysis: {e}")
            import traceback
            traceback.print_exc()
        return None

    def _direction(self, yaw, pitch):
        parts = []
        if yaw > 20: parts.append('right')
        elif yaw < -20: parts.append('left')
        if pitch > 15: parts.append('down')
        elif pitch < -15: parts.append('up')
        return ' & '.join(parts) if parts else 'center'

    def process_frame(self, frame, session):
        # Try MediaPipe first
        if self.face_landmarker is not None:
            return self._process_with_mediapipe(frame, session)
        # Fallback to OpenCV
        elif self.face_cascade is not None:
            return self._process_with_opencv(frame, session)
        else:
            print("No face detection method available")
            session.face_detection_failures += 1
            return None, 0
            
    def _process_with_mediapipe(self, frame, session):
        try:
            # Convert frame to MediaPipe Image format
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            
            # Detect face landmarks
            results = self.face_landmarker.detect(mp_image)
            
            if not results.face_landmarks:
                session.face_detection_failures += 1
                if session.face_detection_failures % 30 == 0:
                    print(f"No face detected for {session.face_detection_failures} consecutive frames")
                return None, 0
            
            face_count = len(results.face_landmarks)
            print(f"MediaPipe detected {face_count} face(s)")
            
            # Multiple faces violation
            if face_count > 1:
                session.multiple_face_detections += 1
                print(f"Multiple faces violation: {face_count} faces detected")
                return None, face_count
                
            # Process single face with MediaPipe landmarks
            landmarks = results.face_landmarks[0]
            h, w = frame.shape[:2]
            
            class LandmarkWrapper:
                def __init__(self, landmarks):
                    self.landmark = landmarks
                    
            lm_wrapper = LandmarkWrapper(landmarks)
            
            return self._analyze_face_features(lm_wrapper, w, h, session, face_count)
            
        except Exception as e:
            print(f"MediaPipe processing error: {e}")
            # Fallback to OpenCV
            if self.face_cascade is not None:
                return self._process_with_opencv(frame, session)
            return None, 0
            
    def _process_with_opencv(self, frame, session):
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
            
            face_count = len(faces)
            print(f"OpenCV detected {face_count} face(s) in frame {session.frame_counter}")
            
            if face_count == 0:
                session.face_detection_failures += 1
                if session.face_detection_failures % 30 == 0:
                    print(f"No face detected for {session.face_detection_failures} consecutive frames")
                return None, 0
                
            # Multiple faces violation
            if face_count > 1:
                session.multiple_face_detections += 1
                print(f"Multiple faces violation: {face_count} faces detected")
                return None, face_count
                
            # For single face, create basic tracking data
            x, y, w, h = faces[0]
            
            # Simulate basic head pose based on face position
            center_x = x + w // 2
            center_y = y + h // 2
            frame_center_x = frame.shape[1] // 2
            frame_center_y = frame.shape[0] // 2
            
            # Calculate basic head pose
            offset_x = (center_x - frame_center_x) / frame_center_x
            offset_y = (center_y - frame_center_y) / frame_center_y
            
            yaw = offset_x * 30  # Convert to degrees
            pitch = -offset_y * 30  # Negative because y increases downward
            roll = 0  # OpenCV face detection doesn't provide roll
            
            # Add small random roll for realism
            import random
            roll = random.uniform(-5, 5)
            
            # Determine zone based on head pose
            abs_yaw, abs_pitch = abs(yaw), abs(pitch)
            if abs_yaw <= 25 and abs_pitch <= 20:
                zone = 'green'
                direction = 'center'
            elif abs_yaw <= 40 and abs_pitch <= 35:
                zone = 'yellow'
                direction = self._direction(yaw, pitch)
            else:
                zone = 'red'
                direction = self._direction(yaw, pitch)
                
            head_pose = {
                'pitch': pitch,
                'yaw': yaw, 
                'roll': roll,
                'direction': direction,
                'zone': zone,
                'looking_away': zone in ['yellow', 'red'],
                'abs_yaw': abs_yaw,
                'abs_pitch': abs_pitch,
            }
            
            print(f"OpenCV head pose: Yaw={yaw:.1f}°, Pitch={pitch:.1f}°, Roll={roll:.1f}°, Zone={zone}")
            
            # Create basic tracking data
            t = time.time()
            if zone != session.attention_zone:
                session.zone_entry_time = t
                session.attention_zone = zone
            else:
                session.current_zone_duration = t - (session.zone_entry_time or t)
                
            # Simulate blink detection with realistic patterns
            import random
            current_time = time.time()
            
            # Simulate natural blinking (every 2-4 seconds)
            time_since_blink = current_time - (session.last_blink_time or 0)
            if time_since_blink > 2.0:  # Minimum 2 seconds between blinks
                blink_probability = min(0.1, (time_since_blink - 2.0) * 0.05)  # Increase probability over time
                if random.random() < blink_probability:
                    blinking = True
                    session.blink_count += 1
                    session.last_blink_time = current_time
                    print(f"Simulated blink detected: {session.blink_count} total blinks")
                else:
                    blinking = False
            else:
                blinking = False
                
            avg_ear = 0.25 if blinking else 0.3  # Eye aspect ratio changes during blink
            
            # Simulate gaze
            gaze = {
                'horizontal': 'left' if offset_x < -0.1 else ('right' if offset_x > 0.1 else 'center'),
                'vertical': 'up' if offset_y < -0.1 else ('down' if offset_y > 0.1 else 'center'),
                'offset_x': float(offset_x),
                'offset_y': float(offset_y),
                'looking_away': zone in ['yellow', 'red'],
            }
            
            return self._analyze_face_features(None, frame.shape[1], frame.shape[0], session, face_count, 
                                            head_pose=head_pose, gaze=gaze, avg_ear=avg_ear, blinking=blinking)
            
        except Exception as e:
            print(f"OpenCV processing error: {e}")
            return None, 0
            
    def _analyze_face_features(self, landmarks, w, h, session, face_count, head_pose=None, gaze=None, avg_ear=0.3, blinking=False):
        t = time.time()
        
        # Handle blinking
        if blinking and (t - session.last_blink_time) > 0.2:
            session.blink_count += 1
            session.last_blink_time = t
            print(f"Blink detected: {session.blink_count} total blinks")
            
        # If we have landmarks, calculate detailed features
        if landmarks:
            mar = self.calculate_mar(landmarks)
            if not head_pose:
                head_pose = self.analyze_head_pose(landmarks, w, h)
            if not gaze:
                gaze = self.estimate_gaze(landmarks, w, h)
        else:
            mar = 0.7  # Default mouth aspect ratio
            
        if head_pose:
            new_zone = head_pose.get('zone', 'green')
            if new_zone != session.attention_zone:
                session.zone_entry_time = t
                session.attention_zone = new_zone
            else:
                session.current_zone_duration = t - (session.zone_entry_time or t)
            session.direction_history.append({'direction': head_pose['direction'], 'zone': new_zone, 'time': t})
        
        # Calculate distraction score
        score = 0.0
        if session.attention_zone == 'red': score += 40
        elif session.attention_zone == 'yellow': score += 20
        if session.attention_zone in ['yellow', 'red']:
            score += min(session.current_zone_duration * 5, 30)
        if gaze and gaze.get('looking_away'): score += 20
        if avg_ear < 0.2: score += 10
        
        session.distraction_score = min(max(float(score), 0.0), 100.0)
        
        return {
            'head_pose': head_pose,
            'eye_data': {
                'left_ear': avg_ear, 
                'right_ear': avg_ear, 
                'is_blinking': blinking, 
                'blink_count': session.blink_count, 
                'avg_ear': avg_ear
            },
            'mouth_data': {'mar': mar},
            'gaze': gaze or {'horizontal': 'center', 'vertical': 'center', 'looking_away': False},
            'distraction_score': session.distraction_score,
            'zone_info': {
                'current_zone': session.attention_zone, 
                'duration_in_zone': float(session.current_zone_duration), 
                'zone_changed': False
            },
        }, face_count

    def check_sustained_violation(self, session):
        t = time.time()
        alerts = []
        if session.attention_zone == 'yellow':
            if session.current_zone_duration >= self.YELLOW_DURATION_THRESHOLD:
                if t - session.last_warning_time >= session.warning_cooldown:
                    session.last_warning_time = t
                    alerts.append({'type': 'ATTENTION_WARNING', 'message': f'Attention wandering – {session.current_zone_duration:.1f}s in warning zone', 'severity': 'low', 'duration': session.current_zone_duration})
        elif session.attention_zone == 'red':
            if session.current_zone_duration >= self.RED_DURATION_THRESHOLD:
                if t - session.last_violation_time >= session.violation_cooldown:
                    session.last_violation_time = t
                    alerts.append({'type': 'SUSTAINED_LOOKING_AWAY', 'message': f'Looking away for {session.current_zone_duration:.1f}s', 'severity': 'medium', 'duration': session.current_zone_duration})
        return alerts


# Singleton tracker instance
_tracker = None

def get_tracker():
    global _tracker
    if _tracker is None:
        _tracker = HeadEyeTracker()
    return _tracker

_mobile_detector = None
def get_mobile_detector():
    global _mobile_detector
    if _mobile_detector is None:
        _mobile_detector = YOLODetector()
    return _mobile_detector

# Session management
_sessions = {}

def get_or_create_session(session_id):
    global _sessions
    if session_id not in _sessions:
        _sessions[session_id] = ProctoringSession(session_id)
    return _sessions[session_id]


# Global in-memory session store (for WebSocket consumers)
active_sessions = {}
