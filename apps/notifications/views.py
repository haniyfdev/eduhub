from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Announcement, AnnouncementRead, Notification, SmsTemplate
from .serializers import AnnouncementSerializer, NotificationSerializer, SmsTemplateSerializer, SmsTemplateCreateSerializer


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


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Announcement.objects.filter(
            is_active=True
        ).prefetch_related('reads')

    def perform_create(self, serializer):
        if self.request.user.role != 'superadmin':
            raise PermissionDenied("Faqat superadmin xabar yoza oladi")
        serializer.save(created_by=self.request.user)

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        announcement = self.get_object()
        AnnouncementRead.objects.get_or_create(
            announcement=announcement,
            user=request.user
        )
        return Response({'status': 'read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        total = Announcement.objects.filter(is_active=True).count()
        read = AnnouncementRead.objects.filter(
            user=request.user,
            announcement__is_active=True
        ).count()
        return Response({'unread': total - read})
