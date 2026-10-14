from django.contrib import admin
from .models import Ticket, Category, Comment, Attachment, Escalation

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'created_at']

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ['id', 'title', 'status', 'priority', 'ticket_type', 'requester', 'assignee', 'created_at']
    list_filter   = ['status', 'priority', 'ticket_type', 'category']
    search_fields = ['title', 'description']
    list_editable = ['status', 'assignee']

@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display  = ['ticket', 'from_user', 'to_user', 'created_at']
    list_filter   = ['to_user', 'created_at']
    search_fields = ['reason']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'is_internal', 'created_at']

admin.site.register(Attachment)
