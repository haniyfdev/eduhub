from rest_framework.permissions import BasePermission


def _active(user):
    """Returns True only for a live, non-archived authenticated user."""
    return user.is_authenticated and user.status == 'active'


class IsSuperAdmin(BasePermission):
    """role == 'superadmin'"""

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role == 'superadmin'


class IsBoss(BasePermission):
    """
    role == 'boss' only.
    Exception to Rule 4 — used where branch/company ownership matters
    and manager should not have access (e.g. company detail management).
    """

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role == 'boss'


class IsBossOrManager(BasePermission):
    """
    role in ['boss', 'manager']
    Rule 4: 'boss' always means boss AND manager — never check boss alone.
    """

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role in ['boss', 'manager']


class IsBossManagerOrAdmin(BasePermission):
    """role in ['boss', 'manager', 'admin']"""

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role in ['boss', 'manager', 'admin']


class IsTeacher(BasePermission):
    """role == 'teacher'"""

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role == 'teacher'


class IsSameCompany(BasePermission):
    """Object-level: obj.company_id must match the requester's company (superadmin bypasses)."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'superadmin':
            return True
        return getattr(obj, 'company_id', None) == request.user.company_id


class IsTeacherOfGroup(BasePermission):
    """Object-level: obj.teacher_id must match the requester's Teacher profile id."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'superadmin':
            return True
        try:
            return obj.teacher_id == request.user.teacher.id
        except AttributeError:
            return False


class IsSuperAdminOrBossOrManager(BasePermission):
    """Convenience: superadmin + boss + manager in one class."""

    def has_permission(self, request, view):
        return _active(request.user) and request.user.role in ['superadmin', 'boss', 'manager']
