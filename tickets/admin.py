from django.contrib import admin
from .models import Ticket, Category, Comment, Attachment

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'created_at']

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ['id', 'title', 'status', 'priority', 'ticket_type', 'requester', 'assignee', 'created_at']
    list_filter   = ['status', 'priority', 'ticket_type', 'category']
    search_fields = ['title', 'description']
    list_editable = ['status', 'assignee']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'is_internal', 'created_at']

admin.site.register(Attachment)
