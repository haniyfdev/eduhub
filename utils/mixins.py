from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response


class ArchiveMixin:
    """
    Adds a POST /{pk}/archive/ action that sets status='archived' and archived_at=now().
    Never deletes records (Rule 1).
    """

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        instance = self.get_object()
        instance.status = 'archived'
        # archived_at yoki closed_at — qaysi field bo'lsa
        if hasattr(instance, 'archived_at'):
            instance.archived_at = timezone.now()
        if hasattr(instance, 'closed_at'):
            instance.closed_at = timezone.now()
        instance.save()
        return Response({'status': 'archived'})


class CompanyFilterMixin:
    """
    Filters queryset to the request user's company. Superadmin sees all.
    Must be combined with a ViewSet that defines `queryset`.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'superadmin':
            return qs
        return qs.filter(company_id=user.company_id)

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if user.role != 'superadmin':
            obj_company_id = getattr(obj, 'company_id', None)
            # Only enforce if the model has a direct company FK; otherwise trust queryset filtering.
            if obj_company_id is not None and obj_company_id != user.company_id:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
        return obj
