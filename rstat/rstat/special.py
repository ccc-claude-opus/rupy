"""Special functions: log-gamma, the normal distribution function, and the
regularized incomplete gamma and beta functions (the base of rstat's
distributions). Written from the published algorithms (Lanczos; Marsaglia's
series and Laplace's continued fraction for the normal tail; series and
continued fractions evaluated by Lentz's method)."""

import math

LN_SQRT_2PI = 0.9189385332046727418
SQRT_2PI = 2.5066282746310005024
EPS = 2.220446049250313e-16
TINY = 1e-300


def _lgamma_large(x: float) -> float:
    """log Γ(x) for x ≥ 10: Stirling's series (Bernoulli numbers, exact fractions)."""
    r = 1.0 / x
    r2 = r * r
    s = r * (1.0 / 12.0 + r2 * (-1.0 / 360.0 + r2 * (1.0 / 1260.0 + r2 * (-1.0 / 1680.0 + r2 * (1.0 / 1188.0 + r2 * (-691.0 / 360360.0 + r2 * (1.0 / 156.0 + r2 * (-3617.0 / 122400.0))))))))
    return (x - 0.5) * math.log(x) - x + LN_SQRT_2PI + s


def lgamma(x: float) -> float:
    """log |Γ(x)|: Stirling's series, after Γ(x) = Γ(x + n) / (x (x + 1) ... (x + n - 1))."""
    if math.isnan(x):
        return x
    if x <= 0.0 and x == float(math.floor(x)):
        return math.inf
    if x < 0.5:
        # reflection: Γ(x) Γ(1 - x) = π / sin(π x)
        return math.log(math.pi / abs(math.sin(math.pi * x))) - lgamma(1.0 - x)
    if x == 1.0 or x == 2.0:
        return 0.0
    if x >= 10.0:
        return _lgamma_large(x)
    prod = 1.0
    y = x
    while y < 10.0:
        prod *= y
        y += 1.0
    return _lgamma_large(y) - math.log(prod)


def gamma(x: float) -> float:
    """Γ(x)."""
    if x == float(math.floor(x)):
        if x <= 0.0:
            return math.nan
        if x <= 171.0:
            r = 1.0
            k = 2.0
            while k < x:
                r *= k
                k += 1.0
            return r
    v = math.exp(lgamma(x))
    if x < 0.0 and float(math.floor(x)) % 2.0 == 1.0:
        return -v
    return v


def lbeta(a: float, b: float) -> float:
    """log B(a, b)."""
    return lgamma(a) + lgamma(b) - lgamma(a + b)


def beta(a: float, b: float) -> float:
    """B(a, b)."""
    return math.exp(lbeta(a, b))


def lchoose(n: float, k: float) -> float:
    """log of the binomial coefficient."""
    return lgamma(n + 1.0) - lgamma(k + 1.0) - lgamma(n - k + 1.0)


def choose(n: float, k: float) -> float:
    """The binomial coefficient (as R's choose: rounded for integer n and k)."""
    if k < 0.0:
        return 0.0
    if k == 0.0:
        return 1.0
    if n == float(math.floor(n)) and k == float(math.floor(k)):
        if n >= 0.0 and k > n:
            return 0.0
        if k < 30.0:
            r = 1.0
            j = 1.0
            while j <= k:
                r = r * (n - k + j) / j
                j += 1.0
            return float(round(r)) if n >= 0.0 else r
        return float(round(math.exp(lchoose(n, k))))
    return math.exp(lchoose(n, k))


# ---------------------------------------------------------------- the normal distribution


def dnorm0(x: float) -> float:
    """The standard normal density."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _norm_tail_cf(x: float) -> float:
    """For x > 0: Q(x) / φ(x) by Laplace's continued fraction
    1 / (x + 1 / (x + 2 / (x + 3 / (x + ...)))) (Lentz)."""
    f = x
    c = x
    d = 0.0
    k = 1.0
    while k < 500.0:
        d = x + k * d
        if d == 0.0:
            d = TINY
        c = x + k / c
        if c == 0.0:
            c = TINY
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < EPS:
            break
        k += 1.0
    return 1.0 / f


def _norm_central(x: float) -> float:
    """Φ(x) - 1/2 for |x| < 3: φ(x) (x + x³/3 + x⁵/15 + ...) (Marsaglia)."""
    s = x
    t = x
    x2 = x * x
    k = 3.0
    while abs(t) > EPS * abs(s):
        t = t * x2 / k
        s += t
        k += 2.0
    return s * dnorm0(x)


def pnorm0(x: float, lower: bool, log_p: bool) -> float:
    """Φ(x) (lower) or 1 - Φ(x), or their logs."""
    if math.isnan(x):
        return x
    if not lower:
        x = -x
    if abs(x) < 3.0:
        p = 0.5 + _norm_central(x)
        return math.log(p) if log_p else p
    if x < 0.0:
        # the lower tail directly
        if log_p:
            return -0.5 * x * x - LN_SQRT_2PI + math.log(_norm_tail_cf(-x))
        if x < -40.0:
            return 0.0
        return dnorm0(x) * _norm_tail_cf(-x)
    if x > 40.0:
        return 0.0 if log_p else 1.0
    q = dnorm0(x) * _norm_tail_cf(x)
    return math.log1p(-q) if log_p else 1.0 - q


def qnorm0(p: float, lower: bool, log_p: bool) -> float:
    """The standard normal quantile: an approximation (Abramowitz and Stegun
    26.2.23), refined by Halley's method on pnorm0."""
    if log_p:
        p = math.exp(p)
    if math.isnan(p) or p < 0.0 or p > 1.0:
        return math.nan
    if p == 0.0:
        return -math.inf if lower else math.inf
    if p == 1.0:
        return math.inf if lower else -math.inf
    return _qnorm_lower(p, lower)


def _qnorm_lower(p: float, lower: bool) -> float:
    """x with Φ(x) = p (lower) or 1 - Φ(x) = p."""
    if 0.075 <= p <= 0.925:
        # central: solve Φ(x) - 1/2 = δ, whose series keeps δ's relative precision
        delta = p - 0.5 if lower else 0.5 - p
        x = delta * SQRT_2PI
        for _ in range(8):
            e = (_norm_central(x) - delta) / dnorm0(x)
            step = e / (1.0 + 0.5 * x * e)
            x -= step
            if abs(step) <= 1e-17 * max(abs(x), 1e-300):
                break
        return x
    tail = p if p <= 0.5 else 1.0 - p
    t = math.sqrt(-2.0 * math.log(tail))
    x = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1.0 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t)
    # x > 0 is the quantile of the upper tail `tail`
    if (p <= 0.5) == lower:
        x = -x
    for _ in range(6):
        if lower:
            e = (pnorm0(x, True, False) - p) / dnorm0(x)
        else:
            e = -(pnorm0(x, False, False) - p) / dnorm0(x)
        step = e / (1.0 + 0.5 * x * e)
        x -= step
        if abs(step) <= 1e-15 * max(1.0, abs(x)):
            break
    return x


# ---------------------------------------------------------------- incomplete gamma


def pgamma_raw(x: float, a: float, lower: bool) -> float:
    """The regularized incomplete gamma function P(a, x) (lower) or Q(a, x)."""
    if x <= 0.0:
        return 0.0 if lower else 1.0
    if math.isinf(x):
        return 1.0 if lower else 0.0
    if x < a + 1.0:
        # series: P = e^{-x} x^a / Γ(a + 1) Σ x^n / ((a + 1) ... (a + n))
        term = 1.0
        s = 1.0
        n = 1.0
        while n < 10000.0:
            term *= x / (a + n)
            s += term
            if term < s * EPS:
                break
            n += 1.0
        p = math.exp(-x + a * math.log(x) - lgamma(a + 1.0)) * s
        if p > 1.0:
            p = 1.0
        return p if lower else 1.0 - p
    # continued fraction for Q (Lentz)
    b = x + 1.0 - a
    c = 1.0 / TINY
    d = 1.0 / b
    h = d
    i = 1.0
    while i < 10000.0:
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < TINY:
            d = TINY
        c = b + an / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
        i += 1.0
    q = math.exp(-x + a * math.log(x) - lgamma(a)) * h
    return 1.0 - q if lower else q


# ---------------------------------------------------------------- incomplete beta


def _betacf(x: float, a: float, b: float) -> float:
    """The continued fraction of the incomplete beta function (Lentz)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    m = 1.0
    while m < 10000.0:
        m2 = 2.0 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
        m += 1.0
    return h


def pbeta_raw(x: float, a: float, b: float, lower: bool) -> float:
    """The regularized incomplete beta function I_x(a, b) (lower) or 1 - I_x(a, b)."""
    if x <= 0.0:
        return 0.0 if lower else 1.0
    if x >= 1.0:
        return 1.0 if lower else 0.0
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - lbeta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        p = front * _betacf(x, a, b) / a
        return p if lower else 1.0 - p
    q = front * _betacf(1.0 - x, b, a) / b
    return 1.0 - q if lower else q
