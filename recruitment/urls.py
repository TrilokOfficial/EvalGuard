from django.urls import path
from . import views

urlpatterns = [
    path('', views.recruiter_dashboard, name='recruiter_dashboard'),
    path('candidate/<str:token>/', views.candidate_portal, name='candidate_portal'),
    path('companies/', views.company_list, name='company_list'),
    path('assess/<uuid:session_id>/', views.assessment_session, name='assessment_session'),
    # Proctoring API endpoints
    path('api/proctoring/stats/', views.api_proctoring_stats, name='api_proctoring_stats'),
    path('api/proctoring/violations/<str:session_id>/', views.api_session_violations, name='api_session_violations'),
    path('api/proctors/', views.api_proctors_list, name='api_proctors_list'),
    path('api/agents/', views.api_agents_list, name='api_agents_list'),
    # Meeting endpoints
    path('meeting/create/', views.create_meeting, name='create_meeting'),
    path('meeting/join/<str:code>/', views.join_meeting, name='join_meeting'),
]
