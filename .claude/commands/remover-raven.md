Refatore o projeto para remover o nome antigo "RAVEN".

Regras:
- "RAVEN ITSM" / "RAVEN" em textos visíveis → "ITSM Enterprise"
- Variáveis CSS `--raven-*` → `--itsm-*`
- Classes CSS `raven-card`, `btn-raven`, `raven-table` etc. → `itsm-card`, `btn-itsm`, `itsm-table`
- E-mails `@raven.local` → `@itsm.local`
- Assinaturas de e-mail "— RAVEN ITSM" → "— ITSM Enterprise"
- Prefixo de log `[RAVEN EMAIL]` → `[ITSM EMAIL]`
- NÃO altere: nomes de pastas fora do projeto, o venv, migrações já aplicadas, db.sqlite3

Passos:
1. Faça `git add -A && git commit -m "backup antes de remover RAVEN"`.
2. Liste todos os arquivos com ocorrências e mostre o plano.
3. Após minha aprovação, aplique as alterações.
4. Rode `python manage.py check` e uma busca final para confirmar zero ocorrências.
5. Faça commit: "refactor: renomeia sistema para ITSM Enterprise".
