"""rupy's `fractions`: CPython's `fractions.Fraction`, written in rupy.

Numerators and denominators are 64-bit ints: a result beyond them raises
OverflowError where CPython's ints would grow. `Fraction(x)` takes an int, a
float, a str or a Fraction, and arithmetic mixes fractions with ints, not with
floats."""

import math


class Fraction:
    def __init__(self, numerator: int | float | str | Fraction = 0, denominator: int | None = None) -> None:
        n = 0
        d = 1
        if isinstance(numerator, int):
            n = numerator
            if denominator is not None:
                d = denominator
        elif isinstance(numerator, float):
            if denominator is not None:
                raise TypeError("both arguments should be Rational instances")
            n, d = _float_ratio(numerator)
        elif isinstance(numerator, str):
            if denominator is not None:
                raise TypeError("both arguments should be Rational instances")
            n, d = _parse(numerator)
        else:
            n = numerator._numerator
            d = numerator._denominator
            if denominator is not None:
                d = d * denominator
        if d == 0:
            raise ZeroDivisionError("Fraction(" + str(n) + ", 0)")
        g = math.gcd(n, d)
        if d < 0:
            g = -g
        self._numerator: int = n // g
        self._denominator: int = d // g

    @staticmethod
    def from_float(f: float) -> Fraction:
        n, d = _float_ratio(f)
        return Fraction(n, d)

    @property
    def numerator(self) -> int:
        return self._numerator

    @property
    def denominator(self) -> int:
        return self._denominator

    def as_integer_ratio(self) -> tuple[int, int]:
        return (self._numerator, self._denominator)

    def is_integer(self) -> bool:
        return self._denominator == 1

    def limit_denominator(self, max_denominator: int = 1000000) -> Fraction:
        if max_denominator < 1:
            raise ValueError("max_denominator should be at least 1")
        if self._denominator <= max_denominator:
            return Fraction(self._numerator, self._denominator)
        p0, q0, p1, q1 = 0, 1, 1, 0
        n, d = self._numerator, self._denominator
        while True:
            a = n // d
            q2 = q0 + a * q1
            if q2 > max_denominator:
                break
            p0, q0, p1, q1 = p1, q1, p0 + a * p1, q2
            n, d = d, n - a * d
        k = (max_denominator - q0) // q1
        if 2 * d * (q0 + k * q1) <= self._denominator:
            return Fraction(p1, q1)
        return Fraction(p0 + k * p1, q0 + k * q1)

    def __repr__(self) -> str:
        return "Fraction(" + str(self._numerator) + ", " + str(self._denominator) + ")"

    def __str__(self) -> str:
        if self._denominator == 1:
            return str(self._numerator)
        return str(self._numerator) + "/" + str(self._denominator)

    def __add__(self, other: Fraction | int) -> Fraction:
        if isinstance(other, int):
            return _add(self._numerator, self._denominator, other, 1)
        else:
            return _add(self._numerator, self._denominator, other._numerator, other._denominator)

    def __radd__(self, other: int) -> Fraction:
        return _add(other, 1, self._numerator, self._denominator)

    def __sub__(self, other: Fraction | int) -> Fraction:
        if isinstance(other, int):
            return _add(self._numerator, self._denominator, -other, 1)
        else:
            return _add(self._numerator, self._denominator, -other._numerator, other._denominator)

    def __rsub__(self, other: int) -> Fraction:
        return _add(other, 1, -self._numerator, self._denominator)

    def __mul__(self, other: Fraction | int) -> Fraction:
        if isinstance(other, int):
            return _mul(self._numerator, self._denominator, other, 1)
        else:
            return _mul(self._numerator, self._denominator, other._numerator, other._denominator)

    def __rmul__(self, other: int) -> Fraction:
        return _mul(other, 1, self._numerator, self._denominator)

    def __truediv__(self, other: Fraction | int) -> Fraction:
        if isinstance(other, int):
            return _div(self._numerator, self._denominator, other, 1)
        else:
            return _div(self._numerator, self._denominator, other._numerator, other._denominator)

    def __rtruediv__(self, other: int) -> Fraction:
        return _div(other, 1, self._numerator, self._denominator)

    def __floordiv__(self, other: Fraction | int) -> int:
        if isinstance(other, int):
            return self._numerator // (self._denominator * other)
        else:
            return (self._numerator * other._denominator) // (self._denominator * other._numerator)

    def __rfloordiv__(self, other: int) -> int:
        return (other * self._denominator) // self._numerator

    def __mod__(self, other: Fraction | int) -> Fraction:
        if isinstance(other, int):
            return Fraction(self._numerator % (other * self._denominator), self._denominator)
        else:
            da = self._denominator
            db = other._denominator
            return Fraction((self._numerator * db) % (other._numerator * da), da * db)

    def __rmod__(self, other: int) -> Fraction:
        db = self._denominator
        return Fraction((other * db) % self._numerator, db)

    def __pow__(self, other: int) -> Fraction:
        if other >= 0:
            return Fraction(self._numerator**other, self._denominator**other)
        if self._numerator > 0:
            return Fraction(self._denominator ** (-other), self._numerator ** (-other))
        if self._numerator == 0:
            raise ZeroDivisionError("Fraction(" + str(self._denominator ** (-other)) + ", 0)")
        return Fraction((-self._denominator) ** (-other), (-self._numerator) ** (-other))

    def __neg__(self) -> Fraction:
        return Fraction(-self._numerator, self._denominator)

    def __pos__(self) -> Fraction:
        return Fraction(self._numerator, self._denominator)

    def __abs__(self) -> Fraction:
        return Fraction(abs(self._numerator), self._denominator)

    def __int__(self) -> int:
        if self._numerator < 0:
            return -(-self._numerator // self._denominator)
        return self._numerator // self._denominator

    def __float__(self) -> float:
        return self._numerator / self._denominator

    def __bool__(self) -> bool:
        return self._numerator != 0

    def __eq__(self, other: Fraction | int) -> bool:
        if isinstance(other, int):
            return self._numerator == other and self._denominator == 1
        else:
            return self._numerator == other._numerator and self._denominator == other._denominator

    def __ne__(self, other: Fraction | int) -> bool:
        return not self == other

    def __lt__(self, other: Fraction | int) -> bool:
        if isinstance(other, int):
            return self._numerator < self._denominator * other
        else:
            return self._numerator * other._denominator < self._denominator * other._numerator

    def __le__(self, other: Fraction | int) -> bool:
        if isinstance(other, int):
            return self._numerator <= self._denominator * other
        else:
            return self._numerator * other._denominator <= self._denominator * other._numerator

    def __gt__(self, other: Fraction | int) -> bool:
        if isinstance(other, int):
            return self._numerator > self._denominator * other
        else:
            return self._numerator * other._denominator > self._denominator * other._numerator

    def __ge__(self, other: Fraction | int) -> bool:
        if isinstance(other, int):
            return self._numerator >= self._denominator * other
        else:
            return self._numerator * other._denominator >= self._denominator * other._numerator


# CPython's _add, _mul and _div: gcds first keep the products small


def _add(na: int, da: int, nb: int, db: int) -> Fraction:
    g = math.gcd(da, db)
    if g == 1:
        return Fraction(na * db + da * nb, da * db)
    s = da // g
    t = na * (db // g) + nb * s
    g2 = math.gcd(t, g)
    if g2 == 1:
        return Fraction(t, s * db)
    return Fraction(t // g2, s * (db // g2))


def _mul(na: int, da: int, nb: int, db: int) -> Fraction:
    g1 = math.gcd(na, db)
    if g1 > 1:
        na //= g1
        db //= g1
    g2 = math.gcd(nb, da)
    if g2 > 1:
        nb //= g2
        da //= g2
    return Fraction(na * nb, db * da)


def _div(na: int, da: int, nb: int, db: int) -> Fraction:
    if nb == 0:
        raise ZeroDivisionError("Fraction(" + str(db) + ", 0)")
    g1 = math.gcd(na, nb)
    if g1 > 1:
        na //= g1
        nb //= g1
    g2 = math.gcd(db, da)
    if g2 > 1:
        da //= g2
        db //= g2
    n = na * db
    d = nb * da
    if d < 0:
        n = -n
        d = -d
    return Fraction(n, d)


def _float_ratio(f: float) -> tuple[int, int]:
    if math.isinf(f):
        raise OverflowError("cannot convert Infinity to integer ratio")
    if math.isnan(f):
        raise ValueError("cannot convert NaN to integer ratio")
    # f * 2**k is an integer for the smallest k: f's exact value
    m = f
    d = 1
    while m % 1.0 != 0.0:
        m *= 2.0
        d *= 2
    return int(m), d


def _digits(s: str) -> bool:
    """Digits, with single underscores between them."""
    if s == "" or s[0] == "_" or s[-1] == "_" or "__" in s:
        return False
    return s.replace("_", "").isdigit()


def _parse(text: str) -> tuple[int, int]:
    """CPython's _RATIONAL_FORMAT: [sign] num [/ den], or a decimal with an exponent."""
    bad = "Invalid literal for Fraction: " + repr(text)
    s = text.strip()
    neg = s.startswith("-")
    if s.startswith("-") or s.startswith("+"):
        s = s[1:]
    n = 0
    d = 1
    slash = s.find("/")
    if slash >= 0:
        # spaces may surround the slash
        num = s[:slash].rstrip()
        den = s[slash + 1 :].lstrip()
        if not _digits(num) or not _digits(den):
            raise ValueError(bad)
        n = int(num.replace("_", ""))
        d = int(den.replace("_", ""))
    else:
        exp = 0
        e = s.lower().find("e")
        if e >= 0:
            ex = s[e + 1 :]
            sign = 1
            if ex.startswith("-") or ex.startswith("+"):
                sign = -1 if ex[0] == "-" else 1
                ex = ex[1:]
            if not _digits(ex):
                raise ValueError(bad)
            exp = sign * int(ex.replace("_", ""))
            s = s[:e]
        whole = s
        frac = ""
        dot = s.find(".")
        if dot >= 0:
            whole = s[:dot]
            frac = s[dot + 1 :]
        if whole == "" and frac == "" or whole != "" and not _digits(whole) or frac != "" and not _digits(frac):
            raise ValueError(bad)
        frac = frac.replace("_", "")
        n = int((whole.replace("_", "") + frac) if whole + frac != "" else "0")
        d = 10 ** len(frac)
        if exp >= 0:
            n *= 10**exp
        else:
            d *= 10 ** (-exp)
    return (-n if neg else n), d
