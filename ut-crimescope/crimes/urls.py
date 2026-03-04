from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('alerts/', views.watch_location_view, name='watch_location'),
    path('alerts/remove/<int:pk>/', views.remove_watch_view, name='remove_watch'),
    path('building/<int:pk>/', views.building_detail, name='building_detail'),
    path('export/', views.export_csv, name='export_csv'),
]
