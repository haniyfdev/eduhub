from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/v1/', include('config.api_router')),
    path('api/superadmin/', include('apps.superadmin_panel.urls')),
]
