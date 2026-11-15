from types import MappingProxyType

from common.departments import Department

_RECIPIENTS = MappingProxyType(
    {
        Department.HUMAN_RESOURCES: "human-resources@example.com",
        Department.HELP_DESK: "help-desk@example.com",
        Department.IT: "it@example.com",
        Department.PERSONNEL: "kadry@example.com",
        Department.OTHER: "other@example.com",
    }
)


def recipient_for(department: Department) -> str:
    return _RECIPIENTS[department]
