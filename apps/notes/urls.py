from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StudentNoteViewSet

router = DefaultRouter()
router.register('', StudentNoteViewSet, basename='student-notes')

urlpatterns = [path('', include(router.urls))]
