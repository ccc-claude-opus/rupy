"""Numbers formatted and printed as R does (`format`, `print` of numeric
vectors, named vectors and matrices), following R's formatReal: the fewest
significant digits (up to `digits`) that show every element, a common number
of decimals, and fixed or scientific notation, whichever is narrower."""

import math


def _sci(x: float, digits: int) -> tuple[int, int, bool]:
    """(the decimal exponent, the significant digits needed, whether rounding
    to `digits` digits reached the next power of ten) of |x|."""
    if x == 0.0:
        return (0, 1, False)
    s = format(abs(x), "." + str(digits - 1) + "e")
    mant, ex = s.split("e")
    kp = int(ex)
    ds = mant.replace(".", "").rstrip("0")
    nsig = max(1, len(ds))
    # scientific notation rounded up to the next power of ten, but fixed
    # notation (showing more digits) would not (R's "roundingwidens")
    rgt = min(22, max(0, digits - kp))
    widens = 0 < kp <= 22 and abs(x) < 10.0**kp - 0.5 / 10.0**rgt
    return (kp, nsig, widens)


class Fmt:
    """A common format: width, decimals, scientific (with exponent digits)."""

    def __init__(self, w: int, d: int, e: int) -> None:
        self.w = w
        self.d = d
        self.e = e


def format_info(xs: list[float], digits: int = 7, nsmall: int = 0) -> Fmt:
    """R's formatReal: the format of a numeric vector."""
    neg = 0
    rgt = -1000000
    mxl = -1000000
    mxsl = -1000000
    mxns = -1000000
    mnl = 1000000
    special = 0
    for x in xs:
        if math.isnan(x):
            special = max(special, 3 if x != x else 2)
            continue
        if math.isinf(x):
            special = max(special, 4 if x < 0.0 else 3)
            continue
        kp, nsig, widens = _sci(x, digits)
        left = kp + 1
        if widens:
            left -= 1
        isneg = 1 if x < 0.0 else 0
        sleft = isneg + (1 if left <= 0 else left)
        right = nsig - left
        if isneg:
            neg = 1
        rgt = max(rgt, right)
        mxl = max(mxl, left)
        mnl = min(mnl, left)
        mxsl = max(mxsl, sleft)
        mxns = max(mxns, nsig)
    if mxns == -1000000:
        return Fmt(special, 0, 0)
    if mxl < 0:
        mxsl = 1 + neg
    if rgt < 0:
        rgt = 0
    wf = mxsl + rgt + (1 if rgt != 0 else 0)
    e = 2 if mxl > 100 or mnl <= -99 else 1
    d = mxns - 1
    w = neg + (1 if d > 0 else 0) + d + 4 + e
    if wf <= w:
        if nsmall > rgt:
            rgt = nsmall
            wf = mxsl + rgt + (1 if rgt != 0 else 0)
        return Fmt(max(wf, special), rgt, 0)
    return Fmt(max(w, special), d, e)


def encode(x: float, f: Fmt) -> str:
    """One number in format f (right-justified to its width)."""
    if math.isnan(x):
        s = "NaN"
    elif math.isinf(x):
        s = "Inf" if x > 0.0 else "-Inf"
    elif f.e > 0:
        s = format(x, "." + str(f.d) + "e")
        mant, ex = s.split("e")
        sign = ex[0]
        digs = ex[1:].lstrip("0")
        while len(digs) < 2:
            digs = "0" + digs
        s = mant + "e" + sign + digs
    else:
        s = format(x, "." + str(f.d) + "f")
    return " " * (f.w - len(s)) + s


def format_vec(xs: list[float], digits: int = 7, nsmall: int = 0) -> list[str]:
    """R's `format(x, digits)` of a numeric vector: strings of one width."""
    f = format_info(xs, digits, nsmall)
    return [encode(x, f) for x in xs]


def format_num(x: float, digits: int = 7) -> str:
    """One number as R formats it (`format(x, digits = digits)`)."""
    return format_vec([x], digits)[0]


def signif(x: float, digits: int = 6) -> float:
    """R's `signif`: x rounded to `digits` significant digits."""
    if x == 0.0 or math.isnan(x) or math.isinf(x):
        return x
    return float(format(x, "." + str(digits - 1) + "e"))


def print_vector(xs: list[float], digits: int = 7, width: int = 80) -> str:
    """R's `print` of an unnamed numeric vector: `[1] ...` lines."""
    if len(xs) == 0:
        return "numeric(0)"
    cells = format_vec(xs, digits)
    w = len(cells[0])
    lab = len(f"[{len(xs)}]")
    per = max(1, (width - lab) // (w + 1))
    lines: list[str] = []
    for i in range(0, len(xs), per):
        tag = f"[{i + 1}]"
        lines.append(" " * (lab - len(tag)) + tag + " " + " ".join(cells[i : i + per]))
    return "\n".join(lines)


def print_named(names: list[str], cells: list[str], width: int = 80) -> str:
    """R's `print` of a named vector whose values are already formatted:
    each column as wide as its widest name or value, right-justified."""
    w = max([len(c) for c in cells] + [len(n) for n in names])
    per = max(1, width // (w + 1))
    lines: list[str] = []
    for i in range(0, len(cells), per):
        # every column is followed by R's gap of one space
        lines.append("".join(" " * (w - len(n)) + n + " " for n in names[i : i + per]))
        lines.append("".join(" " * (w - len(c)) + c + " " for c in cells[i : i + per]))
    return "\n".join(lines)


def print_named_num(names: list[str], xs: list[float], digits: int = 7, width: int = 80) -> str:
    """R's `print` of a named numeric vector."""
    return print_named(names, format_vec(xs, digits), width)


def format_pval(p: float, digits: int = 4) -> str:
    """R's `format.pval(p, digits)`: `< 2.2e-16` below the machine epsilon."""
    eps = 2.220446049250313e-16
    if math.isnan(p):
        return "NA"
    if p < eps:
        return "< " + format_num(eps, digits)
    return format_num(p, digits)
