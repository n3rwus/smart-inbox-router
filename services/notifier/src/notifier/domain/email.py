from email.message import EmailMessage

from common.departments import Department

from notifier.domain.recipients import recipient_for

FROM_ADDRESS = "smart-inbox-router@example.com"


def build_email(*, department: Department, sender: str, message: str) -> EmailMessage:
    email = EmailMessage()
    email["From"] = FROM_ADDRESS
    email["To"] = recipient_for(department)
    email["Reply-To"] = sender
    email["Subject"] = f"[smart-inbox-router] New request for {department}"
    email.set_content(message)
    return email
