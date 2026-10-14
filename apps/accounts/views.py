from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard:index')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
    else:
        form = AuthenticationForm()

    # Com o AD ligado (Fase 3.8), a tela avisa que a senha esperada é a do
    # domínio — senão a pessoa tenta uma senha local que o sistema nem guarda.
    return render(request, 'accounts/login.html', {
        'form': form,
        'ldap_ativo': settings.LDAP_ENABLED,
        'ldap_dominio': settings.LDAP_DOMAIN,
    })


def logout_view(request):
    logout(request)
    return redirect('accounts:login')
