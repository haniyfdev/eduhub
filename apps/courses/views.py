from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Course
from .serializers import CourseSerializer, CourseCreateSerializer


class CourseViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Course.objects.prefetch_related('teachers__user').order_by('name')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'update', 'archive'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CourseCreateSerializer
        return CourseSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
