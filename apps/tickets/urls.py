from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    path('',                             views.ticket_list,          name='list'),
    path('fila/',                        views.queue_view,           name='queue'),
    path('novo/',                        views.ticket_create,        name='create'),
    path('<int:pk>/',                    views.ticket_detail,        name='detail'),
    path('<int:pk>/atualizar/',          views.ticket_update_status, name='update_status'),
    path('<int:pk>/comentar/',           views.add_comment,          name='add_comment'),
    path('<int:pk>/anexar/',             views.upload_attachment,    name='upload_attachment'),
    path('<int:pk>/anexo/<int:att_pk>/', views.download_attachment,  name='download_attachment'),
    path('<int:pk>/atribuir/',           views.assign_ticket,        name='assign'),
    path('sem-tecnico/', views.unassigned_count, name='unassigned_count'),
]