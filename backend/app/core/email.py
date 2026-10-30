import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from app.core.config import settings


def send_password_reset_email(
    to_email: str,
    token: str,
) -> None:
    if not (
        settings.SMTP_HOST
        and settings.SMTP_USER
        and settings.SMTP_PASSWORD
    ):
        raise RuntimeError("SMTP is not configured")

    reset_url = (
        f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?"
        f"{urlencode({'token': token})}"
    )

    message = EmailMessage()
    message["Subject"] = "Talaba AI - Password Reset"
    message["From"] = settings.SMTP_USER
    message["To"] = to_email

    message.set_content(
        "We received a request to reset your Talaba AI password.\n\n"
        f"Use the following link to reset your password:\n{reset_url}\n\n"
        "This link expires in 30 minutes and can only be used once.\n"
        "If you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        timeout=10,
    ) as server:
        server.starttls()
        server.login(
            settings.SMTP_USER,
            settings.SMTP_PASSWORD,
        )
        server.send_message(message)