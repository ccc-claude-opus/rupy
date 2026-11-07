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


class Table:
    """A contingency table (the result of R's `table`)."""

    def __init__(self, counts: list[float], dim: list[int], dimnames: list[list[str]], names: list[str]) -> None:
        self.counts = counts
        self.dim = dim
        self.dimnames = dimnames
        self.names = names

    def __str__(self) -> str:
        return _print_table(self.counts, self.dim, self.dimnames, self.names)

    def __repr__(self) -> str:
        return self.__str__()

    def total(self) -> float:
        """The sum of the counts."""
        s = 0.0
        for c in self.counts:
            s += c
        return s

    def as_list(self) -> list[float]:
        """The counts, as R stores them (the first dimension varies fastest)."""
        return list(self.counts)


def _levels(xs: list[str]) -> list[str]:
    """The distinct values of a vector, sorted (R's factor levels)."""
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    out.sort()
    return out


def table(x: list[str], y: list[str] | None = None, x_name: str = "x", y_name: str = "y") -> Table:
    """The contingency table of the values of x (and of y), as R's `table`."""
    if len(x) == 0:
        raise ValueError("no inputs")
    lx = _levels(x)
    if y is None:
        counts = [0.0] * len(lx)
        for v in x:
            counts[lx.index(v)] += 1.0
        return Table(counts, [len(lx)], [lx], [x_name])
    if len(x) != len(y):
        raise ValueError("'x' and 'y' must have the same length")
    ly = _levels(y)
    counts = [0.0] * (len(lx) * len(ly))
    for i in range(len(x)):
        a = lx.index(x[i])
        b = ly.index(y[i])
        counts[a + b * len(lx)] += 1.0
    return Table(counts, [len(lx), len(ly)], [lx, ly], [x_name, y_name])


def _print_table(counts: list[float], dim: list[int], dimnames: list[list[str]], names: list[str]) -> str:
    """The table as R prints it."""
    if len(dim) == 1:
        labels = dimnames[0]
        cells = format_vec(counts, 7)
        w1 = 1
        for c in cells:
            if len(c) > w1:
                w1 = len(c)
        for l in labels:
            if len(l) > w1:
                w1 = len(l)
        lines = []
        if len(names) > 0:
            lines.append(names[0])
        if labels:
            lines.append(" ".join(l.rjust(w1) for l in labels) + " ")
        lines.append(" ".join(c.rjust(w1) for c in cells) + " ")
        return "\n".join(lines)
    # a two-dimensional table, printed as R prints a matrix with dimnames
    nr = dim[0]
    nc = dim[1]
    rl = dimnames[0]
    cl = dimnames[1]
    rn = ""
    cn = ""
    if len(names) > 0:
        rn = names[0]
    if len(names) > 1:
        cn = names[1]
    # the width of the row labels
    rlabw = 0
    for l in rl:
        if len(l) > rlabw:
            rlabw = len(l)
    lbloff = 0
    if len(names) > 0:
        rnw = len(rn)
        if rnw < rlabw + 2:
            lbloff = 2
        else:
            lbloff = rnw - rlabw
        rlabw += lbloff
    # the width of the columns
    wcols = [0] * nc
    for j in range(nc):
        col: list[float] = []
        for i in range(nr):
            col.append(counts[i + j * nr])
        cw = len(format_vec(col, 7)[0])
        if j < len(cl) and len(cl[j]) > cw:
            cw = len(cl[j])
        wcols[j] = cw + 1
    cells = [format_num(c, 7) for c in counts]
    lines = []
    lines.append(" " * rlabw + cn)
    if rn != "":
        lines.append(rn.ljust(rlabw))
    else:
        lines.append(" " * rlabw)
    for j in range(nc):
        if j < len(cl):
            lines[-1] += " " * (wcols[j] - len(cl[j])) + cl[j]
        else:
            lines[-1] += " " * wcols[j]
    for i in range(nr):
        line = " " * lbloff + rl[i] + " " * (rlabw - len(rl[i]) - lbloff)
        for j in range(nc):
            line += cells[i + j * nr].rjust(wcols[j])
        lines.append(line)
    return "\n".join(lines)
