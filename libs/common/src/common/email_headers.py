from enum import StrEnum


class EmailHeader(StrEnum):
    FROM = "From"
    TO = "To"
    REPLY_TO = "Reply-To"
    SUBJECT = "Subject"
