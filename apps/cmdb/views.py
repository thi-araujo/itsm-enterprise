from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from apps.accounts.permissions import staff_required
from django.contrib import messages
from django.db.models import Q
from .models import Asset, AssetType
from .forms import AssetForm


@login_required
@staff_required
def asset_list(request):
    assets = Asset.objects.select_related('asset_type', 'owner')

    search        = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter   = request.GET.get('type', '')

    if search:
        assets = assets.filter(
            Q(name__icontains=search) |
            Q(asset_tag__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(department__icontains=search) |
            Q(serial__icontains=search)
        )
    if status_filter:
        assets = assets.filter(status=status_filter)
    if type_filter:
        assets = assets.filter(asset_type__pk=type_filter)

    context = {
        'assets':        assets,
        'total':         assets.count(),
        'search':        search,
        'status_filter': status_filter,
        'type_filter':   type_filter,
        'types':         AssetType.objects.all(),
    }
    if request.htmx:
        return render(request, 'partials/asset_table.html', context)
    return render(request, 'cmdb/list.html', context)


@login_required
@staff_required
def asset_detail(request, pk):
    asset   = get_object_or_404(Asset, pk=pk)
    tickets = asset.tickets.select_related(
        'requester', 'assignee'
    ).order_by('-created_at')[:10]
    return render(request, 'cmdb/detail.html', {
        'asset':   asset,
        'tickets': tickets,
    })


@login_required
@staff_required
def asset_create(request):
    if request.method == 'POST':
        form = AssetForm(request.POST)
        if form.is_valid():
            asset = form.save()
            messages.success(request, f'Ativo "{asset.name}" cadastrado!')
            return redirect('cmdb:detail', pk=asset.pk)
    else:
        form = AssetForm()
    return render(request, 'cmdb/form.html', {'form': form, 'action': 'Cadastrar'})


@login_required
@staff_required
def asset_edit(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == 'POST':
        form = AssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, f'Ativo "{asset.name}" atualizado!')
            return redirect('cmdb:detail', pk=asset.pk)
    else:
        form = AssetForm(instance=asset)
    return render(request, 'cmdb/form.html', {'form': form, 'action': 'Editar'})