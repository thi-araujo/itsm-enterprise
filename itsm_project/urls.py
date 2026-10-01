"""Rotas principais do ITSM Enterprise."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('apps.dashboard.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('tickets/', include('apps.tickets.urls')),
    path('cmdb/', include('apps.cmdb.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reports/', include('apps.reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
