from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from .models import Subscription
from .serializers import SubscriptionSerializer


class SubscriptionViewSet(CompanyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/v1/subscriptions/          Own company subscription history
    GET /api/v1/subscriptions/current/  Active subscription detail
    """
    queryset = Subscription.objects.order_by('-started_at')
    serializer_class = SubscriptionSerializer
    http_method_names = ['get', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def current(self, request):
        sub = self.get_queryset().filter(status='active').first()
        if not sub:
            return Response({'detail': 'No active subscription.'}, status=404)
        return Response(SubscriptionSerializer(sub).data)
