from email.message import EmailMessage

from common.departments import Department
from pydantic import EmailStr

from notifier.domain.recipients import recipient_for


def build_email(
    *,
    department: Department,
    sender: EmailStr,
    message: str,
    from_address: EmailStr,
) -> EmailMessage:
    email = EmailMessage()
    email["From"] = from_address
    email["To"] = recipient_for(department)
    email["Reply-To"] = sender
    email["Subject"] = f"[smart-inbox-router] New request for {department}"
    email.set_content(message)
    return email
