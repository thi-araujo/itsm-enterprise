from django import forms
from django.conf import settings
from django.contrib.auth.models import User

from apps.accounts.models import UserProfile
from .models import Approval, Ticket, Comment, Escalation


class TicketForm(forms.ModelForm):
    # Campo extra — não é do model, tratado na view
    attachment = forms.FileField(
        required=False,
        label='Anexar arquivo (opcional)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            # Mesma lista usada na validação da view (ver settings.py).
            'accept': ','.join(settings.ALLOWED_UPLOAD_EXTENSIONS),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # "Aguardando Aprovação" e "Rejeitado" são definidos pelo workflow de
        # aprovação, não escolhidos à mão — saem do <select>. Como o Django
        # valida contra as choices do campo, isso também barra um POST forjado.
        self.fields['status'].choices = [
            (valor, rotulo) for valor, rotulo in Ticket.STATUS_CHOICES
            if valor not in Ticket.WORKFLOW_STATUSES
        ]


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


class TicketFinishForm(forms.ModelForm):
    """Finalizar o chamado: a solução é obrigatória.

    No model `solution` é `blank=True` porque os chamados que já existiam
    nasceram sem solução e o banco precisa aceitá-los. Aqui, no formulário,
    ela é exigida — é a diferença entre "o banco permite" e "o usuário pode
    deixar em branco".
    """

    class Meta:
        model  = Ticket
        fields = ['solution']
        widgets = {
            'solution': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Descreva o que foi feito para resolver o chamado...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['solution'].required = True

    def clean_solution(self):
        solution = self.cleaned_data['solution'].strip()
        # Sem o mínimo, "ok" passaria a valer como documentação da solução.
        if len(solution) < 10:
            raise forms.ValidationError(
                'Descreva a solução com pelo menos 10 caracteres — '
                'ela vai para o solicitante e fica no histórico do chamado.')
        return solution


class EscalationForm(forms.ModelForm):
    """Escalonar o chamado para outro membro da equipe, com motivo."""

    class Meta:
        model  = Escalation
        fields = ['to_user', 'reason']
        labels = {'to_user': 'Escalonar para', 'reason': 'Motivo'}
        widgets = {
            'to_user': forms.Select(attrs={'class': 'form-select'}),
            'reason':  forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Por que o chamado está sendo repassado?',
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        """`user` é quem está escalonando: ele não aparece como destino.

        Escalonar para si mesmo não faz sentido, e tirar a opção da lista é
        melhor que recusar depois — o usuário nem chega a errar.
        """
        super().__init__(*args, **kwargs)
        equipe = User.objects.filter(
            profile__role__in=UserProfile.STAFF_ROLES).select_related('profile')
        if user is not None:
            equipe = equipe.exclude(pk=user.pk)
        self.fields['to_user'].queryset = equipe
        self.fields['to_user'].required = True
        self.fields['to_user'].empty_label = 'Selecione o responsável...'
        self.fields['reason'].required = True

    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if len(reason) < 10:
            raise forms.ValidationError(
                'Explique o motivo com pelo menos 10 caracteres — '
                'quem receber o chamado precisa entender o contexto.')
        return reason


class ApprovalForm(forms.ModelForm):
    """Parecer do gerente sobre um chamado que exige aprovação (Fase 3.3).

    O parecer é opcional ao aprovar e obrigatório ao rejeitar: negar um
    pedido sem dizer por que deixa o solicitante sem saber o que fazer.
    """

    class Meta:
        model  = Approval
        fields = ['comment']
        labels = {'comment': 'Parecer'}
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Justifique a decisão...',
            }),
        }

    def __init__(self, *args, decision=None, **kwargs):
        """`decision` define se o parecer é obrigatório."""
        super().__init__(*args, **kwargs)
        self.decision = decision
        if decision == Approval.DECISION_REJECTED:
            self.fields['comment'].required = True
            self.fields['comment'].label = 'Motivo da rejeição'

    def clean_comment(self):
        comment = self.cleaned_data['comment'].strip()
        if self.decision == Approval.DECISION_REJECTED and len(comment) < 10:
            raise forms.ValidationError(
                'Explique o motivo da rejeição com pelo menos 10 caracteres — '
                'o solicitante precisa saber por que o pedido foi negado.')
        return comment
