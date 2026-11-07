"""Linear models: R's `lm` (the Householder QR of `lm.fit`), the summary of
the fit, the analysis of variance and the predictions.

The algorithms are R's: `dqrdc2` (the Householder QR with the column
pivoting) and `dqrsl` (the least squares solution) of R's `src/appl`, and
the summary of `src/library/stats/R/lm.R`."""

import math

from rstatistics.distributions import pf, pt, qt
from rstatistics.rformat import format_num, format_vec, print_named


def _lm_dnrm2(xs: list[float]) -> float:
    """The 2-norm of a vector, as the reference BLAS computes it."""
    scale = 0.0
    ssq = 1.0
    for x in xs:
        if x != 0.0:
            absxi = abs(x)
            if scale < absxi:
                ssq = 1.0 + ssq * (scale / absxi) ** 2
                scale = absxi
            else:
                ssq = ssq + (absxi / scale) ** 2
    return scale * math.sqrt(ssq)


def _lm_ddot(a: list[float], b: list[float]) -> float:
    """The inner product of two vectors, as the reference BLAS computes it."""
    s = 0.0
    for i in range(len(a)):
        s += a[i] * b[i]
    return s


def _lm_dqrdc2(x: list[list[float]], n: int, p: int, tol: float) -> tuple[int, list[float], list[int]]:
    """R's `dqrdc2`: the Householder QR of an n by p matrix with the column
    pivoting.  The matrix is a list of columns and is overwritten."""
    qraux = [0.0] * p
    work1 = [0.0] * p
    work2 = [0.0] * p
    jpvt = list(range(p))
    for j in range(p):
        qraux[j] = _lm_dnrm2(x[j])
        work1[j] = qraux[j]
        work2[j] = qraux[j]
        if work2[j] == 0.0:
            work2[j] = 1.0
    lup = min(n, p)
    k = p
    for l in range(lup):
        # cycle the columns from l to p until one with a non-negligible norm
        while True:
            if l >= k or qraux[l] >= work2[l] * tol:
                break
            for i in range(n):
                t = x[l][i]
                for j in range(l + 1, p):
                    x[j - 1][i] = x[j][i]
                x[p - 1][i] = t
            i_piv = jpvt[l]
            t = qraux[l]
            tt = work1[l]
            ttt = work2[l]
            for j in range(l + 1, p):
                jpvt[j - 1] = jpvt[j]
                qraux[j - 1] = qraux[j]
                work1[j - 1] = work1[j]
                work2[j - 1] = work2[j]
            jpvt[p - 1] = i_piv
            qraux[p - 1] = t
            work1[p - 1] = tt
            work2[p - 1] = ttt
            k -= 1
        if l != n - 1:
            # the Householder transformation of the column l
            nrmxl = _lm_dnrm2(x[l][l:])
            if nrmxl != 0.0:
                if x[l][l] != 0.0:
                    nrmxl = math.copysign(nrmxl, x[l][l])
                inv = 1.0 / nrmxl
                for i in range(l, n):
                    x[l][i] = x[l][i] * inv
                x[l][l] = 1.0 + x[l][l]
                if p >= l + 2:
                    for j in range(l + 1, p):
                        t = -_lm_ddot(x[l][l:], x[j][l:]) / x[l][l]
                        for i in range(l, n):
                            x[j][i] += t * x[l][i]
                        if qraux[j] != 0.0:
                            tt = 1.0 - (abs(x[j][l]) / qraux[j]) ** 2
                            if tt < 0.0:
                                tt = 0.0
                            if abs(tt) >= 1e-6:
                                qraux[j] = qraux[j] * math.sqrt(tt)
                            else:
                                qraux[j] = _lm_dnrm2(x[j][l + 1:])
                                work1[j] = qraux[j]
                qraux[l] = x[l][l]
                x[l][l] = -nrmxl
    return min(k, n), qraux, jpvt


def _lm_dqrsl(x: list[list[float]], n: int, k: int, qraux: list[float], y: list[float]) -> tuple[list[float], list[float], list[float]]:
    """R's `dqrsl` with job = 1110: the least squares solution and the
    residuals.  The matrix is a list of columns and is overwritten."""
    qty = list(y)
    b = [0.0] * k
    rsd = [0.0] * n
    ju = min(k, n - 1)
    if ju == 0:
        if x[0][0] != 0.0:
            b[0] = qty[0] / x[0][0]
        return b, rsd, qty
    # qty = Q'y
    for j in range(ju):
        if qraux[j] != 0.0:
            temp = x[j][j]
            x[j][j] = qraux[j]
            t = -_lm_ddot(x[j][j:], qty[j:]) / x[j][j]
            for i in range(j, n):
                qty[i] += t * x[j][i]
            x[j][j] = temp
    for i in range(k):
        b[i] = qty[i]
    if k < n:
        for i in range(k, n):
            rsd[i] = qty[i]
    for i in range(k):
        rsd[i] = 0.0
    # the back substitution
    for jj in range(k):
        j = k - 1 - jj
        if x[j][j] != 0.0:
            b[j] = b[j] / x[j][j]
            if j != 0:
                t = -b[j]
                for i in range(j):
                    b[i] += t * x[j][i]
    # the residuals
    for jj in range(ju):
        j = ju - 1 - jj
        if qraux[j] != 0.0:
            temp = x[j][j]
            x[j][j] = qraux[j]
            t = -_lm_ddot(x[j][j:], rsd[j:]) / x[j][j]
            for i in range(j, n):
                rsd[i] += t * x[j][i]
            x[j][j] = temp
    return b, rsd, qty


def _lm_chol2inv_diag(u: list[list[float]]) -> list[float]:
    """The diagonal of (U'U)^-1, as R's `chol2inv` computes it: the squared
    row norms of the inverse of the upper triangular matrix U."""
    n = len(u)
    # the inverse of the upper triangular matrix
    v = [[0.0] * n for _ in range(n)]
    for j in range(n):
        v[j][j] = 1.0 / u[j][j]
        for i in range(j - 1, -1, -1):
            s = 0.0
            for k in range(i + 1, j + 1):
                s += u[i][k] * v[k][j]
            v[i][j] = -s / u[i][i]
    out = [0.0] * n
    for j in range(n):
        s = 0.0
        for k in range(n):
            s += v[j][k] * v[j][k]
        out[j] = s
    return out


class LMSummary:
    """The summary of a linear model, printed as R prints it."""

    def __init__(
        self,
        call: str,
        residuals: list[float],
        names: list[str],
        estimates: list[float],
        std_errors: list[float],
        t_values: list[float],
        p_values: list[float],
        sigma: float,
        r_squared: float,
        adj_r_squared: float,
        f_statistic: list[float],
        df: list[float],
        aliased: list[str],
    ) -> None:
        self.call = call
        self.residuals = residuals
        self.names = names
        self.estimates = estimates
        self.std_errors = std_errors
        self.t_values = t_values
        self.p_values = p_values
        self.sigma = sigma
        self.r_squared = r_squared
        self.adj_r_squared = adj_r_squared
        self.f_statistic = f_statistic
        self.df = df
        self.aliased = aliased

    def __str__(self) -> str:
        digits = 4
        lines: list[str] = []
        lines.append("")
        lines.append("Call:")
        lines.append(self.call)
        lines.append("")
        lines.append("Residuals:")
        r = self.residuals
        if self.df[1] > 5.0:
            q = _lm_zapsmall(_lm_quantiles(r), digits + 1)
            lines.append(print_named(["Min", "1Q", "Median", "3Q", "Max"], format_vec(q, digits)))
        else:
            lines.append(print_named([str(i + 1) for i in range(len(r))], format_vec(r, digits)))
        lines.append("")
        if len(self.aliased) > 0:
            lines.append("Coefficients: (" + str(len(self.aliased)) + " not defined because of singularities)")
        else:
            lines.append("Coefficients:")
        lines.append(_lm_coefmat(self))
        lines.append("---")
        lines.append("Signif. codes:  0 ‘***’ 0.001 ‘**’ 0.01 ‘*’ 0.05 ‘.’ 0.1 ‘ ’ 1")
        lines.append("")
        lines.append("Residual standard error: " + format_num(self.sigma, digits).strip() + " on " + _lm_int(self.df[1]) + " degrees of freedom")
        if self.f_statistic[1] > 0.0:
            lines.append("Multiple R-squared:  " + _lm_formatc(self.r_squared, digits) + ",\tAdjusted R-squared:  " + _lm_formatc(self.adj_r_squared, digits) + " ")
            lines.append("F-statistic: " + _lm_formatc(self.f_statistic[0], digits) + " on " + _lm_int(self.f_statistic[1]) + " and " + _lm_int(self.f_statistic[2]) + " DF,  p-value: " + _lm_pval(pf(self.f_statistic[0], self.f_statistic[1], self.f_statistic[2], lower_tail=False), digits))
        lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()


class LM:
    """A linear model, as R's `lm` object."""

    def __init__(
        self,
        coefficients: list[float],
        names: list[str],
        residuals: list[float],
        fitted_values: list[float],
        df_residual: float,
        rank: int,
        pivot: list[int],
        r_matrix: list[list[float]],
        effects: list[float],
        call: str,
        formula: str,
        intercept: bool,
    ) -> None:
        self.coefficients = coefficients
        self.names = names
        self.residuals = residuals
        self.fitted_values = fitted_values
        self.df_residual = df_residual
        self.rank = rank
        self.pivot = pivot
        self.r_matrix = r_matrix
        self.effects = effects
        self.call = call
        self.formula = formula
        self.intercept = intercept

    def __str__(self) -> str:
        return self.summary().__str__()

    def __repr__(self) -> str:
        return self.summary().__str__()

    def coefficient(self, name: str) -> float:
        """The coefficient named `name`."""
        return self.coefficients[self.names.index(name)]

    def summary(self) -> LMSummary:
        """The summary of the fit, as R's `summary.lm` computes it."""
        n = float(len(self.residuals))
        p = float(self.rank)
        rdf = self.df_residual
        r = self.residuals
        f = self.fitted_values
        if self.intercept:
            mf = 0.0
            for v in f:
                mf += v
            mf /= n
            mss = 0.0
            for v in f:
                mss += (v - mf) * (v - mf)
        else:
            mss = 0.0
            for v in f:
                mss += v * v
        rss = 0.0
        for v in r:
            rss += v * v
        resvar = rss / rdf
        sigma = math.sqrt(resvar)
        r_squared = mss / (mss + rss)
        diag = _lm_chol2inv_diag(self.r_matrix)
        np_ = len(self.coefficients)
        estimates: list[float] = []
        se: list[float] = []
        tval: list[float] = []
        pval: list[float] = []
        for i in range(np_):
            estimates.append(math.nan)
            se.append(math.nan)
            tval.append(math.nan)
            pval.append(math.nan)
        for i in range(int(p)):
            j = self.pivot[i]
            estimates[j] = self.coefficients[j]
            se[j] = math.sqrt(diag[i] * resvar)
            tval[j] = estimates[j] / se[j]
            pval[j] = 2.0 * pt(abs(tval[j]), rdf, lower_tail=False)
        df_int = 1.0 if self.intercept else 0.0
        f_statistic = [0.0, 0.0, 0.0]
        if p > df_int:
            f_statistic[0] = (mss / (p - df_int)) / resvar
            f_statistic[1] = p - df_int
            f_statistic[2] = rdf
            adj_r_squared = 1.0 - (1.0 - r_squared) * ((n - df_int) / rdf)
        else:
            adj_r_squared = 0.0
        aliased: list[str] = []
        for i in range(len(self.coefficients)):
            if math.isnan(self.coefficients[i]):
                aliased.append(self.names[i])
        names = list(self.names)
        return LMSummary(
            self.call,
            list(r),
            names,
            estimates,
            se,
            tval,
            pval,
            sigma,
            r_squared,
            adj_r_squared,
            f_statistic,
            [p, rdf, float(len(self.coefficients))],
            aliased,
        )


def _lm_formatg(x: float, digits: int) -> str:
    """C's "%.*g" format of a number."""
    if x == 0.0:
        return "0"
    neg = x < 0.0
    ax = abs(x)
    s = format(ax, "." + str(digits - 1) + "e")
    mant, ex = s.split("e")
    e = int(ex)
    if e < -4 or e >= digits:
        if "." in mant:
            mant = mant.rstrip("0").rstrip(".")
        return ("-" if neg else "") + mant + "e" + ("+" if e >= 0 else "-") + ("0" + str(abs(e)) if abs(e) < 10 else str(abs(e)))
    dec = digits - 1 - e
    out = format(ax, "." + str(dec) + "f")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return ("-" if neg else "") + out


def _lm_formatc(x: float, digits: int) -> str:
    """R's `formatC(x, digits = digits)`: the "%g" format, right aligned in
    the width digits + 1."""
    s = _lm_formatg(x, digits)
    w = digits + 1
    return " " * (w - len(s)) + s if len(s) < w else s


def _lm_int(v: float) -> str:
    """An integer as R prints it."""
    return str(int(v))


def _lm_pval(p: float, digits: int) -> str:
    """A p-value as R's `format.pval` prints it."""
    eps = 2.220446049250313e-16
    if p < eps:
        return "< " + format_num(eps, digits).strip()
    return format_vec([p], digits)[0].strip()


def _lm_zapsmall(xs: list[float], digits: int) -> list[float]:
    """`zapsmall`: the values too small next to the largest are rounded away."""
    mx = 0.0
    for v in xs:
        if math.isfinite(v) and abs(v) > mx:
            mx = abs(v)
    if mx == 0.0:
        return list(xs)
    d = digits - math.log10(mx)
    if d < 0.0:
        d = 0.0
    nd = int(d)
    return [round(v, nd) for v in xs]


def _lm_quantiles(x: list[float]) -> list[float]:
    """The quartiles of a vector, as R's `quantile` (type 7) computes them."""
    s = sorted(x)
    n = len(s)
    out: list[float] = []
    for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
        index = 1.0 + float(max(n - 1, 0)) * p
        lo = int(math.floor(index))
        hi = int(math.ceil(index))
        q = s[lo - 1]
        h = index - float(lo)
        if index > float(lo) and s[hi - 1] != q:
            q = (1.0 - h) * q + h * s[hi - 1]
        out.append(q)
    return out


def _lm_coefmat(s: LMSummary) -> str:
    """The coefficients table, as R's `printCoefmat` prints it."""
    digits = 4
    n = len(s.estimates)
    # the estimates and their standard errors, rounded as R rounds them
    acs: list[float] = []
    for i in range(n):
        acs.append(abs(s.estimates[i]))
    for i in range(n):
        acs.append(abs(s.std_errors[i]))
    digmin = 0
    smallest = math.inf
    for v in acs:
        if v != 0.0 and math.isfinite(v) and v < smallest:
            smallest = v
    if smallest != math.inf:
        digmin = 1 + int(math.floor(math.log10(smallest)))
    ndec = max(1, digits - digmin)
    est_c = format_vec([round(v, ndec) for v in s.estimates], digits)
    se_c = format_vec([round(v, ndec) for v in s.std_errors], digits)
    dig_tst = max(1, min(5, digits - 1))
    t_c = format_vec([round(v, dig_tst) for v in s.t_values], digits)
    p_c = format_vec(s.p_values, dig_tst)
    # the stars, as a character vector of one width
    stars: list[str] = []
    for v in s.p_values:
        if v < 0.001:
            stars.append("***")
        elif v < 0.01:
            stars.append("**")
        elif v < 0.05:
            stars.append("*")
        elif v < 0.1:
            stars.append(".")
        else:
            stars.append(" ")
    starw = 0
    for t in stars:
        if len(t) > starw:
            starw = len(t)
    star_c = [t.ljust(starw) for t in stars]
    headers = ["Estimate", "Std. Error", "t value", "Pr(>|t|)", ""]
    # the rows of the table
    rows: list[list[str]] = []
    for i in range(n):
        if math.isnan(s.estimates[i]):
            rows.append(["NA", "NA", "NA", "NA", ""])
        else:
            rows.append([est_c[i], se_c[i], t_c[i], p_c[i], star_c[i]])
    names = list(s.names)
    # the width of the columns
    widths: list[int] = []
    for j in range(len(headers)):
        w = len(headers[j])
        for row in rows:
            if len(row[j]) > w:
                w = len(row[j])
        widths.append(w)
    # the row names
    labw = 0
    for nm in names:
        if len(nm) > labw:
            labw = len(nm)
    lines: list[str] = []
    head = " " * labw + " "
    for j in range(len(headers)):
        head += headers[j].rjust(widths[j])
        if j < len(headers) - 1:
            head += " "
    lines.append(head)
    for i in range(n):
        line = names[i].ljust(labw) + " "
        for j in range(len(headers)):
            line += rows[i][j].rjust(widths[j])
            if j < len(headers) - 1:
                line += " "
        lines.append(line)
    return "\n".join(lines)


def lm(
    y: list[float],
    x: list[list[float]],
    names: list[str] | None = None,
    intercept: bool = True,
    call: str = "",
) -> LM:
    """The linear model of y on the columns of x (R's `lm`).

    `x` is a list of columns, one per predictor; `names` names them.  With
    an intercept the first column of the fit is the constant one.  The
    coefficients are computed with the Householder QR of R's `lm.fit`."""
    n = len(y)
    if n == 0:
        raise ValueError("0 (non-NA) cases")
    p = len(x)
    nms = ["" for _ in range(p)] if names is None else list(names)
    if len(nms) != p:
        raise ValueError("'names' must have one name per column of 'x'")
    cols: list[list[float]] = []
    cnms: list[str] = []
    if intercept:
        cols.append([1.0] * n)
        cnms.append("(Intercept)")
    for j in range(p):
        if len(x[j]) != n:
            raise ValueError("'x' and 'y' must have the same number of rows")
        cols.append(list(x[j]))
        cnms.append(nms[j])
    np_ = len(cols)
    k, qraux, jpvt = _lm_dqrdc2(cols, n, np_, 1e-7)
    b, rsd, qty = _lm_dqrsl(cols, n, k, qraux, list(y))
    # the coefficients, in the order of the columns
    coef = [0.0] * np_
    for i in range(k):
        coef[jpvt[i]] = b[i]
    for i in range(k, np_):
        coef[jpvt[i]] = math.nan
    fitted = [0.0] * n
    for i in range(n):
        fitted[i] = y[i] - rsd[i]
    # the upper triangle of R, in the pivot order
    r_matrix = [[0.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i, k):
            r_matrix[i][j] = cols[j][i]
    formula = "y ~ " + " + ".join(nms)
    if not intercept:
        formula = formula + " - 1"
    if call == "":
        call = "lm(formula = " + formula + ")"
    effects = [0.0] * k
    for i in range(k):
        effects[i] = qty[i]
    return LM(coef, cnms, list(rsd), fitted, float(n - k), k, jpvt, r_matrix, effects, call, formula, intercept)


# ------------------------------------------------------------ analysis of variance


class Anova:
    """The analysis of variance table (R's `anova` object)."""

    def __init__(self, rows: list[str], df: list[float], ss: list[float], ms: list[float], f: list[float], p: list[float], response: str, heading: bool, digits: int = 5, label_pad: int = 1, frame: bool = False) -> None:
        self.digits = digits
        self.label_pad = label_pad
        self.frame = frame
        self.rows = rows
        self.df = df
        self.ss = ss
        self.ms = ms
        self.f = f
        self.p = p
        self.response = response
        self.heading = heading

    def __str__(self) -> str:
        lines: list[str] = []
        if self.heading:
            lines.append("Analysis of Variance Table")
            lines.append("")
            lines.append("Response: " + self.response)
        lines.append(_lm_anova_table(self))
        if self.heading:
            lines.append("---")
            lines.append("Signif. codes:  0 ‘***’ 0.001 ‘**’ 0.01 ‘*’ 0.05 ‘.’ 0.1 ‘ ’ 1")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()


def _lm_anova_table(a: Anova) -> str:
    """The table of the analysis of variance, as R prints it."""
    digits = a.digits
    n = len(a.rows)
    dig_tst = max(1, min(5, digits - 1))
    df_c = [str(int(v)) for v in a.df]
    ss_c = format_vec(_lm_zapsmall(a.ss, digits), digits)
    ms_c = format_vec(_lm_zapsmall(a.ms, digits), digits)
    # the F values, rounded to four decimals
    f_vals: list[float] = []
    f_pos: list[int] = []
    for i in range(n):
        if not math.isnan(a.f[i]):
            f_vals.append(round(a.f[i], 4))
            f_pos.append(i)
    f_c = [""] * n
    if len(f_vals) > 0:
        f_all = format_vec(f_vals, digits)
        for i in range(len(f_pos)):
            f_c[f_pos[i]] = f_all[i]
    # the p-values
    p_vals: list[float] = []
    p_pos: list[int] = []
    for i in range(n):
        if not math.isnan(a.p[i]):
            p_vals.append(a.p[i])
            p_pos.append(i)
    p_c = [""] * n
    if len(p_vals) > 0:
        p_all = format_vec(p_vals, dig_tst)
        for i in range(len(p_pos)):
            p_c[p_pos[i]] = p_all[i]
    # the stars
    stars: list[str] = []
    for v in a.p:
        if math.isnan(v):
            stars.append("")
        elif v < 0.001:
            stars.append("***")
        elif v < 0.01:
            stars.append("**")
        elif v < 0.05:
            stars.append("*")
        elif v < 0.1:
            stars.append(".")
        else:
            stars.append(" ")
    # the widths of the columns
    dfw = max(len("Df"), 1)
    ssw = len("Sum Sq")
    for c in ss_c:
        if len(c) > ssw:
            ssw = len(c)
    msw = len("Mean Sq")
    for c in ms_c:
        if len(c) > msw:
            msw = len(c)
    fw = len("F value")
    for c in f_c:
        if len(c) > fw:
            fw = len(c)
    pw = len("Pr(>F)")
    for c in p_c:
        if len(c) > pw:
            pw = len(c)
    stw = 0
    for t in stars:
        if len(t) > stw:
            stw = len(t)
    labw = 0
    for nm in a.rows:
        if len(nm) > labw:
            labw = len(nm)
    labw += a.label_pad
    lines: list[str] = []
    head = " " * labw + "Df".rjust(dfw) + " " + "Sum Sq".rjust(ssw) + " " + "Mean Sq".rjust(msw) + " " + "F value".rjust(fw) + " " + "Pr(>F)".rjust(pw)
    if not a.frame:
        head = head + " " + "".rjust(stw)
    lines.append(head)
    for i in range(n):
        if a.frame:
            # the cells of a data frame are right justified in their column
            line = a.rows[i].ljust(labw) + df_c[i].rjust(dfw) + " " + ss_c[i].rjust(ssw) + " " + ms_c[i].rjust(msw) + " " + f_c[i].rjust(fw) + " " + p_c[i].rjust(pw)
        else:
            p_cell = p_c[i]
            if p_cell == "":
                p_cell = " " * pw
            line = a.rows[i].ljust(labw) + df_c[i].rjust(dfw) + " " + ss_c[i] + " " + ms_c[i] + " " + f_c[i].rjust(fw) + " " + p_cell + " " + stars[i].rjust(stw)
        lines.append(line)
    return "\n".join(lines)


def anova(model: LM) -> Anova:
    """The analysis of variance of a linear model (R's `anova.lm`)."""
    m = model
    n = float(len(m.residuals))
    ssr = 0.0
    for v in m.residuals:
        ssr += v * v
    dfr = m.df_residual
    p = float(m.rank)
    # the sum of squares of every term, in the order of the effects
    terms: list[int] = []
    ss: list[float] = []
    counts: list[float] = []
    for i in range(int(p)):
        j = m.pivot[i]
        term = 0 if j == 0 else j
        if term not in terms:
            terms.append(term)
            ss.append(0.0)
            counts.append(0.0)
        k = terms.index(term)
        ss[k] += m.effects[i] * m.effects[i]
        counts[k] += 1.0
    labels: list[str] = []
    for term in terms:
        if term == 0:
            labels.append("(Intercept)")
        else:
            labels.append(m.names[term])
    if m.intercept:
        # the intercept is not a term of the table
        keep: list[int] = []
        for i in range(len(terms)):
            if terms[i] != 0:
                keep.append(i)
        terms = [terms[i] for i in keep]
        ss = [ss[i] for i in keep]
        counts = [counts[i] for i in keep]
        labels = [labels[i] for i in keep]
    rows = list(labels)
    dfs = list(counts)
    sss = list(ss)
    rows.append("Residuals")
    dfs.append(dfr)
    sss.append(ssr)
    ms = [0.0] * len(sss)
    for i in range(len(sss)):
        if dfs[i] > 0.0:
            ms[i] = sss[i] / dfs[i]
    f = [0.0] * len(sss)
    pvals = [0.0] * len(sss)
    for i in range(len(sss) - 1):
        f[i] = ms[i] / (ssr / dfr)
        pvals[i] = pf(f[i], dfs[i], dfr, lower_tail=False)
    f[len(sss) - 1] = math.nan
    pvals[len(sss) - 1] = math.nan
    response = m.formula.split("~")[0].strip()
    return Anova(rows, dfs, sss, ms, f, pvals, response, True)


class AOV:
    """The analysis of variance of a one-way layout (R's `aov` object)."""

    def __init__(self, groups: list[str], levels: list[str], ss: list[float], df: list[float], ms: list[float], f: float, p: float, residual: float, call: str, formula: str, term_name: str) -> None:
        self.term_name = term_name
        self.groups = groups
        self.levels = levels
        self.ss = ss
        self.df = df
        self.ms = ms
        self.f = f
        self.p = p
        self.residual = residual
        self.call = call
        self.formula = formula

    def __str__(self) -> str:
        return _lm_print_aov(self)

    def __repr__(self) -> str:
        return self.__str__()

    def summary(self) -> Anova:
        """The analysis of variance table (R's `summary.aov`)."""
        rows = [self.term_name, "Residuals"]
        dfs = [self.df[0], self.df[1]]
        sss = [self.ss[0], self.ss[1]]
        ms = [self.ms[0], self.ms[1]]
        f = [self.f, math.nan]
        p = [self.p, math.nan]
        return Anova(rows, dfs, sss, ms, f, p, self.formula.split("~")[0].strip(), False, 4, 3, True)


def _lm_print_aov(a: AOV) -> str:
    """The print of an `aov` object, as R prints it."""
    lines: list[str] = []
    lines.append("Call:")
    lines.append("   " + a.call)
    lines.append("")
    lines.append("Terms:")
    labels = ["Sum of Squares", "Deg. of Freedom"]
    ss_all = format_vec([a.ss[0], a.ss[1]], 7)
    ss_c = ss_all[0]
    ss_r = ss_all[1]
    df_c = str(int(a.df[0]))
    df_r = str(int(a.df[1]))
    w0 = len(labels[1])
    w1 = max(len(a.term_name), len(ss_c), len(df_c))
    w2 = max(len("Residuals"), len(ss_r), len(df_r))
    lines.append(" " * w0 + " " + a.term_name.rjust(w1) + " " + "Residuals".rjust(w2))
    for i in range(2):
        if i == 0:
            val = ss_c
            rval = ss_r
        else:
            val = df_c
            rval = df_r
        lines.append(labels[i].ljust(w0) + " " + val.rjust(w1) + " " + rval.rjust(w2))
    lines.append("")
    lines.append("Residual standard error: " + format_num(a.residual, 7).strip())
    lines.append("Estimated effects may be unbalanced")
    return "\n".join(lines)


def aov(y: list[float], group: list[str], call: str = "", formula: str = "y ~ g") -> AOV:
    """The analysis of variance of a one-way layout (R's `aov`)."""
    if len(y) != len(group):
        raise ValueError("'y' and 'group' must have the same length")
    levels = _lm_unique_sorted(group)
    n = float(len(y))
    k = float(len(levels))
    if k < 2.0:
        raise ValueError("need at least two groups")
    my = 0.0
    for v in y:
        my += v
    my /= n
    ss_between = 0.0
    ss_within = 0.0
    counts = [0.0] * len(levels)
    sums = [0.0] * len(levels)
    for i in range(len(y)):
        j = levels.index(group[i])
        counts[j] += 1.0
        sums[j] += y[i]
    for j in range(len(levels)):
        mj = sums[j] / counts[j]
        ss_between += counts[j] * (mj - my) * (mj - my)
    for i in range(len(y)):
        j = levels.index(group[i])
        mj = sums[j] / counts[j]
        ss_within += (y[i] - mj) * (y[i] - mj)
    df_between = k - 1.0
    df_within = n - k
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    f = ms_between / ms_within
    p = pf(f, df_between, df_within, lower_tail=False)
    if call == "":
        call = "aov(formula = " + formula + ")"
    term = formula.split("~")[1].strip()
    if term == "g":
        term = "g"
    return AOV(group, levels, [ss_between, ss_within], [df_between, df_within], [ms_between, ms_within], f, p, math.sqrt(ms_within), call, formula, term)


def _lm_unique_sorted(xs: list[str]) -> list[str]:
    """The distinct values of a vector, sorted (R's factor levels)."""
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    out.sort()
    return out


# ----------------------------------------------------------------- predictions


class Predict:
    """The predictions of a linear model (R's `predict.lm`)."""

    def __init__(self, fit: list[float], se: list[float], lwr: list[float], upr: list[float], interval: str, level: float) -> None:
        self.fit = fit
        self.se = se
        self.lwr = lwr
        self.upr = upr
        self.interval = interval
        self.level = level

    def __str__(self) -> str:
        names = [str(i + 1) for i in range(len(self.fit))]
        if self.interval == "none":
            return print_named(names, format_vec(self.fit, 7))
        cols = [format_vec(self.fit, 7), format_vec(self.lwr, 7), format_vec(self.upr, 7)]
        cells: list[list[str]] = []
        for i in range(len(self.fit)):
            cells.append([cols[0][i], cols[1][i], cols[2][i]])
        return _lm_print_matrix(cells, names, ["fit", "lwr", "upr"])

    def __repr__(self) -> str:
        return self.__str__()


def _lm_print_matrix(cells: list[list[str]], rownames: list[str], colnames: list[str]) -> str:
    """A matrix of strings, printed as R prints a matrix with dimnames."""
    widths: list[int] = []
    for j in range(len(colnames)):
        w = len(colnames[j])
        for row in cells:
            if len(row[j]) > w:
                w = len(row[j])
        widths.append(w)
    labw = 0
    for nm in rownames:
        if len(nm) > labw:
            labw = len(nm)
    labw += 1
    lines: list[str] = []
    head = " " * labw
    for j in range(len(colnames)):
        head += colnames[j].rjust(widths[j])
        if j < len(colnames) - 1:
            head += " "
    lines.append(head)
    for i in range(len(cells)):
        line = rownames[i].ljust(labw)
        for j in range(len(colnames)):
            line += cells[i][j].rjust(widths[j])
            if j < len(colnames) - 1:
                line += " "
        lines.append(line)
    return "\n".join(lines)


def predict(model: LM, new_x: list[list[float]], interval: str = "none", level: float = 0.95) -> Predict:
    """The predictions of a linear model for new data (R's `predict.lm`).

    `new_x` is a list of columns, as in `lm`.  With `interval` "confidence"
    or "prediction" the interval of the mean or of a new observation is
    returned as well."""
    if interval not in ("none", "confidence", "prediction"):
        raise ValueError("'interval' must be one of \"none\", \"confidence\", \"prediction\"")
    m = model
    n = len(new_x[0]) if len(new_x) > 0 else 0
    for col in new_x:
        if len(col) != n:
            raise ValueError("the columns of 'new_x' must have the same length")
    # the design matrix of the new data
    rows: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        if m.intercept:
            row.append(1.0)
        for col in new_x:
            row.append(col[i])
        rows.append(row)
    # the predictions
    fit = [0.0] * n
    for i in range(n):
        s = 0.0
        for j in range(len(m.coefficients)):
            s += rows[i][j] * m.coefficients[j]
        fit[i] = s
    # the residual variance
    rss = 0.0
    for v in m.residuals:
        rss += v * v
    sigma = math.sqrt(rss / m.df_residual)
    # the leverage of the new observations
    p = len(m.coefficients)
    lev = [0.0] * n
    for i in range(n):
        # the value of the new observation in the pivot order
        xp = [0.0] * p
        for j in range(p):
            xp[j] = rows[i][m.pivot[j]]
        # solve R' z = xp by forward substitution: the leverage is |z|^2
        z = [0.0] * p
        for j in range(p):
            s = xp[j]
            for k in range(j):
                s -= m.r_matrix[k][j] * z[k]
            z[j] = s / m.r_matrix[j][j]
        h = 0.0
        for v in z:
            h += v * v
        lev[i] = h
    se = [0.0] * n
    lwr = [0.0] * n
    upr = [0.0] * n
    if interval != "none":
        t = qt(1.0 - (1.0 - level) / 2.0, m.df_residual)
        for i in range(n):
            if interval == "confidence":
                se[i] = sigma * math.sqrt(lev[i])
                half = t * se[i]
            else:
                half = t * sigma * math.sqrt(1.0 + lev[i])
            lwr[i] = fit[i] - half
            upr[i] = fit[i] + half
    return Predict(fit, se, lwr, upr, interval, level)
