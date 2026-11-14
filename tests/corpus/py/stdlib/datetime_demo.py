import datetime
from datetime import date, datetime as DT, time, timedelta

d = date(2024, 3, 5)
print(d, repr(d), d.year, d.month, d.day, d.weekday(), d.isoweekday(), d.toordinal(), d.ctime())
print(d.isocalendar(), date(2021, 1, 3).isocalendar(), date(2020, 12, 31).isocalendar(), date.fromisocalendar(2024, 10, 2))
print(d + timedelta(days=30), d - timedelta(weeks=10), date(2025, 1, 1) - d, timedelta(1) + d)
print(date.fromordinal(1), date.fromordinal(738950), date.fromisoformat("2024-02-29"), date.fromisoformat("20240229"), date.fromisoformat("2024-W10-2"))
print(d.replace(day=31), d.replace(year=2023, month=12), d < date(2024, 3, 6), d == date(2024, 3, 5), d != d, max([d, date(2020, 1, 1)]))
print(sorted([date(2024, 1, 2), date(2023, 12, 31), date(2024, 1, 1)]))
print(d.strftime("%Y/%m/%d %a %A %b %B %j %U %W %w %u %G-W%V %C %y %e %D %F %x %%"))

td = timedelta(days=1, hours=2, minutes=3, seconds=4.5, milliseconds=6, microseconds=7)
print(td, repr(td), td.days, td.seconds, td.microseconds, td.total_seconds())
print(timedelta(hours=1.5), repr(timedelta(hours=1.5, microseconds=3)), timedelta(days=-1, seconds=5), -timedelta(minutes=1), repr(timedelta()))
print(timedelta(seconds=0.5e-6), timedelta(seconds=1.5e-6), timedelta(seconds=2.5e-6), timedelta(days=0.1), timedelta(weeks=1.25), timedelta(microseconds=-0.5))
print(td * 2, 3 * td, td * 0.5, td / 3, td / 2.5, td / timedelta(hours=1), td // timedelta(hours=1), td // 7, td % timedelta(hours=1))
print(abs(timedelta(days=-2, hours=1)), +td, td - timedelta(days=2), timedelta(hours=1) < timedelta(hours=2), timedelta(0) == timedelta(seconds=0), bool(timedelta(0)))
print(str(timedelta(days=2)), str(timedelta(days=-3, hours=5)), timedelta(minutes=90).seconds, repr(timedelta(days=999999999)))

dt = DT(2024, 3, 5, 7, 8, 9, 12)
print(dt, repr(dt), repr(DT(2024, 3, 5)), repr(DT(2024, 3, 5, 7)), repr(DT(2024, 3, 5, 0, 0, 9)), dt.date(), dt.time(), dt.hour, dt.microsecond)
print(dt.isoformat(), dt.isoformat(" ", "minutes"), dt.isoformat(timespec="milliseconds"), DT(2024, 3, 5, 7).isoformat(), dt.ctime())
print(dt + timedelta(hours=20), dt - timedelta(days=400), DT(2025, 1, 1) - dt, dt - DT(2025, 1, 1), timedelta(seconds=1) + dt)
print(DT.fromisoformat("2024-03-05T07:08:09.123"), DT.fromisoformat("2024-03-05 07:08"), DT.fromisoformat("2024-03-05"), DT.fromisoformat("20240305T070809"), DT.fromisoformat("2024-12-31T24:00"))
print(DT.combine(d, time(12, 30)), dt.replace(hour=0, microsecond=0), dt.weekday(), dt.toordinal(), dt > DT(2024, 3, 5), dt.isocalendar())
print(dt.strftime("%Y-%m-%d %H:%M:%S.%f %I %p %c %X %r %R %T %k %l"), DT(2024, 3, 5, 15).strftime("%I%p %l"))
print(DT.strptime("2024-03-05 07:08:09", "%Y-%m-%d %H:%M:%S"), DT.strptime("5 Mar 24 3pm", "%d %b %y %I%p"), DT.strptime("March 7, 1999", "%B %d, %Y"))
print(DT.strptime("12:30:15.25", "%H:%M:%S.%f"), DT.strptime("2024 060", "%Y %j"), date.strptime("1/2/2003", "%m/%d/%Y"), DT.strptime("12AM", "%I%p"))

t = time(13, 5, 9, 1500)
print(t, repr(t), repr(time()), repr(time(1, 2)), t.isoformat("milliseconds"), t.isoformat("hours"), time.fromisoformat("01:02:03.5"), t.replace(hour=1), t < time(14), t.strftime("%H|%M|%S|%f|%p"))
print(datetime.MINYEAR, datetime.MAXYEAR, date.today().year > 2000, DT.now().year > 2000)

for k in range(14):
    try:
        if k == 0:
            date(2024, 13, 1)
        elif k == 1:
            date(2023, 2, 29)
        elif k == 2:
            DT(2024, 1, 1, 24)
        elif k == 3:
            date.fromisoformat("2024-1-01")
        elif k == 4:
            timedelta(days=1000000000)
        elif k == 5:
            print(date(9999, 12, 31) + timedelta(1))
        elif k == 6:
            DT.strptime("2024-02-30", "%Y-%m-%d")
        elif k == 7:
            DT.strptime("2024-02-3x", "%Y-%m-%d")
        elif k == 8:
            DT.strptime("hello", "%Y")
        elif k == 9:
            dt.isoformat(timespec="x")
        elif k == 10:
            date.fromordinal(0)
        elif k == 11:
            DT.fromisoformat("2024-01-01T25:00")
        elif k == 12:
            time(1, 60)
        else:
            date.fromisocalendar(2023, 53, 1)
    except OverflowError as e:
        print("OverflowError", e)
    except ValueError as e:
        print("ValueError", e)
