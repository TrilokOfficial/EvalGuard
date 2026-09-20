import json
import base64
import time
import numpy as np
import cv2
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .proctoring_engine import ProctoringSession, get_tracker, get_mobile_detector, active_sessions
from .models import (
    ProctoringSessionLog, ViolationEvent, DistractionEvent, MobileDetectionEvent,
    HeadPoseMetrics, EmotionProfile
)


class ProctorConsumer(AsyncWebsocketConsumer):
    """Enhanced WebSocket consumer for the proctoring room with full metrics tracking."""

    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.group_name = f'proctor_{self.session_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add('proctor_dashboard', self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({'type': 'connected', 'message': 'EvalGuard proctoring connected'}))
        await self._get_or_create_session_log()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_discard('proctor_dashboard', self.channel_name)
        await self._end_session_db()

    @database_sync_to_async
    def _get_or_create_session_log(self):
        log, created = ProctoringSessionLog.objects.get_or_create(
            session_id=self.session_id,
            defaults={'final_status': 'pending'}
        )
        return log

    @database_sync_to_async
    def _end_session_db(self):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            log.ended_at = time.time()
            log.duration_seconds = int(time.time() - active_sessions.get(self.session_id, {}).start_time)
            log.final_status = 'completed'
            log.save()
        except:
            pass

    @database_sync_to_async
    def _log_violation(self, v, head_pose_data=None):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            ViolationEvent.objects.create(
                session=log,
                violation_type=v['type'],
                severity=v['severity'],
                message=v['message'],
                elapsed_time_seconds=v['elapsed_time'],
                head_pose_data=head_pose_data or {},
                zone_at_violation=head_pose_data.get('zone', '') if head_pose_data else '',
            )
            log.total_violations += 1
            if v['type'] == 'TAB_SWITCH':
                log.tab_switch_count += 1
            elif v['type'] == 'MOBILE_DETECTED':
                log.mobile_detection_count += 1
            elif v['type'] == 'DISTRACTION_DETECTED':
                log.distraction_event_count += 1
            elif v['type'] == 'NO_FACE':
                log.face_detection_failures += 1
            elif v['type'] == 'MULTIPLE_FACES':
                log.multiple_face_detections += 1
            elif v['type'] == 'SUSTAINED_LOOKING_AWAY':
                log.looking_away_count += 1
            log.save()
        except Exception as e:
            print(f"Error logging violation: {e}")

    @database_sync_to_async
    def _log_head_pose(self, tracking_data):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            head_pose = tracking_data.get('head_pose', {})
            zone_info = tracking_data.get('zone_info', {})
            HeadPoseMetrics.objects.create(
                session=log,
                pitch=head_pose.get('pitch', 0),
                yaw=head_pose.get('yaw', 0),
                roll=head_pose.get('roll', 0),
                zone=zone_info.get('current_zone', 'green'),
                direction=head_pose.get('direction', ''),
                looking_away=head_pose.get('looking_away', False),
            )
        except Exception as e:
            print(f"Error logging head pose: {e}")

    @database_sync_to_async
    def _log_emotion(self, emotion_data):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            EmotionProfile.objects.create(
                session=log,
                happy=emotion_data.get('Happy', 0),
                sad=emotion_data.get('Sad', 0),
                angry=emotion_data.get('Angry', 0),
                surprise=emotion_data.get('Surprise', 0),
                disgust=emotion_data.get('Disgust', 0),
                neutral=emotion_data.get('Neutral', 0),
                dominant_emotion=max(emotion_data, key=emotion_data.get) if emotion_data else 'Neutral',
                confidence=emotion_data.get(max(emotion_data, key=emotion_data.get), 0) if emotion_data else 0,
            )
        except Exception as e:
            print(f"Error logging emotion: {e}")

    @database_sync_to_async
    def _log_mobile_detection(self, confidence, frame_snapshot=''):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            MobileDetectionEvent.objects.create(
                session=log,
                confidence=confidence,
                frame_snapshot=frame_snapshot[:1000] if frame_snapshot else '',
            )
        except Exception as e:
            print(f"Error logging mobile detection: {e}")

    @database_sync_to_async
    def _log_distraction(self, distraction_type, severity='low', description=''):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            DistractionEvent.objects.create(
                session=log,
                distraction_type=distraction_type,
                severity=severity,
                description=description,
            )
            log.distraction_event_count += 1
            log.save()
        except Exception as e:
            print(f"Error logging distraction: {e}")

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return
        msg_type = data.get('type', '')

        if msg_type == 'start_session':
            self._ensure_session()
            await self.send(text_data=json.dumps({'type': 'session_started', 'session_id': self.session_id}))

        elif msg_type == 'video_frame':
            await self.handle_video_frame(data)

        elif msg_type == 'tab_switch':
            await self.handle_tab_switch()

        elif msg_type == 'register_proctor':
            await self.channel_layer.group_add('proctor_dashboard', self.channel_name)
            await self.send(text_data=json.dumps({'type': 'registered', 'role': 'proctor'}))

        elif msg_type == 'end_session':
            self._end_session()
            await self.send(text_data=json.dumps({'type': 'session_ended', 'session_id': self.session_id}))

        elif msg_type == 'trigger_prompt':
            target_session = data.get('session_id')
            message = data.get('message', 'Warning from Proctor')
            if target_session:
                await self.channel_layer.group_send(f'proctor_{target_session}', {
                    'type': 'trigger_prompt_event',
                    'message': message
                })

        elif msg_type == 'meet_link_update':
            meet_link = data.get('meet_link', '')
            await self._update_meet_link(meet_link)
            await self.channel_layer.group_send('proctor_dashboard', {
                'type': 'dashboard.update',
                'data': {
                    'type': 'meet_update',
                    'session_id': self.session_id,
                    'meet_link': meet_link,
                },
            })

    @database_sync_to_async
    def _update_meet_link(self, meet_link):
        try:
            log = ProctoringSessionLog.objects.get(session_id=self.session_id)
            log.meet_link = meet_link
            log.meet_started_at = time.time()
            log.save()
        except:
            pass

    def _ensure_session(self):
        if self.session_id not in active_sessions:
            active_sessions[self.session_id] = ProctoringSession(self.session_id)

    def _end_session(self):
        if self.session_id in active_sessions:
            sess = active_sessions[self.session_id]
            sess.is_active = False

    async def handle_tab_switch(self):
        self._ensure_session()
        sess = active_sessions[self.session_id]
        sess.tab_switch_count += 1
        v = sess.add_violation('TAB_SWITCH', f'Tab switch #{sess.tab_switch_count}',
                               'medium' if sess.tab_switch_count <= 3 else 'high')
        await self._log_violation(v)
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
                return None

            tracker = get_tracker()
            tracking_data = None
            violations_detected = []
            face_count = 0
            emotion_data = None

            small = cv2.resize(frame, (320, 240))
            _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 50])
            sess.last_frame_data = base64.b64encode(buf).decode('utf-8')

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
                import traceback
                print(f"Error in frame processing: {e}")
                traceback.print_exc()

            if tracking_data and tracking_data.get('head_pose'):
                head_pose = tracking_data['head_pose']
                zone = head_pose.get('zone', 'green')
                emotion_data = self._simulate_emotion(zone)
                tracking_data['emotion'] = emotion_data

            # Mobile detection
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

            return face_count, tracking_data, violations_detected, emotion_data

        import asyncio
        result = await asyncio.to_thread(_process_frame_sync)
        if not result:
            return

        face_count, tracking_data, violations_detected, emotion_data = result

        for v in violations_detected:
            await self._log_violation(v, tracking_data.get('head_pose') if tracking_data else None)

        if tracking_data and sess.frame_counter % 30 == 0:
            await self._log_head_pose(tracking_data)

        if emotion_data and sess.frame_counter % 60 == 0:
            await self._log_emotion(emotion_data)

        sess.frame_counter = getattr(sess, 'frame_counter', 0) + 1

        if tracking_data:
            zone_info = tracking_data.get('zone_info', {})
            current_zone = zone_info.get('current_zone', 'green')
            duration = zone_info.get('duration_in_zone', 0)
            if current_zone == 'red' and duration > 3.0 and sess.frame_counter % 90 == 0:
                await self._log_distraction(
                    'HEAD_MOVEMENT',
                    'medium',
                    f'Sustained looking away for {duration:.1f}s'
                )

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
        print(f"Sending frame update: total_violations={len(sess.violations)}, violations_detected={len(violations_detected)}")
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
            'reason': event.get('reason', 'Terminated by Proctor')
        }))

    async def trigger_prompt_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'proctor_prompt',
            'message': event['message']
        }))


class RecruiterDashboardConsumer(AsyncWebsocketConsumer):
    """Dedicated WebSocket consumer for the enhanced recruiter dashboard."""

    async def connect(self):
        self.group_name = 'proctor_dashboard'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Recruiter dashboard connected',
            'role': 'recruiter'
        }))

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return
        msg_type = data.get('type', '')

        if msg_type == 'register_recruiter':
            await self.send(text_data=json.dumps({
                'type': 'registered',
                'role': 'recruiter',
                'active_sessions': len(active_sessions)
            }))

        elif msg_type == 'request_metrics':
            session_id = data.get('session_id')
            if session_id and session_id in active_sessions:
                sess = active_sessions[session_id]
                await self.send(text_data=json.dumps({
                    'type': 'metrics_update',
                    'session_id': session_id,
                    'metrics': sess.get_summary(),
                }))

        elif msg_type == 'terminate_session':
            session_id = data.get('session_id')
            reason = data.get('reason', 'Terminated by Recruiter')
            if session_id:
                await self.channel_layer.group_send(
                    f'proctor_{session_id}',
                    {'type': 'force_terminate', 'reason': reason}
                )
                await self.send(text_data=json.dumps({
                    'type': 'session_terminated',
                    'session_id': session_id,
                }))

    async def dashboard_update(self, event):
        """Forward all dashboard updates to the recruiter"""
        await self.send(text_data=json.dumps(event['data']))
