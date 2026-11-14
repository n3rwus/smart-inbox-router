from collections.abc import Mapping

from common.departments import Department

DEPARTMENT_DESCRIPTIONS: Mapping[Department, str] = {
    Department.PERSONNEL: (
        "employment paperwork and administration: leave and vacation, sick leave, "
        "pay and payslip, contracts and annexes, employment certificates; "
        "PL: urlop, L4, wynagrodzenie, umowa, zaświadczenie."
    ),
    Department.HUMAN_RESOURCES: (
        "people and development: recruitment and referrals, onboarding, training, "
        "benefits, workplace conflicts and feedback; "
        "PL: rekrutacja, szkolenie, benefit, konflikt."
    ),
    Department.HELP_DESK: (
        "end-user support when one person has a problem with their own device, "
        "account or password: laptop, monitor, printer, mail client, forgotten "
        "password, locked account; PL: hasło, konto, drukarka, nie działa."
    ),
    Department.IT: (
        "systems, infrastructure and access rights: accounts and repository "
        "access, network and VPN, servers, hardware purchases, security "
        "incidents; PL: dostęp, VPN, serwer, zakup sprzętu, bezpieczeństwo."
    ),
    Department.OTHER: "anything that does not clearly fit the above.",
}
