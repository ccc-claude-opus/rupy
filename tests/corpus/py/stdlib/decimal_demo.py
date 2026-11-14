from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, ROUND_UP, DivisionByZero, InvalidOperation
from decimal import Decimal as D
print(D("1.1") + D("2.2"), D("1") / D("3"), D("2") / D("4"), D("10") / D("4"), D("1.00") * D("3"), D("-0") + D("0"), D("1") - D("1"), D("0.00") + D("1.5"))
print(D("1.10") ** 2, D("2") ** -2, D("7") % D("-3"), D("-7") // D("3"), D("1E+3"), D("0.000001"), D("0.0000001"), D("123.456e10"), repr(D("-0.0")))
print(D("2.675").quantize(D("0.01")), D("2.675").quantize(D("0.01"), rounding=ROUND_HALF_UP), D("1") / D("7"), D("100") / D("7"), D("1") / D("8"))
print(D("3.0") == D("3"), D("1.5") < 2, int(D("-2.7")), float(D("0.1")), D("1.20").normalize(), D("100").normalize(), D.from_float(0.1), D.from_float(-2.5))
print(D("19.99") * 3, D("0.1") + D("0.2") + D("0.7"), D("0.1") * 3 == D("0.3"), 2 * D("1.5"), 10 - D("0.01"), 1 / D("3"))
print(D("123.456").quantize(D("1"), rounding=ROUND_DOWN), D("-123.456").quantize(D("0.1"), rounding=ROUND_FLOOR), D("1.01").quantize(D("0.1"), rounding=ROUND_UP))
print(D("12345678901234567890.123456789") * D("98765432109876543210"), D("1E+30") + D("1"), D("9" * 30), -D("5"), abs(D("-5.50")), +D("-0"))
print(D("7.5").to_integral_value(), D("8.5").to_integral_value(), D("1.2345").adjusted(), D("0.00").is_zero(), D("-3").is_signed(), D("3").max(D("4")), D("10") / D("0.5"))
print(sorted([D("1.5"), D("-2"), D("0.25")]), max([D("1.5"), D("2.0")]), D("2.50").compare(D("2.5")), D("1") // D("3"), D("-1") // D("3"), D("10") % D("3"))
for k in range(5):
    try:
        if k == 0:
            print(D("1") / D("0"))
        elif k == 1:
            print(D("abc"))
        elif k == 2:
            print(D("0") / D("0"))
        elif k == 3:
            print(D("1") // D("0"))
        else:
            print(D("1e30").quantize(D("0.01")))
    except DivisionByZero as e:
        print("DivisionByZero", e)
    except InvalidOperation as e:
        print("InvalidOperation", e)
