from email.message import EmailMessage

from common.departments import Department
from common.email_headers import EmailHeader
from pydantic import EmailStr

from notifier.domain.recipients import recipient_for

MESSAGE_ID_DOMAIN = "notifier.smart-inbox-router"


def build_email(
    *,
    message_id: str,
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
    email[EmailHeader.MESSAGE_ID] = f"<{message_id}@{MESSAGE_ID_DOMAIN}>"
    email.set_content(message)
    return email
