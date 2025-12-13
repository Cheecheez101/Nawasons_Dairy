from django import forms
from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address']


class LoyaltyAdjustmentForm(forms.Form):
    points = forms.IntegerField(min_value=-1000, max_value=1000, help_text="Use negative values to deduct points")
