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
                print(f"Proctor registered for session {self.session_id}")
                # Send initial analytics update
                await self.send_analytics_heartbeat()
            elif message_type == 'heartbeat':
                await self.send_analytics_heartbeat()
            elif message_type == 'student_joined':
                sess = get_or_create_session(self.session_id)
                if sess:
                    sess.student_name = data.get('student_name', '')
                    sess.university_id = data.get('university_id', '')
                    sess.department = data.get('department', '')
                    sess.exam_name = data.get('exam_name', '')
                    print(f"Student joined session {self.session_id}: {sess.student_name} ({sess.university_id})")
                    await self.channel_layer.group_send('proctor_dashboard', {
                        'type': 'dashboard.update',
                        'data': {
                            'type': 'student_joined',
                            'session_id': self.session_id,
                            'student_name': sess.student_name,
                            'university_id': sess.university_id,
                            'department': sess.department,
                            'exam_name': sess.exam_name,
                        }
                    })
        except Exception as e:
            print(f"Error in receive: {e}")
            import traceback
            traceback.print_exc()

    async def send_analytics_heartbeat(self):
        """Send periodic analytics update even without frames"""
        sess = get_or_create_session(self.session_id)
        if sess:
            heartbeat = {
                'type': 'frame_update',
                'session_id': self.session_id,
                'face_count': 0,  # Unknown without frame
                'tab_switches': sess.tab_switch_count,
                'total_violations': len(sess.violations),
                'blink_count': sess.blink_count,
                'tracking_data': None,
                'frame_data': None,
                'mobile_detected': sess.mobile_detected,
                'mobile_conf': sess.last_mobile_conf,
                'distraction_score': sess.distraction_score,
                'emotion': None,
                'attention_zone': sess.attention_zone,
                'frame_processed': False,
                'heartbeat': True
            }
            print(f"Sending analytics heartbeat for session {self.session_id}")
            await self.channel_layer.group_send('proctor_dashboard', heartbeat)

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
            
            # Decode frame with better error handling
            try:
                # Check if frame_data looks like valid base64
                if not frame_data or len(frame_data) < 100:
                    print(f"Invalid frame data: too short or empty, length: {len(frame_data) if frame_data else 0}")
                    return
                
                # Handle data URLs (data:image/jpeg;base64,xxxxx)
                if frame_data.startswith('data:image'):
                    # Extract the base64 part after the comma
                    if ',' in frame_data:
                        frame_data = frame_data.split(',', 1)[1]
                    else:
                        print(f"Invalid data URL format: {frame_data[:100]}")
                        return
                
                # Try to decode base64
                try:
                    frame_bytes = base64.b64decode(frame_data)
                except Exception as b64_error:
                    print(f"Base64 decode error: {b64_error}, data length: {len(frame_data)}")
                    return
                
                frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                
                if frame is None:
                    print(f"Failed to decode frame. Frame data length: {len(frame_data)}, bytes length: {len(frame_bytes)}")
                    # Try to see if it's a different format
                    print(f"First 50 bytes: {frame_bytes[:50]}")
                    return
                    
                print(f"Frame decoded successfully: {frame.shape}, Data length: {len(frame_data)}")
                
            except Exception as decode_error:
                print(f"Frame decoding error: {decode_error}")
                import traceback
                traceback.print_exc()
                return
            
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
            try:
                small = cv2.resize(frame, (320, 240))
                _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 50])
                sess.last_frame_data = base64.b64encode(buf).decode('utf-8')
            except Exception as resize_error:
                print(f"Frame resize error: {resize_error}")
                return

            # Face detection and tracking
            try:
                tracking_data, face_count = tracker.process_frame(frame, sess)
                print(f"Face detection result: face_count={face_count}, tracking_data={'present' if tracking_data else 'none'}")
                
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

            # Send frame update message (even if frame processing failed)
            frame_update = {
                'type': 'frame_update',
                'session_id': self.session_id,
                'face_count': face_count,
                'tab_switches': sess.tab_switch_count,
                'total_violations': len(sess.violations),
                'blink_count': sess.blink_count,
                'tracking_data': tracking_data,
                'frame_data': sess.last_frame_data if hasattr(sess, 'last_frame_data') else None,
                'mobile_detected': sess.mobile_detected,
                'mobile_conf': sess.last_mobile_conf,
                'distraction_score': sess.distraction_score,
                'emotion': emotion_data,
                'attention_zone': sess.attention_zone,
                'frame_processed': frame is not None,  # Add flag to indicate if frame was processed
            }
            print(f"Sending frame update: total_violations={len(sess.violations)}, face_count={face_count}, blinks={sess.blink_count}, frame_processed={frame is not None}")
            await self.channel_layer.group_send(
                'proctor_dashboard',
                {
                    'type': 'frame_update',
                    'session_id': self.session_id,
                    'face_count': face_count,
                    'tab_switches': sess.tab_switch_count,
                    'total_violations': len(sess.violations),
                    'blink_count': sess.blink_count,
                    'tracking_data': tracking_data,
                    'frame_data': sess.last_frame_data if hasattr(sess, 'last_frame_data') else None,
                    'mobile_detected': sess.mobile_detected,
                    'mobile_conf': sess.last_mobile_conf,
                    'distraction_score': sess.distraction_score,
                    'emotion': emotion_data,
                    'attention_zone': sess.attention_zone,
                    'frame_processed': frame is not None,  # Add flag to indicate if frame was processed
                }
            )
            
            # Send individual violation alerts
            for v in violations_detected:
                print(f"Sending violation alert: {v}")
                await self.channel_layer.group_send(
                    'proctor_dashboard',
                    {
                        'type': 'violation_alert',
                        'session_id': self.session_id,
                        'violation': {
                            'type': v['type'],
                            'message': v['message'],
                            'severity': v['severity'],
                            'timestamp': v['timestamp']
                        }
                    }
                )

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
                'blink_count': sess.blink_count,
                'head_pose': tracking_data.get('head_pose') if tracking_data else None,
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
        data = event['data']
        message_type = data.get('type')
        
        if message_type == 'frame_update':
            # Forward frame updates to dashboard
            await self.send(text_data=json.dumps(data))
        elif message_type == 'violation_alert':
            # Forward violation alerts to dashboard
            await self.send(text_data=json.dumps(data))
        else:
            # Forward other messages
            await self.send(text_data=json.dumps(data))

    async def frame_update(self, event):
        """Handle frame_update messages from group_send"""
        await self.send(text_data=json.dumps(event))

    async def force_terminate(self, event):
        await self.send(text_data=json.dumps({
            'type': 'force_terminate',
            'reason': event.get('reason', 'Session terminated by proctor')
        }))

    async def session_completed(self, event):
        """
        Broadcast completion events to any connected proctor dashboards
        so they can immediately move sessions into the Completed view.
        """
        await self.send(text_data=json.dumps({
            'type': 'session_completed',
            'session_id': event.get('session_id'),
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
