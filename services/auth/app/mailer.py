import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode


@dataclass(frozen=True)
class MailerSettings:
    email_provider: str
    email_from: str
    public_app_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_ssl: bool
    smtp_starttls: bool


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool
    delivery: str


class Mailer:
    def __init__(self, settings: MailerSettings) -> None:
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
            html_body=_action_email_html(
                title="Verify your Travel Agent Cloud email",
                intro="Verify your Travel Agent Cloud email address.",
                button_text="Verify email",
                url=url,
                footer="If you did not create this account, you can ignore this email.",
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
            html_body=_action_email_html(
                title="Reset your Travel Agent Cloud password",
                intro="Reset your Travel Agent Cloud password.",
                button_text="Set new password",
                url=url,
                footer="If you did not request this reset, you can ignore this email.",
            ),
        )

    def _send(self, to: str, subject: str, body: str, html_body: str | None = None) -> EmailDeliveryResult:
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
        if html_body:
            message.add_alternative(html_body, subtype="html")

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
    return f"{public_app_url.rstrip('/')}?{urlencode({'authAction': action, 'token': token})}"


def _action_email_html(title: str, intro: str, button_text: str, url: str, footer: str) -> str:
    safe_title = escape(title)
    safe_intro = escape(intro)
    safe_button_text = escape(button_text)
    safe_url = escape(url, quote=True)
    safe_footer = escape(footer)
    return f"""<!doctype html>
<html>
  <body style="margin:0;background:#f8fafc;font-family:Arial,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8fafc;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:28px;">
            <tr>
              <td>
                <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;color:#0f172a;">{safe_title}</h1>
                <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#334155;">{safe_intro}</p>
                <a href="{safe_url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;border-radius:6px;padding:12px 18px;">{safe_button_text}</a>
                <p style="margin:24px 0 0;font-size:13px;line-height:1.6;color:#64748b;">{safe_footer}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
