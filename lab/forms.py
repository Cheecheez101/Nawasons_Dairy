from decimal import Decimal

from django import forms
from django.forms import formset_factory

from storage.models import ColdStorageInventory, StorageLocation, Packaging
from inventory.models import InventoryItem

from .models import Batch, BatchTest, LabBatchApproval, MilkYield


ACTIVE_TANK_CHOICES = [
    (tank, tank)
    for tank in MilkYield.TANK_CAPACITY_LITRES.keys()
    if tank != "Unassigned"
]


class BatchTestForm(forms.ModelForm):
    class Meta:
        model = BatchTest
        fields = [
            "fat_percentage",
            "snf_percentage",
            "acidity",
            "contaminants",
            "result",
        ]
        widgets = {
            "fat_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "snf_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "acidity": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "contaminants": forms.Textarea(attrs={"rows": 3}),
            "result": forms.Select(),
        }


class LabBatchApprovalForm(forms.ModelForm):
    shelf_life_days = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        help_text="Optional: auto-calculate expiry by adding these days.",
    )
    storage_location = forms.ModelChoiceField(
        queryset=StorageLocation.objects.none(),
        required=False,
        label="Storage location",
        help_text="Where the approved batch will be placed.",
    )
    storage_quantity = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        label="Quantity to move",
    )
    # New: allow entering packet count directly (units)
    storage_quantity_packets = forms.IntegerField(
        required=False,
        min_value=0,
        label="Quantity to move (packets)",
        help_text="Optional: enter total packets (preferred) instead of litres."
    )
    storage_status = forms.ChoiceField(
        choices=ColdStorageInventory.STATUS_CHOICES,
        required=False,
        label="Storage status",
        initial="in_storage",
    )
    storage_tank = forms.ChoiceField(
        choices=ACTIVE_TANK_CHOICES,
        required=False,
        label="Destination tank",
        help_text="Pick the certified tank that will hold the approved yields.",
    )
    audit_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Storage audit notes",
    )

    class Meta:
        model = LabBatchApproval
        fields = ["overall_result", "expiry_date", "remarks"]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, batch=None, storage_record=None, **kwargs):
        self.batch = batch
        self.storage_record = storage_record
        super().__init__(*args, **kwargs)
        self.fields["storage_location"].queryset = StorageLocation.objects.order_by("name")
        if storage_record:
            self.fields["storage_location"].initial = storage_record.location_id
            # storage_quantity historically represented litres/quantity.
            # New ColdStorageInventory stores cartons/loose_units. Try to
            # infer a sensible initial total from the storage record.
            try:
                self.fields["storage_quantity"].initial = storage_record.total_units()
            except Exception:
                # Fallback: leave initial blank when inference fails
                self.fields["storage_quantity"].initial = None
            try:
                self.fields["storage_quantity_packets"].initial = int(storage_record.total_units() or 0)
            except Exception:
                self.fields["storage_quantity_packets"].initial = None
            self.fields["storage_status"].initial = storage_record.status
            self.fields["audit_notes"].initial = storage_record.audit_notes
        elif batch:
            self.fields["storage_quantity"].initial = batch.quantity_produced
            # Pre-fill packet count if packaging can be inferred later in save
            try:
                self.fields["storage_quantity_packets"].initial = None
            except Exception:
                pass
        if batch and batch.source_tank:
            self.fields["storage_tank"].initial = batch.source_tank
        if not self.fields["storage_status"].initial:
            self.fields["storage_status"].initial = "in_storage"

    def clean(self):
        cleaned = super().clean()
        result = cleaned.get("overall_result")
        location = cleaned.get("storage_location")
        # Prefer explicit packet count when provided
        packet_count = cleaned.get("storage_quantity_packets")
        quantity = None
        if packet_count is not None:
            quantity = packet_count
        else:
            quantity = cleaned.get("storage_quantity") or (
                (self.storage_record.total_units() if self.storage_record else None)
            )
        destination_tank = cleaned.get("storage_tank")
        if result == "approved":
            if not location:
                self.add_error("storage_location", "Pick a storage location for approved batches.")
            if quantity in (None, 0):
                self.add_error("storage_quantity", "Enter the quantity moving into storage.")
            if not cleaned.get("expiry_date") and not cleaned.get("shelf_life_days"):
                self.add_error("expiry_date", "Provide an expiry date or shelf-life days.")
            if not destination_tank:
                self.add_error("storage_tank", "Assign the tank that will hold this batch.")
        if destination_tank and destination_tank not in dict(ACTIVE_TANK_CHOICES):
            self.add_error("storage_tank", "Select a valid certified tank.")
        return cleaned

    def sync_destination_tank(self):
        tank = self.cleaned_data.get("storage_tank") if hasattr(self, "cleaned_data") else None
        if not (self.batch and tank):
            return None
        if self.batch.source_tank == tank:
            return self.batch
        self.batch.source_tank = tank
        self.batch.save(update_fields=["source_tank"])
        return self.batch

    def save_storage_assignment(self, approval):
        if approval.overall_result != "approved":
            return None
        location = self.cleaned_data.get("storage_location")
        if not location:
            return None
        # We no longer store `product`/`quantity` on ColdStorageInventory. Create
        # or update a storage record with the new fields. For now we set
        # `packaging` to None (nullable) and map any provided quantity into
        # `cartons`/`loose_units` only if a Packaging rule can be inferred.
        # Prefer explicit packet count when provided, otherwise use storage_quantity
        packet_count = self.cleaned_data.get("storage_quantity_packets")
        quantity = None
        if packet_count is not None:
            try:
                quantity = int(packet_count)
            except Exception:
                quantity = None
        else:
            quantity = self.cleaned_data.get("storage_quantity")
        status = self.cleaned_data.get("storage_status") or "in_storage"
        audit_notes = self.cleaned_data.get("audit_notes") or ""
        expiry = approval.expiry_date
        if not expiry and self.batch:
            expiry = self.batch.produced_at.date()

        record = getattr(self.batch, "storage_record", None)
        if record:
            record.location = location
            record.status = status
            record.audit_notes = audit_notes
            record.expiry_date = expiry
            # If a numeric quantity was provided and the record has packaging,
            # compute cartons/loose_units. Otherwise leave cartons/loose_units as-is.
            try:
                if quantity is not None and record.packaging:
                    per_carton = record.packaging.packets_per_carton
                    total = int(quantity)
                    record.cartons = total // per_carton
                    record.loose_units = total % per_carton
            except Exception:
                pass
            record.save()
            self.storage_record = record
        else:
            # Attempt to infer a Packaging rule from the batch SKU -> InventoryItem
            inferred_packaging = None
            try:
                if self.batch and getattr(self.batch, 'sku', None):
                    inv = InventoryItem.objects.filter(sku=self.batch.sku).first()
                    if inv:
                        inferred_packaging = Packaging.objects.filter(product=inv).order_by('-pack_size_ml').first()
            except Exception:
                inferred_packaging = None

            cartons = 0
            loose_units = 0
            # If storage quantity provided, try to compute units
            if quantity is None and self.batch:
                quantity = self.batch.quantity_produced

            try:
                if quantity is not None:
                    # If the inventory item unit is litres, convert litres -> packets
                    # using packaging.pack_size_ml when possible. Otherwise assume
                    # the provided quantity is packet count.
                    if inferred_packaging and getattr(inv, 'unit', None) == 'L':
                        # convert litres to ml then to packet count
                        units = int((Decimal(str(quantity)) * Decimal('1000')) // Decimal(inferred_packaging.pack_size_ml))
                    elif inferred_packaging and float(quantity) != int(float(quantity)):
                        # quantity has fractional part — likely litres; convert
                        units = int((Decimal(str(quantity)) * Decimal('1000')) // Decimal(inferred_packaging.pack_size_ml))
                    else:
                        units = int(Decimal(str(quantity)) if quantity is not None else 0)

                    if inferred_packaging:
                        per_carton = inferred_packaging.packets_per_carton
                        cartons = units // per_carton
                        loose_units = units % per_carton
                    else:
                        # No packaging known — store as loose units
                        cartons = 0
                        loose_units = units
            except Exception:
                cartons = 0
                loose_units = 0

            record = ColdStorageInventory.objects.create(
                production_batch=self.batch,
                packaging=inferred_packaging,
                expiry_date=expiry,
                cartons=cartons,
                loose_units=loose_units,
                location=location,
                status=status,
                audit_notes=audit_notes,
            )
            self.storage_record = record

        return record


class BatchEditForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["session", "collection_date", "state"]
        widgets = {
            "collection_date": forms.DateInput(attrs={"type": "date"}),
            "session": forms.Select(),
            "state": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session"].widget.attrs.update({"class": "form-select"})
        self.fields["collection_date"].widget.attrs.update({"class": "form-control"})
        self.fields["state"].widget.attrs.update({"class": "form-select"})

    def clean_state(self):
        state = self.cleaned_data.get("state")
        if state not in Batch.State.values:
            raise forms.ValidationError("Pick a valid batch state.")
        return state


class SessionWindowForm(forms.Form):
    session_key = forms.CharField(widget=forms.HiddenInput())
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control form-control-sm"}),
        label="Start time",
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control form-control-sm"}),
        label="End time",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        if start and end and start == end:
            raise forms.ValidationError("Start and end time cannot be identical.")
        return cleaned


SessionWindowFormSet = formset_factory(SessionWindowForm, extra=0)
