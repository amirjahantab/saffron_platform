from django import forms
from .models import Ticket, Review


class TicketForm(forms.ModelForm):
    body = forms.CharField(label="شرح درخواست", max_length=5000, widget=forms.Textarea(attrs={"rows": 6}))

    class Meta:
        model = Ticket
        fields = ["subject", "order"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        self.fields["order"].queryset = user.orders.all()


class ReplyForm(forms.Form):
    body = forms.CharField(label="پیام شما", max_length=5000, widget=forms.Textarea(attrs={"rows": 4}))


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "title", "body"]
        widgets = {"rating": forms.Select(choices=[(i, str(i)) for i in range(5, 0, -1)]), "body": forms.Textarea(attrs={"rows": 4})}
