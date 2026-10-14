Verifique o projeto antes de eu testar no navegador:
1. `python manage.py check`
2. `python manage.py makemigrations --check --dry-run`
3. Procure templates com `{% block %}` sem `{% endblock %}` correspondente.
4. Procure acessos a atributos de `assignee`, `owner` ou `category` sem proteção para valor nulo.
5. Confira se toda URL usada em `{% url %}` existe nos `urls.py`.
Relate os problemas e proponha correções. Não altere nada sem minha aprovação.
