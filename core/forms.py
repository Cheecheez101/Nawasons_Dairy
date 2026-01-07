from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission, User

from .models import UserProfile


class UserCreateForm(UserCreationForm):
    email = forms.EmailField(required=False)
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    is_staff = forms.BooleanField(required=False, initial=False)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
        help_text="Assign the user to one or more groups",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "groups",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.order_by("name")
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                f"A user with the username '{username}' already exists. Please choose a different username."
            )
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email")
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.is_active = self.cleaned_data.get("is_active", True)
        user.is_staff = self.cleaned_data.get("is_staff", False)
        if commit:
            user.save()
            self.save_m2m()
            groups = self.cleaned_data.get("groups")
            user.groups.set(groups)
        return user


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ("name",)
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Team name"})
        }


class GroupPermissionForm(forms.Form):
    group = forms.ModelChoiceField(queryset=Group.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
        help_text="Choose which permissions belong to the group",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = Group.objects.order_by("name")
        self.fields["permissions"].queryset = Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )


class UserGroupAssignmentForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        help_text="Update the groups assigned to this user",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.order_by("username")
        self.fields["groups"].queryset = Group.objects.order_by("name")

    def save(self):
        user = self.cleaned_data["user"]
        groups = self.cleaned_data["groups"]
        user.groups.set(groups)
        return user


class UserGroupInlineForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.order_by("name")


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            else:
                widget.attrs.setdefault("class", "form-control")


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("avatar", "phone_number", "job_title", "location", "bio")
        widgets = {
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            "job_title": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    avatar = forms.ImageField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
