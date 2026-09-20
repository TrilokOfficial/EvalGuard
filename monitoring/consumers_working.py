import json
import base64
import time
import numpy as np
import cv2
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .proctoring_engine import get_tracker, get_or_create_session, get_mobile_detector

class ProctorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        await self.accept()
        print(f"WebSocket connected for session {self.session_id}")

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected for session {self.session_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'video_frame':
                await self.handle_video_frame(data)
            elif message_type == 'tab_switch':
                await self.handle_tab_switch(data)
            elif message_type == 'register_proctor':
                await self.channel_layer.group_add('proctor_dashboard', self.channel_name)
                await self.send(text_data=json.dumps({'type': 'registered'}))
        except Exception as e:
            print(f"Error in receive: {e}")
            import traceback
            traceback.print_exc()

    async def handle_tab_switch(self, data):
        sess = get_or_create_session(self.session_id)
        if sess:
            sess.tab_switch_count += 1
            v = sess.add_violation('TAB_SWITCH', f'Tab switch #{sess.tab_switch_count}',
                                   'medium' if sess.tab_switch_count <= 3 else 'high')
            await self.channel_layer.group_send('proctor_dashboard', {
                'type': 'dashboard.update',
                'data': {'type': 'violation_alert', **v},
            })
            await self.send(text_data=json.dumps({'type': 'violation_alert', **v}))

    async def handle_video_frame(self, data):
        try:
            frame_data = data.get('frame')
            if not frame_data:
                print("No frame data received")
                return
            
            # Decode frame
            frame = base64.b64decode(frame_data)
            frame_array = np.frombuffer(frame, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            
            if frame is None:
                print("Failed to decode frame")
                return
                
            print(f"Frame decoded successfully: {frame.shape}")
            
            sess = get_or_create_session(self.session_id)
            if not sess:
                print(f"Failed to get/create session {self.session_id}")
                return

            # Process frame synchronously
            tracker = get_tracker()
            tracking_data = None
            violations_detected = []
            face_count = 0
            emotion_data = None

            # Create thumbnail for dashboard
            small = cv2.resize(frame, (320, 240))
            _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 50])
            sess.last_frame_data = base64.b64encode(buf).decode('utf-8')

            # Face detection and tracking
            try:
                tracking_data, face_count = tracker.process_frame(frame, sess)
                
                # Handle multiple faces violation
                if face_count > 1:
                    sess.multiple_face_detections += 1
                    v = sess.add_violation('MULTIPLE_FACES', f'{face_count} faces detected - violation', 'high')
                    violations_detected.append(v)
                    print(f"Multiple faces violation logged: {face_count} faces")
                elif face_count == 1:
                    if tracking_data:
                        alerts = tracker.check_sustained_violation(sess)
                        for alert in alerts:
                            v = sess.add_violation(alert['type'], alert['message'], alert['severity'])
                            violations_detected.append(v)
                            if alert['type'] == 'SUSTAINED_LOOKING_AWAY':
                                sess.looking_away_count += 1
                else:
                    sess.face_detection_failures += 1
                    if sess.face_detection_failures % 30 == 0:
                        v = sess.add_violation('NO_FACE', 'No face detected', 'high')
                        violations_detected.append(v)
                        print(f"No face violation logged: {sess.face_detection_failures} failures")
            except Exception as e:
                print(f"Error in frame processing: {e}")
                import traceback
                traceback.print_exc()

            # Emotion simulation
            if tracking_data and tracking_data.get('head_pose'):
                head_pose = tracking_data['head_pose']
                zone = head_pose.get('zone', 'green')
                emotion_data = self._simulate_emotion(zone)
                tracking_data['emotion'] = emotion_data

            # Mobile detection
            try:
                mobile_detector = get_mobile_detector()
                mobile_detected, mobile_conf = mobile_detector.detect_mobile(frame)
                if mobile_detected:
                    sess.mobile_detected = True
                    sess.last_mobile_conf = mobile_conf
                    sess.last_mobile_time = time.time()
                    v = sess.add_violation('MOBILE_DETECTED', f'Mobile phone detected ({mobile_conf:.0%} confidence)', 'high')
                    violations_detected.append(v)
                    print(f"Mobile detected: {mobile_conf:.0%} confidence")
                else:
                    if sess.mobile_detected and sess.last_mobile_time and time.time() - sess.last_mobile_time > 3.0:
                        sess.mobile_detected = False
            except Exception as e:
                print(f"Mobile detection error: {e}")

            # Update frame counter
            sess.frame_counter = getattr(sess, 'frame_counter', 0) + 1

            # Send frame update message
            frame_update = {
                'type': 'frame_update',
                'session_id': self.session_id,
                'face_count': face_count,
                'tab_switches': sess.tab_switch_count,
                'total_violations': len(sess.violations),
                'blink_count': sess.blink_count,
                'tracking_data': tracking_data,
                'frame_data': sess.last_frame_data,
                'mobile_detected': sess.mobile_detected,
                'mobile_conf': sess.last_mobile_conf,
                'distraction_score': sess.distraction_score,
                'emotion': emotion_data,
                'attention_zone': sess.attention_zone,
            }
            print(f"Sending frame update: total_violations={len(sess.violations)}, face_count={face_count}")
            await self.channel_layer.group_send('proctor_dashboard', frame_update)
            
            # Send individual violation alerts
            for v in violations_detected:
                print(f"Sending violation alert: {v}")
                violation_alert = {
                    'type': 'violation_alert',
                    'session_id': self.session_id,
                    'violation': {
                        'type': v['type'],
                        'message': v['message'],
                        'severity': v['severity'],
                        'timestamp': v['timestamp']
                    }
                }
                await self.channel_layer.group_send('proctor_dashboard', violation_alert)

            # Send analysis back to student
            await self.send(text_data=json.dumps({
                'type': 'frame_analysis',
                'face_detected': face_count > 0,
                'face_count': face_count,
                'tracking_data': tracking_data,
                'violations': violations_detected,
                'distraction_score': sess.distraction_score,
                'mobile_detected': sess.mobile_detected,
                'mobile_conf': sess.last_mobile_conf,
                'emotion': emotion_data,
            }))
            
        except Exception as e:
            print(f"Error in handle_video_frame: {e}")
            import traceback
            traceback.print_exc()

    def _simulate_emotion(self, zone='green'):
        import random
        baseline = {'Neutral': 60, 'Happy': 15, 'Sad': 8, 'Angry': 5, 'Surprise': 7, 'Disgust': 5}
        if zone == 'red':
            baseline['Angry'] += 15
            baseline['Neutral'] -= 10
        elif zone == 'yellow':
            baseline['Sad'] += 10
            baseline['Neutral'] -= 5
        emotions = {k: max(0, v + random.randint(-3, 3)) for k, v in baseline.items()}
        total = sum(emotions.values())
        return {k: round(v / total * 100, 1) for k, v in emotions.items()}

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def force_terminate(self, event):
        await self.send(text_data=json.dumps({
            'type': 'force_terminate',
            'reason': event.get('reason', 'Session terminated by proctor')
        }))

    async def _log_violation(self, violation, head_pose=None):
        pass

    async def _log_head_pose(self, tracking_data):
        pass

    async def _log_emotion(self, emotion_data):
        pass

    async def _log_mobile_detection(self, confidence, frame_data):
        pass

    async def _log_distraction(self, distraction_type, severity, message):
        pass


class RecruiterDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.channel_layer.group_add('recruiter_dashboard', self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('recruiter_dashboard', self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        pass
