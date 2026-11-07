"""Hypothesis tests that return an HTest, printed as R prints an `htest`:
t_test, var_test, chisq_test, binom_test, prop_test and cor_test. The data
name R takes from the call is the `data_name` argument ("x", "x and y")."""

import math

from rstatistics.describe import Named, cor, mean, rank, var
from rstatistics.distributions import dbinom, dhyper, pbinom, pchisq, pf, phyper, pnorm, pt, qbeta, qf, qnorm, qt
from rstatistics.rformat import format_vec, format_num, format_pval, print_named
from rstatistics.special import choose, qnorm0


class HTest:
    """The result of a test (R's class `htest`)."""

    def __init__(self, method: str, data_name: str) -> None:
        self.method = method
        self.data_name = data_name
        self.statistic_name = ""
        self.statistic = math.nan
        self.parameter_names: list[str] = []
        self.parameter: list[float] = []
        self.p_value = math.nan
        self.alternative = ""
        self.null_name = ""
        self.null_value = math.nan
        self.conf_int: list[float] = []
        self.conf_level = 0.95
        self.estimate_names: list[str] = []
        self.estimate: list[float] = []

    def __str__(self) -> str:
        digits = 7
        lines = ["", "\t" + self.method.strip(), ""]
        lines.append(f"data:  {self.data_name}")
        out: list[str] = []
        if self.statistic_name != "":
            out.append(f"{self.statistic_name} = {format_num(self.statistic, digits - 2).strip()}")
        for i in range(len(self.parameter)):
            out.append(f"{self.parameter_names[i]} = {format_num(self.parameter[i], digits - 2).strip()}")
        if not math.isnan(self.p_value):
            fp = format_pval(self.p_value, digits - 3).strip()
            out.append("p-value " + (fp if fp.startswith("<") else "= " + fp))
        lines.append(", ".join(out))
        if self.alternative != "":
            alt = {"two.sided": "not equal to", "less": "less than", "greater": "greater than"}.get(self.alternative, "")
            if self.null_name != "" and alt != "":
                lines.append(f"alternative hypothesis: true {self.null_name} is {alt} {_num(self.null_value)}")
            else:
                lines.append(f"alternative hypothesis: {self.alternative}")
        if len(self.conf_int) == 2:
            ci = format_vec(self.conf_int, digits)
            lines.append(f"{_num(100.0 * self.conf_level)} percent confidence interval:")
            lines.append(" " + " ".join(ci))
        if len(self.estimate) > 0:
            lines.append("sample estimates:")
            lines.append(print_named(self.estimate_names, format_vec(self.estimate, digits)))
        lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()


def _num(v: float) -> str:
    """A number as R's `cat` prints it (up to 7 significant digits)."""
    return format_num(v, 7).strip()


def _alternative(a: str) -> str:
    if a not in ("two.sided", "less", "greater"):
        raise ValueError("'alternative' must be one of \"two.sided\", \"less\", \"greater\"")
    return a


def t_test(
    x: list[float],
    y: list[float] | None = None,
    alternative: str = "two.sided",
    mu: float = 0.0,
    paired: bool = False,
    var_equal: bool = False,
    conf_level: float = 0.95,
    data_name: str = "",
) -> HTest:
    """Student's / Welch's t-test: one sample, two samples, or paired."""
    alternative = _alternative(alternative)
    if y is not None and paired:
        if len(x) != len(y):
            raise ValueError("'x' and 'y' must have the same length")
        d = [x[i] - y[i] for i in range(len(x))]
        h = _t_one(d, alternative, mu, conf_level, data_name if data_name != "" else "x and y")
        h.method = "Paired t-test"
        h.estimate_names = ["mean difference"]
        h.null_name = "mean difference"
        return h
    if y is None:
        return _t_one(x, alternative, mu, conf_level, data_name if data_name != "" else "x")
    nx = float(len(x))
    ny = float(len(y))
    mx = mean(x)
    my = mean(y)
    vx = var(x)
    vy = var(y)
    if var_equal:
        df = nx + ny - 2.0
        v = 0.0
        if nx > 1.0:
            v = v + (nx - 1.0) * vx
        if ny > 1.0:
            v = v + (ny - 1.0) * vy
        v = v / df
        stderr = math.sqrt(v * (1.0 / nx + 1.0 / ny))
        method = " Two Sample t-test"
    else:
        sx = vx / nx
        sy = vy / ny
        stderr = math.sqrt(sx + sy)
        df = (stderr**4) / (sx * sx / (nx - 1.0) + sy * sy / (ny - 1.0))
        method = "Welch Two Sample t-test"
    tstat = (mx - my - mu) / stderr
    h = HTest(method, data_name if data_name != "" else "x and y")
    _t_finish(h, tstat, df, stderr, alternative, mu, conf_level)
    h.estimate_names = ["mean of x", "mean of y"]
    h.estimate = [mx, my]
    h.null_name = "difference in means"
    return h


def _t_one(x: list[float], alternative: str, mu: float, conf_level: float, data_name: str) -> HTest:
    n = float(len(x))
    if n < 2.0:
        raise ValueError("not enough 'x' observations")
    m = mean(x)
    stderr = math.sqrt(var(x) / n)
    tstat = (m - mu) / stderr
    h = HTest("One Sample t-test", data_name)
    _t_finish(h, tstat, n - 1.0, stderr, alternative, mu, conf_level)
    h.estimate_names = ["mean of x"]
    h.estimate = [m]
    h.null_name = "mean"
    return h


def _t_finish(h: HTest, tstat: float, df: float, stderr: float, alternative: str, mu: float, conf_level: float) -> None:
    if alternative == "less":
        p = pt(tstat, df)
        ci = [-math.inf, tstat + qt(conf_level, df)]
    elif alternative == "greater":
        p = pt(tstat, df, lower_tail=False)
        ci = [tstat - qt(conf_level, df), math.inf]
    else:
        p = 2.0 * pt(-abs(tstat), df)
        a = 1.0 - conf_level
        c = qt(1.0 - a / 2.0, df)
        ci = [tstat - c, tstat + c]
    h.statistic_name = "t"
    h.statistic = tstat
    h.parameter_names = ["df"]
    h.parameter = [df]
    h.p_value = p
    h.alternative = alternative
    h.null_value = mu
    h.conf_int = [mu + ci[0] * stderr, mu + ci[1] * stderr]
    h.conf_level = conf_level


def var_test(x: list[float], y: list[float], ratio: float = 1.0, alternative: str = "two.sided", conf_level: float = 0.95, data_name: str = "x and y") -> HTest:
    """The F test comparing two variances."""
    alternative = _alternative(alternative)
    dfx = float(len(x)) - 1.0
    dfy = float(len(y)) - 1.0
    est = var(x) / var(y)
    stat = est / ratio
    p = pf(stat, dfx, dfy)
    if alternative == "two.sided":
        p = 2.0 * min(p, 1.0 - p)
        beta = (1.0 - conf_level) / 2.0
        ci = [est / qf(1.0 - beta, dfx, dfy), est / qf(beta, dfx, dfy)]
    elif alternative == "greater":
        p = 1.0 - p
        ci = [est / qf(conf_level, dfx, dfy), math.inf]
    else:
        ci = [0.0, est / qf(1.0 - conf_level, dfx, dfy)]
    h = HTest("F test to compare two variances", data_name)
    h.statistic_name = "F"
    h.statistic = stat
    h.parameter_names = ["num df", "denom df"]
    h.parameter = [dfx, dfy]
    h.p_value = p
    h.alternative = alternative
    h.null_name = "ratio of variances"
    h.null_value = ratio
    h.conf_int = ci
    h.conf_level = conf_level
    h.estimate_names = ["ratio of variances"]
    h.estimate = [est]
    return h


def chisq_test(x: list[float], p: list[float] | None = None, data_name: str = "x") -> HTest:
    """Pearson's chi-squared test of given probabilities (uniform by default)."""
    n = 0.0
    for v in x:
        n += v
    k = len(x)
    probs = p if p is not None else [1.0 / float(k)] * k
    stat = 0.0
    for i in range(k):
        e = n * probs[i]
        stat += (x[i] - e) * (x[i] - e) / e
    df = float(k - 1)
    h = HTest("Chi-squared test for given probabilities", data_name)
    h.statistic_name = "X-squared"
    h.statistic = stat
    h.parameter_names = ["df"]
    h.parameter = [df]
    h.p_value = pchisq(stat, df, lower_tail=False)
    return h


def chisq_test_table(table: list[list[float]], correct: bool = True, data_name: str = "x") -> HTest:
    """Pearson's chi-squared test of independence in a contingency table
    (rows of counts), with Yates' continuity correction for 2 × 2 tables."""
    r = len(table)
    c = len(table[0])
    rows = [0.0] * r
    cols = [0.0] * c
    n = 0.0
    for i in range(r):
        for j in range(c):
            rows[i] += table[i][j]
            cols[j] += table[i][j]
            n += table[i][j]
    yates = correct and r == 2 and c == 2
    if yates:
        # R: min(0.5, |x - E|)
        corr = 0.5
        for i in range(r):
            for j in range(c):
                corr = min(corr, abs(table[i][j] - rows[i] * cols[j] / n))
    else:
        corr = 0.0
    stat = 0.0
    for i in range(r):
        for j in range(c):
            e = rows[i] * cols[j] / n
            d = abs(table[i][j] - e) - corr
            stat += d * d / e
    df = float((r - 1) * (c - 1))
    method = "Pearson's Chi-squared test"
    if yates:
        method += " with Yates' continuity correction"
    h = HTest(method, data_name)
    h.statistic_name = "X-squared"
    h.statistic = stat
    h.parameter_names = ["df"]
    h.parameter = [df]
    h.p_value = pchisq(stat, df, lower_tail=False)
    return h


def binom_test(x: int, n: int, p: float = 0.5, alternative: str = "two.sided", conf_level: float = 0.95, data_name: str = "") -> HTest:
    """The exact binomial test, with Clopper and Pearson's confidence interval."""
    alternative = _alternative(alternative)
    fx = float(x)
    fn = float(n)
    if alternative == "less":
        pv = pbinom(fx, fn, p)
    elif alternative == "greater":
        pv = pbinom(fx - 1.0, fn, p, lower_tail=False)
    else:
        rel = 1.0 + 1e-7
        d = dbinom(fx, fn, p)
        m = fn * p
        if fx == m:
            pv = 1.0
        elif fx < m:
            y = 0
            i = float(math.ceil(m))
            while i <= fn:
                if dbinom(i, fn, p) <= d * rel:
                    y += 1
                i += 1.0
            pv = pbinom(fx, fn, p) + pbinom(fn - float(y), fn, p, lower_tail=False)
        else:
            y = 0
            i = 0.0
            while i <= float(math.floor(m)):
                if dbinom(i, fn, p) <= d * rel:
                    y += 1
                i += 1.0
            pv = pbinom(float(y) - 1.0, fn, p) + pbinom(fx - 1.0, fn, p, lower_tail=False)
        pv = min(1.0, pv)
    if alternative == "less":
        ci = [0.0, _p_upper(fx, fn, 1.0 - conf_level)]
    elif alternative == "greater":
        ci = [_p_lower(fx, fn, 1.0 - conf_level), 1.0]
    else:
        a = (1.0 - conf_level) / 2.0
        ci = [_p_lower(fx, fn, a), _p_upper(fx, fn, a)]
    h = HTest("Exact binomial test", data_name if data_name != "" else f"{x} and {n}")
    h.statistic_name = "number of successes"
    h.statistic = fx
    h.parameter_names = ["number of trials"]
    h.parameter = [fn]
    h.p_value = pv
    h.alternative = alternative
    h.null_name = "probability of success"
    h.null_value = p
    h.conf_int = ci
    h.conf_level = conf_level
    h.estimate_names = ["probability of success"]
    h.estimate = [fx / fn]
    return h


def _p_lower(x: float, n: float, alpha: float) -> float:
    return 0.0 if x == 0.0 else qbeta(alpha, x, n - x + 1.0)


def _p_upper(x: float, n: float, alpha: float) -> float:
    return 1.0 if x == n else qbeta(1.0 - alpha, x + 1.0, n - x)


def prop_test(x: int, n: int, p: float = 0.5, alternative: str = "two.sided", conf_level: float = 0.95, correct: bool = True, data_name: str = "") -> HTest:
    """One-sample proportion test (chi-squared, with continuity correction),
    with Wilson's score interval."""
    alternative = _alternative(alternative)
    fx = float(x)
    fn = float(n)
    est = fx / fn
    yates = min(0.5, abs(fx - fn * p)) if correct else 0.0
    stat = (abs(fx - fn * p) - yates) ** 2 / (fn * p * (1.0 - p))
    z = math.sqrt(stat)
    if alternative == "two.sided":
        pv = pchisq(stat, 1.0, lower_tail=False)
        zq = qnorm((1.0 + conf_level) / 2.0)
    else:
        zz = z if est > p else -z
        pv = pnorm(zz, lower_tail=(alternative == "less"))
        zq = qnorm(conf_level)
    yc = yates / fn
    z22n = zq * zq / (2.0 * fn)
    pc = est + yc
    p_u = 1.0 if pc >= 1.0 else (pc + z22n + zq * math.sqrt(pc * (1.0 - pc) / fn + z22n / (2.0 * fn))) / (1.0 + 2.0 * z22n)
    pc = est - yc
    p_l = 0.0 if pc <= 0.0 else (pc + z22n - zq * math.sqrt(pc * (1.0 - pc) / fn + z22n / (2.0 * fn))) / (1.0 + 2.0 * z22n)
    if alternative == "two.sided":
        ci = [max(p_l, 0.0), min(p_u, 1.0)]
    elif alternative == "less":
        ci = [0.0, min(p_u, 1.0)]
    else:
        ci = [max(p_l, 0.0), 1.0]
    method = "1-sample proportions test with continuity correction" if correct and yates > 0.0 else "1-sample proportions test without continuity correction"
    h = HTest(method, data_name if data_name != "" else f"{x} out of {n}, null probability {_num(p)}")
    h.statistic_name = "X-squared"
    h.statistic = stat
    h.parameter_names = ["df"]
    h.parameter = [1.0]
    h.p_value = pv
    h.alternative = alternative
    h.null_name = "p"
    h.null_value = p
    h.conf_int = ci
    h.conf_level = conf_level
    h.estimate_names = ["p"]
    h.estimate = [est]
    return h


def cor_test(x: list[float], y: list[float], alternative: str = "two.sided", conf_level: float = 0.95, data_name: str = "x and y") -> HTest:
    """The test of Pearson's correlation (t statistic, Fisher's z interval)."""
    alternative = _alternative(alternative)
    n = float(len(x))
    r = cor(x, y)
    df = n - 2.0
    stat = math.sqrt(df) * r / math.sqrt(1.0 - r * r)
    if alternative == "less":
        pv = pt(stat, df)
    elif alternative == "greater":
        pv = pt(stat, df, lower_tail=False)
    else:
        pv = 2.0 * min(pt(stat, df), pt(stat, df, lower_tail=False))
    h = HTest("Pearson's product-moment correlation", data_name)
    h.statistic_name = "t"
    h.statistic = stat
    h.parameter_names = ["df"]
    h.parameter = [df]
    h.p_value = pv
    h.alternative = alternative
    h.null_name = "correlation"
    h.null_value = 0.0
    if n > 3.0:
        z = 0.5 * math.log((1.0 + r) / (1.0 - r))
        sigma = 1.0 / math.sqrt(n - 3.0)
        if alternative == "less":
            ci = [-math.inf, z + sigma * qnorm(conf_level)]
        elif alternative == "greater":
            ci = [z - sigma * qnorm(conf_level), math.inf]
        else:
            c = sigma * qnorm((1.0 + conf_level) / 2.0)
            ci = [z - c, z + c]
        h.conf_int = [math.tanh(ci[0]), math.tanh(ci[1])]
        h.conf_level = conf_level
    h.estimate_names = ["cor"]
    h.estimate = [r]
    return h


def _named(h: HTest) -> Named:
    return Named(h.estimate_names, h.estimate)


# ------------------------------------------------------ nonparametric tests


def _unique_sorted(xs: list[str]) -> list[str]:
    """The distinct values of a vector, sorted (R's factor levels)."""
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    out.sort()
    return out


def kruskal_test(x: list[float], g: list[str], data_name: str = "x and g") -> HTest:
    """The Kruskal-Wallis rank sum test (R's kruskal.test)."""
    if len(x) != len(g):
        raise ValueError("'x' and 'g' must have the same length")
    n = float(len(x))
    if n < 2.0:
        raise ValueError("not enough observations")
    groups = _unique_sorted(g)
    k = len(groups)
    if k < 2:
        raise ValueError("all observations are in the same group")
    r = rank(x)
    counts = [0.0] * k
    sums = [0.0] * k
    for i in range(len(x)):
        j = groups.index(g[i])
        counts[j] += 1.0
        sums[j] += r[i]
    stat = 0.0
    for j in range(k):
        stat += sums[j] * sums[j] / counts[j]
    # the ties of x
    xs = sorted(x)
    ties = 0.0
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        t = float(j - i + 1)
        ties += t * t * t - t
        i = j + 1
    stat = (12.0 * stat / (n * (n + 1.0)) - 3.0 * (n + 1.0)) / (1.0 - ties / (n * n * n - n))
    h = HTest("Kruskal-Wallis rank sum test", data_name)
    h.statistic_name = "Kruskal-Wallis chi-squared"
    h.statistic = stat
    h.parameter_names = ["df"]
    h.parameter = [float(k - 1)]
    h.p_value = pchisq(stat, float(k - 1), lower_tail=False)
    return h


# --------------------------------------------------------- Fisher's exact test


def _dnhyper(support: list[float], logdc: list[float], ncp: float) -> list[float]:
    """The non-central hypergeometric probabilities on the support."""
    d = [0.0] * len(support)
    if ncp == 0.0:
        d[0] = 1.0
        return d
    mx = -math.inf
    for i in range(len(support)):
        d[i] = logdc[i] + math.log(ncp) * support[i]
        if d[i] > mx:
            mx = d[i]
    total = 0.0
    for i in range(len(support)):
        d[i] = math.exp(d[i] - mx)
        total += d[i]
    out = [0.0] * len(support)
    for i in range(len(support)):
        out[i] = d[i] / total
    return out


def _fisher_mean(support: list[float], logdc: list[float], ncp: float) -> float:
    """The mean of the non-central hypergeometric distribution."""
    if ncp == 0.0:
        return support[0]
    d = _dnhyper(support, logdc, ncp)
    m = 0.0
    for i in range(len(support)):
        m += support[i] * d[i]
    return m


def _fisher_pnhyper(q: float, ncp: float, m: float, n: float, k: float, support: list[float], logdc: list[float], upper: bool) -> float:
    """P(X <= q) (or P(X >= q)) of the non-central hypergeometric distribution."""
    if ncp == 1.0:
        if upper:
            return phyper(q - 1.0, m, n, k, lower_tail=False)
        return phyper(q, m, n, k)
    if ncp == 0.0:
        if upper:
            return 1.0 if q <= support[0] else 0.0
        return 1.0 if q >= support[0] else 0.0
    d = _dnhyper(support, logdc, ncp)
    s = 0.0
    for i in range(len(support)):
        if (support[i] >= q) if upper else (support[i] <= q):
            s += d[i]
    return s


def _zeroin2_fisher(kind: int, q: float, alpha: float, x: float, m: float, n: float, k: float, support: list[float], logdc: list[float], a: float, b: float, fa: float, fb: float, invert: bool, upper: bool) -> float:
    """R's uniroot (R_zeroin2) for the roots of fisher.test.

    kind 0: the mean of the non-central hypergeometric, kind 1: its tail
    probability."""
    eps = 2.220446049250313e-16
    tol = 1.220703125e-04  # .Machine$double.eps^0.25
    c = a
    fc = fa
    maxit = 1001
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    while maxit > 0:
        maxit -= 1
        if abs(fc) < abs(fb):
            # the best approximation becomes b (as in R_zeroin2)
            a = b
            b = c
            c = a
            fa = fb
            fb = fc
            fc = fa
        prev_step = b - a
        tol_act = 2.0 * eps * abs(b) + tol / 2.0
        new_step = (c - b) / 2.0
        if abs(new_step) <= tol_act or fb == 0.0:
            return b
        if abs(prev_step) >= tol_act and abs(fa) > abs(fb):
            cb = c - b
            if a == c:
                t1 = fb / fa
                p = cb * t1
                qq = 1.0 - t1
            else:
                qq = fa / fc
                t1 = fb / fc
                t2 = fb / fa
                p = t2 * (cb * qq * (qq - t1) - (b - a) * (t1 - 1.0))
                qq = (qq - 1.0) * (t1 - 1.0) * (t2 - 1.0)
            if p > 0.0:
                qq = -qq
            else:
                p = -p
            if p < 0.75 * cb * qq - abs(tol_act * qq) / 2.0 and p < abs(prev_step * qq / 2.0):
                new_step = p / qq
        if abs(new_step) < tol_act:
            if new_step > 0.0:
                new_step = tol_act
            else:
                new_step = -tol_act
        a = b
        fa = fb
        b += new_step
        if kind == 0:
            ncp = 1.0 / b if invert else b
            fb = _fisher_mean(support, logdc, ncp) - x
        else:
            ncp = 1.0 / b if invert else b
            fb = _fisher_pnhyper(q, ncp, m, n, k, support, logdc, upper) - alpha
        if (fb > 0.0 and fc > 0.0) or (fb < 0.0 and fc < 0.0):
            c = a
            fc = fa
    return b


def _fisher_root_mean(x: float, support: list[float], logdc: list[float], a: float, b: float, invert: bool) -> float:
    """The root of E(X) = x (R's uniroot on the mean of the hypergeometric)."""
    if invert:
        fa = _fisher_mean(support, logdc, 1.0 / a) - x
        fb = _fisher_mean(support, logdc, 1.0 / b) - x
    else:
        fa = _fisher_mean(support, logdc, a) - x
        fb = _fisher_mean(support, logdc, b) - x
    return _zeroin2_fisher(0, 0.0, 0.0, x, 0.0, 0.0, 0.0, support, logdc, a, b, fa, fb, invert, False)


def _fisher_root_p(q: float, alpha: float, m: float, n: float, k: float, support: list[float], logdc: list[float], upper: bool, invert: bool) -> float:
    """The root of P(X <= q) = alpha (R's uniroot on the tail probability)."""
    a = 0.0
    b = 1.0
    if invert:
        a = 2.220446049250313e-16
    fa = _fisher_pnhyper(q, 1.0 / a if invert else a, m, n, k, support, logdc, upper) - alpha
    fb = _fisher_pnhyper(q, 1.0 / b if invert else b, m, n, k, support, logdc, upper) - alpha
    return _zeroin2_fisher(1, q, alpha, 0.0, m, n, k, support, logdc, a, b, fa, fb, invert, upper)


def fisher_test(x: list[list[float]], alternative: str = "two.sided", or_: float = 1.0, conf_int: bool = True, conf_level: float = 0.95, data_name: str = "x") -> HTest:
    """Fisher's exact test for a 2x2 table (R's fisher.test)."""
    if len(x) != 2 or len(x[0]) != 2 or len(x[1]) != 2:
        raise ValueError("'x' must be a 2x2 table")
    alternative = _alternative(alternative)
    m = x[0][0] + x[1][0]
    n = x[0][1] + x[1][1]
    k = x[0][0] + x[0][1]
    xx = x[0][0]
    lo = max(0.0, k - n)
    hi = min(k, m)
    support: list[float] = []
    v = lo
    while v <= hi:
        support.append(v)
        v += 1.0
    logdc: list[float] = []
    for s in support:
        logdc.append(dhyper(s, m, n, k, log=True))
    # the p-value
    if alternative == "less":
        p = _fisher_pnhyper(xx, or_, m, n, k, support, logdc, False)
    elif alternative == "greater":
        p = _fisher_pnhyper(xx, or_, m, n, k, support, logdc, True)
    elif or_ == 0.0:
        p = 1.0 if xx == lo else 0.0
    elif math.isinf(or_):
        p = 1.0 if xx == hi else 0.0
    else:
        d = _dnhyper(support, logdc, or_)
        dx = d[int(xx - lo)]
        rel = 1.0 + 1e-7
        p = 0.0
        for i in range(len(d)):
            if d[i] <= dx * rel:
                p += d[i]
    # the maximum likelihood estimate of the odds ratio
    if xx == lo:
        est = 0.0
    elif xx == hi:
        est = math.inf
    else:
        mu = _fisher_mean(support, logdc, 1.0)
        if mu > xx:
            est = _fisher_root_mean(xx, support, logdc, 0.0, 1.0, False)
        elif mu < xx:
            est = 1.0 / _fisher_root_mean(xx, support, logdc, 2.220446049250313e-16, 1.0, True)
        else:
            est = 1.0
    h = HTest("Fisher's Exact Test for Count Data", data_name)
    h.p_value = p
    h.alternative = alternative
    h.null_name = "odds ratio"
    h.null_value = or_
    h.estimate_names = ["odds ratio"]
    h.estimate = [est]
    if conf_int:
        alpha = 1.0 - conf_level
        if alternative == "less":
            up = math.inf if xx == hi else _fisher_root_p(xx, alpha, m, n, k, support, logdc, False, False)
            if xx == lo:
                low = 0.0
            else:
                low = 0.0
            h.conf_int = [0.0, up]
        elif alternative == "greater":
            if xx == lo:
                low = 0.0
            else:
                p1 = _fisher_pnhyper(xx, 1.0, m, n, k, support, logdc, True)
                if p1 > alpha:
                    low = _fisher_root_p(xx, alpha, m, n, k, support, logdc, True, False)
                elif p1 < alpha:
                    low = 1.0 / _fisher_root_p(xx, alpha, m, n, k, support, logdc, True, True)
                else:
                    low = 1.0
            h.conf_int = [low, math.inf]
        else:
            a2 = (1.0 - conf_level) / 2.0
            if xx == lo:
                low = 0.0
            else:
                p1 = _fisher_pnhyper(xx, 1.0, m, n, k, support, logdc, True)
                if p1 > a2:
                    low = _fisher_root_p(xx, a2, m, n, k, support, logdc, True, False)
                elif p1 < a2:
                    low = 1.0 / _fisher_root_p(xx, a2, m, n, k, support, logdc, True, True)
                else:
                    low = 1.0
            if xx == hi:
                up = math.inf
            else:
                p2 = _fisher_pnhyper(xx, 1.0, m, n, k, support, logdc, False)
                if p2 < a2:
                    up = _fisher_root_p(xx, a2, m, n, k, support, logdc, False, False)
                elif p2 > a2:
                    up = 1.0 / _fisher_root_p(xx, a2, m, n, k, support, logdc, False, True)
                else:
                    up = 1.0
            h.conf_int = [low, up]
        h.conf_level = conf_level
    return h


# ------------------------------------------------------------- Wilcoxon tests


def _cwilcox_sigma(k: int, m: int, n: int) -> int:
    """The sum of the divisors of k that are at most m (R's cwilcox_sigma)."""
    s = 0
    iter1 = m if m < k else k
    iter2 = (m + n) if (m + n) < k else k
    d = 1
    while d <= iter1:
        if k % d == 0:
            s += d
        d += 1
    d = n + 1
    while d <= iter2:
        if k % d == 0:
            s -= d
        d += 1
    return s


def _cwilcox(k: int, m: int, n: int) -> float:
    """The number of choices of m of n+m with the Wilcoxon statistic k."""
    u = m * n
    if k < 0 or k > u:
        return 0.0
    c = u // 2
    if k > c:
        k = u - k
    i = m
    j = n
    if m >= n:
        i = n
        j = m
    if i == 0 or j == 0 or k == 0:
        return 1.0 if k == 0 else 0.0
    sigma = [0] * (k + 1)
    for kk in range(1, k + 1):
        sigma[kk] = _cwilcox_sigma(kk, i, j)
    w = [0.0] * (k + 1)
    w[0] = 1.0
    for kk in range(1, k + 1):
        s = 0.0
        for ii in range(0, kk):
            s += w[ii] * sigma[kk - ii]
        w[kk] = s / float(kk)
    return w[k]


def _pwilcox(q: float, m: int, n: int, lower_tail: bool) -> float:
    """R's pwilcox: the distribution function of the Wilcoxon statistic."""
    if m <= 0 or n <= 0:
        return math.nan
    qq = float(math.floor(q + 1e-7))
    if qq < 0.0:
        return 0.0 if lower_tail else 1.0
    if qq >= float(m * n):
        return 1.0 if lower_tail else 0.0
    c = choose(float(m + n), float(n))
    p = 0.0
    if qq <= float(m * n) / 2.0:
        i = 0
        while i <= int(qq):
            p += _cwilcox(i, m, n) / c
            i += 1
    else:
        qq = float(m * n) - qq
        i = 0
        while i < int(qq):
            p += _cwilcox(i, m, n) / c
            i += 1
        lower_tail = not lower_tail
    if lower_tail:
        return p
    return 1.0 - p


def _wilcox_tied_density(z: list[float], m: int) -> list[float]:
    """The density of the Wilcoxon statistic when the ranks have ties."""
    n = len(z) - m
    # the doubled ranks (always integers)
    allint = True
    for v in z:
        if v != float(int(v)):
            allint = False
    f = 1.0 if allint else 2.0
    vals = [0.0] * len(z)
    for i in range(len(z)):
        vals[i] = 2.0 * z[i]
    # the largest sum of m ranks
    vs = sorted(vals)
    smax = 0.0
    for i in range(len(vs) - m, len(vs)):
        smax += vs[i]
    size = int(smax) + 1
    # dp[k * size + s]: the number of ways to choose k ranks with sum s
    dp = [0.0] * ((m + 1) * size)
    dp[0] = 1.0
    for i in range(len(vals)):
        v = int(vals[i])
        for k in range(min(m, i + 1), 0, -1):
            base = k * size
            prev = (k - 1) * size
            for s in range(size - 1, v - 1, -1):
                dp[base + s] += dp[prev + s - v]
    total = 0.0
    for s in range(size):
        total += dp[m * size + s]
    # the density on the support of the statistic
    step = 1.0 if allint else 0.5
    nsup = int(float(m * n) / step) + 1
    dens = [0.0] * nsup
    for i in range(nsup):
        w = step * i
        s = int(f * (w + float(m * (m + 1)) / 2.0))
        if s < size:
            dens[i] = dp[m * size + s] / total
    return dens


def _pwilcox_tied(q: float, m: int, n: int, z: list[float], lower_tail: bool) -> float:
    """R's .pwilcox with ties: the distribution function of the statistic."""
    dens = _wilcox_tied_density(z, m)
    allint = True
    for v in z:
        if v != float(int(v)):
            allint = False
    step = 1.0 if allint else 0.5
    nsup = int(float(m * n) / step) + 1
    y = 0.0
    for i in range(nsup):
        if step * i < q + 1e-8:
            y += dens[i]
    if lower_tail:
        return min(y, 1.0)
    if abs(y - 1.0) < 0.015625:
        # the complementary sum, to avoid the cancellation
        r = 0.0
        for i in range(nsup):
            if step * i >= q + 1e-8:
                r += dens[i]
        return r
    return 1.0 - y


def _signrank_counts(vals: list[float]) -> list[float]:
    """The number of subsets of the ranks with each sum."""
    total = 0.0
    for v in vals:
        total += abs(v)
    size = int(total) + 1
    dp = [0.0] * size
    dp[0] = 1.0
    for i in range(len(vals)):
        vi = int(abs(vals[i]))
        for s in range(size - 1, vi - 1, -1):
            dp[s] += dp[s - vi]
    return dp


def _psignrank(q: float, z: list[float], lower_tail: bool, exact_c: bool) -> float:
    """R's psignrank (no ties) and .psignrank (with ties)."""
    n = len(z)
    if n == 0:
        return 0.0
    x = math.floor(q + 1e-7)
    u = float(n * (n + 1)) / 2.0
    if x < 0.0:
        return 0.0 if lower_tail else 1.0
    if x >= u:
        return 1.0 if lower_tail else 0.0
    allint = True
    for v in z:
        if v != float(int(v)):
            allint = False
    if exact_c:
        # R's psignrank: the counts times exp(-n log(2))
        dp = _signrank_counts(z)
        fl = math.exp(-float(n) * math.log(2.0))
        p = 0.0
        if x <= float(n * (n + 1)) / 4.0:
            i = 0
            while i <= int(x):
                p += dp[i] * fl
                i += 1
        else:
            xx = u - x
            i = 0
            while i < int(xx):
                p += dp[i] * fl
                i += 1
            lower_tail = not lower_tail
        return p if lower_tail else 1.0 - p
    # R's .psignrank with ties: the density over the support
    f = 1.0 if allint else 2.0
    vals = [0.0] * n
    for i in range(n):
        vals[i] = f * z[i]
    dp = _signrank_counts(vals)
    tot = 0.0
    for i in range(len(dp)):
        tot += dp[i]
    step = 1.0 if allint else 0.5
    nsup = int(u / step) + 1
    y = 0.0
    for i in range(nsup):
        s = step * i
        if s < q + 1e-8:
            idx = int(f * s)
            if idx < len(dp):
                y += dp[idx] / tot
    if lower_tail:
        return min(y, 1.0)
    if abs(y - 1.0) < 0.015625:
        r = 0.0
        for i in range(nsup):
            s = step * i
            if s >= q + 1e-8:
                idx = int(f * s)
                if idx < len(dp):
                    r += dp[idx] / tot
        return r
    return 1.0 - y


def wilcox_test(
    x: list[float],
    y: list[float] | None = None,
    alternative: str = "two.sided",
    exact: bool | None = None,
    correct: bool = True,
    conf_int: bool = False,
    conf_level: float = 0.95,
    paired: bool = False,
    data_name: str = "",
) -> HTest:
    """The Wilcoxon rank sum test (two samples) or the signed rank test (one)."""
    alternative = _alternative(alternative)
    if y is not None and paired:
        if len(x) != len(y):
            raise ValueError("'x' and 'y' must have the same length")
        d = [x[i] - y[i] for i in range(len(x))]
        h = _wilcox_signed(d, alternative, exact, correct, conf_int, conf_level, data_name if data_name != "" else "x and y")
        h.null_name = "location shift"
        return h
    if y is None:
        return _wilcox_signed(x, alternative, exact, correct, conf_int, conf_level, data_name if data_name != "" else "x")
    if len(x) < 1 or len(y) < 1:
        raise ValueError("not enough observations")
    n_x = float(len(x))
    n_y = float(len(y))
    both = x + y
    r = rank(both)
    rs = sorted(r)
    ties = False
    for i in range(1, len(rs)):
        if rs[i] == rs[i - 1]:
            ties = True
    w = 0.0
    for i in range(len(x)):
        w += r[i]
    w -= n_x * (n_x + 1.0) / 2.0
    if exact is None:
        do_exact = n_x < 50.0 and n_y < 50.0
    else:
        do_exact = exact
    corr = 0 if correct else -1
    if do_exact:
        method = "Wilcoxon rank sum exact test"
        if ties:
            p1 = _pwilcox_tied(w, len(x), len(y), r, True)
            p2 = _pwilcox_tied(w - 0.25, len(x), len(y), r, False)
        else:
            p1 = _pwilcox(w, len(x), len(y), True)
            p2 = _pwilcox(w - 0.25, len(x), len(y), False)
        if alternative == "two.sided":
            p = min(2.0 * p1, 2.0 * p2, 1.0)
        elif alternative == "less":
            p = p1
        else:
            p = p2
    else:
        method = "Wilcoxon rank sum test"
        if corr >= 0:
            method = "Wilcoxon rank sum test with continuity correction"
        ex = n_x * n_y / 2.0
        # the ties of the ranks
        rs = sorted(r)
        nt = 0.0
        i = 0
        while i < len(rs):
            j = i
            while j + 1 < len(rs) and rs[j + 1] == rs[i]:
                j += 1
            t = float(j - i + 1)
            nt += t * t * t - t
            i = j + 1
        sd = math.sqrt((n_x * n_y / 12.0) * ((n_x + n_y + 1.0) - nt / ((n_x + n_y) * (n_x + n_y - 1.0))))
        z = w - ex
        if corr >= 0:
            if alternative == "two.sided":
                z -= 0.5 if z > 0.0 else -0.5
            elif alternative == "greater":
                z -= 0.5
            else:
                z -= -0.5
        z = z / sd
        if alternative == "less":
            p = pnorm(z)
        elif alternative == "greater":
            p = pnorm(z, lower_tail=False)
        else:
            p = 2.0 * min(pnorm(z), 1.0 - pnorm(z))
    h = HTest(method, data_name if data_name != "" else "x and y")
    h.statistic_name = "W"
    h.statistic = w
    h.p_value = p
    h.alternative = alternative
    h.null_name = "location shift"
    h.null_value = 0.0
    return h


def _wilcox_signed(x: list[float], alternative: str, exact: bool | None, correct: bool, conf_int: bool, conf_level: float, data_name: str) -> HTest:
    """The Wilcoxon signed rank test (one sample)."""
    n = float(len(x))
    if n < 1.0:
        raise ValueError("not enough (non-missing) 'x' observations")
    if exact is None:
        do_exact = n < 50.0
    else:
        do_exact = exact
    corr = 0 if correct else -1
    r = rank([abs(v) for v in x])
    v = 0.0
    for i in range(len(x)):
        if x[i] > 0.0:
            v += r[i]
    # the ranks of the non-zero values (for the exact distribution)
    zr: list[float] = []
    for i in range(len(x)):
        if x[i] != 0.0:
            zr.append(r[i])
    zrs = sorted(zr)
    ties = False
    for i in range(1, len(zrs)):
        if zrs[i] == zrs[i - 1]:
            ties = True
    if do_exact:
        method = "Wilcoxon signed rank exact test"
        if ties or len(zr) != len(x):
            zz = zr
            use_c = False
        else:
            zz = [float(i + 1) for i in range(len(x))]
            use_c = True
        if alternative == "two.sided":
            m = sum(zz) / 2.0 if not use_c else n * (n + 1.0) / 4.0
            if v > m:
                p = _psignrank(v - 0.25, zz, False, use_c)
            else:
                p = _psignrank(v, zz, True, use_c)
            p = min(2.0 * p, 1.0)
        elif alternative == "greater":
            p = _psignrank(v - 0.25, zz, False, use_c)
        else:
            p = _psignrank(v, zz, True, use_c)
    else:
        method = "Wilcoxon signed rank test"
        if corr >= 0:
            method = "Wilcoxon signed rank test with continuity correction"
        ex = n * (n + 1.0) / 4.0
        rs = sorted(r)
        nt = 0.0
        i = 0
        while i < len(rs):
            j = i
            while j + 1 < len(rs) and rs[j + 1] == rs[i]:
                j += 1
            t = float(j - i + 1)
            nt += t * t * t - t
            i = j + 1
        sd = math.sqrt(n * (n + 1.0) * (2.0 * n + 1.0) / 24.0 - nt / 48.0)
        stat = v
        if corr >= 0:
            stat = stat + (-0.5 if stat > ex else 0.5)
            corr = 1
        z = (stat - ex) / sd
        if alternative == "two.sided":
            pp = pnorm(z)
            p = 2.0 * min(pp, 1.0 - pp)
        elif alternative == "less":
            p = pnorm(z)
        else:
            p = pnorm(z, lower_tail=False)
    h = HTest(method, data_name)
    h.statistic_name = "V"
    h.statistic = v
    h.p_value = p
    h.alternative = alternative
    h.null_name = "location"
    h.null_value = 0.0
    return h


# -------------------------------------------------- Kolmogorov-Smirnov test


def _kolmogorov_limit(x: float, lower: bool, tol: float) -> float:
    """The limiting distribution of the Kolmogorov statistic (R's K2l)."""
    if x <= 0.0:
        return 0.0 if lower else 1.0
    if x < 1.0:
        k_max = int(math.sqrt(2.0 - math.log(tol)))
        w = math.log(x)
        z = -(1.5707963267948966 * 0.7853981633974483) / (x * x)
        s = 0.0
        k = 1
        while k < k_max:
            s += math.exp(float(k * k) * z - w)
            k += 2
        p = s / 2.5066282746310002
        if not lower:
            p = 1.0 - p
        return p
    z = -2.0 * x * x
    s = -1.0
    if lower:
        k = 1
        old = 0.0
        new = 1.0
    else:
        k = 2
        old = 0.0
        new = 2.0 * math.exp(z)
    while abs(old - new) > tol:
        old = new
        new += 2.0 * s * math.exp(z * float(k * k))
        s *= -1.0
        k += 1
    return new


def _ks_exact(q: float, m: int, n: int, z: list[int], two: bool, lower: bool) -> float:
    """R's psmirnov_exact: the exact distribution of the KS statistic."""
    md = float(m)
    nd = float(n)
    qq = (0.5 + math.floor(q * md * nd - 1e-7)) / (md * nd)
    ties = len(z) > 0
    u = [0.0] * (n + 1)
    if lower:
        u[0] = 1.0
        for j in range(1, n + 1):
            if _ks_test(qq, 0.0, float(j) / nd, two) and (not ties or z[j] != 0):
                u[j] = 0.0
            else:
                u[j] = u[j - 1]
        for i in range(1, m + 1):
            w = float(i) / float(i + n)
            if _ks_test(qq, float(i) / md, 0.0, two) and (not ties or z[i] != 0):
                u[0] = 0.0
            else:
                u[0] = w * u[0]
            for j in range(1, n + 1):
                if _ks_test(qq, float(i) / md, float(j) / nd, two) and (not ties or z[i + j] != 0):
                    u[j] = 0.0
                else:
                    u[j] = w * u[j] + u[j - 1]
        return u[n]
    u[0] = 0.0
    for j in range(1, n + 1):
        if _ks_test(qq, 0.0, float(j) / nd, two) and (not ties or z[j] != 0):
            u[j] = 1.0
        else:
            u[j] = u[j - 1]
    for i in range(1, m + 1):
        if _ks_test(qq, float(i) / md, 0.0, two) and (not ties or z[i] != 0):
            u[0] = 1.0
        for j in range(1, n + 1):
            if _ks_test(qq, float(i) / md, float(j) / nd, two) and (not ties or z[i + j] != 0):
                u[j] = 1.0
            else:
                v = float(i) / float(i + j)
                w = float(j) / float(i + j)
                u[j] = v * u[j] + w * u[j - 1]
    return u[n]


def _ks_test(q: float, r: float, s: float, two: bool) -> bool:
    """Whether the difference of the two distribution functions is too large."""
    if two:
        return abs(r - s) >= q
    return (r - s) >= q


def ks_test(x: list[float], y: list[float], alternative: str = "two.sided", exact: bool | None = None, data_name: str = "x and y") -> HTest:
    """The two-sample Kolmogorov-Smirnov test (R's ks.test)."""
    if alternative not in ("two.sided", "less", "greater"):
        raise ValueError("'alternative' must be one of \"two.sided\", \"less\", \"greater\"")
    n_x = float(len(x))
    n_y = float(len(y))
    if n_x < 1.0 or n_y < 1.0:
        raise ValueError("not enough data")
    if exact is None:
        do_exact = n_x * n_y < 10000.0
    else:
        do_exact = exact
    # the empirical difference, at the ends of the ties
    w = x + y
    order = sorted(range(len(w)), key=lambda i: w[i])
    z = [0.0] * len(w)
    acc = 0.0
    for pos in range(len(w)):
        if order[pos] < len(x):
            acc += 1.0 / n_x
        else:
            acc += -1.0 / n_y
        z[pos] = acc
    ws = sorted(w)
    ties = False
    for i in range(1, len(ws)):
        if ws[i] == ws[i - 1]:
            ties = True
    if ties:
        keep: list[int] = []
        i = 0
        while i < len(ws):
            j = i
            while j + 1 < len(ws) and ws[j + 1] == ws[i]:
                j += 1
            keep.append(j)
            i = j + 1
        keep.append(len(w) - 1)
        zz: list[float] = []
        for k in keep:
            zz.append(z[k])
        z = zz
    dmax = -math.inf
    zmax = -math.inf
    dmin = math.inf
    for v in z:
        if abs(v) > dmax:
            dmax = abs(v)
        if v > zmax:
            zmax = v
        if v < dmin:
            dmin = v
    if alternative == "two.sided":
        stat = dmax
        name = "D"
        nm_alt = "two-sided"
    elif alternative == "greater":
        stat = zmax
        name = "D^+"
        nm_alt = "the CDF of x lies above that of y"
    else:
        stat = -dmin
        name = "D^-"
        nm_alt = "the CDF of x lies below that of y"
    # the p-value
    two = alternative == "two.sided"
    m = int(n_x)
    n = int(n_y)
    sizes_x = m
    sizes_y = n
    if alternative == "less":
        sizes_x = n
        sizes_y = m
    zt: list[int] = []
    if ties:
        for i in range(1, len(w)):
            zt.append(1 if ws[i] != ws[i - 1] else 0)
        zt.append(1)
        zt.insert(0, 0)
    if stat <= 0.0:
        p = 1.0
    elif stat > 1.0:
        p = 0.0
    elif do_exact:
        p = _ks_exact(stat, sizes_x, sizes_y, zt, two, False)
    else:
        nn = float(m) * float(n) / (float(m) + float(n))
        if two:
            p = _kolmogorov_limit(math.sqrt(nn) * stat, False, 1e-6)
        else:
            p = 1.0 - -math.expm1(-2.0 * nn * stat * stat)
    p = min(1.0, max(0.0, p))
    h = HTest(("Exact" if do_exact else "Asymptotic") + " two-sample Kolmogorov-Smirnov test", data_name)
    h.statistic_name = name
    h.statistic = stat
    h.p_value = p
    h.alternative = nm_alt
    return h


# ------------------------------------------------------- Shapiro-Wilk test


def _poly(cc: list[float], x: float) -> float:
    """The polynomial with the coefficients cc, evaluated at x (R's poly)."""
    ret = cc[0]
    p = x * cc[len(cc) - 1]
    for j in range(len(cc) - 2, 0, -1):
        p = (p + cc[j]) * x
    return ret + p


def _swilk(x: list[float]) -> tuple[float, float]:
    """R's swilk: the Shapiro-Wilk statistic and its p-value."""
    n = len(x)
    nn2 = n // 2
    g = [-2.273, 0.459]
    c1 = [0.0, 0.221157, -0.147981, -2.07119, 4.434685, -2.706056]
    c2 = [0.0, 0.042981, -0.293762, -1.752461, 5.682633, -3.582633]
    c3 = [0.544, -0.39978, 0.025054, -6.714e-4]
    c4 = [1.3822, -0.77857, 0.062767, -0.0020322]
    c5 = [-1.5861, -0.31082, -0.083751, 0.0038915]
    c6 = [-0.4803, -0.082676, 0.0030302]
    a = [0.0] * (nn2 + 1)
    small = 1e-19
    an = float(n)
    if n == 3:
        a[1] = 0.70710678
    else:
        an25 = an + 0.25
        summ2 = 0.0
        for i in range(1, nn2 + 1):
            a[i] = qnorm0((float(i) - 0.375) / an25, True, False)
            summ2 += a[i] * a[i]
        summ2 *= 2.0
        ssumm2 = math.sqrt(summ2)
        rsn = 1.0 / math.sqrt(an)
        a1 = _poly(c1, rsn) - a[1] / ssumm2
        if n > 5:
            i1 = 3
            a2 = -a[2] / ssumm2 + _poly(c2, rsn)
            fac = math.sqrt((summ2 - 2.0 * a[1] * a[1] - 2.0 * a[2] * a[2]) / (1.0 - 2.0 * a1 * a1 - 2.0 * a2 * a2))
            a[2] = a2
        else:
            i1 = 2
            fac = math.sqrt((summ2 - 2.0 * a[1] * a[1]) / (1.0 - 2.0 * a1 * a1))
        a[1] = a1
        for i in range(i1, nn2 + 1):
            a[i] = a[i] / (-fac)
    rng = x[n - 1] - x[0]
    if rng < small:
        return math.nan, math.nan
    # the sums of the coefficients and the data
    xx = x[0] / rng
    sx = xx
    sa = -a[1]
    i = 1
    j = n - 1
    while i < n:
        xi = x[i] / rng
        sx += xi
        i += 1
        if i != j:
            k = i if i < j else j
            if i < j:
                sa -= a[k]
            else:
                sa += a[k]
        xx = xi
        j -= 1
    sa /= an
    sx /= an
    ssa = 0.0
    ssx = 0.0
    sax = 0.0
    for i in range(n):
        j = n - 1 - i
        if i != j:
            k = 1 + (i if i < j else j)
            asa = (-a[k] if i < j else a[k]) - sa
        else:
            asa = -sa
        xsx = x[i] / rng - sx
        ssa += asa * asa
        ssx += xsx * xsx
        sax += asa * xsx
    ssassx = math.sqrt(ssa * ssx)
    w1 = (ssassx - sax) * (ssassx + sax) / (ssa * ssx)
    w = 1.0 - w1
    # the significance level
    if n == 3:
        pi6 = 1.90985931710274
        stqr = 1.04719755119660
        pw = pi6 * (math.asin(math.sqrt(w)) - stqr)
        if pw < 0.0:
            pw = 0.0
        return w, pw
    y = math.log(w1)
    xx = math.log(an)
    if n <= 11:
        gamma = _poly(g, an)
        if y >= gamma:
            return w, 1e-99
        y = -math.log(gamma - y)
        m = _poly(c3, an)
        s = math.exp(_poly(c4, an))
    else:
        m = _poly(c5, xx)
        s = math.exp(_poly(c6, xx))
    return w, pnorm(y, m, s, lower_tail=False)


def shapiro_test(x: list[float], data_name: str = "x") -> HTest:
    """The Shapiro-Wilk normality test (R's shapiro.test)."""
    xs = sorted(x)
    n = len(xs)
    if n < 3 or n > 5000:
        raise ValueError("sample size must be between 3 and 5000")
    rng = xs[n - 1] - xs[0]
    if rng == 0.0:
        raise ValueError("all 'x' values are identical")
    if rng < 1e-10:
        xs = [v / rng for v in xs]
    w, p = _swilk(xs)
    h = HTest("Shapiro-Wilk normality test", data_name)
    h.statistic_name = "W"
    h.statistic = w
    h.p_value = p
    return h


# ------------------------------------------------------------ adjusting p-values


def p_adjust(p: list[float], method: str = "holm", n: int = 0) -> list[float]:
    """Adjusted p-values (R's p.adjust).

    The methods are R's: "holm", "hochberg", "hommel", "bonferroni", "BH"
    (the same as "fdr"), "BY" and "none". `n` is the number of tests (by
    default the number of p-values)."""
    if method == "fdr":
        method = "BH"
    if method not in ("holm", "hochberg", "hommel", "bonferroni", "BH", "BY", "none"):
        raise ValueError("'method' must be one of \"holm\", \"hochberg\", \"hommel\", \"bonferroni\", \"BH\", \"BY\", \"fdr\", \"none\"")
    # the missing values keep their place
    vals: list[float] = []
    where: list[int] = []
    for i in range(len(p)):
        if not math.isnan(p[i]):
            vals.append(p[i])
            where.append(i)
    lp = len(vals)
    if n <= 0:
        n = lp
    out = [math.nan] * len(p)
    if n <= 1 or lp == 0:
        for i in range(len(p)):
            out[i] = p[i]
        return out
    if n == 2 and method == "hommel":
        method = "hochberg"
    if method == "bonferroni":
        adj = [min(1.0, float(n) * v) for v in vals]
    elif method == "none":
        adj = list(vals)
    elif method == "holm":
        o = sorted(range(lp), key=lambda i: vals[i])
        ro = sorted(range(lp), key=lambda i: o[i])
        acc = 0.0
        q: list[float] = []
        for i in range(lp):
            v = float(n + 1 - (i + 1)) * vals[o[i]]
            if v > acc:
                acc = v
            q.append(min(1.0, acc))
        adj = [0.0] * lp
        for i in range(lp):
            adj[ro[i]] = q[i]
    elif method == "hochberg":
        o = sorted(range(lp), key=lambda i: -vals[i])
        ro = sorted(range(lp), key=lambda i: o[i])
        acc = math.inf
        q = [0.0] * lp
        for i in range(lp):
            v = float(n + 1 - (lp - i)) * vals[o[i]]
            if v < acc:
                acc = v
            q[i] = min(1.0, acc)
        adj = [0.0] * lp
        for i in range(lp):
            adj[ro[i]] = q[i]
    elif method == "hommel":
        if n > lp:
            vals = vals + [1.0] * (n - lp)
        nn = n
        o = sorted(range(nn), key=lambda i: vals[i])
        ro = sorted(range(nn), key=lambda i: o[i])
        ps = [0.0] * nn
        for i in range(nn):
            ps[i] = vals[o[i]]
        q = [0.0] * nn
        pa = [0.0] * nn
        m0 = math.inf
        for i in range(nn):
            v = float(nn) * ps[i] / float(i + 1)
            if v < m0:
                m0 = v
        for i in range(nn):
            q[i] = m0
            pa[i] = m0
        j = nn - 1
        while j >= 2:
            q1 = math.inf
            for k in range(j - 1):
                v = float(j) * ps[nn - j + 1 + k] / float(2 + k)
                if v < q1:
                    q1 = v
            for k in range(nn - j + 1):
                v = float(j) * ps[k]
                if q1 < v:
                    v = q1
                q[k] = v
            for k in range(nn - j + 1, nn):
                q[k] = q[nn - j]
            for k in range(nn):
                pa[k] = max(pa[k], q[k])
            j -= 1
        adj = [0.0] * lp
        for i in range(lp):
            v = max(pa[i], ps[i])
            adj[ro[i] if lp == nn else ro[i]] = v
    else:
        # BH and BY
        o = sorted(range(lp), key=lambda i: -vals[i])
        ro = sorted(range(lp), key=lambda i: o[i])
        q = [0.0] * lp
        acc = math.inf
        c = 0.0
        if method == "BY":
            for k in range(1, n + 1):
                c += 1.0 / float(k)
        for i in range(lp):
            v = float(n) / float(lp - i) * vals[o[i]]
            if method == "BY":
                v = c * float(n) / float(lp - i) * vals[o[i]]
            if v < acc:
                acc = v
            q[i] = min(1.0, acc)
        adj = [0.0] * lp
        for i in range(lp):
            adj[ro[i]] = q[i]
    for i in range(lp):
        out[where[i]] = adj[i]
    return out
