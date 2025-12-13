from django import forms
from .models import RawMilkTest, TankBatchTest, LabBatchApproval
from production.models import MilkYield


class RawMilkTestForm(forms.ModelForm):
    # allow lab tech to choose which tank to assign when approving
    storage_tank = forms.ChoiceField(choices=[(k, k) for k in MilkYield.TANK_CAPACITY_LITRES.keys()], required=False)

    class Meta:
        model = RawMilkTest
        fields = ["milk_yield", "result", "storage_tank"]  # notes, tested_by set in view

    def clean(self):
        cleaned = super().clean()
        result = cleaned.get('result')
        tank = cleaned.get('storage_tank')
        if result == 'approved' and not tank:
            raise forms.ValidationError('Select a storage tank when approving raw milk.')
        return cleaned


class TankBatchTestForm(forms.ModelForm):
    class Meta:
        model = TankBatchTest
        fields = ["milk_yield", "result", "notes"]  # tested_by set in view


class LabBatchApprovalForm(forms.ModelForm):
    shelf_life_days = forms.IntegerField(
        min_value=1,
        initial=7,
        required=False,
        help_text="Optional: override default shelf life (days)"
    )

    class Meta:
        model = LabBatchApproval
        fields = ["production_batch", "overall_result", "expiry_date", "remarks"]

    def clean(self):
        cleaned = super().clean()
        result = cleaned.get("overall_result")
        expiry = cleaned.get("expiry_date")
        if result == "approved" and not expiry and not cleaned.get("shelf_life_days"):
            raise forms.ValidationError(
                "Provide expiry date or shelf life days for approved batches."
            )
        return cleaned
