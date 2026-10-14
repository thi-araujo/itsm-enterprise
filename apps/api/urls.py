"""Rotas da API REST — prefixo /api/v1/ (Fase 3.5).

A versão no caminho existe para o dia em que um campo mudar de forma: a v2
nasce ao lado e quem já integrou continua usando a v1.
"""

from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

router = DefaultRouter()
router.register('tickets',    views.TicketViewSet,   basename='ticket')
router.register('categorias', views.CategoryViewSet, basename='categoria')
router.register('ativos',     views.AssetViewSet,    basename='ativo')
router.register('tecnicos',   views.TecnicoViewSet,  basename='tecnico')

urlpatterns = [
    path('', include(router.urls)),
    path('eu/',            views.eu,            name='eu'),
    path('estatisticas/',  views.estatisticas,  name='estatisticas'),
    # Troca usuário+senha por um token para usar em integrações:
    #   POST /api/v1/token/  {"username": "...", "password": "..."}
    path('token/',         obtain_auth_token,   name='token'),
]
