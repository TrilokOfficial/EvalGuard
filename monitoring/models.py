from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Proctor(models.Model):
    """Represents a human proctor assigned to monitor exam sessions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='proctor_profile')
    is_active = models.BooleanField(default=True)
    max_sessions = models.IntegerField(default=10)
    specialization = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Proctor: {self.user.username}"


class ProctorAssignment(models.Model):
    """Links proctors to specific exam sessions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proctor = models.ForeignKey(Proctor, on_delete=models.CASCADE, related_name='assignments')
    session_id = models.CharField(max_length=100, db_index=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['proctor', 'session_id']
        ordering = ['-assigned_at']


class ParrokitAgent(models.Model):
    """AI agent configuration for automated proctoring assistance"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    agent_type = models.CharField(max_length=50, choices=[
        ('face_detection', 'Face Detection'),
        ('mobile_detection', 'Mobile Device Detection'),
        ('distraction_detection', 'Distraction Detection'),
        ('emotion_analysis', 'Emotion Analysis'),
        ('voice_analysis', 'Voice Analysis'),
        ('multi_agent', 'Multi-Agent Orchestrator'),
    ])
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.agent_type})"


class ProctoringSessionLog(models.Model):
    """Persistent storage for proctoring session data"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=100, db_index=True)
    candidate_name = models.CharField(max_length=200, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    
    # Violation counts
    total_violations = models.IntegerField(default=0)
    tab_switch_count = models.IntegerField(default=0)
    mobile_detection_count = models.IntegerField(default=0)
    distraction_event_count = models.IntegerField(default=0)
    face_detection_failures = models.IntegerField(default=0)
    multiple_face_detections = models.IntegerField(default=0)
    looking_away_count = models.IntegerField(default=0)
    
    # Risk assessment
    risk_score = models.FloatField(default=0.0)
    final_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
        ('flagged', 'Flagged'),
    ])
    
    # Google Meet integration
    meet_link = models.URLField(blank=True)
    meet_started_at = models.DateTimeField(null=True, blank=True)
    
    # Assigned proctors and agents
    proctors = models.ManyToManyField(Proctor, blank=True)
    agents = models.ManyToManyField(ParrokitAgent, blank=True)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Session {self.session_id[:8]}... ({self.candidate_name or 'Unknown'})"


class ViolationEvent(models.Model):
    """Detailed violation log with rich metadata"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSessionLog, on_delete=models.CASCADE, related_name='violations')
    violation_type = models.CharField(max_length=50, choices=[
        ('TAB_SWITCH', 'Tab Switch'),
        ('MOBILE_DETECTED', 'Mobile Phone Detected'),
        ('MULTIPLE_FACES', 'Multiple Faces Detected'),
        ('NO_FACE', 'No Face Detected'),
        ('SUSTAINED_LOOKING_AWAY', 'Looking Away'),
        ('ATTENTION_WARNING', 'Attention Warning'),
        ('DISTRACTION_DETECTED', 'Distraction Detected'),
        ('VOICE_DETECTED', 'Voice/Unusual Sound'),
        ('SUSPICIOUS_OBJECT', 'Suspicious Object'),
    ])
    severity = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    elapsed_time_seconds = models.FloatField(default=0)
    
    # Screenshot/evidence
    frame_data = models.TextField(blank=True, help_text="Base64 encoded frame snapshot")
    
    # Context data
    head_pose_data = models.JSONField(default=dict, blank=True)
    zone_at_violation = models.CharField(max_length=20, blank=True)
    confidence_score = models.FloatField(default=0.0)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.violation_type} at {self.timestamp.strftime('%H:%M:%S')}"


class DistractionEvent(models.Model):
    """Tracks specific distraction incidents"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSessionLog, on_delete=models.CASCADE, related_name='distractions')
    distraction_type = models.CharField(max_length=50, choices=[
        ('HEAD_MOVEMENT', 'Excessive Head Movement'),
        ('EYE_GAZE', 'Eye Gaze Away'),
        ('POSTURE_CHANGE', 'Posture Change'),
        ('OBJECT_INTERACTION', 'Object Interaction'),
        ('ENVIRONMENT_NOISE', 'Environment Noise'),
    ])
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0)
    severity = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], default='low')
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-started_at']


class MobileDetectionEvent(models.Model):
    """Tracks mobile phone detection events"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSessionLog, on_delete=models.CASCADE, related_name='mobile_detections')
    detected_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=0.0)
    device_type_estimate = models.CharField(max_length=50, blank=True)
    duration_seconds = models.FloatField(default=0)
    frame_snapshot = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-detected_at']


class HeadPoseMetrics(models.Model):
    """Continuous head pose tracking data"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSessionLog, on_delete=models.CASCADE, related_name='head_pose_metrics')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Pose angles
    pitch = models.FloatField(default=0.0)
    yaw = models.FloatField(default=0.0)
    roll = models.FloatField(default=0.0)
    
    # Zone classification
    zone = models.CharField(max_length=20, choices=[
        ('green', 'Green - Focused'),
        ('yellow', 'Yellow - Warning'),
        ('red', 'Red - Looking Away'),
    ], default='green')
    
    # Direction
    direction = models.CharField(max_length=50, blank=True)
    looking_away = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['timestamp']


class EmotionProfile(models.Model):
    """Emotion analysis over time"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSessionLog, on_delete=models.CASCADE, related_name='emotion_profiles')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Emotion percentages
    happy = models.FloatField(default=0.0)
    sad = models.FloatField(default=0.0)
    angry = models.FloatField(default=0.0)
    surprise = models.FloatField(default=0.0)
    disgust = models.FloatField(default=0.0)
    neutral = models.FloatField(default=0.0)
    
    # Dominant emotion
    dominant_emotion = models.CharField(max_length=20, default='Neutral')
    confidence = models.FloatField(default=0.0)
    
    class Meta:
        ordering = ['timestamp']
    
    def get_emotion_dict(self):
        return {
            'Happy': self.happy,
            'Sad': self.sad,
            'Angry': self.angry,
            'Surprise': self.surprise,
            'Disgust': self.disgust,
            'Neutral': self.neutral,
        }
