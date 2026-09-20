from django.urls import path
from . import views

urlpatterns = [
    path('', views.analytics_dashboard, name='analytics_dashboard'),
    path('live/', views.live_monitor, name='live_monitor'),
    path('session/<str:session_id>/', views.session_analytics, name='session_analytics'),
    path('api/session/<str:session_id>/data/', views.api_analytics_data, name='api_analytics_data'),
    path('api/reports/data/', views.api_reports_data, name='api_reports_data'),
    path('reports/', views.reports_list, name='reports_list'),
    path('reports/<str:session_id>/pdf/', views.generate_pdf_report, name='generate_pdf_report'),
]
