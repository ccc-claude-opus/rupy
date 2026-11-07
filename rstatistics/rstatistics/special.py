"""Special functions: log-gamma, the normal distribution function, and the
regularized incomplete gamma and beta functions (the base of rstatistics's
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
    """The standard normal quantile: R's qnorm, Wichura's algorithm AS 241
    with its improved asymptotic tail formulas."""
    # p' = the probability p refers to (R's R_DT_qIv)
    if log_p:
        p_ = math.exp(p) if lower else -math.expm1(p)
    else:
        p_ = p if lower else 0.5 - p + 0.5
    q = p_ - 0.5
    if abs(q) <= 0.425:
        r = math.fma(-q, q, 0.180625)
        num = math.fma(r, 2509.0809287301226727, 33430.575583588128105)
        for co in [67265.770927008700853, 45921.953931549871457, 13731.693765509461125, 1971.5909503065514427, 133.14166789178437745, 3.387132872796366608]:
            num = math.fma(num, r, co)
        den = math.fma(r, 5226.495278852854561, 28729.085735721942674)
        for co in [39307.89580009271061, 21213.794301586595867, 5394.1960214247511077, 687.1870074920579083, 42.313330701600911252, 1.0]:
            den = math.fma(den, r, co)
        val = q * num / den
        return val
    # closer than 0.075 from {0, 1}: lp = log(min(p, 1 - p))
    if log_p and ((lower and q <= 0.0) or (not lower and q > 0.0)):
        lp = p
    else:
        lp = math.log(-math.expm1(p) if q > 0.0 else p_) if log_p else math.log(0.5 - p_ + 0.5 if q > 0.0 else p_)
    r = math.sqrt(-lp)
    if r <= 5.0:
        r += -1.6
        num = math.fma(r, 7.7454501427834140764e-4, 0.0227238449892691845833)
        for co in [0.24178072517745061177, 1.27045825245236838258, 3.64784832476320460504, 5.7694972214606914055, 4.6303378461565452959, 1.42343711074968357734]:
            num = math.fma(num, r, co)
        den = math.fma(r, 1.05075007164441684324e-9, 5.475938084995344946e-4)
        for co in [0.0151986665636164571966, 0.14810397642748007459, 0.68976733498510000455, 1.6763848301838038494, 2.05319162663775882187, 1.0]:
            den = math.fma(den, r, co)
        val = num / den
    elif r <= 27.0:
        r += -5.0
        num = math.fma(r, 2.01033439929228813265e-7, 2.71155556874348757815e-5)
        for co in [0.0012426609473880784386, 0.026532189526576123093, 0.29656057182850489123, 1.7848265399172913358, 5.4637849111641143699, 6.6579046435011037772]:
            num = math.fma(num, r, co)
        den = math.fma(r, 2.04426310338993978564e-15, 1.4215117583164458887e-7)
        for co in [1.8463183175100546818e-5, 7.868691311456132591e-4, 0.0148753612908506148525, 0.13692988092273580531, 0.59983220655588793769, 1.0]:
            den = math.fma(den, r, co)
        val = num / den
    else:
        if r >= 6.4e8:
            val = r * 1.414213562373095048801688724210
        else:
            s2 = -lp * 2.0
            x2 = s2 - math.log(6.283185307179586476925286766559 * s2)
            if r < 36000.0:
                x2 = s2 - math.log(6.283185307179586476925286766559 * x2) - 2.0 / (2.0 + x2)
                if r < 840.0:
                    x2 = s2 - math.log(6.283185307179586476925286766559 * x2) + 2.0 * math.log1p(-((1.0 - 1.0 / (4.0 + x2)) / (2.0 + x2)))
                    if r < 109.0:
                        x2 = s2 - math.log(6.283185307179586476925286766559 * x2) + 2.0 * math.log1p(-(1.0 - (1.0 - 5.0 / (6.0 + x2)) / (4.0 + x2)) / (2.0 + x2))
                        if r < 55.0:
                            x2 = s2 - math.log(6.283185307179586476925286766559 * x2) + 2.0 * math.log1p(-(1.0 - (1.0 - (5.0 - 9.0 / (8.0 + x2)) / (6.0 + x2)) / (4.0 + x2)) / (2.0 + x2))
            val = math.sqrt(x2)
    if q < 0.0:
        val = -val
    return val


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
