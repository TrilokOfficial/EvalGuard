from django.contrib import admin
from .models import Exam, Question, ExamSession, Violation, StudentAnswer

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'professor', 'status', 'access_code', 'duration_minutes', 'created_at']
    list_filter = ['status']

@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'status', 'violation_count', 'risk_score', 'started_at']

@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ['violation_type', 'severity', 'session', 'timestamp']
    list_filter = ['severity', 'violation_type']

admin.site.register(Question)
admin.site.register(StudentAnswer)
