from django.core import signing
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
    UserCreateSerializer,
    UserListSerializer,
    UserMeSerializer,
    UserUpdateSerializer,
)


_COMPANY_SELECT_SALT = 'company-select'
_COMPANY_SELECT_MAX_AGE = 300  # 5 minutes


def _build_user_payload(user):
    """Build the user dict included in auth responses."""
    accessible_companies = []
    if user.company_id:
        from apps.companies.models import Company
        own = Company.objects.filter(id=user.company_id).first()
        if own:
            accessible_companies.append({'id': str(own.id), 'name': own.name})
        if user.role in ['boss', 'manager']:
            branches = Company.objects.filter(
                branch_of_id=user.company_id, status='active'
            ).values('id', 'name')
            for b in branches:
                accessible_companies.append({'id': str(b['id']), 'name': b['name']})
    return {
        'id': str(user.id),
        'role': user.role,
        'company_id': str(user.company_id) if user.company_id else None,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'accessible_companies': accessible_companies,
    }


class LoginView(APIView):
    """POST /api/auth/login/

    Single company  → returns access + refresh tokens immediately.
    Multiple companies → returns requires_company_selection=true with company
                         list and a short-lived signed temp_token; client must
                         POST to /api/auth/select-company/ to get a real token.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        password = request.data.get('password', '')

        if not phone or not password:
            return Response(
                {'non_field_errors': ['Phone and password are required.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find all active users with this phone and verify password manually
        # (can't use authenticate() when multiple users share a phone)
        candidates = User.objects.filter(phone=phone, is_active=True).exclude(status='archived')
        matching = [u for u in candidates if u.check_password(password)]

        if not matching:
            return Response(
                {'non_field_errors': ['Invalid phone number or password.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(matching) == 1:
            user = matching[0]
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': _build_user_payload(user),
            }, status=status.HTTP_200_OK)

        # Multiple companies — ask the client to choose
        from apps.companies.models import Company
        company_ids = [u.company_id for u in matching if u.company_id]
        companies = Company.objects.filter(id__in=company_ids).values('id', 'name')
        company_list = [{'id': str(c['id']), 'name': c['name']} for c in companies]

        temp_token = signing.dumps(
            {'phone': phone, 'user_ids': [str(u.id) for u in matching]},
            salt=_COMPANY_SELECT_SALT,
        )

        return Response({
            'requires_company_selection': True,
            'companies': company_list,
            'temp_token': temp_token,
        }, status=status.HTTP_200_OK)


class SelectCompanyView(APIView):
    """POST /api/auth/select-company/

    Accepts temp_token (from multi-company login) + company_id.
    Returns real access + refresh tokens for the chosen company.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        temp_token = request.data.get('temp_token', '')
        company_id = request.data.get('company_id', '')

        if not temp_token or not company_id:
            return Response(
                {'error': 'temp_token and company_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = signing.loads(
                temp_token,
                salt=_COMPANY_SELECT_SALT,
                max_age=_COMPANY_SELECT_MAX_AGE,
            )
        except signing.SignatureExpired:
            return Response(
                {'error': 'Selection token has expired. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response(
                {'error': 'Invalid selection token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_ids = payload.get('user_ids', [])
        try:
            user = User.objects.get(
                id__in=user_ids,
                company_id=company_id,
                is_active=True,
            )
        except User.DoesNotExist:
            return Response(
                {'error': 'No account found for the selected company.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.status == 'archived':
            return Response(
                {'error': 'This account has been deactivated.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': _build_user_payload(user),
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


_RESET_SALT = 'password-reset'
_RESET_MAX_AGE = 300  # 5 minutes


class ForgotPasswordView(APIView):
    """POST /api/auth/forgot-password/

    Body: { "phone": "+998XXXXXXXXX" }
    Sends a 6-digit OTP to the user's linked Telegram account.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from utils.otp import check_rate_limit, generate_otp, increment_attempts
        from utils.telegram import send_otp_to_telegram

        phone = request.data.get('phone', '').strip()
        if not phone:
            return Response({'error': 'phone is required'}, status=status.HTTP_400_BAD_REQUEST)

        rate = check_rate_limit(phone)
        if not rate['allowed']:
            return Response(
                {'error': 'rate_limited', 'wait_seconds': rate['wait_seconds']},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # If no user exists, return success silently (prevent phone enumeration)
        if not User.objects.filter(phone=phone, is_active=True).exists():
            return Response({'success': True, 'expires_in': 100})

        has_telegram = (
            User.objects
            .filter(phone=phone, is_active=True)
            .exclude(telegram_chat_id=None)
            .exists()
        )
        if not has_telegram:
            return Response(
                {
                    'error': 'telegram_not_linked',
                    'message': 'Avval Telegram botimizga /start yuboring va telefon raqamingizni ulang',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = generate_otp(phone)
        sent = send_otp_to_telegram(phone, code)
        if not sent:
            return Response(
                {'error': 'telegram_send_failed', 'message': "Telegram xabar yuborishda xatolik yuz berdi"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        increment_attempts(phone)
        return Response({'success': True, 'expires_in': 100})


class VerifyOtpView(APIView):
    """POST /api/auth/verify-otp/

    Body: { "phone": "+998XXXXXXXXX", "code": "123456" }
    Returns a short-lived reset_token on success.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from utils.otp import verify_otp

        phone = request.data.get('phone', '').strip()
        code = request.data.get('code', '').strip()

        if not phone or not code:
            return Response(
                {'error': 'phone and code are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = verify_otp(phone, code)
        if result == 'expired':
            return Response({'error': 'otp_expired'}, status=status.HTTP_400_BAD_REQUEST)
        if result == 'invalid':
            return Response({'error': 'invalid_otp'}, status=status.HTTP_400_BAD_REQUEST)

        reset_token = signing.dumps({'phone': phone}, salt=_RESET_SALT)
        return Response({'reset_token': reset_token})


class ResetPasswordView(APIView):
    """POST /api/auth/reset-password/

    Body: { "reset_token": "...", "new_password": "..." }
    Updates password for ALL accounts sharing the phone number.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        reset_token = request.data.get('reset_token', '')
        new_password = request.data.get('new_password', '')

        if not reset_token or not new_password:
            return Response(
                {'error': 'reset_token and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'error': 'password_too_short', 'message': "Parol kamida 8 ta belgidan iborat bo'lishi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = signing.loads(reset_token, salt=_RESET_SALT, max_age=_RESET_MAX_AGE)
        except signing.SignatureExpired:
            return Response({'error': 'token_expired'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'error': 'invalid_token'}, status=status.HTTP_400_BAD_REQUEST)

        phone = payload.get('phone', '')
        users = User.objects.filter(phone=phone, is_active=True)
        if not users.exists():
            return Response({'error': 'user_not_found'}, status=status.HTTP_400_BAD_REQUEST)

        for user in users:
            user.set_password(new_password)
            user.save(update_fields=['password'])

        return Response({'success': True})


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

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and user.role in ['boss', 'manager'] and user.company:
            ctx['company'] = user.company
        return ctx

    def perform_create(self, serializer):
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

    @action(detail=False, methods=['post', 'patch'], url_path='change-password',
            permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """POST /api/v1/users/change-password/ — change own password."""
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response(
                {'detail': 'old_password and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(old_password):
            return Response(
                {'detail': 'Old password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'detail': "Parol kamida 8 ta belgidan iborat bo'lishi kerak."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)
