from django.urls import path
from . import views

urlpatterns = [
    path('sessions/', views.SessionListView.as_view(), name='api_sessions'),
    path('sessions/active/', views.active_sessions_api, name='api_active_sessions_rest'),
    path('sessions/<str:session_id>/analytics/', views.SessionAnalyticsView.as_view(), name='api_session_analytics'),
    path('health/', views.health_check, name='api_health'),
]
