from django.db import models
from core.models import User
import uuid
import secrets
import string


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    industry = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    recruiter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='companies')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class JobRole(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='roles')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    skills_required = models.TextField(blank=True)
    assessment_duration = models.IntegerField(default=45)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} @ {self.company}"


class Candidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='candidates')
    job_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='candidates')
    applied_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, default='invited',
                              choices=[('invited', 'Invited'), ('in_progress', 'In Progress'),
                                       ('completed', 'Completed'), ('rejected', 'Rejected'), ('hired', 'Hired')])
    access_token = models.CharField(max_length=32, unique=True)

    def save(self, *args, **kwargs):
        if not self.access_token:
            import secrets
            self.access_token = secrets.token_hex(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} → {self.job_role}"


class CandidateSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    overall_score = models.FloatField(null=True, blank=True)
    risk_score = models.FloatField(default=0.0)
    session_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='pending')
    notes = models.TextField(blank=True)


class AssessmentReport(models.Model):
    candidate_session = models.OneToOneField(CandidateSession, on_delete=models.CASCADE, related_name='report')
    generated_at = models.DateTimeField(auto_now_add=True)
    emotion_summary = models.JSONField(default=dict)
    physiological_summary = models.JSONField(default=dict)
    biometric_status = models.JSONField(default=dict)
    violation_count = models.IntegerField(default=0)
    recommendation = models.CharField(max_length=50, default='review',
                                      choices=[('proceed', 'Proceed'), ('review', 'Review'), ('reject', 'Reject')])
    notes = models.TextField(blank=True)


def _generate_meeting_code():
    """Generate a short uppercase alphanumeric code like AB12CD34"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class MeetingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=8, unique=True, default=_generate_meeting_code)
    room_name = models.CharField(max_length=64, unique=True)  # Jitsi room name
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meeting_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.room_name:
            self.room_name = f'evalguard-{uuid.uuid4().hex[:12]}'
        super().save(*args, **kwargs)

    def get_jitsi_url(self):
        return f'https://meet.jit.si/{self.room_name}'

    def __str__(self):
        return f'Meeting {self.code} by {self.created_by.username}'
