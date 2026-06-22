from __future__ import annotations

from django import forms

from apps.accounts.models import TelegramAccount
from apps.developers.models import Developer
from apps.messaging.models import AutoReplyRule, ScheduledMessage
from apps.scraping.models import ScrapeSource


class JSONListField(forms.CharField):
    """Textarea where each non-empty line becomes a list item."""

    widget = forms.Textarea(attrs={"rows": 4})

    def to_python(self, value):
        if not value:
            return []
        return [line.strip() for line in value.splitlines() if line.strip()]

    def prepare_value(self, value):
        if isinstance(value, list):
            return "\n".join(str(v) for v in value)
        return value


class AccountForm(forms.ModelForm):
    class Meta:
        model = TelegramAccount
        fields = [
            "label", "phone", "api_id", "api_hash",
            "owner", "is_private", "presence", "is_enabled",
        ]
        widgets = {"api_hash": forms.TextInput(attrs={"autocomplete": "off"})}


class ConnectStartForm(forms.Form):
    METHOD_CHOICES = [("phone", "Phone + code"), ("qr", "QR code")]
    label = forms.CharField(max_length=120)
    method = forms.ChoiceField(choices=METHOD_CHOICES)
    phone = forms.CharField(max_length=32, required=False)
    api_id = forms.IntegerField(required=False)
    api_hash = forms.CharField(max_length=64, required=False)
    owner = forms.ModelChoiceField(
        queryset=Developer.objects.all(), required=False
    )
    is_private = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("method") == "phone" and not cleaned.get("phone"):
            self.add_error("phone", "Phone is required for phone login.")
        return cleaned


class CodeForm(forms.Form):
    code = forms.CharField(max_length=12, label="Login code")


class PasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="2FA password")


class ScheduledMessageForm(forms.ModelForm):
    targets = JSONListField(
        help_text="One target per line (username, @handle, t.me link or numeric id)."
    )

    class Meta:
        model = ScheduledMessage
        fields = [
            "title", "text", "file_path", "from_mode", "account",
            "targets", "scheduled_for", "silent", "repeat_cron", "owner",
        ]
        widgets = {
            "scheduled_for": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "text": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scheduled_for"].input_formats = ["%Y-%m-%dT%H:%M"]


class AutoReplyForm(forms.ModelForm):
    keywords = JSONListField(
        required=False,
        help_text="Optional keyword triggers, one per line. Empty = any message.",
    )

    class Meta:
        model = AutoReplyRule
        fields = [
            "name", "mode", "account", "apply_to_all", "keywords",
            "reply_text", "only_private_chats", "cooldown_minutes",
            "is_active", "owner",
        ]
        widgets = {"reply_text": forms.Textarea(attrs={"rows": 3})}


class ScrapeSourceForm(forms.ModelForm):
    keywords = JSONListField(
        required=False, help_text="Keywords, one per line. Empty = capture everything."
    )
    forward_targets = JSONListField(
        required=False, help_text="Forward destinations, one per line."
    )

    class Meta:
        model = ScrapeSource
        fields = [
            "name", "source", "account", "keywords", "match_mode",
            "forward_targets", "auto_forward", "forward_account",
            "extra_caption", "poll_interval_minutes", "is_active", "owner",
        ]


class CreateChannelForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=TelegramAccount.objects.filter(status="active")
    )
    title = forms.CharField(max_length=128)
    about = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    kind = forms.ChoiceField(
        choices=[("channel", "Broadcast channel"), ("group", "Supergroup")]
    )


class KeyRequestReviewForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class UnlockForm(forms.Form):
    """Enter the developer API key to decrypt private message content."""

    api_key = forms.CharField(label="Developer API key")
