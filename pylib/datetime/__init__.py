"""rupy's `datetime`: CPython's `timedelta`, `date`, `time` and `datetime`
(naive: no tzinfo), written in rupy after CPython's `_pydatetime.py` and
`_datetime` C module.

`datetime` is not a subclass of `date` here (`isinstance(dt, date)` is
False), `strftime` and `strptime` know the C locale's directives, and
`timedelta`'s arguments are floats (ints convert exactly up to 2**53)."""

import math
from time import strftime as _now_strftime, time as _now_time
from dataclasses import dataclass

MINYEAR = 1
MAXYEAR = 9999
_MAXORDINAL = 3652059

_DAYS_IN_MONTH = "_31_28_31_30_31_30_31_31_30_31_30_31"
_MONTHNAMES = "JanFebMarAprMayJunJulAugSepOctNovDec"
_DAYNAMES = "MonTueWedThuFriSatSun"


def _month_name(m: int) -> str:
    return _MONTHNAMES[3 * (m - 1) : 3 * m]


def _day_name(wd: int) -> str:
    """wd: 0 is Monday."""
    return _DAYNAMES[3 * wd : 3 * wd + 3]


def _full_month(m: int) -> str:
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return names[m - 1]


def _full_day(wd: int) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[wd]


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_before_year(year: int) -> int:
    y = year - 1
    return y * 365 + y // 4 - y // 100 + y // 400


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return int(_DAYS_IN_MONTH[3 * month - 2 : 3 * month])


def _days_before_month(year: int, month: int) -> int:
    n = 0
    for m in range(1, month):
        n += _days_in_month(year, m)
    return n


def _ymd2ord(year: int, month: int, day: int) -> int:
    return _days_before_year(year) + _days_before_month(year, month) + day


def _ord2ymd(n: int) -> tuple[int, int, int]:
    n -= 1
    n400, n = divmod(n, 146097)
    year = n400 * 400 + 1
    n100, n = divmod(n, 36524)
    n4, n = divmod(n, 1461)
    n1, n = divmod(n, 365)
    year += n100 * 100 + n4 * 4 + n1
    if n1 == 4 or n100 == 4:
        return year - 1, 12, 31
    month = 1
    while n >= _days_in_month(year, month):
        n -= _days_in_month(year, month)
        month += 1
    return year, month, n + 1


def _isoweek1monday(year: int) -> int:
    firstday = _ymd2ord(year, 1, 1)
    firstweekday = (firstday + 6) % 7
    week1monday = firstday - firstweekday
    if firstweekday > 3:
        week1monday += 7
    return week1monday


def _check_date(year: int, month: int, day: int) -> None:
    if not MINYEAR <= year <= MAXYEAR:
        raise ValueError("year must be in 1..9999, not " + str(year))
    if not 1 <= month <= 12:
        raise ValueError("month must be in 1..12, not " + str(month))
    dim = _days_in_month(year, month)
    if not 1 <= day <= dim:
        raise ValueError("day " + str(day) + " must be in range 1.." + str(dim) + " for month " + str(month) + " in year " + str(year))


def _check_time(hour: int, minute: int, second: int, microsecond: int) -> None:
    if not 0 <= hour <= 23:
        raise ValueError("hour must be in 0..23, not " + str(hour))
    if not 0 <= minute <= 59:
        raise ValueError("minute must be in 0..59, not " + str(minute))
    if not 0 <= second <= 59:
        raise ValueError("second must be in 0..59, not " + str(second))
    if not 0 <= microsecond <= 999999:
        raise ValueError("microsecond must be in 0..999999, not " + str(microsecond))


def _pad(n: int, width: int) -> str:
    s = str(abs(n))
    while len(s) < width:
        s = "0" + s
    return "-" + s if n < 0 else s


def _format_time(hh: int, mm: int, ss: int, us: int, timespec: str) -> str:
    if timespec == "auto":
        timespec = "microseconds" if us != 0 else "seconds"
    if timespec == "hours":
        return _pad(hh, 2)
    if timespec == "minutes":
        return _pad(hh, 2) + ":" + _pad(mm, 2)
    if timespec == "seconds":
        return _pad(hh, 2) + ":" + _pad(mm, 2) + ":" + _pad(ss, 2)
    if timespec == "milliseconds":
        return _pad(hh, 2) + ":" + _pad(mm, 2) + ":" + _pad(ss, 2) + "." + _pad(us // 1000, 3)
    if timespec == "microseconds":
        return _pad(hh, 2) + ":" + _pad(mm, 2) + ":" + _pad(ss, 2) + "." + _pad(us, 6)
    raise ValueError("Unknown timespec value")


def _c_round(x: float) -> float:
    """C's round(): halves away from zero."""
    t = float(math.trunc(x))
    if abs(x - t) >= 0.5:
        t += math.copysign(1.0, x)
    return t


# ------------------------------------------------------------------ timedelta


class timedelta:
    def __init__(
        self,
        days: float = 0.0,
        seconds: float = 0.0,
        microseconds: float = 0.0,
        milliseconds: float = 0.0,
        minutes: float = 0.0,
        hours: float = 0.0,
        weeks: float = 0.0,
    ) -> None:
        # CPython's delta_new: the integral parts exactly, the fractions as
        # microseconds left over, rounded once (halves to even)
        d = 0
        s = 0
        us = 0
        left = 0.0
        parts = [(microseconds, 0, 0, 1), (milliseconds, 0, 0, 1000), (seconds, 0, 1, 0), (minutes, 0, 60, 0), (hours, 0, 3600, 0), (days, 1, 0, 0), (weeks, 7, 0, 0)]
        factors = [1.0, 1000.0, 1e6, 6e7, 3.6e9, 8.64e10, 6.048e11]
        for k in range(7):
            num, fd, fs, fus = parts[k]
            if num == 0.0:
                continue
            whole = math.trunc(num)
            d += whole * fd
            s += whole * fs
            us += whole * fus
            frac = num - float(whole)
            if frac != 0.0:
                x = factors[k] * frac
                w = math.trunc(x)
                us += w
                left += x - float(w)
        if left != 0.0:
            whole_us = _c_round(left)
            if abs(whole_us - left) == 0.5:
                odd = float(us % 2)
                whole_us = 2.0 * _c_round((left + odd) * 0.5) - odd
            us += int(whole_us)
        q, us = divmod(us, 1000000)
        s += q
        q, s = divmod(s, 86400)
        d += q
        if abs(d) > 999999999:
            raise OverflowError("days=" + str(d) + "; must have magnitude <= 999999999")
        self._days: int = d
        self._seconds: int = s
        self._microseconds: int = us

    @property
    def days(self) -> int:
        return self._days

    @property
    def seconds(self) -> int:
        return self._seconds

    @property
    def microseconds(self) -> int:
        return self._microseconds

    def total_seconds(self) -> float:
        return _total(self._days, self._seconds, self._microseconds)

    def __repr__(self) -> str:
        args: list[str] = []
        if self._days != 0:
            args.append("days=" + str(self._days))
        if self._seconds != 0:
            args.append("seconds=" + str(self._seconds))
        if self._microseconds != 0:
            args.append("microseconds=" + str(self._microseconds))
        if len(args) == 0:
            args.append("0")
        return "datetime.timedelta(" + ", ".join(args) + ")"

    def __str__(self) -> str:
        mm, ss = divmod(self._seconds, 60)
        hh, mm = divmod(mm, 60)
        s = str(hh) + ":" + _pad(mm, 2) + ":" + _pad(ss, 2)
        if self._days != 0:
            s = str(self._days) + (" days, " if abs(self._days) != 1 else " day, ") + s
        if self._microseconds != 0:
            s = s + "." + _pad(self._microseconds, 6)
        return s

    def _us(self) -> int:
        return (self._days * 86400 + self._seconds) * 1000000 + self._microseconds

    def __add__(self, other: timedelta) -> timedelta:
        return _delta(self._days + other._days, self._seconds + other._seconds, self._microseconds + other._microseconds)

    def __sub__(self, other: timedelta) -> timedelta:
        return _delta(self._days - other._days, self._seconds - other._seconds, self._microseconds - other._microseconds)

    def __neg__(self) -> timedelta:
        return _delta(-self._days, -self._seconds, -self._microseconds)

    def __pos__(self) -> timedelta:
        return _delta(self._days, self._seconds, self._microseconds)

    def __abs__(self) -> timedelta:
        if self._days < 0:
            return -self
        return _delta(self._days, self._seconds, self._microseconds)

    def __mul__(self, other: int | float) -> timedelta:
        if isinstance(other, int):
            return _delta(self._days * other, self._seconds * other, self._microseconds * other)
        else:
            a, b = _float_ratio(other)
            return _delta(0, 0, _divide_and_round(self._us() * a, b))

    def __rmul__(self, other: int | float) -> timedelta:
        if isinstance(other, int):
            return _delta(self._days * other, self._seconds * other, self._microseconds * other)
        else:
            a, b = _float_ratio(other)
            return _delta(0, 0, _divide_and_round(self._us() * a, b))

    def __floordiv__(self, other: timedelta | int) -> int | timedelta:
        if isinstance(other, int):
            return _delta(0, 0, self._us() // other)
        else:
            return self._us() // other._us()

    def __truediv__(self, other: timedelta | int | float) -> float | timedelta | timedelta:
        if isinstance(other, int):
            return _delta(0, 0, _divide_and_round(self._us(), other))
        elif isinstance(other, float):
            a, b = _float_ratio(other)
            return _delta(0, 0, _divide_and_round(b * self._us(), a))
        else:
            return self._us() / other._us()

    def __mod__(self, other: timedelta) -> timedelta:
        return _delta(0, 0, self._us() % other._us())

    def __eq__(self, other: timedelta) -> bool:
        return self._days == other._days and self._seconds == other._seconds and self._microseconds == other._microseconds

    def __ne__(self, other: timedelta) -> bool:
        return not self == other

    def __lt__(self, other: timedelta) -> bool:
        return (self._days, self._seconds, self._microseconds) < (other._days, other._seconds, other._microseconds)

    def __le__(self, other: timedelta) -> bool:
        return (self._days, self._seconds, self._microseconds) <= (other._days, other._seconds, other._microseconds)

    def __gt__(self, other: timedelta) -> bool:
        return (self._days, self._seconds, self._microseconds) > (other._days, other._seconds, other._microseconds)

    def __ge__(self, other: timedelta) -> bool:
        return (self._days, self._seconds, self._microseconds) >= (other._days, other._seconds, other._microseconds)

    def __bool__(self) -> bool:
        return self._days != 0 or self._seconds != 0 or self._microseconds != 0


def _total(d: int, s: int, us: int) -> float:
    return ((d * 86400 + s) * 1000000 + us) / 1000000


def _delta(d: int, s: int, us: int) -> timedelta:
    """A timedelta of ints, normalized."""
    q, us = divmod(us, 1000000)
    s += q
    q, s = divmod(s, 86400)
    d += q
    if abs(d) > 999999999:
        raise OverflowError("days=" + str(d) + "; must have magnitude <= 999999999")
    t = timedelta()
    t._days = d
    t._seconds = s
    t._microseconds = us
    return t


def _float_ratio(x: float) -> tuple[int, int]:
    if math.isinf(x):
        raise OverflowError("cannot convert Infinity to integer ratio")
    if math.isnan(x):
        raise ValueError("cannot convert NaN to integer ratio")
    m = x
    d = 1
    while m % 1.0 != 0.0:
        m *= 2.0
        d *= 2
    return int(m), d


def _divide_and_round(a: int, b: int) -> int:
    q, r = divmod(a, b)
    r *= 2
    greater_than_half = r > b if b > 0 else r < b
    if greater_than_half or r == b and q % 2 == 1:
        q += 1
    return q


# ----------------------------------------------------------------------- date


@dataclass(frozen=True)
class IsoCalendarDate:
    year: int
    week: int
    weekday: int

    def __repr__(self) -> str:
        return "datetime.IsoCalendarDate(year=" + str(self.year) + ", week=" + str(self.week) + ", weekday=" + str(self.weekday) + ")"


class date:
    def __init__(self, year: int, month: int, day: int) -> None:
        _check_date(year, month, day)
        self._year: int = year
        self._month: int = month
        self._day: int = day

    @staticmethod
    def today() -> date:
        y, m, d, _, _, _, _ = _now()
        return date(y, m, d)

    @staticmethod
    def fromordinal(n: int) -> date:
        if n < 1:
            raise ValueError("ordinal must be >= 1")
        if n > _MAXORDINAL:
            raise ValueError("year 10000 is out of range")
        y, m, d = _ord2ymd(n)
        return date(y, m, d)

    @staticmethod
    def fromisoformat(date_string: str) -> date:
        n = len(date_string)
        if not date_string.isascii() or not (n == 7 or n == 8 or n == 10):
            raise ValueError("Invalid isoformat string: " + repr(date_string))
        y, m, d = _parse_isoformat_date(date_string, date_string)
        return date(y, m, d)

    @staticmethod
    def fromisocalendar(year: int, week: int, day: int) -> date:
        y, m, d = _isoweek_to_gregorian(year, week, day)
        return date(y, m, d)

    @staticmethod
    def strptime(date_string: str, format: str) -> date:
        y, m, d, _, _, _, _ = _strptime(date_string, format)
        return date(y, m, d)

    @property
    def year(self) -> int:
        return self._year

    @property
    def month(self) -> int:
        return self._month

    @property
    def day(self) -> int:
        return self._day

    def __repr__(self) -> str:
        return "datetime.date(" + str(self._year) + ", " + str(self._month) + ", " + str(self._day) + ")"

    def isoformat(self) -> str:
        return _pad(self._year, 4) + "-" + _pad(self._month, 2) + "-" + _pad(self._day, 2)

    def __str__(self) -> str:
        return self.isoformat()

    def ctime(self) -> str:
        wd = (self.toordinal() + 6) % 7
        return _day_name(wd) + " " + _month_name(self._month) + " " + _spad(self._day) + " 00:00:00 " + _pad(self._year, 4)

    def strftime(self, format: str) -> str:
        return _strftime(format, self._year, self._month, self._day, 0, 0, 0, 0)

    def toordinal(self) -> int:
        return _ymd2ord(self._year, self._month, self._day)

    def weekday(self) -> int:
        return (self.toordinal() + 6) % 7

    def isoweekday(self) -> int:
        return (self.toordinal() + 6) % 7 + 1

    def isocalendar(self) -> IsoCalendarDate:
        y, w, d = _isocalendar(self._year, self._month, self._day)
        return IsoCalendarDate(y, w, d)

    def replace(self, year: int | None = None, month: int | None = None, day: int | None = None) -> date:
        return date(self._year if year is None else year, self._month if month is None else month, self._day if day is None else day)

    def __add__(self, other: timedelta) -> date:
        o = self.toordinal() + other.days
        if 0 < o <= _MAXORDINAL:
            return date.fromordinal(o)
        raise OverflowError("date value out of range")

    def __radd__(self, other: timedelta) -> date:
        return self + other

    def __sub__(self, other: date | timedelta) -> timedelta | date:
        if isinstance(other, timedelta):
            return self + _delta(-other.days, 0, 0)
        else:
            return _delta(self.toordinal() - other.toordinal(), 0, 0)

    def __eq__(self, other: date) -> bool:
        return self._year == other._year and self._month == other._month and self._day == other._day

    def __ne__(self, other: date) -> bool:
        return not self == other

    def __lt__(self, other: date) -> bool:
        return (self._year, self._month, self._day) < (other._year, other._month, other._day)

    def __le__(self, other: date) -> bool:
        return (self._year, self._month, self._day) <= (other._year, other._month, other._day)

    def __gt__(self, other: date) -> bool:
        return (self._year, self._month, self._day) > (other._year, other._month, other._day)

    def __ge__(self, other: date) -> bool:
        return (self._year, self._month, self._day) >= (other._year, other._month, other._day)


def _isocalendar(year: int, month: int, day: int) -> tuple[int, int, int]:
    week1monday = _isoweek1monday(year)
    today = _ymd2ord(year, month, day)
    week, d = divmod(today - week1monday, 7)
    if week < 0:
        year -= 1
        week1monday = _isoweek1monday(year)
        week, d = divmod(today - week1monday, 7)
    elif week >= 52:
        if today >= _isoweek1monday(year + 1):
            year += 1
            week = 0
    return year, week + 1, d + 1


def _isoweek_to_gregorian(year: int, week: int, day: int) -> tuple[int, int, int]:
    if not MINYEAR <= year <= MAXYEAR:
        raise ValueError("year must be in 1..9999, not " + str(year))
    if not 0 < week < 53:
        out_of_range = True
        if week == 53:
            first_weekday = _ymd2ord(year, 1, 1) % 7
            if first_weekday == 4 or (first_weekday == 3 and _is_leap(year)):
                out_of_range = False
        if out_of_range:
            raise ValueError("Invalid week: " + str(week))
    if not 0 < day < 8:
        raise ValueError("Invalid weekday: " + str(day) + " (range is [1, 7])")
    return _ord2ymd(_isoweek1monday(year) + (week - 1) * 7 + (day - 1))


# ----------------------------------------------------------------------- time


class time:
    def __init__(self, hour: int = 0, minute: int = 0, second: int = 0, microsecond: int = 0) -> None:
        _check_time(hour, minute, second, microsecond)
        self._hour: int = hour
        self._minute: int = minute
        self._second: int = second
        self._microsecond: int = microsecond

    @staticmethod
    def fromisoformat(time_string: str) -> time:
        s = time_string[1:] if time_string.startswith("T") else time_string
        hh, mm, ss, us = _parse_isoformat_time(s, time_string)
        return time(hh, mm, ss, us)

    @property
    def hour(self) -> int:
        return self._hour

    @property
    def minute(self) -> int:
        return self._minute

    @property
    def second(self) -> int:
        return self._second

    @property
    def microsecond(self) -> int:
        return self._microsecond

    def isoformat(self, timespec: str = "auto") -> str:
        return _format_time(self._hour, self._minute, self._second, self._microsecond, timespec)

    def __str__(self) -> str:
        return self.isoformat()

    def __repr__(self) -> str:
        return "datetime.time(" + _fields_repr([self._hour, self._minute, self._second, self._microsecond], 2) + ")"

    def strftime(self, format: str) -> str:
        return _strftime(format, 1900, 1, 1, self._hour, self._minute, self._second, self._microsecond)

    def replace(self, hour: int | None = None, minute: int | None = None, second: int | None = None, microsecond: int | None = None) -> time:
        return time(
            self._hour if hour is None else hour,
            self._minute if minute is None else minute,
            self._second if second is None else second,
            self._microsecond if microsecond is None else microsecond,
        )

    def _key(self) -> tuple[int, int, int, int]:
        return (self._hour, self._minute, self._second, self._microsecond)

    def __eq__(self, other: time) -> bool:
        return self._key() == other._key()

    def __ne__(self, other: time) -> bool:
        return self._key() != other._key()

    def __lt__(self, other: time) -> bool:
        return self._key() < other._key()

    def __le__(self, other: time) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: time) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: time) -> bool:
        return self._key() >= other._key()

    def __bool__(self) -> bool:
        return True


def _fields_repr(xs: list[int], keep: int) -> str:
    """The fields, without the trailing zeros after the first `keep`."""
    n = len(xs)
    while n > keep and xs[n - 1] == 0:
        n -= 1
    return ", ".join([str(x) for x in xs[:n]])


# ------------------------------------------------------------------- datetime


class datetime:
    def __init__(self, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0, microsecond: int = 0) -> None:
        _check_date(year, month, day)
        _check_time(hour, minute, second, microsecond)
        self._year: int = year
        self._month: int = month
        self._day: int = day
        self._hour: int = hour
        self._minute: int = minute
        self._second: int = second
        self._microsecond: int = microsecond

    @staticmethod
    def now() -> datetime:
        y, m, d, hh, mm, ss, us = _now()
        return datetime(y, m, d, hh, mm, ss, us)

    @staticmethod
    def today() -> datetime:
        return datetime.now()

    @staticmethod
    def combine(d: date, t: time) -> datetime:
        return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond)

    @staticmethod
    def fromordinal(n: int) -> datetime:
        d = date.fromordinal(n)
        return datetime(d.year, d.month, d.day)

    @staticmethod
    def fromisoformat(date_string: str) -> datetime:
        if len(date_string) < 7:
            raise ValueError("Invalid isoformat string: " + repr(date_string))
        sep = _find_isoformat_datetime_separator(date_string)
        dstr = date_string[0:sep]
        tstr = date_string[sep + 1 :]
        y, m, d = _parse_isoformat_date(dstr, date_string)
        hh, mm, ss, us = 0, 0, 0, 0
        if tstr != "":
            hh, mm, ss, us = _parse_isoformat_time(tstr, date_string)
            if hh == 24:
                if mm != 0 or ss != 0 or us != 0:
                    raise ValueError("minute, second, and microsecond must be 0 when hour is 24")
                hh = 0
                if 1 <= m <= 12 and d <= _days_in_month(y, m):
                    d += 1
                    if d > _days_in_month(y, m):
                        d = 1
                        m += 1
                        if m > 12:
                            m = 1
                            y += 1
        return datetime(y, m, d, hh, mm, ss, us)

    @staticmethod
    def strptime(date_string: str, format: str) -> datetime:
        y, m, d, hh, mm, ss, us = _strptime(date_string, format)
        return datetime(y, m, d, hh, mm, ss, us)

    @property
    def year(self) -> int:
        return self._year

    @property
    def month(self) -> int:
        return self._month

    @property
    def day(self) -> int:
        return self._day

    @property
    def hour(self) -> int:
        return self._hour

    @property
    def minute(self) -> int:
        return self._minute

    @property
    def second(self) -> int:
        return self._second

    @property
    def microsecond(self) -> int:
        return self._microsecond

    def date(self) -> date:
        return date(self._year, self._month, self._day)

    def time(self) -> time:
        return time(self._hour, self._minute, self._second, self._microsecond)

    def toordinal(self) -> int:
        return _ymd2ord(self._year, self._month, self._day)

    def weekday(self) -> int:
        return (self.toordinal() + 6) % 7

    def isoweekday(self) -> int:
        return (self.toordinal() + 6) % 7 + 1

    def isocalendar(self) -> IsoCalendarDate:
        y, w, d = _isocalendar(self._year, self._month, self._day)
        return IsoCalendarDate(y, w, d)

    def isoformat(self, sep: str = "T", timespec: str = "auto") -> str:
        return _pad(self._year, 4) + "-" + _pad(self._month, 2) + "-" + _pad(self._day, 2) + sep + _format_time(self._hour, self._minute, self._second, self._microsecond, timespec)

    def __str__(self) -> str:
        return self.isoformat(" ")

    def __repr__(self) -> str:
        return "datetime.datetime(" + _fields_repr([self._year, self._month, self._day, self._hour, self._minute, self._second, self._microsecond], 5) + ")"

    def ctime(self) -> str:
        wd = (self.toordinal() + 6) % 7
        return _day_name(wd) + " " + _month_name(self._month) + " " + _spad(self._day) + " " + _pad(self._hour, 2) + ":" + _pad(self._minute, 2) + ":" + _pad(self._second, 2) + " " + _pad(self._year, 4)

    def strftime(self, format: str) -> str:
        return _strftime(format, self._year, self._month, self._day, self._hour, self._minute, self._second, self._microsecond)

    def replace(
        self,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
        minute: int | None = None,
        second: int | None = None,
        microsecond: int | None = None,
    ) -> datetime:
        return datetime(
            self._year if year is None else year,
            self._month if month is None else month,
            self._day if day is None else day,
            self._hour if hour is None else hour,
            self._minute if minute is None else minute,
            self._second if second is None else second,
            self._microsecond if microsecond is None else microsecond,
        )

    def _key(self) -> tuple[int, int, int, int, int, int, int]:
        return (self._year, self._month, self._day, self._hour, self._minute, self._second, self._microsecond)

    def __add__(self, other: timedelta) -> datetime:
        d = self.toordinal() + other.days
        s = self._hour * 3600 + self._minute * 60 + self._second + other.seconds
        us = self._microsecond + other.microseconds
        q, us = divmod(us, 1000000)
        s += q
        q, s = divmod(s, 86400)
        d += q
        if not 0 < d <= _MAXORDINAL:
            raise OverflowError("date value out of range")
        y, m, dd = _ord2ymd(d)
        hh, rem = divmod(s, 3600)
        mi, ss = divmod(rem, 60)
        return datetime(y, m, dd, hh, mi, ss, us)

    def __radd__(self, other: timedelta) -> datetime:
        return self + other

    def __sub__(self, other: datetime | timedelta) -> timedelta | datetime:
        if isinstance(other, timedelta):
            return self + -other
        else:
            secs1 = self._second + self._minute * 60 + self._hour * 3600
            secs2 = other._second + other._minute * 60 + other._hour * 3600
            return _delta(self.toordinal() - other.toordinal(), secs1 - secs2, self._microsecond - other._microsecond)

    def __eq__(self, other: datetime) -> bool:
        return self._key() == other._key()

    def __ne__(self, other: datetime) -> bool:
        return self._key() != other._key()

    def __lt__(self, other: datetime) -> bool:
        return self._key() < other._key()

    def __le__(self, other: datetime) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: datetime) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: datetime) -> bool:
        return self._key() >= other._key()


def _spad(n: int) -> str:
    return " " + str(n) if n < 10 else str(n)


def _now() -> tuple[int, int, int, int, int, int, int]:
    """The local time, from time.strftime and the fraction of time.time()."""
    t = _now_time()
    s = _now_strftime("%Y %m %d %H %M %S")
    f = [int(x) for x in s.split(" ")]
    us = int((t - math.floor(t)) * 1000000.0)
    return f[0], f[1], f[2], f[3], f[4], f[5], min(us, 999999)


# ------------------------------------------------------------- ISO 8601 text


def _digits(s: str) -> bool:
    if s == "":
        return False
    for c in s:
        if c not in "0123456789":
            return False
    return True


def _num(s: str, whole: str) -> int:
    if not _digits(s):
        raise ValueError("Invalid isoformat string: " + repr(whole))
    return int(s)


def _find_isoformat_datetime_separator(dtstr: str) -> int:
    n = len(dtstr)
    if n == 7:
        return 7
    if dtstr[4] == "-":
        if dtstr[5] == "W":
            if n < 8:
                raise ValueError("Invalid ISO string")
            if n > 8 and dtstr[8] == "-":
                if n == 9:
                    raise ValueError("Invalid ISO string")
                if n > 10 and dtstr[10] in "0123456789":
                    return 8
                return 10
            return 8
        return 10
    if dtstr[4] == "W":
        idx = 7
        while idx < n:
            if dtstr[idx] not in "0123456789":
                break
            idx += 1
        if idx < 9:
            return idx
        if idx % 2 == 0:
            return 7
        return 8
    return 8


def _parse_isoformat_date(dtstr: str, whole: str) -> tuple[int, int, int]:
    n = len(dtstr)
    if not (n == 7 or n == 8 or n == 10):
        raise ValueError("Invalid isoformat string: " + repr(whole))
    year = _num(dtstr[0:4], whole)
    has_sep = 1 if dtstr[4] == "-" else 0
    pos = 4 + has_sep
    if dtstr[pos : pos + 1] == "W":
        pos += 1
        weekno = _num(dtstr[pos : pos + 2], whole)
        pos += 2
        dayno = 1
        if len(dtstr) > pos:
            if (dtstr[pos : pos + 1] == "-") != (has_sep == 1):
                raise ValueError("Invalid isoformat string: " + repr(whole))
            pos += has_sep
            dayno = _num(dtstr[pos : pos + 1], whole)
        return _isoweek_to_gregorian(year, weekno, dayno)
    month = _num(dtstr[pos : pos + 2], whole)
    pos += 2
    if (dtstr[pos : pos + 1] == "-") != (has_sep == 1):
        raise ValueError("Invalid isoformat string: " + repr(whole))
    pos += has_sep
    day = _num(dtstr[pos : pos + 2], whole)
    if pos + 2 != len(dtstr):
        raise ValueError("Invalid isoformat string: " + repr(whole))
    return year, month, day


def _parse_isoformat_time(tstr: str, whole: str) -> tuple[int, int, int, int]:
    """hh[:mm[:ss[.ffffff]]] (no time zones: rupy's datetime is naive)."""
    n = len(tstr)
    if n < 2:
        raise ValueError("Invalid isoformat string: " + repr(whole))
    for c in "+-Z":
        if c in tstr:
            raise ValueError("rupy's datetime has no time zones: " + repr(whole))
    comps = [0, 0, 0, 0]
    pos = 0
    has_sep = False
    for comp in range(3):
        if n - pos < 2:
            raise ValueError("Invalid isoformat string: " + repr(whole))
        comps[comp] = _num(tstr[pos : pos + 2], whole)
        pos += 2
        nxt = tstr[pos : pos + 1]
        if comp == 0:
            has_sep = nxt == ":"
        if nxt == "" or comp >= 2:
            break
        if has_sep and nxt != ":":
            raise ValueError("Invalid isoformat string: " + repr(whole))
        if has_sep:
            pos += 1
    if pos < n:
        if tstr[pos] not in ".,":
            raise ValueError("Invalid isoformat string: " + repr(whole))
        pos += 1
        frac = tstr[pos:]
        if not _digits(frac):
            raise ValueError("Invalid isoformat string: " + repr(whole))
        k = min(len(frac), 6)
        us = int(frac[:k])
        for _ in range(6 - k):
            us *= 10
        comps[3] = us
    return comps[0], comps[1], comps[2], comps[3]


# ------------------------------------------------------------------ strftime


def _strftime(format: str, y: int, mo: int, d: int, hh: int, mi: int, ss: int, us: int) -> str:
    """C's strftime in the C locale (macOS), with %f as Python adds it."""
    out: list[str] = []
    n = len(format)
    i = 0
    wd = (_ymd2ord(y, mo, d) + 6) % 7
    yday = _days_before_month(y, mo) + d
    while i < n:
        c = format[i]
        i += 1
        if c != "%" or i >= n:
            out.append(c)
            continue
        c = format[i]
        i += 1
        out.append(_directive(c, y, mo, d, hh, mi, ss, us, wd, yday))
    return "".join(out)


def _directive(c: str, y: int, mo: int, d: int, hh: int, mi: int, ss: int, us: int, wd: int, yday: int) -> str:
    h12 = hh % 12
    if h12 == 0:
        h12 = 12
    if c == "a":
        return _day_name(wd)
    if c == "A":
        return _full_day(wd)
    if c == "b" or c == "h":
        return _month_name(mo)
    if c == "B":
        return _full_month(mo)
    if c == "c":
        return _day_name(wd) + " " + _month_name(mo) + " " + _spad(d) + " " + _pad(hh, 2) + ":" + _pad(mi, 2) + ":" + _pad(ss, 2) + " " + str(y)
    if c == "C":
        return _pad(y // 100, 2)
    if c == "d":
        return _pad(d, 2)
    if c == "D":
        return _pad(mo, 2) + "/" + _pad(d, 2) + "/" + _pad(y % 100, 2)
    if c == "e":
        return _spad(d)
    if c == "f":
        return _pad(us, 6)
    if c == "F":
        return str(y) + "-" + _pad(mo, 2) + "-" + _pad(d, 2)
    if c == "G" or c == "g" or c == "V":
        iy, iw, _ = _isocalendar(y, mo, d)
        if c == "G":
            return str(iy)
        if c == "g":
            return _pad(iy % 100, 2)
        return _pad(iw, 2)
    if c == "H":
        return _pad(hh, 2)
    if c == "I":
        return _pad(h12, 2)
    if c == "j":
        return _pad(yday, 3)
    if c == "k":
        return _spad(hh)
    if c == "l":
        return _spad(h12)
    if c == "m":
        return _pad(mo, 2)
    if c == "M":
        return _pad(mi, 2)
    if c == "n":
        return "\n"
    if c == "p":
        return "AM" if hh < 12 else "PM"
    if c == "r":
        return _pad(h12, 2) + ":" + _pad(mi, 2) + ":" + _pad(ss, 2) + " " + ("AM" if hh < 12 else "PM")
    if c == "R":
        return _pad(hh, 2) + ":" + _pad(mi, 2)
    if c == "S":
        return _pad(ss, 2)
    if c == "t":
        return "\t"
    if c == "T" or c == "X":
        return _pad(hh, 2) + ":" + _pad(mi, 2) + ":" + _pad(ss, 2)
    if c == "u":
        return str(wd + 1)
    if c == "U":
        return _pad((yday + 6 - (wd + 1) % 7) // 7, 2)
    if c == "w":
        return str((wd + 1) % 7)
    if c == "W":
        return _pad((yday + 6 - wd) // 7, 2)
    if c == "x":
        return _pad(mo, 2) + "/" + _pad(d, 2) + "/" + _pad(y % 100, 2)
    if c == "y":
        return _pad(y % 100, 2)
    if c == "Y":
        return str(y)
    if c == "z" or c == "Z":
        return ""
    if c == "%":
        return "%"
    return c


# ------------------------------------------------------------------ strptime


def _lower(s: str) -> str:
    return s.lower()


class _Parsed:
    def __init__(self) -> None:
        self.year: int = 1900
        self.month: int = 1
        self.day: int = 1
        self.hour: int = 0
        self.minute: int = 0
        self.second: int = 0
        self.us: int = 0
        self.yday: int = -1
        self.pm: int = -1
        self.h12: bool = False


def _alts(c: str) -> list[str]:
    """The alternatives of _strptime's regex for directive c, in its order;
    `D` is a digit, `N` a word (a month or day name)."""
    if c == "d":
        return ["3[01]", "[12]D", "0[1-9]", "[1-9]", " [1-9]"]
    if c == "m":
        return ["1[0-2]", "0[1-9]", "[1-9]"]
    if c == "H":
        return ["2[0-3]", "[0-1]D", "D"]
    if c == "I":
        return ["1[0-2]", "0[1-9]", "[1-9]"]
    if c == "M":
        return ["[0-5]D", "D"]
    if c == "S":
        return ["6[0-1]", "[0-5]D", "D"]
    if c == "y":
        return ["DD"]
    if c == "Y":
        return ["DDDD"]
    if c == "j":
        return ["36[0-6]", "3[0-5]D", "[12]DD", "0[1-9]D", "00[1-9]", "[1-9]D", "0[1-9]", "[1-9]"]
    return []


def _class_match(cls: str, ch: str) -> bool:
    if cls == "D":
        return ch in "0123456789"
    if len(cls) == 1:
        return ch == cls
    lo = cls[1]
    hi = cls[3]
    return lo <= ch <= hi


def _pattern_len(p: str) -> int:
    n = 0
    i = 0
    while i < len(p):
        if p[i] == "[":
            i += 5
        else:
            i += 1
        n += 1
    return n


def _match_alt(p: str, s: str, pos: int) -> bool:
    i = 0
    k = pos
    while i < len(p):
        if k >= len(s):
            return False
        if p[i] == "[":
            if not _class_match(p[i : i + 5], s[k]):
                return False
            i += 5
        else:
            if not _class_match(p[i], s[k]):
                return False
            i += 1
        k += 1
    return True


def _names(c: str) -> list[str]:
    if c == "b":
        return [_month_name(m).lower() for m in range(1, 13)]
    if c == "B":
        return [_full_month(m).lower() for m in range(1, 13)]
    if c == "a":
        return [_day_name(k).lower() for k in range(7)]
    if c == "A":
        return [_full_day(k).lower() for k in range(7)]
    return ["am", "pm"]


def _match(fmt: str, fi: int, s: str, si: int, got: list[tuple[str, str]]) -> int:
    """Match fmt[fi:] at s[si:] as _strptime's regex would (alternatives in
    order, backtracking); the end of the match or -1, and the fields in got."""
    if fi >= len(fmt):
        return si
    c = fmt[fi]
    if c == "%" and fi + 1 < len(fmt):
        dch = fmt[fi + 1]
        if dch == "%":
            if si < len(s) and s[si] == "%":
                return _match(fmt, fi + 2, s, si + 1, got)
            return -1
        if dch == "f":
            # [0-9]{1,6}: greedy
            k = si
            while k < len(s) and k - si < 6 and s[k] in "0123456789":
                k += 1
            while k > si:
                got.append(("f", s[si:k]))
                r = _match(fmt, fi + 2, s, k, got)
                if r >= 0:
                    return r
                got.pop()
                k -= 1
            return -1
        if dch in "bBaAp":
            low = s.lower()
            # the regex lists the names longest first
            ns = sorted(_names(dch), key=lambda x: -len(x))
            for name in ns:
                if low[si : si + len(name)] == name:
                    got.append((dch, s[si : si + len(name)]))
                    r = _match(fmt, fi + 2, s, si + len(name), got)
                    if r >= 0:
                        return r
                    got.pop()
            return -1
        alts = _alts(dch)
        if len(alts) == 0:
            raise ValueError("'" + dch + "' is a bad directive in format '%" + dch + "'")
        for p in alts:
            if _match_alt(p, s, si):
                k = si + _pattern_len(p)
                got.append((dch, s[si:k]))
                r = _match(fmt, fi + 2, s, k, got)
                if r >= 0:
                    return r
                got.pop()
        return -1
    if c == " " or c == "\t" or c == "\n":
        # whitespace in the format: \s+
        k = si
        while k < len(s) and s[k] in " \t\n\r\f\v":
            k += 1
        j = fi
        while j < len(fmt) and fmt[j] in " \t\n\r\f\v":
            j += 1
        while k > si:
            r = _match(fmt, j, s, k, got)
            if r >= 0:
                return r
            k -= 1
        return -1
    if si < len(s) and s[si].lower() == c.lower():
        return _match(fmt, fi + 1, s, si + 1, got)
    return -1


def _strptime(data: str, format: str) -> tuple[int, int, int, int, int, int, int]:
    got: list[tuple[str, str]] = []
    end = _match(format, 0, data, 0, got)
    if end < 0:
        raise ValueError("time data " + repr(data) + " does not match format " + repr(format))
    if end != len(data):
        raise ValueError("unconverted data remains: " + data[end:])
    p = _Parsed()
    for k, v in got:
        if k == "Y":
            p.year = int(v)
        elif k == "y":
            yy = int(v)
            p.year = yy + 2000 if yy <= 68 else yy + 1900
        elif k == "m":
            p.month = int(v)
        elif k == "b" or k == "B":
            p.month = _names(k).index(v.lower()) + 1
        elif k == "d":
            p.day = int(v.strip())
        elif k == "H":
            p.hour = int(v)
            p.h12 = False
        elif k == "I":
            p.hour = int(v)
            p.h12 = True
        elif k == "M":
            p.minute = int(v)
        elif k == "S":
            p.second = int(v)
        elif k == "f":
            us = int(v)
            for _ in range(6 - len(v)):
                us *= 10
            p.us = us
        elif k == "p":
            p.pm = 1 if v.lower() == "pm" else 0
        elif k == "j":
            p.yday = int(v)
    if p.h12:
        if p.pm == 1:
            p.hour = 12 if p.hour == 12 else p.hour + 12
        elif p.pm == 0 and p.hour == 12:
            p.hour = 0
    if p.second == 61:
        p.second = 59
    if p.yday != -1:
        o = _ymd2ord(p.year, 1, 1) + p.yday - 1
        p.year, p.month, p.day = _ord2ymd(o)
    return p.year, p.month, p.day, p.hour, p.minute, p.second, p.us
