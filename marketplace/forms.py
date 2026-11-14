from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import ActivityTag, Booking, CompanionProfile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class BookingRequestForm(forms.ModelForm):
    conduct = forms.BooleanField(
        required=True,
        label="I agree to the platonic Code of Conduct and public-place policy.",
    )

    class Meta:
        model = Booking
        fields = ("activity", "date", "start_time", "hours", "location")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "hours": forms.NumberInput(attrs={"min": 1, "max": 24}),
        }

    def __init__(self, *args, companion, **kwargs):
        super().__init__(*args, **kwargs)
        self.companion = companion
        self.fields["activity"].queryset = companion.activities.all()

    def clean(self):
        cleaned_data = super().clean()
        self.instance.companion = self.companion
        return cleaned_data

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.companion = self.companion
        if commit:
            booking.save()
        return booking


class CompanionProfileForm(forms.ModelForm):
    public_meeting_places_only = forms.BooleanField(
        required=True,
        label="I agree to meet clients in public places only and follow the platonic Code of Conduct.",
    )

    class Meta:
        model = CompanionProfile
        fields = (
            "display_name",
            "date_of_birth",
            "gender",
            "city",
            "bio",
            "hourly_rate",
            "min_hours",
            "languages",
            "activities",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "bio": forms.Textarea(attrs={"rows": 4}),
            "hourly_rate": forms.NumberInput(attrs={"min": 1}),
            "min_hours": forms.NumberInput(attrs={"min": 1, "max": 24}),
            "activities": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activities"].queryset = ActivityTag.objects.filter(is_active=True)

    def clean_date_of_birth(self):
        birth_date = self.cleaned_data["date_of_birth"]
        today = timezone.localdate()
        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
        if age < 18:
            raise forms.ValidationError("Companions must be at least 18 years old.")
        return birth_date

    def clean_activities(self):
        activities = self.cleaned_data["activities"]
        if activities.count() > 2:
            raise forms.ValidationError("The Basic plan allows up to 2 activity categories.")
        return activities