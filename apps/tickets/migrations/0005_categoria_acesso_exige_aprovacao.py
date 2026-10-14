"""Marca a categoria de acesso como exigindo aprovação do gerente.

É o exemplo do ROADMAP ("chamados de acesso precisam de aprovação do
gerente") e a categoria já existe no banco. As outras categorias ficam como
estão, e nenhum chamado já aberto é tocado — eles mantêm o status atual.

Reversível: o `migrate tickets 0004` devolve a flag para False.
"""

from django.db import migrations

# Casado por nome: é o dado que existe no banco de desenvolvimento.
CATEGORIAS_COM_APROVACAO = ['Acesso e Permissões']


def marcar(apps, schema_editor):
    Category = apps.get_model('tickets', 'Category')
    Category.objects.filter(name__in=CATEGORIAS_COM_APROVACAO).update(
        requires_approval=True)


def desmarcar(apps, schema_editor):
    Category = apps.get_model('tickets', 'Category')
    Category.objects.filter(name__in=CATEGORIAS_COM_APROVACAO).update(
        requires_approval=False)


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0004_category_requires_approval_alter_ticket_status_and_more'),
    ]

    operations = [
        migrations.RunPython(marcar, desmarcar),
    ]
