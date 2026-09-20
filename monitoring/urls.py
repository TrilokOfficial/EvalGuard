from django.urls import path
from . import views

urlpatterns = [
    path('proctor/', views.proctor_dashboard, name='proctor_dashboard'),
    path('proctor/session/<str:session_id>/', views.proctor_session_detail, name='proctor_session_detail'),
    path('api/active-sessions/', views.api_active_sessions, name='api_active_sessions'),
    path('api/session/<str:session_id>/violations/', views.api_session_violations, name='api_session_violations'),
    path('api/session/<str:session_id>/terminate/', views.terminate_session, name='terminate_session'),
]
