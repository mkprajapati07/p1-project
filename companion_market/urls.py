from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from marketplace.admin_views import dashboard as admin_dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("marketplace.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)