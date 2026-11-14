"""rupy's `statistics`: CPython's `statistics`, written in rupy.

CPython sums the data exactly with fractions and rounds once; here the exact
sums are expansions of floats (lists of non-overlapping floats, as in
`math.fsum`), so `mean`, `variance`, `stdev`, ... give CPython's floats to the
last bit. Data are lists of floats: `mean`, `median`, `variance`, ... of ints
would be ints or floats depending on the values in CPython. `mode`,
`multimode`, `median_low` and `median_high` take any list."""

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass


class StatisticsError(ValueError):
    pass


# ---------------------------------------------------------------- exact sums


def _grow(ps: list[float], x: float) -> list[float]:
    """The expansion ps + x (Shewchuk's algorithm, as in math.fsum)."""
    out: list[float] = []
    for y in ps:
        if abs(x) < abs(y):
            x, y = y, x
        hi = x + y
        lo = y - (hi - x)
        if lo != 0.0:
            out.append(lo)
        x = hi
    out.append(x)
    return out


def _add_product(ps: list[float], a: float, b: float) -> list[float]:
    """The expansion ps + a * b, exactly."""
    p = a * b
    return _grow(_grow(ps, p), math.fma(a, b, -p))


def _times(ps: list[float], c: float) -> list[float]:
    """The expansion ps * c, exactly."""
    out: list[float] = []
    for p in ps:
        out = _add_product(out, p, c)
    return out


def _product(ps: list[float], qs: list[float]) -> list[float]:
    out: list[float] = []
    for p in ps:
        for q in qs:
            out = _add_product(out, p, q)
    return out


def _minus(ps: list[float], qs: list[float]) -> list[float]:
    out = ps
    for q in qs:
        out = _grow(out, -q)
    return out


def _is_even(q: float) -> bool:
    """Is the last bit of q's significand 0?"""
    return (q / math.ulp(q)) % 2.0 == 0.0


def _div(num: list[float], den: list[float]) -> float:
    """num / den rounded once (den > 0)."""
    q = math.fsum(num) / math.fsum(den)
    if q == 0.0 or not math.isfinite(q):
        return q
    while True:
        up = math.nextafter(q, math.inf)
        c = math.fsum(_minus(num, _product([q, (up - q) / 2.0], den)))
        if c > 0.0 or c == 0.0 and not _is_even(q):
            q = up
            continue
        down = math.nextafter(q, -math.inf)
        c = math.fsum(_minus(num, _product([q, (down - q) / 2.0], den)))
        if c < 0.0 or c == 0.0 and not _is_even(q):
            q = down
            continue
        return q


def _sqrt_div(num: list[float], den: list[float]) -> float:
    """sqrt(num / den) rounded once (num >= 0, den > 0)."""
    q = math.sqrt(_div(num, den))
    if q == 0.0 or not math.isfinite(q):
        return q
    while True:
        up = math.nextafter(q, math.inf)
        h = (up - q) / 2.0
        sq = _add_product(_add_product(_add_product([], q, q), 2.0 * q, h), h, h)
        c = math.fsum(_minus(num, _product(sq, den)))
        if c > 0.0 or c == 0.0 and not _is_even(q):
            q = up
            continue
        down = math.nextafter(q, -math.inf)
        h = (down - q) / 2.0
        sq = _add_product(_add_product(_add_product([], q, q), 2.0 * q, h), h, h)
        c = math.fsum(_minus(num, _product(sq, den)))
        if c < 0.0 or c == 0.0 and not _is_even(q):
            q = down
            continue
        return q


def _floats(data: list[float] | list[int]) -> list[float]:
    """The data as floats: ints beyond 2**53 are not exact as floats."""
    out: list[float] = []
    for x in data:
        if isinstance(x, int):
            if abs(x) > 9007199254740992:
                raise OverflowError("rupy's statistics: int too large to convert to float exactly")
        out.append(float(x))
    return out


def _exact(r: float) -> float:
    """A result of finite data: an overflow inside the exact sums is not CPython's result."""
    if not math.isfinite(r):
        raise OverflowError("rupy's statistics: data too large for exact sums")
    return r


def _nonfinite(data: list[float]) -> float | None:
    """The sum of the infinities and nans of the data (CPython keeps them apart), if any."""
    s = 0.0
    found = False
    for x in data:
        if not math.isfinite(x):
            s += x
            found = True
    if found:
        return s
    return None


def _sums(data: list[float]) -> tuple[list[float], list[float]]:
    """The exact sums of x and of x * x."""
    sx: list[float] = []
    sxx: list[float] = []
    for x in data:
        sx = _grow(sx, x)
        sxx = _add_product(sxx, x, x)
    return sx, sxx


def _ssd_n(data: list[float]) -> list[float]:
    """n * (sum of squared deviations from the mean), exactly: n * Sxx - Sx * Sx."""
    sx, sxx = _sums(data)
    return _minus(_times(sxx, float(len(data))), _product(sx, sx))


def _ss_about(data: list[float], c: float) -> list[float]:
    """The exact sum of (x - c) ** 2, each term rounded as in CPython."""
    s: list[float] = []
    for x in data:
        d = x - c
        s = _grow(s, d * d)
    return s


def _sumprod(p: list[float], q: list[float]) -> float:
    """math.sumprod: the exact sum of products, rounded once."""
    if len(p) != len(q):
        raise ValueError("Inputs are not the same length")
    ps: list[float] = []
    plain = 0.0
    for i in range(len(p)):
        x = p[i] * q[i]
        plain += x
        if math.isfinite(x):
            ps = _add_product(ps, p[i], q[i])
    if not math.isfinite(plain):
        return plain
    return math.fsum(ps)


# ------------------------------------------------------------------- averages


def mean(data: list[float]) -> float:
    n = len(data)
    if n < 1:
        raise StatisticsError("mean requires at least one data point")
    s = _nonfinite(data)
    if s is not None:
        return s / n
    sx, _ = _sums(data)
    return _exact(_div(sx, [float(n)]))


def fmean(data: list[float] | list[int], weights: list[float] | None = None) -> float:
    xs = _floats(data)
    if weights is None:
        n = len(xs)
        if n == 0:
            raise StatisticsError("fmean requires at least one data point")
        return math.fsum(xs) / n
    if len(xs) != len(weights):
        raise StatisticsError("data and weights must be the same length")
    num = _sumprod(xs, weights)
    den = math.fsum(weights)
    if den == 0.0:
        raise StatisticsError("sum of weights must be non-zero")
    return num / den


def geometric_mean(data: list[float] | list[int]) -> float:
    n = 0
    found_zero = False
    logs: list[float] = []
    for x in _floats(data):
        n += 1
        if x > 0.0 or math.isnan(x):
            logs.append(math.log(x))
        elif x == 0.0:
            found_zero = True
        else:
            raise StatisticsError("('No negative inputs allowed', " + repr(x) + ")")
    total = math.fsum(logs)
    if n == 0:
        raise StatisticsError("Must have a non-empty dataset")
    if math.isnan(total):
        return math.nan
    if found_zero:
        if total == math.inf:
            return math.nan
        return 0.0
    return math.exp(total / n)


def harmonic_mean(data: list[float], weights: list[float] | None = None) -> float:
    errmsg = "harmonic mean does not support negative values"
    n = len(data)
    if n < 1:
        raise StatisticsError("harmonic_mean requires at least one data point")
    if n == 1 and weights is None:
        if data[0] < 0.0:
            raise StatisticsError(errmsg)
        return data[0]
    ws: list[float] = []
    sum_weights: list[float] = [float(n)]
    if weights is None:
        ws = [1.0] * n
    else:
        if len(weights) != n:
            raise StatisticsError("Number of weights does not match data size")
        sum_weights = []
        for w in weights:
            if w < 0.0:
                raise StatisticsError(errmsg)
            sum_weights = _grow(sum_weights, w)
        ws = weights
    total: list[float] = []
    for i in range(n):
        x = data[i]
        if x < 0.0:
            raise StatisticsError(errmsg)
        if ws[i] != 0.0:
            if x == 0.0:
                return 0.0
            total = _grow(total, ws[i] / x)
    if math.fsum(total) <= 0.0:
        raise StatisticsError("Weighted sum must be positive")
    return _div(sum_weights, total)


def median(data: list[float]) -> float:
    xs = sorted(data)
    n = len(xs)
    if n == 0:
        raise StatisticsError("no median for empty data")
    if n % 2 == 1:
        return xs[n // 2]
    i = n // 2
    return (xs[i - 1] + xs[i]) / 2


def median_low[T](data: list[T]) -> T:
    xs = sorted(data)
    n = len(xs)
    if n == 0:
        raise StatisticsError("no median for empty data")
    if n % 2 == 1:
        return xs[n // 2]
    return xs[n // 2 - 1]


def median_high[T](data: list[T]) -> T:
    xs = sorted(data)
    n = len(xs)
    if n == 0:
        raise StatisticsError("no median for empty data")
    return xs[n // 2]


def median_grouped(data: list[float] | list[int], interval: float = 1.0) -> float:
    xs = sorted(_floats(data))
    n = len(xs)
    if n == 0:
        raise StatisticsError("no median for empty data")
    x = xs[n // 2]
    i = bisect_left(xs, x)
    j = bisect_right(xs, x)
    L = x - interval / 2
    cf = i
    f = j - i
    return L + interval * (n / 2 - cf) / f


def _counts[T](data: list[T]) -> tuple[list[T], list[int]]:
    """The distinct values in the order they first occur, and their counts."""
    values: list[T] = []
    counts: list[int] = []
    for x in data:
        found = False
        for k in range(len(values)):
            if values[k] == x:
                counts[k] += 1
                found = True
                break
        if not found:
            values.append(x)
            counts.append(1)
    return values, counts


def mode[T](data: list[T]) -> T:
    values, counts = _counts(data)
    if len(values) == 0:
        raise StatisticsError("no mode for empty data")
    best = 0
    for k in range(1, len(values)):
        if counts[k] > counts[best]:
            best = k
    return values[best]


def multimode[T](data: list[T]) -> list[T]:
    values, counts = _counts(data)
    if len(values) == 0:
        return []
    top = max(counts)
    return [values[k] for k in range(len(values)) if counts[k] == top]


def quantiles(data: list[float], *, n: int = 4, method: str = "exclusive") -> list[float]:
    if n < 1:
        raise StatisticsError("n must be at least 1")
    xs = sorted(data)
    ld = len(xs)
    if ld < 2:
        if ld == 1:
            return xs * (n - 1)
        raise StatisticsError("must have at least one data point")
    result: list[float] = []
    if method == "inclusive":
        m = ld - 1
        for i in range(1, n):
            j, delta = divmod(i * m, n)
            result.append((xs[j] * (n - delta) + xs[j + 1] * delta) / n)
        return result
    if method == "exclusive":
        m = ld + 1
        for i in range(1, n):
            j = i * m // n
            j = 1 if j < 1 else ld - 1 if j > ld - 1 else j
            delta = i * m - j * n
            result.append((xs[j - 1] * (n - delta) + xs[j] * delta) / n)
        return result
    raise ValueError("Unknown method: " + repr(method))


# --------------------------------------------------------------------- spread


def variance(data: list[float], xbar: float | None = None) -> float:
    n = len(data)
    if xbar is not None:
        if n < 2:
            raise StatisticsError("variance requires at least two data points")
        sq = _nonfinite([(x - xbar) * (x - xbar) for x in data])
        if sq is not None:
            return sq / (n - 1)
        return _exact(_div(_ss_about(data, xbar), [float(n - 1)]))
    if n < 2:
        raise StatisticsError("variance requires at least two data points")
    s = _nonfinite(data)
    if s is not None:
        return s / (n - 1)
    return _exact(_div(_ssd_n(data), [float(n) * float(n - 1)]))


def pvariance(data: list[float], mu: float | None = None) -> float:
    n = len(data)
    if mu is not None:
        if n < 1:
            raise StatisticsError("pvariance requires at least one data point")
        sq = _nonfinite([(x - mu) * (x - mu) for x in data])
        if sq is not None:
            return sq / n
        return _exact(_div(_ss_about(data, mu), [float(n)]))
    if n < 1:
        raise StatisticsError("pvariance requires at least one data point")
    s = _nonfinite(data)
    if s is not None:
        return s / n
    return _exact(_div(_ssd_n(data), [float(n) * float(n)]))


def stdev(data: list[float] | list[int], xbar: float | None = None) -> float:
    xs = _floats(data)
    n = len(xs)
    if n < 2:
        raise StatisticsError("stdev requires at least two data points")
    if xbar is not None:
        ss = _ss_about(xs, xbar)
        if not math.isfinite(math.fsum(ss)):
            raise ValueError("inf or nan encountered in data")
        return _exact(_sqrt_div(ss, [float(n - 1)]))
    if _nonfinite(xs) is not None:
        raise ValueError("inf or nan encountered in data")
    return _exact(_sqrt_div(_ssd_n(xs), [float(n) * float(n - 1)]))


def pstdev(data: list[float] | list[int], mu: float | None = None) -> float:
    xs = _floats(data)
    n = len(xs)
    if n < 1:
        raise StatisticsError("pstdev requires at least one data point")
    if mu is not None:
        ss = _ss_about(xs, mu)
        if not math.isfinite(math.fsum(ss)):
            raise ValueError("inf or nan encountered in data")
        return _exact(_sqrt_div(ss, [float(n)]))
    if _nonfinite(xs) is not None:
        raise ValueError("inf or nan encountered in data")
    return _exact(_sqrt_div(_ssd_n(xs), [float(n) * float(n)]))


# ------------------------------------------------------------------ relations


def covariance(x: list[float], y: list[float]) -> float:
    n = len(x)
    if len(y) != n:
        raise StatisticsError("covariance requires that both inputs have same number of data points")
    if n < 2:
        raise StatisticsError("covariance requires at least two data points")
    xbar = math.fsum(x) / n
    ybar = math.fsum(y) / n
    sxy = _sumprod([xi - xbar for xi in x], [yi - ybar for yi in y])
    return sxy / (n - 1)


def _rank(data: list[float], start: float) -> list[float]:
    """Ranks from start, ties averaged."""
    order = sorted(range(len(data)), key=lambda k: data[k])
    result = [0.0] * len(data)
    i = start - 1
    a = 0
    while a < len(order):
        b = a
        while b < len(order) and data[order[b]] == data[order[a]]:
            b += 1
        size = b - a
        rank = i + (size + 1) / 2
        for k in range(a, b):
            result[order[k]] = rank
        i += size
        a = b
    return result


def _sqrtprod(x: float, y: float) -> float:
    h = math.sqrt(x * y)
    if not math.isfinite(h):
        if math.isinf(h) and not math.isinf(x) and not math.isinf(y):
            scale = 2.0**-512
            return _sqrtprod(scale * x, scale * y) / scale
        return h
    if h == 0.0:
        if x != 0.0 and y != 0.0:
            scale = 2.0**537
            return _sqrtprod(scale * x, scale * y) / scale
        return h
    d = _sumprod([x, h], [y, -h])
    return h + d / (2.0 * h)


def correlation(x: list[float], y: list[float], *, method: str = "linear") -> float:
    n = len(x)
    if len(y) != n:
        raise StatisticsError("correlation requires that both inputs have same number of data points")
    if n < 2:
        raise StatisticsError("correlation requires at least two data points")
    if method != "linear" and method != "ranked":
        raise ValueError("Unknown method: " + repr(method))
    xs: list[float] = []
    ys: list[float] = []
    if method == "ranked":
        start = (n - 1) / -2
        xs = _rank(x, start)
        ys = _rank(y, start)
    else:
        xbar = math.fsum(x) / n
        ybar = math.fsum(y) / n
        xs = [xi - xbar for xi in x]
        ys = [yi - ybar for yi in y]
    sxy = _sumprod(xs, ys)
    sxx = _sumprod(xs, xs)
    syy = _sumprod(ys, ys)
    p = _sqrtprod(sxx, syy)
    if p == 0.0:
        raise StatisticsError("at least one of the inputs is constant")
    return sxy / p


@dataclass(frozen=True)
class LinearRegression:
    slope: float
    intercept: float


def linear_regression(x: list[float], y: list[float], *, proportional: bool = False) -> LinearRegression:
    n = len(x)
    if len(y) != n:
        raise StatisticsError("linear regression requires that both inputs have same number of data points")
    if n < 2:
        raise StatisticsError("linear regression requires at least two data points")
    xs = x
    ys = y
    xbar = 0.0
    ybar = 0.0
    if not proportional:
        xbar = math.fsum(x) / n
        ybar = math.fsum(y) / n
        xs = [xi - xbar for xi in x]
        ys = [yi - ybar for yi in y]
    sxy = _sumprod(xs, ys) + 0.0
    sxx = _sumprod(xs, xs)
    if sxx == 0.0:
        raise StatisticsError("x is constant")
    slope = sxy / sxx
    intercept = 0.0 if proportional else ybar - slope * xbar
    return LinearRegression(slope, intercept)


# ------------------------------------------------------- normal distribution

_SQRT2 = 1.4142135623730951


def _mean_stdev(data: list[float]) -> tuple[float, float]:
    n = len(data)
    if n < 2:
        raise StatisticsError("stdev requires at least two data points")
    s = _nonfinite(data)
    if s is not None:
        return s / n, math.nan
    sx, _ = _sums(data)
    return _exact(_div(sx, [float(n)])), _exact(_sqrt_div(_ssd_n(data), [float(n) * float(n - 1)]))


def _poly(r: float, c7: float, c6: float, c5: float, c4: float, c3: float, c2: float, c1: float, c0: float) -> float:
    """c7 * r**7 + ... + c0 by Horner's rule, with fused multiply-adds as CPython's
    C code is compiled (clang contracts `a * r + b`)."""
    v = math.fma(c7, r, c6)
    v = math.fma(v, r, c5)
    v = math.fma(v, r, c4)
    v = math.fma(v, r, c3)
    v = math.fma(v, r, c2)
    v = math.fma(v, r, c1)
    return math.fma(v, r, c0)


def _normal_dist_inv_cdf(p: float, mu: float, sigma: float) -> float:
    """Wichura's AS241 (1988), as CPython's C version."""
    q = p - 0.5
    if math.fabs(q) <= 0.425:
        r = math.fma(-q, q, 0.180625)
        num = _poly(
            r,
            2.50908_09287_30122_6727e+3,
            3.34305_75583_58812_8105e+4,
            6.72657_70927_00870_0853e+4,
            4.59219_53931_54987_1457e+4,
            1.37316_93765_50946_1125e+4,
            1.97159_09503_06551_4427e+3,
            1.33141_66789_17843_7745e+2,
            3.38713_28727_96366_6080e+0,
        ) * q
        den = _poly(
            r,
            5.22649_52788_52854_5610e+3,
            2.87290_85735_72194_2674e+4,
            3.93078_95800_09271_0610e+4,
            2.12137_94301_58659_5867e+4,
            5.39419_60214_24751_1077e+3,
            6.87187_00749_20579_0830e+2,
            4.23133_30701_60091_1252e+1,
            1.0,
        )
        return math.fma(num / den, sigma, mu)
    r = p if q <= 0.0 else 1.0 - p
    r = math.sqrt(-math.log(r))
    x = 0.0
    if r <= 5.0:
        r = r - 1.6
        num = _poly(
            r,
            7.74545_01427_83414_07640e-4,
            2.27238_44989_26918_45833e-2,
            2.41780_72517_74506_11770e-1,
            1.27045_82524_52368_38258e+0,
            3.64784_83247_63204_60504e+0,
            5.76949_72214_60691_40550e+0,
            4.63033_78461_56545_29590e+0,
            1.42343_71107_49683_57734e+0,
        )
        den = _poly(
            r,
            1.05075_00716_44416_84324e-9,
            5.47593_80849_95344_94600e-4,
            1.51986_66563_61645_71966e-2,
            1.48103_97642_74800_74590e-1,
            6.89767_33498_51000_04550e-1,
            1.67638_48301_83803_84940e+0,
            2.05319_16266_37758_82187e+0,
            1.0,
        )
        x = num / den
    else:
        r = r - 5.0
        num = _poly(
            r,
            2.01033_43992_92288_13265e-7,
            2.71155_55687_43487_57815e-5,
            1.24266_09473_88078_43860e-3,
            2.65321_89526_57612_30930e-2,
            2.96560_57182_85048_91230e-1,
            1.78482_65399_17291_33580e+0,
            5.46378_49111_64114_36990e+0,
            6.65790_46435_01103_77720e+0,
        )
        den = _poly(
            r,
            2.04426_31033_89939_78564e-15,
            1.42151_17583_16445_88870e-7,
            1.84631_83175_10054_68180e-5,
            7.86869_13114_56132_59100e-4,
            1.48753_61290_85061_48525e-2,
            1.36929_88092_27358_05310e-1,
            5.99832_20655_58879_37690e-1,
            1.0,
        )
        x = num / den
    if q < 0.0:
        x = -x
    return math.fma(x, sigma, mu)


class NormalDist:
    def __init__(self, mu: float = 0.0, sigma: float = 1.0) -> None:
        if sigma < 0.0:
            raise StatisticsError("sigma must be non-negative")
        self._mu: float = float(mu)
        self._sigma: float = float(sigma)

    @staticmethod
    def from_samples(data: list[float]) -> NormalDist:
        m, s = _mean_stdev(data)
        return NormalDist(m, s)

    def pdf(self, x: float) -> float:
        variance = self._sigma * self._sigma
        if variance == 0.0:
            raise StatisticsError("pdf() not defined when sigma is zero")
        diff = x - self._mu
        return math.exp(diff * diff / (-2.0 * variance)) / math.sqrt(math.tau * variance)

    def cdf(self, x: float) -> float:
        if self._sigma == 0.0:
            raise StatisticsError("cdf() not defined when sigma is zero")
        return 0.5 * math.erfc((self._mu - x) / (self._sigma * _SQRT2))

    def inv_cdf(self, p: float) -> float:
        if p <= 0.0 or p >= 1.0:
            raise StatisticsError("p must be in the range 0.0 < p < 1.0")
        return _normal_dist_inv_cdf(p, self._mu, self._sigma)

    def quantiles(self, n: int = 4) -> list[float]:
        return [self.inv_cdf(i / n) for i in range(1, n)]

    def overlap(self, other: NormalDist) -> float:
        xm, xs, ym, ys = self._mu, self._sigma, other._mu, other._sigma
        if (ys, ym) < (xs, xm):
            xm, xs, ym, ys = ym, ys, xm, xs
        x_var = xs * xs
        y_var = ys * ys
        if x_var == 0.0 or y_var == 0.0:
            raise StatisticsError("overlap() not defined when sigma is zero")
        dv = y_var - x_var
        dm = math.fabs(ym - xm)
        if dv == 0.0:
            return math.erfc(dm / (2.0 * xs * _SQRT2))
        a = xm * y_var - ym * x_var
        b = xs * ys * math.sqrt(dm * dm + dv * math.log(y_var / x_var))
        x1 = (a + b) / dv
        x2 = (a - b) / dv
        cx = NormalDist(xm, xs)
        cy = NormalDist(ym, ys)
        return 1.0 - (math.fabs(cy.cdf(x1) - cx.cdf(x1)) + math.fabs(cy.cdf(x2) - cx.cdf(x2)))

    def zscore(self, x: float) -> float:
        if self._sigma == 0.0:
            raise StatisticsError("zscore() not defined when sigma is zero")
        return (x - self._mu) / self._sigma

    @property
    def mean(self) -> float:
        return self._mu

    @property
    def median(self) -> float:
        return self._mu

    @property
    def mode(self) -> float:
        return self._mu

    @property
    def stdev(self) -> float:
        return self._sigma

    @property
    def variance(self) -> float:
        return self._sigma * self._sigma

    def __add__(self, other: NormalDist | float) -> NormalDist:
        if isinstance(other, float):
            return NormalDist(self._mu + other, self._sigma)
        else:
            return NormalDist(self._mu + other._mu, math.hypot(self._sigma, other._sigma))

    def __radd__(self, other: float) -> NormalDist:
        return NormalDist(self._mu + other, self._sigma)

    def __sub__(self, other: NormalDist | float) -> NormalDist:
        if isinstance(other, float):
            return NormalDist(self._mu - other, self._sigma)
        else:
            return NormalDist(self._mu - other._mu, math.hypot(self._sigma, other._sigma))

    def __rsub__(self, other: float) -> NormalDist:
        return NormalDist(-(self._mu - other), self._sigma)

    def __mul__(self, other: float) -> NormalDist:
        return NormalDist(self._mu * other, self._sigma * math.fabs(other))

    def __rmul__(self, other: float) -> NormalDist:
        return NormalDist(self._mu * other, self._sigma * math.fabs(other))

    def __truediv__(self, other: float) -> NormalDist:
        return NormalDist(self._mu / other, self._sigma / math.fabs(other))

    def __pos__(self) -> NormalDist:
        return NormalDist(self._mu, self._sigma)

    def __neg__(self) -> NormalDist:
        return NormalDist(-self._mu, self._sigma)

    def __eq__(self, other: NormalDist) -> bool:
        return self._mu == other._mu and self._sigma == other._sigma

    def __repr__(self) -> str:
        return "NormalDist(mu=" + repr(self._mu) + ", sigma=" + repr(self._sigma) + ")"
