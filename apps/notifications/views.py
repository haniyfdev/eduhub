from rest_framework import status, viewsets, mixins
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


class SmsTemplateViewSet(viewsets.ModelViewSet):
    """Rule 1 exception: SmsTemplate CAN be deleted."""
    queryset = SmsTemplate.objects.all()
    serializer_class = SmsTemplateSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        from django.db.models import Q
        user = self.request.user
        if user.role == 'superadmin':
            return SmsTemplate.objects.filter(
                company__isnull=True
            ).order_by('-is_default', 'name')
        company = user.company
        company_names = SmsTemplate.objects.filter(
            company=company
        ).values_list('name', flat=True)
        return SmsTemplate.objects.filter(
            Q(company=company) | Q(company__isnull=True, is_default=True)
        ).exclude(
            Q(company__isnull=True) & Q(name__in=company_names)
        ).order_by('-is_default', 'name')

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'superadmin':
            serializer.save(company=None, is_default=True)
        else:
            serializer.save(company=user.company, is_default=False)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.company is None and user.role != 'superadmin':
            new_template = SmsTemplate.objects.create(
                company=user.company,
                name=instance.name,
                trigger=instance.trigger,
                body=request.data.get('body', instance.body),
                is_default=False,
                is_active=True,
            )
            return Response(SmsTemplateSerializer(new_template).data)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.company is None and user.role != 'superadmin':
            return Response(
                {'error': "Standart shablonni o'chira olmaysiz"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if instance.company and instance.company != user.company:
            return Response({'error': "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


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
