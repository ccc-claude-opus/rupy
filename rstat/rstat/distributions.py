"""Probability distributions in R's naming: for each, d (density or mass), p
(distribution function), q (quantile); `r` (random numbers) is a method of
rstat.RNG. Arguments are R's (`lower.tail` is `lower_tail`, `log.p` is
`log_p`, `lambda` is `lambda_`); functions take and return floats."""

import math

from rstat.special import EPS, LN_SQRT_2PI, dnorm0, lbeta, lchoose, lgamma, pbeta_raw, pgamma_raw, pnorm0, qnorm0


def _out(p: float, lower_tail: bool, log_p: bool) -> float:
    """A lower-tail probability as asked."""
    if not lower_tail:
        p = 1.0 - p
    return math.log(p) if log_p else p


def _dens(d: float, log: bool) -> float:
    return math.log(d) if log else d


# ---------------------------------------------------------------- normal


def dnorm(x: float, mean: float = 0.0, sd: float = 1.0, log: bool = False) -> float:
    if sd <= 0.0:
        return math.nan
    z = (x - mean) / sd
    if log:
        return -LN_SQRT_2PI - 0.5 * z * z - math.log(sd)
    return dnorm0(z) / sd


def pnorm(q: float, mean: float = 0.0, sd: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if sd <= 0.0:
        return math.nan
    return pnorm0((q - mean) / sd, lower_tail, log_p)


def qnorm(p: float, mean: float = 0.0, sd: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    return mean + sd * qnorm0(p, lower_tail, log_p)


# ---------------------------------------------------------------- the inversion of distribution functions


def _cdf(kind: str, x: float, a: float, b: float, lower: bool) -> float:
    """The distribution function of a continuous distribution (no log)."""
    if kind == "gamma":
        return pgamma_raw(x * b, a, lower)
    if kind == "beta":
        return pbeta_raw(x, a, b, lower)
    if kind == "t":
        return pt(x, a, lower)
    if kind == "f":
        return pf(x, a, b, lower)
    return math.nan


def _support(kind: str) -> tuple[float, float]:
    if kind == "beta":
        return (0.0, 1.0)
    if kind == "t":
        return (-math.inf, math.inf)
    return (0.0, math.inf)


def _invert(kind: str, p: float, a: float, b: float, lower_tail: bool, log_p: bool) -> float:
    """x with P(X ≤ x) = p (or P(X > x) = p): a bracket, then bisection."""
    if log_p:
        p = math.exp(p)
    if math.isnan(p) or p < 0.0 or p > 1.0:
        return math.nan
    lo, hi = _support(kind)
    if p == 0.0:
        return lo if lower_tail else hi
    if p == 1.0:
        return hi if lower_tail else lo
    # a finite bracket: double outwards until it holds p
    if math.isinf(lo):
        lo = -1.0
        while not _left_of(kind, lo, a, b, p, lower_tail):
            lo *= 2.0
    if math.isinf(hi):
        hi = 1.0
        while _left_of(kind, hi, a, b, p, lower_tail):
            lo = max(lo, hi)
            hi *= 2.0
    # bisection, to the last bit
    for _ in range(2000):
        mid = 0.5 * (lo + hi)
        if mid <= lo or mid >= hi:
            break
        if _left_of(kind, mid, a, b, p, lower_tail):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _left_of(kind: str, x: float, a: float, b: float, p: float, lower_tail: bool) -> bool:
    """Whether x is below the quantile of p."""
    if lower_tail:
        return _cdf(kind, x, a, b, True) < p
    return _cdf(kind, x, a, b, False) > p


# ---------------------------------------------------------------- continuous


def dunif(x: float, min: float = 0.0, max: float = 1.0, log: bool = False) -> float:
    d = 1.0 / (max - min) if min <= x <= max else 0.0
    return _dens(d, log)


def punif(q: float, min: float = 0.0, max: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if q <= min:
        p = 0.0
    elif q >= max:
        p = 1.0
    else:
        p = (q - min) / (max - min)
    return _out(p, lower_tail, log_p)


def qunif(p: float, min: float = 0.0, max: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    return min + p * (max - min)


def dexp(x: float, rate: float = 1.0, log: bool = False) -> float:
    if x < 0.0:
        return _dens(0.0, log)
    if log:
        return math.log(rate) - rate * x
    return rate * math.exp(-rate * x)


def pexp(q: float, rate: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if q <= 0.0:
        return _out(0.0, lower_tail, log_p)
    if lower_tail:
        p = -math.expm1(-rate * q)
        return math.log(p) if log_p else p
    return -rate * q if log_p else math.exp(-rate * q)


def qexp(p: float, rate: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if lower_tail:
        return -math.log1p(-p) / rate
    return -math.log(p) / rate


def dgamma(x: float, shape: float, rate: float = 1.0, log: bool = False) -> float:
    if x < 0.0:
        return _dens(0.0, log)
    if x == 0.0:
        if shape < 1.0:
            return math.inf
        if shape > 1.0:
            return _dens(0.0, log)
        return _dens(rate, log)
    ld = shape * math.log(rate) + (shape - 1.0) * math.log(x) - rate * x - lgamma(shape)
    return ld if log else math.exp(ld)


def pgamma(q: float, shape: float, rate: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    p = pgamma_raw(q * rate, shape, lower_tail)
    return math.log(p) if log_p else p


def qgamma(p: float, shape: float, rate: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    return _invert("gamma", p, shape, rate, lower_tail, log_p)


def dchisq(x: float, df: float, log: bool = False) -> float:
    return dgamma(x, df / 2.0, 0.5, log)


def pchisq(q: float, df: float, lower_tail: bool = True, log_p: bool = False) -> float:
    return pgamma(q, df / 2.0, 0.5, lower_tail, log_p)


def qchisq(p: float, df: float, lower_tail: bool = True, log_p: bool = False) -> float:
    return _invert("gamma", p, df / 2.0, 0.5, lower_tail, log_p)


def dbeta(x: float, shape1: float, shape2: float, log: bool = False) -> float:
    if x < 0.0 or x > 1.0:
        return _dens(0.0, log)
    if x == 0.0 or x == 1.0:
        a = shape1 if x == 0.0 else shape2
        if a < 1.0:
            return math.inf
        if a > 1.0:
            return _dens(0.0, log)
        return _dens(1.0 / math.exp(lbeta(shape1, shape2)), log)
    ld = (shape1 - 1.0) * math.log(x) + (shape2 - 1.0) * math.log1p(-x) - lbeta(shape1, shape2)
    return ld if log else math.exp(ld)


def pbeta(q: float, shape1: float, shape2: float, lower_tail: bool = True, log_p: bool = False) -> float:
    p = pbeta_raw(q, shape1, shape2, lower_tail)
    return math.log(p) if log_p else p


def qbeta(p: float, shape1: float, shape2: float, lower_tail: bool = True, log_p: bool = False) -> float:
    return _invert("beta", p, shape1, shape2, lower_tail, log_p)


def dt(x: float, df: float, log: bool = False) -> float:
    ld = lgamma((df + 1.0) / 2.0) - lgamma(df / 2.0) - 0.5 * math.log(df * math.pi) - (df + 1.0) / 2.0 * math.log1p(x * x / df)
    return ld if log else math.exp(ld)


def pt(q: float, df: float, lower_tail: bool = True, log_p: bool = False) -> float:
    if math.isinf(df):
        return pnorm0(q, lower_tail, log_p)
    # the tail beyond |q|: I_{df / (df + q²)}(df / 2, 1 / 2) / 2
    x = df / (df + q * q)
    tail = 0.5 * pbeta_raw(x, df / 2.0, 0.5, True)
    if q > 0.0:
        p = tail if not lower_tail else 1.0 - tail
    else:
        p = tail if lower_tail else 1.0 - tail
    return math.log(p) if log_p else p


def qt(p: float, df: float, lower_tail: bool = True, log_p: bool = False) -> float:
    return _invert("t", p, df, 0.0, lower_tail, log_p)


def df(x: float, df1: float, df2: float, log: bool = False) -> float:
    """The density of the F distribution (R's `df`)."""
    if x < 0.0:
        return _dens(0.0, log)
    if x == 0.0:
        return _dens(math.inf if df1 < 2.0 else (1.0 if df1 == 2.0 else 0.0), log)
    ld = 0.5 * df1 * math.log(df1) + 0.5 * df2 * math.log(df2) + (0.5 * df1 - 1.0) * math.log(x)
    ld -= 0.5 * (df1 + df2) * math.log(df2 + df1 * x) + lbeta(df1 / 2.0, df2 / 2.0)
    return ld if log else math.exp(ld)


def pf(q: float, df1: float, df2: float, lower_tail: bool = True, log_p: bool = False) -> float:
    if q <= 0.0:
        return _out(0.0, lower_tail, log_p)
    x = df1 * q / (df1 * q + df2)
    p = pbeta_raw(x, df1 / 2.0, df2 / 2.0, lower_tail)
    return math.log(p) if log_p else p


def qf(p: float, df1: float, df2: float, lower_tail: bool = True, log_p: bool = False) -> float:
    return _invert("f", p, df1, df2, lower_tail, log_p)


def dlnorm(x: float, meanlog: float = 0.0, sdlog: float = 1.0, log: bool = False) -> float:
    if x <= 0.0:
        return _dens(0.0, log)
    z = (math.log(x) - meanlog) / sdlog
    ld = -LN_SQRT_2PI - 0.5 * z * z - math.log(x * sdlog)
    return ld if log else math.exp(ld)


def plnorm(q: float, meanlog: float = 0.0, sdlog: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if q <= 0.0:
        return _out(0.0, lower_tail, log_p)
    return pnorm0((math.log(q) - meanlog) / sdlog, lower_tail, log_p)


def qlnorm(p: float, meanlog: float = 0.0, sdlog: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    return math.exp(meanlog + sdlog * qnorm0(p, lower_tail, log_p))


def dweibull(x: float, shape: float, scale: float = 1.0, log: bool = False) -> float:
    if x < 0.0:
        return _dens(0.0, log)
    t = (x / scale) ** (shape - 1.0)
    d = shape / scale * t * math.exp(-t * x / scale)
    return _dens(d, log)


def pweibull(q: float, shape: float, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if q <= 0.0:
        return _out(0.0, lower_tail, log_p)
    t = -((q / scale) ** shape)
    if lower_tail:
        p = -math.expm1(t)
        return math.log(p) if log_p else p
    return t if log_p else math.exp(t)


def qweibull(p: float, shape: float, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    t = -math.log1p(-p) if lower_tail else -math.log(p)
    return scale * t ** (1.0 / shape)


def dcauchy(x: float, location: float = 0.0, scale: float = 1.0, log: bool = False) -> float:
    z = (x - location) / scale
    return _dens(1.0 / (math.pi * scale * (1.0 + z * z)), log)


def pcauchy(q: float, location: float = 0.0, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    z = (q - location) / scale
    if not lower_tail:
        z = -z
    # the smaller tail by atan(1 / |z|), for accuracy
    if z > 1.0:
        p = 1.0 - math.atan(1.0 / z) / math.pi
    elif z < -1.0:
        p = -math.atan(1.0 / z) / math.pi
    else:
        p = 0.5 + math.atan(z) / math.pi
    return math.log(p) if log_p else p


def qcauchy(p: float, location: float = 0.0, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    if p == 0.5:
        return location
    return location + scale * math.tan(math.pi * (p - 0.5))


def dlogis(x: float, location: float = 0.0, scale: float = 1.0, log: bool = False) -> float:
    z = abs((x - location) / scale)
    e = math.exp(-z)
    f = 1.0 + e
    return _dens(e / (scale * f * f), log)


def plogis(q: float, location: float = 0.0, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    z = (q - location) / scale
    if not lower_tail:
        z = -z
    if log_p:
        return -math.log1p(math.exp(-z)) if z > -30.0 else z
    return 1.0 / (1.0 + math.exp(-z))


def qlogis(p: float, location: float = 0.0, scale: float = 1.0, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    return location + scale * math.log(p / (1.0 - p))


# ---------------------------------------------------------------- discrete


def _int(x: float) -> bool:
    return abs(x - round(x)) <= 1e-7 * max(1.0, abs(x))


def dbinom(x: float, size: float, prob: float, log: bool = False) -> float:
    if x < 0.0 or x > size or not _int(x):
        return _dens(0.0, log)
    x = float(round(x))
    if prob == 0.0:
        return _dens(1.0 if x == 0.0 else 0.0, log)
    if prob == 1.0:
        return _dens(1.0 if x == size else 0.0, log)
    ld = lchoose(size, x) + x * math.log(prob) + (size - x) * math.log1p(-prob)
    return ld if log else math.exp(ld)


def pbinom(q: float, size: float, prob: float, lower_tail: bool = True, log_p: bool = False) -> float:
    k = float(math.floor(q + 1e-7))
    if k < 0.0:
        return _out(0.0, lower_tail, log_p)
    if k >= size:
        return _out(1.0, lower_tail, log_p)
    p = pbeta_raw(prob, k + 1.0, size - k, not lower_tail)
    return math.log(p) if log_p else p


def qbinom(p: float, size: float, prob: float, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    # the smallest k with P(X ≤ k) ≥ p (with R's fuzz)
    p = p * (1.0 - 64.0 * EPS)
    k = 0.0
    while k < size and pbinom(k, size, prob) < p:
        k += 1.0
    return k


def dpois(x: float, lambda_: float, log: bool = False) -> float:
    if x < 0.0 or not _int(x):
        return _dens(0.0, log)
    x = float(round(x))
    if lambda_ == 0.0:
        return _dens(1.0 if x == 0.0 else 0.0, log)
    ld = x * math.log(lambda_) - lambda_ - lgamma(x + 1.0)
    return ld if log else math.exp(ld)


def ppois(q: float, lambda_: float, lower_tail: bool = True, log_p: bool = False) -> float:
    k = float(math.floor(q + 1e-7))
    if k < 0.0:
        return _out(0.0, lower_tail, log_p)
    p = pgamma_raw(lambda_, k + 1.0, not lower_tail)
    return math.log(p) if log_p else p


def qpois(p: float, lambda_: float, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    p = p * (1.0 - 64.0 * EPS)
    k = 0.0
    while ppois(k, lambda_) < p:
        k += 1.0
    return k


def dgeom(x: float, prob: float, log: bool = False) -> float:
    if x < 0.0 or not _int(x):
        return _dens(0.0, log)
    ld = math.log(prob) + float(round(x)) * math.log1p(-prob)
    return ld if log else math.exp(ld)


def pgeom(q: float, prob: float, lower_tail: bool = True, log_p: bool = False) -> float:
    k = float(math.floor(q + 1e-7))
    if k < 0.0:
        return _out(0.0, lower_tail, log_p)
    # P(X > k) = (1 - prob)^(k + 1)
    lq = (k + 1.0) * math.log1p(-prob)
    if lower_tail:
        p = -math.expm1(lq)
        return math.log(p) if log_p else p
    return lq if log_p else math.exp(lq)


def qgeom(p: float, prob: float, lower_tail: bool = True, log_p: bool = False) -> float:
    if log_p:
        p = math.exp(p)
    if not lower_tail:
        p = 1.0 - p
    return max(0.0, float(math.ceil(math.log1p(-p) / math.log1p(-prob) - 1.0 - 1e-12)))


def dnbinom(x: float, size: float, prob: float, log: bool = False) -> float:
    if x < 0.0 or not _int(x):
        return _dens(0.0, log)
    x = float(round(x))
    ld = lgamma(x + size) - lgamma(size) - lgamma(x + 1.0) + size * math.log(prob) + x * math.log1p(-prob)
    return ld if log else math.exp(ld)


def pnbinom(q: float, size: float, prob: float, lower_tail: bool = True, log_p: bool = False) -> float:
    k = float(math.floor(q + 1e-7))
    if k < 0.0:
        return _out(0.0, lower_tail, log_p)
    p = pbeta_raw(prob, size, k + 1.0, lower_tail)
    return math.log(p) if log_p else p


def dhyper(x: float, m: float, n: float, k: float, log: bool = False) -> float:
    if x < 0.0 or not _int(x) or x > k or x > m or k - x > n:
        return _dens(0.0, log)
    x = float(round(x))
    ld = lchoose(m, x) + lchoose(n, k - x) - lchoose(m + n, k)
    return ld if log else math.exp(ld)


def phyper(q: float, m: float, n: float, k: float, lower_tail: bool = True, log_p: bool = False) -> float:
    top = float(math.floor(q + 1e-7))
    s = 0.0
    x = max(0.0, k - n)
    while x <= top and x <= min(k, m):
        s += dhyper(x, m, n, k)
        x += 1.0
    if s > 1.0:
        s = 1.0
    return _out(s, lower_tail, log_p)
