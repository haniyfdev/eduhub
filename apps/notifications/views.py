from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Notification, SmsTemplate
from .serializers import NotificationSerializer, SmsTemplateSerializer, SmsTemplateCreateSerializer


class NotificationViewSet(CompanyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/notifications/ — read-only log."""
    queryset = Notification.objects.order_by('-created_at')
    serializer_class = NotificationSerializer
    filterset_fields = ['status', 'type']
    http_method_names = ['get', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]


class SmsTemplateViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    """
    GET/POST/PATCH/DELETE on /api/v1/sms-templates/
    Rule 1 exception: SmsTemplate CAN be deleted.
    """
    queryset = SmsTemplate.objects.order_by('name')
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return SmsTemplateCreateSerializer
        return SmsTemplateSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
