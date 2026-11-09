from enum import StrEnum


class Department(StrEnum):
    """Closed set of routing targets. The LLM may only choose one of these values."""

    HUMAN_RESOURCES = "human-resources"
    HELP_DESK = "help-desk"
    IT = "it"
    PERSONNEL = "kadry"
    OTHER = "other"
