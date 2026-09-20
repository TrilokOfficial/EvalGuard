from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('exam/', include('exams.urls')),
    path('monitoring/', include('monitoring.urls')),
    # Fix: /proctor/ redirects to the proper monitoring proctor dashboard
    path('proctor/', RedirectView.as_view(url='/monitoring/proctor/', permanent=False)),
    path('analytics/', include('analytics.urls')),
    path('recruitment/', include('recruitment.urls')),
    path('api/', include('api_layer.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
