import datetime
import itertools

from cogs.utils.helper_functions import format_interval


def test_format_interval_zero():
    assert format_interval(0) == '0m'
    assert format_interval(0, show_minutes=False) == '0h'
    assert format_interval(0, show_seconds=True) == '0s'


def test_format_interval_timedelta():
    base_time = datetime.datetime(2000, 1, 1, 12, 0, 0)

    one_day_later = datetime.datetime(2000, 1, 2, 12, 0, 0)
    for show_seconds, show_minutes in itertools.product([True, False], repeat=2):
        assert format_interval(one_day_later - base_time, show_minutes=show_minutes,
                               show_seconds=show_seconds) == '1d'

    one_hour_later = datetime.datetime(2000, 1, 1, 13, 0, 0)
    assert format_interval(one_hour_later - base_time) == '1h'

    one_minute_later = datetime.datetime(2000, 1, 1, 12, 1, 0)
    assert format_interval(one_minute_later - base_time) == '1m'
    assert format_interval(one_minute_later - base_time, show_minutes=False) == '0h'
    assert format_interval(one_minute_later - base_time, show_seconds=True) == '1m'

    not_quite_one_day_later = datetime.datetime(2000, 1, 2, 11, 59, 59, 999_999)
    assert format_interval(not_quite_one_day_later - base_time) == '23h 59m'
    assert format_interval(not_quite_one_day_later - base_time, show_minutes=False) == '23h'
    assert format_interval(not_quite_one_day_later - base_time, show_seconds=True) == '23h 59m 59s'

    not_quite_one_hour_later = datetime.datetime(2000, 1, 1, 12, 59, 59, 999_999)
    assert format_interval(not_quite_one_hour_later - base_time) == '59m'
    assert format_interval(not_quite_one_hour_later - base_time, show_minutes=False) == '0h'
    assert format_interval(not_quite_one_hour_later - base_time, show_seconds=True) == '59m 59s'

    not_quite_one_minute_later = datetime.datetime(2000, 1, 1, 12, 0, 59, 999_999)
    assert format_interval(not_quite_one_minute_later - base_time) == '0m'
    assert format_interval(not_quite_one_minute_later - base_time, show_minutes=False) == '0h'
    assert format_interval(not_quite_one_minute_later - base_time, show_seconds=True) == '59s'


def test_format_interval_years():
    # Years aren't supported, and shouldn't be, because they require knowledge of leap years
    # (same goes for months)
    assert format_interval(60 * 60 * 24 * 366) == '366d'


def test_format_interval_negative():
    base_time = datetime.datetime(2000, 1, 1, 12, 0, 0)

    one_day_later = datetime.datetime(2000, 1, 2, 12, 0, 0)
    assert format_interval(base_time - one_day_later) == '-1d'

    not_quite_one_minute_later = datetime.datetime(2000, 1, 1, 12, 0, 59, 999_999)
    assert format_interval(base_time - not_quite_one_minute_later) == '0m'
    assert format_interval(base_time - not_quite_one_minute_later, show_seconds=True) == '-59s'

    not_quite_one_hour_later = datetime.datetime(2000, 1, 1, 12, 59, 59, 999_999)
    assert format_interval(base_time - not_quite_one_hour_later) == '-59m'
    assert format_interval(base_time - not_quite_one_hour_later, show_minutes=False) == '0h'
    assert format_interval(base_time - not_quite_one_hour_later, show_seconds=True) == '-59m -59s'


def test_format_interval_float():
    assert format_interval(3661.123, show_seconds=True) == '1h 1m 1s'


def test_format_interval_gap():
    assert format_interval(datetime.timedelta(days=1, minutes=1)) == '1d 1m'
    assert format_interval(datetime.timedelta(hours=1, seconds=1), show_seconds=True) == '1h 1s'
