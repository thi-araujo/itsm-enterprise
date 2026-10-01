from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('',              views.notification_list, name='list'),
    path('marcar-todas/', views.mark_all_read,     name='mark_all_read'),
    path('contador/',     views.unread_count,       name='unread_count'),
]