import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlencode

from app.settings import Settings


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool
    delivery: str


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verification_url(self, token: str) -> str:
        return _build_action_url(self._settings.public_app_url, "verify-email", token)

    def password_reset_url(self, token: str) -> str:
        return _build_action_url(self._settings.public_app_url, "reset-password", token)

    def send_email_verification(self, email: str, token: str) -> EmailDeliveryResult:
        url = self.verification_url(token)
        return self._send(
            to=email,
            subject="Verify your Travel Agent Cloud email",
            body=(
                "Verify your Travel Agent Cloud email address.\n\n"
                f"Open this link to verify your email:\n{url}\n\n"
                "If you did not create this account, you can ignore this email."
            ),
        )

    def send_password_reset(self, email: str, token: str) -> EmailDeliveryResult:
        url = self.password_reset_url(token)
        return self._send(
            to=email,
            subject="Reset your Travel Agent Cloud password",
            body=(
                "Reset your Travel Agent Cloud password.\n\n"
                f"Open this link to set a new password:\n{url}\n\n"
                "If you did not request this reset, you can ignore this email."
            ),
        )

    def _send(self, to: str, subject: str, body: str) -> EmailDeliveryResult:
        provider = self._settings.email_provider.strip().lower()
        if provider in {"", "mock"}:
            return EmailDeliveryResult(sent=True, delivery="mock")
        if provider != "smtp":
            return EmailDeliveryResult(sent=False, delivery="disabled")
        if not self._settings.smtp_host or not self._settings.smtp_username or not self._settings.smtp_password:
            return EmailDeliveryResult(sent=False, delivery="smtp_not_configured")

        message = EmailMessage()
        message["From"] = self._settings.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            if self._settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as smtp:
                    smtp.login(self._settings.smtp_username, self._settings.smtp_password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as smtp:
                    if self._settings.smtp_starttls:
                        smtp.starttls()
                    smtp.login(self._settings.smtp_username, self._settings.smtp_password)
                    smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            return EmailDeliveryResult(sent=False, delivery="smtp_failed")
        return EmailDeliveryResult(sent=True, delivery="smtp")


def _build_action_url(public_app_url: str, action: str, token: str) -> str:
    base_url = public_app_url.rstrip("/")
    return f"{base_url}/?{urlencode({'authAction': action, 'token': token})}"
