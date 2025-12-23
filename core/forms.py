from django import forms

from .models import Config


class RecipeKeywordsForm(forms.Form):
    keywords = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}), required=False
    )


class ConfigForm(forms.ModelForm):
    api_key = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "off"}, render_value=True
        ),
        required=False,
        label="API Key",
    )

    class Meta:
        model = Config
        fields = [
            "ai_provider",
            "api_key",
            "extraction_rate_limit_per_minute",
        ]
        widgets = {
            "ai_provider": forms.Select(attrs={"class": "form-select"}),
            "extraction_rate_limit_per_minute": forms.NumberInput(attrs={"class": "form-control"}),
        }
        labels = {
            "ai_provider": "AI Provider",
            "extraction_rate_limit_per_minute": "Extraction Rate Limit (per minute)",
        }
