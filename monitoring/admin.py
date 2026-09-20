from django.contrib import admin
from .models import (
    Proctor, ProctorAssignment, ParrokitAgent, ProctoringSessionLog,
    ViolationEvent, DistractionEvent, MobileDetectionEvent, HeadPoseMetrics, EmotionProfile
)


@admin.register(Proctor)
class ProctorAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'max_sessions', 'specialization', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'user__email', 'specialization']


@admin.register(ParrokitAgent)
class ParrokitAgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'agent_type', 'is_active', 'created_at']
    list_filter = ['agent_type', 'is_active']


@admin.register(ProctoringSessionLog)
class ProctoringSessionLogAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'candidate_name', 'final_status', 'risk_score', 'started_at']
    list_filter = ['final_status', 'started_at']
    search_fields = ['session_id', 'candidate_name']
    filter_horizontal = ['proctors', 'agents']


@admin.register(ViolationEvent)
class ViolationEventAdmin(admin.ModelAdmin):
    list_display = ['violation_type', 'session', 'severity', 'timestamp']
    list_filter = ['violation_type', 'severity', 'timestamp']


@admin.register(DistractionEvent)
class DistractionEventAdmin(admin.ModelAdmin):
    list_display = ['distraction_type', 'session', 'severity', 'started_at', 'duration_seconds']
    list_filter = ['distraction_type', 'severity']


@admin.register(MobileDetectionEvent)
class MobileDetectionEventAdmin(admin.ModelAdmin):
    list_display = ['session', 'confidence', 'detected_at', 'duration_seconds']
    list_filter = ['detected_at']


@admin.register(HeadPoseMetrics)
class HeadPoseMetricsAdmin(admin.ModelAdmin):
    list_display = ['session', 'zone', 'pitch', 'yaw', 'roll', 'timestamp']
    list_filter = ['zone', 'timestamp']


@admin.register(EmotionProfile)
class EmotionProfileAdmin(admin.ModelAdmin):
    list_display = ['session', 'dominant_emotion', 'confidence', 'timestamp']
    list_filter = ['dominant_emotion', 'timestamp']
