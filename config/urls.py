from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.telegram_bot.webhook import TelegramWebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/v1/', include('config.api_router')),
    path('api/superadmin/', include('apps.superadmin_panel.urls')),
    path('api/telegram/webhook/', TelegramWebhookView.as_view(), name='telegram-webhook'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
