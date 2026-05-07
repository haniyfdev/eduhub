from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AwardViewSet

router = DefaultRouter()
router.register('', AwardViewSet, basename='awards')

urlpatterns = [path('', include(router.urls))]

