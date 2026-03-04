from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Building, WatchedLocation


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'password1', 'password2']


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['watched_buildings', 'alert_crime_types']
        widgets = {
            'watched_buildings': forms.CheckboxSelectMultiple(),
        }


class WatchedLocationForm(forms.Form):
    location_query = forms.CharField(
        label='Building name or address',
        max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. PCL Library or 2100 Speedway Ave'}),
    )
    radius_miles = forms.ChoiceField(
        label='Alert radius',
        choices=WatchedLocation.RADIUS_CHOICES,
    )