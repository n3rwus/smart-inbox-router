from collections.abc import Mapping

from common.departments import Department

DEPARTMENT_DESCRIPTIONS: Mapping[Department, str] = {
    Department.PERSONNEL: (
        "personnel administration: employment contracts, annexes, leave requests, "
        "sick leave (L4, zwolnienie lekarskie), payroll and salary, employment certificates "
        "(umowa, urlop, wynagrodzenie, zaświadczenie)."
    ),
    Department.HUMAN_RESOURCES: (
        "people and development: recruitment, onboarding, training, benefits "
        "(e.g. sports card, medical care), workplace conflicts, feedback "
        "(rekrutacja, szkolenia, benefity, konflikt)."
    ),
    Department.HELP_DESK: (
        "end-user support: forgotten password, locked account, my laptop/printer/monitor "
        "does not work, email client problems (hasło, konto, drukarka, nie działa)."
    ),
    Department.IT: (
        "systems and infrastructure: access to systems and repositories, network and VPN, "
        "servers, new hardware purchase, security incidents "
        "(dostęp, VPN, serwer, zakup sprzętu, bezpieczeństwo)."
    ),
    Department.OTHER: "anything that does not clearly fit the above.",
}
