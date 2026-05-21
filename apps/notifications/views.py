from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from .models import Announcement, AnnouncementRead, Notification, SmsTemplate
from .serializers import AnnouncementSerializer, NotificationSerializer, SmsTemplateSerializer


class NotificationViewSet(CompanyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/notifications/ — read-only log."""
    queryset = Notification.objects.order_by('-created_at')
    serializer_class = NotificationSerializer
    filterset_fields = ['status', 'type']
    http_method_names = ['get', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]


class SmsTemplateViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    """Rule 1 exception: SmsTemplate CAN be deleted."""
    queryset = SmsTemplate.objects.all()
    serializer_class = SmsTemplateSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True).order_by('-is_default', 'name')

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'teacher':
            return Announcement.objects.none()
        return Announcement.objects.filter(
            is_active=True
        ).prefetch_related('reads').order_by('-created_at')

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
        user = request.user
        if user.role in ['superadmin', 'teacher']:
            return Response({'unread': 0})
        total = Announcement.objects.filter(is_active=True).count()
        read = AnnouncementRead.objects.filter(
            user=user,
            announcement__is_active=True
        ).count()
        return Response({'unread': max(total - read, 0)})
