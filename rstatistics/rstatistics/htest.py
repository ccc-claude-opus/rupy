"""Hypothesis tests that return an HTest, printed as R prints an `htest`:
t_test, var_test, chisq_test, binom_test, prop_test and cor_test. The data
name R takes from the call is the `data_name` argument ("x", "x and y")."""

import math

from rstatistics.describe import Named, cor, mean, var
from rstatistics.distributions import dbinom, pbinom, pchisq, pf, pnorm, pt, qbeta, qf, qnorm, qt
from rstatistics.rformat import format_vec, format_num, format_pval, print_named


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
            alt = {"two.sided": "not equal to", "less": "less than", "greater": "greater than"}[self.alternative]
            if self.null_name != "":
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
