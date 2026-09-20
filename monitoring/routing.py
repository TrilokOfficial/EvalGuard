from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/proctor/(?P<session_id>[^/]+)/$', consumers.ProctorConsumer.as_asgi()),
    re_path(r'^ws/proctor/dashboard/$', consumers.ProctorConsumer.as_asgi()),
    re_path(r'^ws/recruiter/dashboard/$', consumers.RecruiterDashboardConsumer.as_asgi()),
]
