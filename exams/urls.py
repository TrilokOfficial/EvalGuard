from django.urls import path
from . import views

urlpatterns = [
    path('', views.student_home, name='student_home'),
    path('create/', views.create_exam, name='create_exam'),
    path('join/', views.join_exam, name='join_exam'),
    path('<uuid:exam_id>/session/<uuid:session_id>/', views.exam_session, name='exam_session'),
    path('<uuid:exam_id>/session/<uuid:session_id>/identify/', views.verify_identity, name='verify_identity'),
    path('<uuid:exam_id>/session/<uuid:session_id>/submit/', views.submit_exam, name='submit_exam'),
    path('<uuid:exam_id>/delete/', views.delete_exam, name='delete_exam'),
    path('<uuid:exam_id>/questions/', views.manage_questions, name='manage_questions'),
]
