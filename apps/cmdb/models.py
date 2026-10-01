from django.db import models
from django.contrib.auth.models import User


class AssetType(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome")
    icon = models.CharField(max_length=50, default="bi-hdd", verbose_name="Ícone Bootstrap")

    class Meta:
        verbose_name = "Tipo de Ativo"
        verbose_name_plural = "Tipos de Ativo"
        ordering = ['name']

    def __str__(self):
        return self.name


class Asset(models.Model):
    STATUS_CHOICES = [
        ('active',      'Ativo'),
        ('inactive',    'Inativo'),
        ('maintenance', 'Em Manutenção'),
        ('disposed',    'Descartado'),
    ]

    # Identificação
    name      = models.CharField(max_length=200, verbose_name="Nome / Hostname")
    asset_tag = models.CharField(max_length=50, unique=True, verbose_name="Tag / Patrimônio")
    asset_type = models.ForeignKey(AssetType, on_delete=models.SET_NULL,
                                   null=True, blank=True, verbose_name="Tipo")

    # Hardware
    brand  = models.CharField(max_length=100, blank=True, verbose_name="Fabricante")
    model  = models.CharField(max_length=100, blank=True, verbose_name="Modelo")
    serial = models.CharField(max_length=100, blank=True, verbose_name="Número de Série")

    # Rede
    ip_address  = models.GenericIPAddressField(null=True, blank=True, verbose_name="Endereço IP")
    mac_address = models.CharField(max_length=17, blank=True, verbose_name="MAC Address")

    # Localização
    location   = models.CharField(max_length=200, blank=True, verbose_name="Localização")
    department = models.CharField(max_length=100, blank=True, verbose_name="Departamento")

    # Responsável
    owner = models.ForeignKey(User, on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='assets', verbose_name="Responsável")

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                               default='active', verbose_name="Status")

    # Datas
    purchase_date   = models.DateField(null=True, blank=True, verbose_name="Data de Compra")
    warranty_expiry = models.DateField(null=True, blank=True, verbose_name="Garantia até")

    # Observações
    notes = models.TextField(blank=True, verbose_name="Observações")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ativo"
        verbose_name_plural = "Ativos"
        ordering = ['name']

    def __str__(self):
        return f"{self.asset_tag} — {self.name}"