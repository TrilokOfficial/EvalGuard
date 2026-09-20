from django.db import models
from core.models import User
import uuid


class Exam(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    professor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exams_created')
    duration_minutes = models.IntegerField(default=60)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    access_code = models.CharField(max_length=12, unique=True)
    max_violations = models.IntegerField(default=5)
    proctoring_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_start = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.access_code:
            import random, string
            self.access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        super().save(*args, **kwargs)


class Question(models.Model):
    QUESTION_TYPES = [
        ('mcq', 'Multiple Choice'),
        ('text', 'Descriptive / Short Answer'),
        ('code', 'Coding Challenge'),
        ('media', 'Media Upload required'),
    ]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, default='mcq')
    attachment = models.FileField(upload_to='questions/attachments/', null=True, blank=True)
    option_a = models.TextField(blank=True)
    option_b = models.TextField(blank=True)
    option_c = models.TextField(blank=True)
    option_d = models.TextField(blank=True)
    correct_answer = models.CharField(max_length=1, blank=True)
    marks = models.IntegerField(default=1)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q{self.order}: {self.text[:60]}"


class ExamSession(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sessions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_sessions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Identity Verification Fields
    student_name = models.CharField(max_length=255, blank=True)
    university_id = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=255, blank=True)
    tab_switch_count = models.IntegerField(default=0)
    violation_count = models.IntegerField(default=0)
    risk_score = models.FloatField(default=0.0)
    face_detection_failures = models.IntegerField(default=0)
    multiple_face_detections = models.IntegerField(default=0)
    looking_away_count = models.IntegerField(default=0)
    blink_count = models.IntegerField(default=0)
    is_terminated = models.BooleanField(default=False)
    termination_reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"


class Violation(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='violations')
    violation_type = models.CharField(max_length=50)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    timestamp = models.DateTimeField(auto_now_add=True)
    elapsed_seconds = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.violation_type} ({self.severity}) - {self.session}"


class StudentAnswer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    selected_option = models.CharField(max_length=1, blank=True)
    media_upload = models.FileField(upload_to='answers/media/', null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_correct = models.BooleanField(null=True, blank=True)
