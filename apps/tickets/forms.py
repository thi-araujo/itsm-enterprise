from django import forms
from .models import Ticket, Comment


class TicketForm(forms.ModelForm):
    # Campo extra — não é do model, tratado na view
    attachment = forms.FileField(
        required=False,
        label='Anexar arquivo (opcional)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt,.log,.zip'
        })
    )

    class Meta:
        model  = Ticket
        fields = ['title', 'description', 'ticket_type', 'category', 'priority', 'asset']
        widgets = {
            'title':       forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descreva brevemente o problema...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Detalhe o problema, impacto, passos para reproduzir...'
            }),
            'ticket_type': forms.Select(attrs={'class': 'form-select'}),
            'category':    forms.Select(attrs={'class': 'form-select'}),
            'priority':    forms.Select(attrs={'class': 'form-select'}),
            'asset':       forms.Select(attrs={'class': 'form-select'}),
        }


class TicketUpdateForm(forms.ModelForm):
    class Meta:
        model  = Ticket
        fields = ['status', 'assignee', 'priority']
        widgets = {
            'status':   forms.Select(attrs={'class': 'form-select'}),
            'assignee': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model  = Comment
        fields = ['content', 'is_internal']
        widgets = {
            'content':     forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Adicione um comentário...'
            }),
            'is_internal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }