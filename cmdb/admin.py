from django.contrib import admin
from .models import Asset, AssetType

@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display  = ['asset_tag', 'name', 'asset_type', 'status', 'ip_address', 'department', 'owner']
    list_filter   = ['status', 'asset_type']
    search_fields = ['name', 'asset_tag', 'serial', 'ip_address']