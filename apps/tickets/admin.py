from django.contrib import admin
from .models import Ticket, Category, Comment, Attachment, Escalation, Approval

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
