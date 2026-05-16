from django.urls import path
from .rooms_view import RoomsView

urlpatterns = [
    path('', RoomsView.as_view(), name='rooms'),
]
