from django import forms
from .models import Asset


class AssetForm(forms.ModelForm):
    class Meta:
        model  = Asset
        fields = [
            'name', 'asset_tag', 'asset_type', 'status',
            'brand', 'model', 'serial',
            'ip_address', 'mac_address',
            'location', 'department', 'owner',
            'purchase_date', 'warranty_expiry', 'notes',
        ]
        widgets = {
            'name':           forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: DESKTOP-RH-01'}),
            'asset_tag':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: PAT-2024-001'}),
            'asset_type':     forms.Select(attrs={'class': 'form-select'}),
            'status':         forms.Select(attrs={'class': 'form-select'}),
            'brand':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Dell, HP, Lenovo'}),
            'model':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: OptiPlex 7090'}),
            'serial':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de série'}),
            'ip_address':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 192.168.1.100'}),
            'mac_address':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: AA:BB:CC:DD:EE:FF'}),
            'location':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Sala 203, Andar 2'}),
            'department':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Recursos Humanos'}),
            'owner':          forms.Select(attrs={'class': 'form-select'}),
            'purchase_date':  forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'warranty_expiry':forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes':          forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }