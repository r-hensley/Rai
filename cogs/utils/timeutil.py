import datetime
from typing import Union


def format_interval(interval: Union[datetime.timedelta, int, float], show_minutes=True,
                    show_seconds=False) -> str:
    """
    Display a time interval in a format like "10d 2h 5m"
    :param interval: time interval as a timedelta or as seconds
    :param show_minutes: whether to add the minutes to the string
    :param show_seconds: whether to add the seconds to the string
    :return: a string of the time interval, or "no more time" if there was nothing to display
    """
    if isinstance(interval, (int, float)):
        interval = datetime.timedelta(seconds=interval)

    total_seconds = int(interval.total_seconds())
    sign = ''
    if total_seconds < 0:
        sign = '-'
        total_seconds = -total_seconds

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    components = []
    if days:
        components.append(f"{days}d")
    if hours:
        components.append(f"{hours}h")
    if minutes and show_minutes:
        components.append(f"{minutes}m")
    if seconds and show_seconds:
        components.append(f"{seconds}s")

    if components:
        return " ".join(f"{sign}{component}" for component in components)
    else:
        if show_seconds:
            unit = 's'
        elif show_minutes:
            unit = 'm'
        else:
            unit = 'h'
        return f"0{unit}"
