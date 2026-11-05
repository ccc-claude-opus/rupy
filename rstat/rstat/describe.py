"""Descriptive statistics with R's algorithms (two-pass means and variances,
the nine quantile types) and R's printed form (named vectors, `summary`)."""

import math

from rstat.rformat import format_vec, format_num, print_named, signif


class Named:
    """A named numeric vector, printed as R prints one."""

    def __init__(self, names: list[str], values: list[float], digits: int = 7) -> None:
        self.names = names
        self.values = values
        self.digits = digits

    def __str__(self) -> str:
        return print_named(self.names, format_vec(self.values, self.digits))

    def __repr__(self) -> str:
        return self.__str__()

    def __getitem__(self, i: int) -> float:
        return self.values[i]

    def __len__(self) -> int:
        return len(self.values)

    def get(self, name: str) -> float:
        """The value named `name`."""
        return self.values[self.names.index(name)]


def _check(x: list[float]) -> None:
    if len(x) == 0:
        raise ValueError("'x' must have at least one element")


def mean(x: list[float]) -> float:
    """R's mean: the sum over n, corrected by a second pass."""
    _check(x)
    n = float(len(x))
    s = 0.0
    for v in x:
        s += v
    s /= n
    if not math.isinf(s) and not math.isnan(s):
        t = 0.0
        for v in x:
            t += v - s
        s += t / n
    return s


def var(x: list[float]) -> float:
    """The sample variance (denominator n - 1)."""
    n = len(x)
    if n < 2:
        return math.nan
    m = mean(x)
    s = 0.0
    for v in x:
        s += (v - m) * (v - m)
    return s / float(n - 1)


def sd(x: list[float]) -> float:
    """The sample standard deviation."""
    return math.sqrt(var(x))


def cov(x: list[float], y: list[float]) -> float:
    """The sample covariance."""
    if len(x) != len(y):
        raise ValueError("incompatible dimensions")
    n = len(x)
    if n < 2:
        return math.nan
    mx = mean(x)
    my = mean(y)
    s = 0.0
    for i in range(n):
        s += (x[i] - mx) * (y[i] - my)
    return s / float(n - 1)


def rank(x: list[float]) -> list[float]:
    """Ranks, ties getting their average rank (R's `rank`)."""
    n = len(x)
    order = sorted(range(n), key=lambda i: x[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and x[order[j + 1]] == x[order[i]]:
            j += 1
        avg = (float(i) + float(j)) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def cor(x: list[float], y: list[float], method: str = "pearson") -> float:
    """The correlation of x and y: "pearson", "spearman" or "kendall" (tau-b)."""
    if len(x) != len(y):
        raise ValueError("incompatible dimensions")
    if method == "spearman":
        return cor(rank(x), rank(y), "pearson")
    if method == "kendall":
        n = len(x)
        conc = 0.0
        tx = 0.0
        ty = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                a = x[i] - x[j]
                b = y[i] - y[j]
                sa = 1.0 if a > 0.0 else (-1.0 if a < 0.0 else 0.0)
                sb = 1.0 if b > 0.0 else (-1.0 if b < 0.0 else 0.0)
                conc += sa * sb
                tx += sa * sa
                ty += sb * sb
        return conc / math.sqrt(tx * ty)
    mx = mean(x)
    my = mean(y)
    sxy = 0.0
    sxx = 0.0
    syy = 0.0
    for i in range(len(x)):
        dx = x[i] - mx
        dy = y[i] - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    r = sxy / math.sqrt(sxx * syy)
    return max(-1.0, min(1.0, r))


def median(x: list[float]) -> float:
    """The median."""
    _check(x)
    s = sorted(x)
    n = len(s)
    half = (n + 1) // 2
    if n % 2 == 1:
        return s[half - 1]
    return mean([s[half - 1], s[half]])


def quantile(x: list[float], probs: list[float] | None = None, type: int = 7) -> Named:
    """Sample quantiles of the nine types of R's `quantile` (default 7; probs
    default 0, 0.25, 0.5, 0.75, 1), named as R names them ("25%")."""
    _check(x)
    ps = [0.0, 0.25, 0.5, 0.75, 1.0] if probs is None else probs
    s = sorted(x)
    n = len(s)
    out: list[float] = []
    eps = 2.220446049250313e-16
    for p in ps:
        if p < 0.0 or p > 1.0:
            raise ValueError("'probs' outside [0,1]")
        if type == 7:
            index = 1.0 + float(max(n - 1, 0)) * p
            lo = int(math.floor(index))
            hi = int(math.ceil(index))
            q = s[lo - 1]
            h = index - float(lo)
            if index > float(lo) and s[hi - 1] != q:
                q = (1.0 - h) * q + h * s[hi - 1]
            out.append(q)
            continue
        if type <= 3:
            nppm = float(n) * p - 0.5 if type == 3 else float(n) * p
            j = int(math.floor(nppm + 4.0 * eps))
            if type == 1:
                h = 1.0 if nppm > float(j) else 0.0
            elif type == 2:
                h = ((1.0 if nppm > float(j) else 0.0) + 1.0) / 2.0
            else:
                h = 1.0 if (nppm != float(j) or j % 2 == 1) else 0.0
        else:
            a = 0.0
            b = 1.0
            if type == 5:
                a = 0.5
                b = 0.5
            elif type == 6:
                a = 0.0
                b = 0.0
            elif type == 8:
                a = 1.0 / 3.0
                b = 1.0 / 3.0
            elif type == 9:
                a = 3.0 / 8.0
                b = 3.0 / 8.0
            fuzz = 4.0 * eps
            nppm = a + p * (float(n) + 1.0 - a - b)
            j = int(math.floor(nppm + fuzz))
            h = nppm - float(j)
            if abs(h) < fuzz:
                h = 0.0
        # x padded as R pads it: x[1], x[1], x..., x[n], x[n]
        xs = [s[0], s[0]] + s + [s[n - 1], s[n - 1]]
        lo_v = xs[j + 1]
        hi_v = xs[j + 2]
        if h == 1.0:
            q = hi_v
        elif 0.0 < h < 1.0 and lo_v != hi_v:
            q = (1.0 - h) * lo_v + h * hi_v
        else:
            q = lo_v
        out.append(q)
    names = [_trim_pct(100.0 * p) for p in ps]
    return Named(names, out)


def _trim_pct(v: float) -> str:
    """`paste0(formatC(100 * probs, format = "fg", width = 1, digits = 7), "%")`."""
    s = format_num(v, 7).strip()
    if "." in s and "e" not in s:
        s = s.rstrip("0").rstrip(".")
    return s + "%"


def IQR(x: list[float], type: int = 7) -> float:
    """The interquartile range."""
    q = quantile(x, [0.25, 0.75], type)
    return q[1] - q[0]


def mad(x: list[float], constant: float = 1.4826) -> float:
    """The median absolute deviation (scaled to estimate σ of normal data)."""
    m = median(x)
    return constant * median([abs(v - m) for v in x])


def fivenum(x: list[float]) -> list[float]:
    """Tukey's five numbers: minimum, lower hinge, median, upper hinge, maximum."""
    _check(x)
    s = sorted(x)
    n = len(s)
    n4 = float(math.floor((float(n) + 3.0) / 2.0)) / 2.0
    d = [1.0, n4, (float(n) + 1.0) / 2.0, float(n) + 1.0 - n4, float(n)]
    out: list[float] = []
    for v in d:
        lo = int(math.floor(v))
        hi = int(math.ceil(v))
        out.append(0.5 * (s[lo - 1] + s[hi - 1]))
    return out


def scale(x: list[float]) -> list[float]:
    """x centered by its mean and divided by its standard deviation."""
    m = mean(x)
    s = sd(x)
    return [(v - m) / s for v in x]


def weighted_mean(x: list[float], w: list[float]) -> float:
    """The weighted mean."""
    sw = 0.0
    swx = 0.0
    for i in range(len(x)):
        sw += w[i]
        swx += w[i] * x[i]
    return swx / sw


class Summary:
    """`summary(x)` of a numeric vector, printed as R prints it."""

    def __init__(self, values: list[float]) -> None:
        self.names = ["Min.", "1st Qu.", "Median", "Mean", "3rd Qu.", "Max."]
        self.values = values

    def __str__(self) -> str:
        # R's format.summaryDefault: 4 significant digits, after zapping
        # values tiny next to the largest
        digits = 4
        mx = max(abs(v) for v in self.values)
        zap = [v for v in self.values]
        if mx > 0.0:
            lim = 10.0 ** (float(math.floor(math.log10(mx))) - 7.0 - digits + 1.0)
            zap = [0.0 if abs(v) < lim else v for v in self.values]
        return print_named(self.names, format_vec(zap, digits))

    def __repr__(self) -> str:
        return self.__str__()

    def get(self, name: str) -> float:
        return self.values[self.names.index(name)]


def summary(x: list[float]) -> Summary:
    """Minimum, quartiles, mean and maximum (R's `summary` of a numeric vector)."""
    q = quantile(x)
    return Summary([q[0], q[1], q[2], mean(x), q[3], q[4]])


def range_(x: list[float]) -> list[float]:
    """`range(x)`: the minimum and the maximum."""
    return [min(x), max(x)]


def round_(x: float, digits: int = 0) -> float:
    """R's `round` (to even, at the decimal digit)."""
    return round(x, digits)


def signif_(x: float, digits: int = 6) -> float:
    """R's `signif`."""
    return signif(x, digits)
