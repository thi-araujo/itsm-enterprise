"""
Execute: python manage.py shell < seed_data.py
Cria superuser admin/admin e dados de exemplo
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'itsm_project.settings')
django.setup()

from django.contrib.auth.models import User
from tickets.models import Category, Ticket

# Superuser
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@itsm.local', 'admin')
    print("Superuser admin criado (senha: admin)")

# Técnico
if not User.objects.filter(username='thiago').exists():
    u = User.objects.create_user('thiago', 'thiago@itsm.local', 'thiago123')
    u.first_name = 'Thiago'
    u.last_name = 'Analista'
    u.save()
    print("Usuário thiago criado (senha: thiago123)")

admin = User.objects.get(username='admin')
thiago = User.objects.get(username='thiago')

# Categorias
cats = [
    ('Rede e Conectividade', 'bi-wifi', 'primary'),
    ('Hardware', 'bi-cpu', 'warning'),
    ('Software / Aplicações', 'bi-app-indicator', 'info'),
    ('Segurança', 'bi-shield-lock', 'danger'),
    ('Acesso e Permissões', 'bi-key', 'success'),
    ('Impressão', 'bi-printer', 'secondary'),
]
for name, icon, color in cats:
    Category.objects.get_or_create(name=name, defaults={'icon': icon, 'color': color})
print(f"{Category.objects.count()} categorias criadas")

# Tickets de exemplo
rede = Category.objects.get(name='Rede e Conectividade')
seg  = Category.objects.get(name='Segurança')
sw   = Category.objects.get(name='Software / Aplicações')

tickets_data = [
    ('VPN corporativa fora do ar — setor financeiro', 'Usuários do financeiro não conseguem conectar à VPN. Erro: timeout na porta 443.', 'critical', 'open', rede),
    ('Atualização do antivírus pendente em 47 máquinas', 'Relatório do WSUS mostra 47 estações com definições desatualizadas há mais de 7 dias.', 'high', 'in_progress', seg),
    ('Lentidão no ERP após atualização de ontem', 'Após update da versão 3.4.1 para 3.5.0, módulo de estoque apresenta lentidão grave.', 'high', 'open', sw),
    ('Solicitação de acesso ao sistema de RH', 'Novo colaborador Paulo Silva precisa de acesso ao módulo de folha de pagamento.', 'medium', 'open', None),
    ('Impressora do 3º andar não imprime em PDF', 'HP LaserJet M428 recusa trabalhos PDF. Outros formatos funcionam normalmente.', 'low', 'resolved', None),
]

for title, desc, priority, status, cat in tickets_data:
    t, created = Ticket.objects.get_or_create(
        title=title,
        defaults={
            'description': desc,
            'priority': priority,
            'status': status,
            'category': cat,
            'requester': admin,
            'assignee': thiago if status == 'in_progress' else None,
        }
    )
    if created:
        print(f"  Ticket criado: #{t.pk} {t.title[:40]}")

print("\nSeed concluído! Acesse: http://127.0.0.1:8000")
print("Login: admin / admin  ou  thiago / thiago123")
