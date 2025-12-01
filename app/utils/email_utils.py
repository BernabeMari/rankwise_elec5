import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional, Tuple

# Set environment variables directly (remove this in production)
os.environ["SMTP_USERNAME"] = "spradax20@gmail.com"
os.environ["SMTP_PASSWORD"] = "zffv ffib yfjc wqkw"
os.environ["SMTP_FROM_NAME"] = "Rankwise"

def send_email(recipient_email: str, subject: str, body: str) -> Tuple[bool, Optional[str]]:
    # ... rest of your function remains the same
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_username or not smtp_password:
        return False, "Email credentials are not configured. Please set SMTP_USERNAME and SMTP_PASSWORD."

    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    from_name = os.environ.get("SMTP_FROM_NAME", "Rankwise Notifications")
    sender = f"{from_name} <{smtp_username}>"

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

        return True, None
    except Exception as exc:
        return False, f"Failed to send email: {exc}"

# Test
if __name__ == "__main__":
    success, error = send_email(
        recipient_email="someone@gmail.com",  # Use a real email address
        subject="Test Email",
        body="This is a test email."
    )
    print(f"Success: {success}, Error: {error}")