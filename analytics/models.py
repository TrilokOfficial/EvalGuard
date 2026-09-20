from django.db import models
from core.models import User
import uuid


class AnalyticsSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=100, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    head_yaw = models.FloatField(null=True, blank=True)
    head_pitch = models.FloatField(null=True, blank=True)
    head_roll = models.FloatField(null=True, blank=True)
    gaze_direction = models.CharField(max_length=30, blank=True)
    attention_zone = models.CharField(max_length=10, default='green')
    blink_rate = models.FloatField(null=True, blank=True)
    risk_score = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-timestamp']


class EmotionRecord(models.Model):
    snapshot = models.ForeignKey(AnalyticsSnapshot, on_delete=models.CASCADE, related_name='emotions')
    happy = models.FloatField(default=0)
    sad = models.FloatField(default=0)
    angry = models.FloatField(default=0)
    surprise = models.FloatField(default=0)
    disgust = models.FloatField(default=0)
    neutral = models.FloatField(default=0)

    def dominant_emotion(self):
        emotions = {'Happy': self.happy, 'Sad': self.sad, 'Angry': self.angry,
                    'Surprise': self.surprise, 'Disgust': self.disgust, 'Neutral': self.neutral}
        return max(emotions, key=emotions.get)


class PhysiologicalRecord(models.Model):
    snapshot = models.ForeignKey(AnalyticsSnapshot, on_delete=models.CASCADE, related_name='physiological')
    heart_rate = models.IntegerField(null=True)
    stress_level = models.FloatField(null=True)
    respiration = models.FloatField(null=True)
    blood_oxygen = models.FloatField(null=True)
    hrv = models.FloatField(null=True)
