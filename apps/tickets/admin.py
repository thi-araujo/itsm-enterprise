from django.contrib import admin
from .models import (Ticket, Category, Comment, Attachment, Escalation,
                     Approval, AuditLog)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    # requires_approval editavel na propria lista: e o botao de liga/desliga
    # do workflow de aprovacao.
    list_display  = ['name', 'requires_approval', 'color', 'created_at']
    list_editable = ['requires_approval']
    list_filter   = ['requires_approval']

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ['id', 'title', 'status', 'priority', 'ticket_type', 'requester', 'assignee', 'created_at']
    list_filter   = ['status', 'priority', 'ticket_type', 'category']
    search_fields = ['title', 'description']
    list_editable = ['status', 'assignee']

    def save_model(self, request, obj, form, change):
        # Informa o autor para a auditoria: sem isso a alteracao feita pelo
        # /admin/ apareceria como "Sistema".
        obj._audit_user = request.user
        super().save_model(request, obj, form, change)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Somente leitura: um log de auditoria editavel nao e um log de auditoria."""

    list_display  = ['created_at', 'ticket', 'user', 'action', 'field',
                     'old_value', 'new_value']
    list_filter   = ['action', 'user', 'created_at']
    search_fields = ['field', 'old_value', 'new_value', 'description']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display  = ['ticket', 'decision', 'decided_by', 'created_at']
    list_filter   = ['decision', 'decided_by', 'created_at']
    search_fields = ['comment']


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display  = ['ticket', 'from_user', 'to_user', 'created_at']
    list_filter   = ['to_user', 'created_at']
    search_fields = ['reason']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'is_internal', 'created_at']

admin.site.register(Attachment)
