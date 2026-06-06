import re
from datetime import timedelta

_DURATION_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(sec|secs|second|seconds|s|"
    r"min|mins|minute|minutes|m|"
    r"h|hr|hour|hours|"
    r"d|day|days|"
    r"w|week|weeks)?$",
    re.IGNORECASE,
)

_UNIT_TO_SECONDS: dict[str, float] = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}

MAX_DURATION = timedelta(days=365)
MIN_DURATION = timedelta(seconds=1)


class DurationParseError(ValueError):
    pass


def parse_duration(text: str) -> timedelta:
    """Парсит: 30, 30d, 5h, 4sec, 15min, 2w."""
    raw = (text or "").strip().lower().replace(" ", "")
    if not raw:
        raise DurationParseError("Укажите период, например: 30d, 5h, 4sec")

    if raw.isdigit():
        return _clamp(timedelta(days=int(raw)))

    match = _DURATION_RE.match(raw)
    if not match:
        raise DurationParseError(
            "Формат: число + единица (sec/s, min/m, h, d, w). Примеры: 4sec, 5h, 30d"
        )

    value = float(match.group(1))
    unit = (match.group(2) or "d").lower()
    seconds = value * _UNIT_TO_SECONDS[unit]
    return _clamp(timedelta(seconds=seconds))


def _clamp(delta: timedelta) -> timedelta:
    if delta < MIN_DURATION:
        raise DurationParseError("Минимальный период — 1 секунда")
    if delta > MAX_DURATION:
        raise DurationParseError("Максимальный период — 365 дней")
    return delta


def format_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total < 60:
        return f"{total} сек."
    if total < 3600:
        return f"{total // 60} мин."
    if total < 86400:
        hours = total // 3600
        mins = (total % 3600) // 60
        return f"{hours} ч." + (f" {mins} мин." if mins else "")
    days = total // 86400
    hours = (total % 86400) // 3600
    return f"{days} дн." + (f" {hours} ч." if hours else "")
