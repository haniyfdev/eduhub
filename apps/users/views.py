from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsSuperAdmin
from .models import User
from .serializers import (
    LoginSerializer,
    UserCreateSerializer,
    UserListSerializer,
    UserMeSerializer,
    UserUpdateSerializer,
)


class LoginView(APIView):
    """POST /api/auth/login/ — returns access + refresh tokens with user payload."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        # Build list of company IDs this user can access
        accessible_companies = []
        if user.company_id:
            accessible_companies.append(str(user.company_id))
            if user.role in ['boss', 'manager']:
                from apps.companies.models import Company
                branch_ids = Company.objects.filter(
                    branch_of_id=user.company_id
                ).values_list('id', flat=True)
                accessible_companies += [str(bid) for bid in branch_ids]

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': str(user.id),
                'role': user.role,
                'company_id': str(user.company_id) if user.company_id else None,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone,
                'accessible_companies': accessible_companies,
            },
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ — blacklists the provided refresh token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            # Already blacklisted or invalid — still treat as successful logout.
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)


# Re-export simplejwt's refresh view under our URL path.
RefreshTokenView = TokenRefreshView


class UserViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    """
    GET    /api/v1/users/         List staff in company
    POST   /api/v1/users/         Create staff user
    GET    /api/v1/users/{id}/    Detail
    PATCH  /api/v1/users/{id}/    Update
    POST   /api/v1/users/{id}/archive/  Archive (sets status=archived + is_active=False)
    """
    queryset = User.objects.all().order_by('created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('list', 'create', 'archive'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ('update', 'partial_update'):
            return UserUpdateSerializer
        return UserListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Superadmins are never listed inside a company view.
        user = self.request.user
        if user.role != 'superadmin':
            qs = qs.exclude(role='superadmin')
        return qs

    def perform_create(self, serializer):
        # Boss/manager can only create users in their own company.
        user = self.request.user
        if user.role in ['boss', 'manager']:
            serializer.save(company=user.company)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        instance = self.get_object()
        instance.status = 'archived'
        instance.closed_at = timezone.now()
        instance.is_active = False   # revoke JWT auth immediately
        instance.save()
        return Response({'status': 'archived'})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """GET /api/v1/users/me/ — returns the authenticated user's profile."""
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data)
