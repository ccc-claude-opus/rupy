from fractions import Fraction


def show(name: str, f: Fraction) -> None:
    print(name, f, repr(f), f.numerator, f.denominator)


a = Fraction(1, 3)
b = Fraction(-6, 4)
c = Fraction(5)
show("a", a)
show("b", b)
show("c", c)
show("zero", Fraction())
show("neg den", Fraction(3, -9))
show("a+b", a + b)
show("a-b", a - b)
show("a*b", a * b)
show("a/b", a / b)
show("a+2", a + 2)
show("2+a", 2 + a)
show("2-a", 2 - a)
show("a-2", a - 2)
show("3*a", 3 * a)
show("a*3", a * 3)
show("1/a", 1 / a)
show("a/4", a / 4)
show("a**3", a**3)
show("b**-3", b**-3)
show("a**0", a**0)
show("-a", -a)
show("+b", +b)
show("abs(b)", abs(b))
print(b // a, b // 2, 7 // a)
show("b%a", b % a)
show("b%2", b % 2)
show("7%b", 7 % b)
print(int(b), int(Fraction(7, 2)), float(a), float(b))
print(a == Fraction(2, 6), a == 1, c == 5, a != b, a < b, b < a, a <= a, a > 0, b >= -2)
print(bool(Fraction(0, 3)), bool(a))
print(a.as_integer_ratio(), c.is_integer(), a.is_integer())
show("from_float(0.1)", Fraction.from_float(0.1))
show("from_float(-2.5)", Fraction.from_float(-2.5))
show("from_float(3.0)", Fraction.from_float(3.0))
pi = Fraction.from_float(3.141592653589793)
show("pi", pi)
show("pi 1000", pi.limit_denominator(1000))
show("pi 100", pi.limit_denominator(100))
show("pi 1", pi.limit_denominator(1))
show("0.1 limit", Fraction.from_float(0.1).limit_denominator())
total = Fraction(0)
for i in range(1, 11):
    total += Fraction(1, i)
show("harmonic 10", total)
xs = sorted([Fraction(1, 2), Fraction(-1, 3), Fraction(5, 7), Fraction(0)])
print([str(x) for x in xs])
print(max(xs), min(xs))
print(f"{a} and {b!r}")

try:
    Fraction(1, 0)
except ZeroDivisionError as e:
    print("ZeroDivisionError", e)
try:
    print(a / Fraction(0))
except ZeroDivisionError as e:
    print("ZeroDivisionError", e)
try:
    print(Fraction(0) ** -2)
except ZeroDivisionError as e:
    print("ZeroDivisionError", e)
try:
    print(a.limit_denominator(0))
except ValueError as e:
    print("ValueError", e)
try:
    print(Fraction.from_float(float("inf")))
except OverflowError as e:
    print("OverflowError", e)
try:
    print(Fraction.from_float(float("nan")))
except ValueError as e:
    print("ValueError", e)
print(float(Fraction(2**62 + 1, 3)), float(Fraction(-(2**61) - 1, 2**60 + 7)))
