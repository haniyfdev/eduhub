from rest_framework.routers import DefaultRouter
from .views import RoomViewSet

router = DefaultRouter()
router.register('', RoomViewSet, basename='rooms')

urlpatterns = router.urls
