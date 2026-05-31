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
    Boss can switch to a branch via the X-Active-Company request header;
    the header value is validated against companies the boss owns.
    """

    def _resolve_company_id(self):
        """Return the effective company_id for the current request."""
        user = self.request.user
        if user.role != 'boss':
            return user.company_id
        active = self.request.headers.get('X-Active-Company')
        if active and active != str(user.company_id):
            from apps.companies.models import Company
            from django.db.models import Q
            allowed = Company.objects.filter(
                id=active
            ).filter(
                Q(id=user.company_id) | Q(branch_of_id=user.company_id)
            ).exists()
            if allowed:
                return active
        return user.company_id

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'superadmin':
            return qs
        return qs.filter(company_id=self._resolve_company_id())

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if user.role != 'superadmin':
            obj_company_id = getattr(obj, 'company_id', None)
            if obj_company_id is not None and str(obj_company_id) != str(self._resolve_company_id()):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
        return obj
