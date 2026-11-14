"""rupy's `decimal`: CPython's `Decimal` in the default context (28 digits,
ROUND_HALF_EVEN), written in rupy after `_pydecimal`. Coefficients are digit
strings, so they have any number of digits.

`Decimal(value)` takes a str, an int, a float (its exact value) or a
Decimal; the context cannot be changed (`getcontext().prec = ...`), so use
`quantize`. NaN and Infinity are not supported."""

ROUND_DOWN = "ROUND_DOWN"
ROUND_HALF_UP = "ROUND_HALF_UP"
ROUND_HALF_EVEN = "ROUND_HALF_EVEN"
ROUND_CEILING = "ROUND_CEILING"
ROUND_FLOOR = "ROUND_FLOOR"
ROUND_UP = "ROUND_UP"
ROUND_HALF_DOWN = "ROUND_HALF_DOWN"
ROUND_05UP = "ROUND_05UP"

_PREC = 28


class DecimalException(ArithmeticError):
    pass


class InvalidOperation(DecimalException):
    pass


class DivisionByZero(ZeroDivisionError):
    pass


# ----------------------------------------- non-negative integers as digit strings


def _strip(a: str) -> str:
    i = 0
    while i < len(a) - 1 and a[i] == "0":
        i += 1
    return a[i:]


def _cmp(a: str, b: str) -> int:
    a = _strip(a)
    b = _strip(b)
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    if a == b:
        return 0
    return -1 if a < b else 1


def _add(a: str, b: str) -> str:
    out: list[str] = []
    i = len(a) - 1
    j = len(b) - 1
    carry = 0
    while i >= 0 or j >= 0 or carry > 0:
        s = carry
        if i >= 0:
            s += ord(a[i]) - 48
        if j >= 0:
            s += ord(b[j]) - 48
        out.append(chr(48 + s % 10))
        carry = s // 10
        i -= 1
        j -= 1
    out.reverse()
    return _strip("".join(out)) if len(out) > 0 else "0"


def _sub(a: str, b: str) -> str:
    """a - b for a >= b"""
    out: list[str] = []
    i = len(a) - 1
    j = len(b) - 1
    borrow = 0
    while i >= 0:
        s = ord(a[i]) - 48 - borrow
        if j >= 0:
            s -= ord(b[j]) - 48
        borrow = 0
        if s < 0:
            s += 10
            borrow = 1
        out.append(chr(48 + s))
        i -= 1
        j -= 1
    out.reverse()
    return _strip("".join(out))


def _mul_small(a: str, m: int) -> str:
    if m == 0:
        return "0"
    out: list[str] = []
    carry = 0
    for k in range(len(a) - 1, -1, -1):
        s = (ord(a[k]) - 48) * m + carry
        out.append(chr(48 + s % 10))
        carry = s // 10
    while carry > 0:
        out.append(chr(48 + carry % 10))
        carry //= 10
    out.reverse()
    return _strip("".join(out))


def _mul(a: str, b: str) -> str:
    total = "0"
    for k in range(len(b)):
        d = ord(b[k]) - 48
        total = _add(total + "0", _mul_small(a, d)) if total != "0" else _mul_small(a, d)
    return total


def _divmod(a: str, b: str) -> tuple[str, str]:
    """(a // b, a % b) for b > 0, by long division."""
    q: list[str] = []
    r = "0"
    for c in a:
        r = _strip(r + c)
        d = 0
        while _cmp(r, b) >= 0:
            r = _sub(r, b)
            d += 1
        q.append(chr(48 + d))
    return _strip("".join(q)) if len(q) > 0 else "0", r


def _shift(a: str, n: int) -> str:
    """a * 10**n"""
    return a if a == "0" else a + "0" * n


# --------------------------------------------------------------------- Decimal


class Decimal:
    def __init__(self, value: str | int | float | Decimal = "0") -> None:
        sign = 0
        coeff = "0"
        exp = 0
        if isinstance(value, int):
            sign = 1 if value < 0 else 0
            coeff = str(abs(value))
        elif isinstance(value, float):
            sign, coeff, exp = _from_float(value)
        elif isinstance(value, str):
            sign, coeff, exp = _parse(value)
        else:
            sign = value._sign
            coeff = value._int
            exp = value._exp
        self._sign: int = sign
        self._int: str = coeff
        self._exp: int = exp

    @staticmethod
    def from_float(f: float) -> Decimal:
        return Decimal(f)

    # ----------------------------------------------------------- inspection

    def __str__(self) -> str:
        coeff = self._int
        leftdigits = self._exp + len(coeff)
        dotplace = leftdigits if self._exp <= 0 and leftdigits > -6 else 1
        intpart = ""
        fracpart = ""
        if dotplace <= 0:
            intpart = "0"
            fracpart = "." + "0" * (-dotplace) + coeff
        elif dotplace >= len(coeff):
            intpart = coeff + "0" * (dotplace - len(coeff))
        else:
            intpart = coeff[:dotplace]
            fracpart = "." + coeff[dotplace:]
        e = ""
        if leftdigits != dotplace:
            n = leftdigits - dotplace
            e = "E" + ("+" if n >= 0 else "") + str(n)
        return ("-" if self._sign == 1 else "") + intpart + fracpart + e

    def __repr__(self) -> str:
        return "Decimal('" + str(self) + "')"

    def is_zero(self) -> bool:
        return self._int == "0"

    def is_signed(self) -> bool:
        return self._sign == 1

    def adjusted(self) -> int:
        return self._exp + len(self._int) - 1

    def __bool__(self) -> bool:
        return self._int != "0"

    def __float__(self) -> float:
        return float(str(self))

    def __int__(self) -> int:
        if self._exp >= 0:
            v = int(_shift(self._int, self._exp))
        else:
            head = self._int[: len(self._int) + self._exp]
            v = int(head) if head != "" else 0
        return -v if self._sign == 1 else v

    def as_tuple(self) -> tuple[int, list[int], int]:
        return (self._sign, [ord(c) - 48 for c in self._int], self._exp)

    # ------------------------------------------------------------- rounding

    def quantize(self, exp: Decimal, rounding: str = ROUND_HALF_EVEN) -> Decimal:
        r = _rescale(self, exp._exp, rounding)
        if len(r._int) > _PREC:
            raise InvalidOperation("[<class 'decimal.InvalidOperation'>]")
        return r

    def normalize(self) -> Decimal:
        if self._int == "0":
            return _dec(self._sign, "0", 0)
        coeff = self._int
        exp = self._exp
        while coeff.endswith("0"):
            coeff = coeff[:-1]
            exp += 1
        return _dec(self._sign, coeff, exp)

    def to_integral_value(self, rounding: str = ROUND_HALF_EVEN) -> Decimal:
        if self._exp >= 0:
            return _dec(self._sign, self._int, self._exp)
        return _rescale(self, 0, rounding)

    def copy_abs(self) -> Decimal:
        return _dec(0, self._int, self._exp)

    def copy_negate(self) -> Decimal:
        return _dec(1 - self._sign, self._int, self._exp)

    # ----------------------------------------------------------- arithmetic

    def __neg__(self) -> Decimal:
        if self._int == "0":
            return _fix(_dec(0, "0", self._exp))
        return _fix(_dec(1 - self._sign, self._int, self._exp))

    def __pos__(self) -> Decimal:
        if self._int == "0":
            return _fix(_dec(0, "0", self._exp))
        return _fix(_dec(self._sign, self._int, self._exp))

    def __abs__(self) -> Decimal:
        return _fix(_dec(0, self._int, self._exp))

    def __add__(self, other: Decimal | int) -> Decimal:
        return _add_dec(self, _conv(other))

    def __radd__(self, other: int) -> Decimal:
        return _add_dec(_conv(other), self)

    def __sub__(self, other: Decimal | int) -> Decimal:
        o = _conv(other)
        return _add_dec(self, _dec(1 - o._sign, o._int, o._exp))

    def __rsub__(self, other: int) -> Decimal:
        return _add_dec(_conv(other), _dec(1 - self._sign, self._int, self._exp))

    def __mul__(self, other: Decimal | int) -> Decimal:
        return _mul_dec(self, _conv(other))

    def __rmul__(self, other: int) -> Decimal:
        return _mul_dec(_conv(other), self)

    def __truediv__(self, other: Decimal | int) -> Decimal:
        return _div_dec(self, _conv(other))

    def __rtruediv__(self, other: int) -> Decimal:
        return _div_dec(_conv(other), self)

    def __floordiv__(self, other: Decimal | int) -> Decimal:
        q, _ = _divmod_dec(self, _conv(other), True)
        return q

    def __rfloordiv__(self, other: int) -> Decimal:
        q, _ = _divmod_dec(_conv(other), self, True)
        return q

    def __mod__(self, other: Decimal | int) -> Decimal:
        _, r = _divmod_dec(self, _conv(other), False)
        return r

    def __rmod__(self, other: int) -> Decimal:
        _, r = _divmod_dec(_conv(other), self, False)
        return r

    def __pow__(self, other: int) -> Decimal:
        if other == 0:
            if self._int == "0":
                raise InvalidOperation("[<class 'decimal.InvalidOperation'>]")
            return _dec(0, "1", 0)
        n = abs(other)
        coeff = "1"
        for _ in range(n):
            coeff = _mul(coeff, self._int)
        sign = self._sign if n % 2 == 1 else 0
        p = _dec(sign, coeff, self._exp * n)
        if other > 0:
            return _fix(p)
        return _div_dec(_dec(0, "1", 0), p)

    # ---------------------------------------------------------- comparisons

    def _compare(self, other: Decimal) -> int:
        if self._int == "0" and other._int == "0":
            return 0
        if self._int == "0":
            return 1 if other._sign == 1 else -1
        if other._int == "0":
            return -1 if self._sign == 1 else 1
        if self._sign != other._sign:
            return -1 if self._sign == 1 else 1
        e = min(self._exp, other._exp)
        c = _cmp(_shift(self._int, self._exp - e), _shift(other._int, other._exp - e))
        return -c if self._sign == 1 else c

    def compare(self, other: Decimal) -> Decimal:
        return Decimal(str(self._compare(other)))

    def __eq__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) == 0

    def __ne__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) != 0

    def __lt__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) < 0

    def __le__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) <= 0

    def __gt__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) > 0

    def __ge__(self, other: Decimal | int) -> bool:
        return self._compare(_conv(other)) >= 0

    def max(self, other: Decimal) -> Decimal:
        m = other if self._compare(other) < 0 else _dec(self._sign, self._int, self._exp)
        return _fix(_dec(m._sign, m._int, m._exp))

    def min(self, other: Decimal) -> Decimal:
        m = other if self._compare(other) > 0 else _dec(self._sign, self._int, self._exp)
        return _fix(_dec(m._sign, m._int, m._exp))


def _dec(sign: int, coeff: str, exp: int) -> Decimal:
    d = Decimal()
    d._sign = sign
    d._int = coeff
    d._exp = exp
    return d


def _conv(x: Decimal | int) -> Decimal:
    if isinstance(x, int):
        return _dec(1 if x < 0 else 0, str(abs(x)), 0)
    else:
        return _dec(x._sign, x._int, x._exp)


def _round_up(mode: str, sign: int, kept: str, first: int, rest_nonzero: bool) -> bool:
    """Does rounding away the digits (first one `first`, the others nonzero or
    not) increment the kept coefficient?"""
    dropped = first != 0 or rest_nonzero
    if mode == ROUND_DOWN:
        return False
    if mode == ROUND_UP:
        return dropped
    if mode == ROUND_CEILING:
        return dropped and sign == 0
    if mode == ROUND_FLOOR:
        return dropped and sign == 1
    if mode == ROUND_HALF_UP:
        return first >= 5
    if mode == ROUND_HALF_DOWN:
        return first > 5 or first == 5 and rest_nonzero
    if mode == ROUND_HALF_EVEN:
        if first > 5 or first == 5 and rest_nonzero:
            return True
        return first == 5 and (ord(kept[-1]) - 48) % 2 == 1 if len(kept) > 0 else False
    if mode == ROUND_05UP:
        last = ord(kept[-1]) - 48 if len(kept) > 0 else 0
        return dropped and (last == 0 or last == 5)
    raise ValueError("rupy's decimal: unknown rounding " + repr(mode))


def _drop(d: Decimal, n: int, mode: str) -> Decimal:
    """d without its last n digits (n > 0), rounded."""
    coeff = d._int
    if n > len(coeff):
        # all digits go (and a zero in front of them)
        coeff = "0" * (n - len(coeff)) + coeff
    kept = coeff[: len(coeff) - n]
    gone = coeff[len(coeff) - n :]
    first = ord(gone[0]) - 48
    rest = gone[1:].strip("0") != ""
    k = kept if kept != "" else "0"
    if _round_up(mode, d._sign, k, first, rest):
        k = _add(k, "1")
    return _dec(d._sign, _strip(k), d._exp + n)


def _rescale(d: Decimal, exp: int, mode: str) -> Decimal:
    if d._int == "0":
        return _dec(d._sign, "0", exp)
    if d._exp >= exp:
        return _dec(d._sign, _shift(d._int, d._exp - exp), exp)
    return _drop(d, exp - d._exp, mode)


def _fix(d: Decimal) -> Decimal:
    """Round to the context's 28 digits."""
    if len(d._int) <= _PREC:
        return d
    r = _drop(d, len(d._int) - _PREC, ROUND_HALF_EVEN)
    if len(r._int) > _PREC:
        r = _dec(r._sign, r._int[:-1], r._exp + 1)
    return r


def _add_dec(a: Decimal, b: Decimal) -> Decimal:
    exp = min(a._exp, b._exp)
    x = _shift(a._int, a._exp - exp)
    y = _shift(b._int, b._exp - exp)
    if a._int == "0" and b._int == "0":
        return _fix(_dec(1 if a._sign == 1 and b._sign == 1 else 0, "0", exp))
    if a._sign == b._sign:
        return _fix(_dec(a._sign, _add(x, y), exp))
    c = _cmp(x, y)
    if c == 0:
        return _fix(_dec(0, "0", exp))
    if c > 0:
        return _fix(_dec(a._sign, _sub(x, y), exp))
    return _fix(_dec(b._sign, _sub(y, x), exp))


def _mul_dec(a: Decimal, b: Decimal) -> Decimal:
    sign = a._sign ^ b._sign
    if a._int == "0" or b._int == "0":
        return _fix(_dec(sign, "0", a._exp + b._exp))
    return _fix(_dec(sign, _mul(a._int, b._int), a._exp + b._exp))


def _div_dec(a: Decimal, b: Decimal) -> Decimal:
    sign = a._sign ^ b._sign
    if b._int == "0":
        if a._int == "0":
            raise InvalidOperation("[<class 'decimal.DivisionUndefined'>]")
        raise DivisionByZero("[<class 'decimal.DivisionByZero'>]")
    if a._int == "0":
        return _fix(_dec(sign, "0", a._exp - b._exp))
    shift = len(b._int) - len(a._int) + _PREC + 1
    exp = a._exp - b._exp - shift
    coeff = "0"
    rem = "0"
    if shift >= 0:
        coeff, rem = _divmod(_shift(a._int, shift), b._int)
    else:
        coeff, rem = _divmod(a._int, _shift(b._int, -shift))
    if rem != "0":
        # a sticky last digit
        if (ord(coeff[-1]) - 48) % 5 == 0:
            coeff = _add(coeff, "1")
    else:
        ideal = a._exp - b._exp
        while exp < ideal and coeff.endswith("0") and coeff != "0":
            coeff = coeff[:-1]
            exp += 1
    return _fix(_dec(sign, coeff, exp))


def _divmod_dec(a: Decimal, b: Decimal, floor: bool) -> tuple[Decimal, Decimal]:
    """Decimal // and %: the quotient truncated toward zero, the remainder with a's sign."""
    if b._int == "0":
        if a._int == "0":
            raise InvalidOperation("[<class 'decimal.DivisionUndefined'>]")
        if floor:
            raise DivisionByZero("[<class 'decimal.DivisionByZero'>]")
        raise InvalidOperation("[<class 'decimal.InvalidOperation'>]")
    sign = a._sign ^ b._sign
    exp = min(a._exp, b._exp)
    x = _shift(a._int, a._exp - exp)
    y = _shift(b._int, b._exp - exp)
    q, r = _divmod(x, y)
    if len(q) > _PREC:
        raise InvalidOperation("[<class 'decimal.DivisionImpossible'>]")
    return _dec(sign, q, 0), _fix(_dec(a._sign, r, exp))


def _parse(value: str) -> tuple[int, str, int]:
    s = value.strip().replace("_", "")
    sign = 0
    if s.startswith("-"):
        sign = 1
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    low = s.lower()
    if low in ["inf", "infinity", "nan", "snan"]:
        raise ValueError("rupy's decimal: NaN and Infinity are not supported")
    exp = 0
    e = low.find("e")
    if e >= 0:
        ex = s[e + 1 :]
        digits_ok = len(ex) > 0 and (ex[0] in "+-" and len(ex) > 1 and ex[1:].isdigit() or ex.isdigit())
        if not digits_ok:
            raise InvalidOperation("[<class 'decimal.ConversionSyntax'>]")
        exp = int(ex)
        s = s[:e]
    intpart = s
    frac = ""
    dot = s.find(".")
    if dot >= 0:
        intpart = s[:dot]
        frac = s[dot + 1 :]
    if intpart + frac == "" or not (intpart == "" or intpart.isdigit()) or not (frac == "" or frac.isdigit()):
        raise InvalidOperation("[<class 'decimal.ConversionSyntax'>]")
    return sign, _strip(intpart + frac), exp - len(frac)


def _from_float(f: float) -> tuple[int, str, int]:
    if f != f or f in [float("inf"), float("-inf")]:
        raise ValueError("rupy's decimal: NaN and Infinity are not supported")
    sign = 1 if f < 0.0 or f == 0.0 and str(f).startswith("-") else 0
    x = abs(f)
    e = 0
    while x % 1.0 != 0.0:
        x *= 2.0
        e -= 1
    while x >= 9007199254740992.0:
        x /= 2.0
        e += 1
    coeff = str(int(x))
    exp = 0
    if e >= 0:
        for _ in range(e):
            coeff = _mul_small(coeff, 2)
    else:
        for _ in range(-e):
            coeff = _mul_small(coeff, 5)
        exp = e
    return sign, coeff, exp
