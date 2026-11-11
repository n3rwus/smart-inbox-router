from email.message import EmailMessage

from common.departments import Department
from common.email_headers import EmailHeader
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
    email[EmailHeader.FROM] = from_address
    email[EmailHeader.TO] = recipient_for(department)
    email[EmailHeader.REPLY_TO] = sender
    email[EmailHeader.SUBJECT] = f"[smart-inbox-router] New request for {department}"
    email.set_content(message)
    return email
