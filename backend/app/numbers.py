"""Русские числа для серверного текста — инсайтов, сообщений, выгрузок.

В интерфейсе числа форматирует клиент, но текст резюме собирается здесь, и
подставлять в него «1234567.0» нельзя. Неразрывные пробелы обязательны:
«3 377 млн ₽» не должно переноситься по словам.
"""

NBSP = " "


def money(value: float) -> str:
    if abs(value) >= 1e9:
        return f"{_decimal(value / 1e9, 2)}{NBSP}млрд{NBSP}₽"
    if abs(value) >= 1e6:
        return f"{_decimal(value / 1e6, 1)}{NBSP}млн{NBSP}₽"
    return f"{grouped(round(value))}{NBSP}₽"


def percent(value: float, digits: int = 1) -> str:
    return f"{_decimal(value, digits)}%"


def signed_percent(value: float, digits: int = 1) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{_decimal(abs(value), digits)}%"


def signed_money(value: float) -> str:
    return ("+" if value >= 0 else "−") + money(abs(value))


def grouped(value: float) -> str:
    return f"{int(value):,}".replace(",", NBSP)


def _decimal(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}".replace(",", NBSP).replace(".", ",")


MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
ROMAN = ["I", "II", "III", "IV"]


def period_label(value, grain: str) -> str:
    """Дата из базы приходит первым днём периода — показываем сам период."""
    if value is None:
        return "—"
    if grain == "year":
        return str(value.year)
    if grain == "quarter":
        return f"{ROMAN[(value.month - 1) // 3]}{NBSP}кв.{NBSP}{value.year}"
    return f"{MONTHS[value.month - 1]}{NBSP}{value.year}"


def period_genitive(value, grain: str) -> str:
    """Для оборотов «против августа 2026». Именительный там звучит дико."""
    if value is None:
        return "—"
    if grain == "year":
        return str(value.year)
    if grain == "quarter":
        return f"{ROMAN[(value.month - 1) // 3]}{NBSP}кв.{NBSP}{value.year}"
    return f"{MONTHS_GENITIVE[value.month - 1]}{NBSP}{value.year}"


def range_label(start, end) -> str:
    """Именительный падеж: подпись живёт и в заголовке («План-факт, октябрь
    2025 — сентябрь 2026»), и после предлога («За октябрь 2025 — …»).
    Родительный читался бы верно только во втором случае.
    """
    if start is None or end is None:
        return "весь период"
    if (start.year, start.month) == (end.year, end.month):
        return f"{MONTHS[start.month - 1]}{NBSP}{start.year}"
    if start.year == end.year:
        return f"{MONTHS[start.month - 1]} — {MONTHS[end.month - 1]}{NBSP}{start.year}"
    return (
        f"{MONTHS[start.month - 1]}{NBSP}{start.year} — "
        f"{MONTHS[end.month - 1]}{NBSP}{end.year}"
    )
