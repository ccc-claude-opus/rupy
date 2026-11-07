"""The calculation layer of R's graphics: the pretty ticks, the statistics
of a histogram and of a density, the empirical distribution, the box
plot's statistics and the probability points.

The algorithms are R's: `pretty` (R's `R_pretty`), the histogram
(R's `hist.default` with the fuzz of the breaks), the density (R's
`density.default`: the bandwidth `bw.nrd0`, the binning of `BinDist` and
the FFT convolution), the box plot's statistics (R's `boxplot.stats`)
and `ppoints`."""

import math

from rstatistics.describe import fivenum, quantile, sd
from rstatistics.distributions import dnorm, qnorm0

# the machine epsilon (a name of its own: the package shares one namespace)
_EPS_MACHINE = 2.220446049250313e-16


def _pretty_bounds(
    lo: float,
    up: float,
    ndiv: int,
    min_n: int,
    shrink_sml: float,
    h: float,
    h5: float,
    f_min: float,
    eps_correction: bool,
    return_bounds: bool,
) -> tuple[float, float, float, int]:
    """R's `R_pretty`: the unit and the bounds of a pretty sequence."""
    rounding_eps = 1e-10
    lo_ = lo
    up_ = up
    dx = up_ - lo_
    if dx == 0.0 and up_ == 0.0:
        cell = 1.0
        i_small = True
    else:
        cell = max(abs(lo_), abs(up_))
        u = 1.0 + (1.0 / (1.0 + h) if (h5 >= 1.5 * h + 0.5) else 1.5 / (1.0 + h5))
        u *= max(1, ndiv) * _EPS_MACHINE
        i_small = dx < cell * u * 3
    if i_small:
        if cell > 10.0:
            cell = 9.0 + cell / 10.0
        cell *= shrink_sml
        if min_n > 1:
            cell /= float(min_n)
    else:
        cell = dx
        if math.isfinite(dx):
            if ndiv > 1:
                cell /= float(ndiv)
        else:
            if ndiv < 2:
                cell = 1.0
            else:
                cell = up_ / float(ndiv) - lo_ / float(ndiv)
    subsmall = f_min * 2.2250738585072014e-308
    if subsmall == 0.0:
        subsmall = 2.2250738585072014e-308
    if cell < subsmall:
        cell = subsmall
    elif cell > 1.7976931348623157e308 / 1.25:
        cell = 1.7976931348623157e308 / 1.25
    base = 10.0 ** math.floor(math.log10(cell))
    unit = base
    u = 2.0 * base
    if u - cell < h * (cell - unit):
        unit = u
        u = 5.0 * base
        if u - cell < h5 * (cell - unit):
            unit = u
            u = 10.0 * base
            if u - cell < h * (cell - unit):
                unit = u
    ns = math.floor(lo_ / unit + rounding_eps)
    nu = math.ceil(up_ / unit - rounding_eps)
    if eps_correction and (not i_small):
        d_max = 1.7976931348623157e308 * (1.0 - 2.0 ** -53)
        if lo_ < 0.0:
            lo_ = lo_ * (1.0 + _EPS_MACHINE)
        elif lo_ > 0.0:
            lo_ = lo_ * (1.0 - _EPS_MACHINE)
        else:
            lo_ = -min(unit, 2.2250738585072014e-308)
        if up_ < 0.0:
            up_ = up_ * (1.0 - _EPS_MACHINE)
        elif up_ > 0.0:
            if up_ < d_max:
                up_ = up_ * (1.0 + _EPS_MACHINE)
        else:
            up_ = min(unit, 2.2250738585072014e-308)
    while ns * unit > lo_ + rounding_eps * unit:
        ns -= 1
    while not math.isfinite(ns * unit):
        ns += 1
    while nu * unit < up_ - rounding_eps * unit:
        nu += 1
    while not math.isfinite(nu * unit):
        nu -= 1
    k = int(0.5 + nu - ns)
    if k < min_n:
        k = min_n - k
        if lo_ == 0.0 and ns == 0.0 and up_ != 0.0:
            nu += k
        elif up_ == 0.0 and nu == 0.0 and lo_ != 0.0:
            ns -= k
        elif ns >= 0.0:
            nu += k // 2
            ns -= k // 2 + k % 2
        else:
            ns -= k // 2
            nu += k // 2 + k % 2
        ndiv = min_n
    else:
        ndiv = k
    if return_bounds:
        if ns * unit < lo:
            lo = ns * unit
        if nu * unit > up:
            up = nu * unit
    else:
        lo = ns
        up = nu
    return (lo, up, unit, ndiv)


def pretty(x: list[float], n: int = 5, min_n: int = -1) -> list[float]:
    """R's `pretty`: a sequence of nice numbers covering the range of x."""
    if min_n < 0:
        min_n = n // 3
    vals: list[float] = []
    for v in x:
        if math.isfinite(v):
            vals.append(v)
    if len(vals) == 0:
        return []
    lo, up, unit, n = _pretty_bounds(min(vals), max(vals), n, min_n, 0.75, 1.5, 0.5 + 1.5 * 1.5, 2.0 ** -20, False, True)
    s: list[float] = []
    if n > 0:
        step = (up - lo) / float(n)
        i = 0
        while i <= n:
            s.append(lo + step * float(i))
            i += 1
    # zap the smalls from the rounding of seq()
    if n > 0:
        delta = abs(up - lo) / float(n)
        for i in range(len(s)):
            if abs(s[i]) < 1e-14 * delta:
                s[i] = 0.0
    return s


class Histogram:
    """The statistics of a histogram (R's `histogram` object)."""

    def __init__(self, breaks: list[float], counts: list[float], density: list[float], mids: list[float], equidist: bool) -> None:
        self.breaks = breaks
        self.counts = counts
        self.density = density
        self.mids = mids
        self.equidist = equidist

    def __str__(self) -> str:
        return "Histogram with " + str(len(self.counts)) + " bins"


def nclass_sturges(x: list[float]) -> int:
    """R's `nclass.Sturges`: the number of classes of a histogram."""
    n = len(x)
    if n < 1:
        return 1
    return int(math.ceil(math.log(n, 2.0))) + 1


def hist_stats(x: list[float], breaks: str = "Sturges", include_lowest: bool = True, right: bool = True, freq: bool = True) -> Histogram:
    """The statistics of a histogram (R's `hist` without the plot)."""
    n = len(x)
    if n == 0:
        raise ValueError("'x' must have at least one element")
    if breaks == "Sturges":
        nb = nclass_sturges(x)
    elif breaks == "FD":
        nb = _nclass_fd(x)
    elif breaks == "Scott":
        nb = _nclass_scott(x)
    else:
        raise ValueError("unknown 'breaks' algorithm")
    br = pretty([min(x), max(x)], nb, 1)
    nb = len(br)
    widths: list[float] = []
    for i in range(nb - 1):
        widths.append(br[i + 1] - br[i])
    equidist = True
    if len(widths) > 0:
        lo = min(widths)
        hi = max(widths)
        mean = sum(widths) / float(len(widths))
        if hi - lo >= 1e-7 * mean:
            equidist = False
    # the fuzz of the breaks (R's hist.default)
    if nb > 5:
        srt = sorted(widths)
        diddle = 1e-7 * srt[len(srt) // 2]
    elif nb <= 3:
        diddle = 1e-7 * (max(x) - min(x))
    else:
        positive = [w for w in widths if w > 0.0]
        diddle = 1e-7 * (min(positive) if len(positive) > 0 else 0.0)
    if right:
        fuzz = [-diddle if include_lowest else diddle]
        for _ in range(nb - 1):
            fuzz.append(diddle)
    else:
        fuzz = []
        for _ in range(nb - 1):
            fuzz.append(-diddle)
        fuzz.append(diddle if include_lowest else -diddle)
    fuzzy = [br[i] + fuzz[i] for i in range(nb)]
    # the counts
    counts = [0.0] * (nb - 1)
    for v in x:
        k = -1
        if right:
            for i in range(nb - 1):
                lo = fuzzy[i]
                hi = fuzzy[i + 1]
                if v > lo and v <= hi:
                    k = i
                    break
                if i == 0 and include_lowest and v >= lo and v <= hi:
                    k = i
                    break
        else:
            for i in range(nb - 1):
                lo = fuzzy[i]
                hi = fuzzy[i + 1]
                if v >= lo and v < hi:
                    k = i
                    break
                if i == nb - 2 and include_lowest and v >= lo and v <= hi:
                    k = i
                    break
        if k >= 0:
            counts[k] += 1.0
    dens: list[float] = []
    for i in range(nb - 1):
        dens.append(counts[i] / (float(n) * widths[i]))
    mids: list[float] = []
    for i in range(nb - 1):
        mids.append(0.5 * (br[i] + br[i + 1]))
    if not freq:
        dens = []
        for i in range(nb - 1):
            dens.append(counts[i] / float(n))
    return Histogram(br, counts, dens, mids, equidist)


def _nclass_fd(x: list[float]) -> int:
    """R's `nclass.FD`: Freedman and Diaconis' rule."""
    h = 2.0 * _iqr(x) / (len(x) ** (1.0 / 3.0))
    lo = min(x)
    hi = max(x)
    if h <= 0.0:
        h = 1.0
    nbin = max(1, int(math.ceil((hi - lo) / h)))
    return nbin


def _nclass_scott(x: list[float]) -> int:
    """R's `nclass.scott`: Scott's rule."""
    h = 3.49 * sd(x) / (len(x) ** (1.0 / 3.0))
    lo = min(x)
    hi = max(x)
    if h <= 0.0:
        h = 1.0
    nbin = max(1, int(math.ceil((hi - lo) / h)))
    return nbin


def _iqr(x: list[float]) -> float:
    q = quantile(x, [0.25, 0.75])
    return q[1] - q[0]


class Density:
    """A kernel density estimate (R's `density` object)."""

    def __init__(self, x: list[float], y: list[float], bw: float, n: int) -> None:
        self.x = x
        self.y = y
        self.bw = bw
        self.n = n

    def __str__(self) -> str:
        return "Density with " + str(len(self.x)) + " points"


def bw_nrd0(x: list[float]) -> float:
    """R's `bw.nrd0`: the normal reference bandwidth."""
    if len(x) < 2:
        raise ValueError("need at least 2 data points")
    hi = sd(x)
    lo = min(hi, _iqr(x) / 1.34)
    if hi > lo:
        lo = hi
    elif lo <= 0.0:
        lo = abs(x[0])
        if lo <= 0.0:
            lo = 1.0
    return 0.9 * lo * len(x) ** -0.2


def _fft(re: list[float], im: list[float], inverse: bool) -> tuple[list[float], list[float]]:
    """The complex FFT of the vectors re and im (a radix 2 transform)."""
    n = len(re)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while (j & bit) != 0:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            tr = re[i]
            re[i] = re[j]
            re[j] = tr
            ti = im[i]
            im[i] = im[j]
            im[j] = ti
    length = 2
    while length <= n:
        ang = 2.0 * math.pi / float(length) * (-1.0 if inverse else 1.0)
        wr = math.cos(ang)
        wi = math.sin(ang)
        half = length // 2
        for i in range(0, n, length):
            cr = 1.0
            ci = 0.0
            for k in range(half):
                ur = re[i + k]
                ui = im[i + k]
                vr = re[i + k + half] * cr - im[i + k + half] * ci
                vi = re[i + k + half] * ci + im[i + k + half] * cr
                re[i + k] = ur + vr
                im[i + k] = ui + vi
                re[i + k + half] = ur - vr
                im[i + k + half] = ui - vi
                cr2 = cr * wr - ci * wi
                ci = cr * wi + ci * wr
                cr = cr2
        length *= 2
    if inverse:
        for i in range(n):
            re[i] /= float(n)
            im[i] /= float(n)
    return (re, im)


def _bin_dist(x: list[float], lo: float, hi: float, n: int) -> list[float]:
    """R's `BinDist`: the binned distances of the observations."""
    y = [0.0] * (2 * n)
    ixmin = 0
    ixmax = n - 2
    xdelta = (hi - lo) / float(n - 1)
    for i in range(len(x)):
        v = x[i]
        if math.isfinite(v):
            xpos = (v - lo) / xdelta
            ix = int(math.floor(xpos))
            fx = xpos - float(ix)
            if ixmin <= ix <= ixmax:
                y[ix] += (1.0 - fx)
                y[ix + 1] += fx
            elif ix == -1:
                y[0] += fx
            elif ix == ixmax + 1:
                y[ix] += (1.0 - fx)
    return y


def density_stats(x: list[float], bw: str = "nrd0", n: int = 512, from_: float = 0.0, to: float = 0.0, cut: float = 3.0, ext: float = 4.0, given_range: bool = False) -> Density:
    """The kernel density estimate of x (R's `density`)."""
    if len(x) == 0:
        raise ValueError("'x' must have at least one observation")
    n_user = n
    if n < 512:
        n = 512
    if bw == "nrd0":
        b = bw_nrd0(x)
    elif bw == "nrd":
        b = bw_nrd(x)
    else:
        b = float(bw)
    if given_range:
        lo_from = from_
        hi_to = to
    else:
        lo_from = min(x) - cut * b
        hi_to = max(x) + cut * b
    lo = lo_from - ext * b
    up = hi_to + ext * b
    y = _bin_dist(x, lo, up, n)
    # the kernel on the doubled grid
    kords: list[float] = []
    step = (up - lo) / float(n - 1)
    for i in range(2 * n):
        kords.append(step * float(i))
    for i in range(n + 1, 2 * n):
        kords[i] = -kords[2 * n - i]
    kvals: list[float] = []
    for v in kords:
        kvals.append(dnorm(v, 0.0, b))
    # the convolution by the FFT
    yre, yim = _fft(list(y), [0.0] * len(y), False)
    kre, kim = _fft(kvals, [0.0] * len(kvals), False)
    # the product with the conjugate
    pre = [yre[i] * kre[i] + yim[i] * kim[i] for i in range(len(yre))]
    pim = [yim[i] * kre[i] - yre[i] * kim[i] for i in range(len(yre))]
    cre, cim = _fft(pre, pim, True)
    # the convolution is divided by the total mass of the data (R's density)
    dens: list[float] = []
    for i in range(n):
        v = cre[i] / float(len(x))
        dens.append(v if v > 0.0 else 0.0)
    # the grid
    xords: list[float] = []
    for i in range(n):
        xords.append(lo + (up - lo) * float(i) / float(n - 1))
    xs: list[float] = []
    for i in range(n_user):
        xs.append(lo_from + (hi_to - lo_from) * float(i) / float(n_user - 1))
    # the linear interpolation (R's approx with rule = 1)
    ys: list[float] = []
    for v in xs:
        ys.append(_approx(xords, dens, v))
    return Density(xs, ys, b, len(x))


def bw_nrd(x: list[float]) -> float:
    """R's `bw.nrd`: the normal reference bandwidth."""
    if len(x) < 2:
        raise ValueError("need at least 2 data points")
    q = quantile(x, [0.25, 0.75])
    h = (q[1] - q[0]) / 1.34
    return 1.06 * min(sd(x), h) * len(x) ** -0.2


def _approx(x: list[float], y: list[float], v: float) -> float:
    """R's `approx` with rule = 1: the linear interpolation at v."""
    n = len(x)
    if n == 0:
        return math.nan
    if v < x[0] or v > x[n - 1]:
        return math.nan
    if v == x[n - 1]:
        return y[n - 1]
    lo = 0
    hi = n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if x[mid] <= v:
            lo = mid
        else:
            hi = mid
    if x[hi] == x[lo]:
        return y[lo]
    return y[lo] + (y[hi] - y[lo]) * (v - x[lo]) / (x[hi] - x[lo])


class ECDF:
    """The empirical distribution function (R's `ecdf` object)."""

    def __init__(self, x: list[float], y: list[float], n: int) -> None:
        self.x = x
        self.y = y
        self.n = n

    def __str__(self) -> str:
        return "ECDF of " + str(self.n) + " observations"


def ecdf(x: list[float]) -> ECDF:
    """The empirical distribution function of x (R's `ecdf`)."""
    n = len(x)
    xs = sorted(x)
    ys: list[float] = []
    for i in range(n):
        ys.append(float(i + 1) / float(n))
    return ECDF(xs, ys, n)


class BoxplotStats:
    """The statistics of a box plot (R's `boxplot.stats` object)."""

    def __init__(self, n: int, conf: list[float], out: list[float], group: list[int], stats: list[float], x: list[float]) -> None:
        self.n = n
        self.stats = stats
        self.lower = stats[1]
        self.upper = stats[3]
        self.middle = stats[2]
        self.conf = conf
        self.out = out
        self.group = group
        self.x = x

    def __str__(self) -> str:
        return "Box plot statistics of " + str(self.n) + " observations"


def boxplot_stats(x: list[float], coef: float = 1.5, do_conf: bool = True, do_out: bool = True) -> BoxplotStats:
    """The statistics of a box plot (R's `boxplot.stats`)."""
    if coef < 0.0:
        raise ValueError("'coef' must not be negative")
    vals = [v for v in x if not math.isnan(v)]
    n = float(len(vals))
    if n == 0.0:
        raise ValueError("'x' must have at least one element")
    stats = fivenum(vals)
    iqr = stats[3] - stats[1]
    out: list[float] = []
    if coef == 0.0:
        do_out = False
    else:
        low = stats[1] - coef * iqr
        high = stats[3] + coef * iqr
        isout = [v < low or v > high for v in vals]
        if any(isout):
            inner = [vals[i] for i in range(len(vals)) if not isout[i]]
            if len(inner) > 0:
                stats[0] = min(inner)
                stats[4] = max(inner)
        if do_out:
            for i in range(len(vals)):
                if isout[i]:
                    out.append(vals[i])
    conf = [stats[2], stats[2]]
    if do_conf:
        conf = [stats[2] - 1.58 * iqr / math.sqrt(n), stats[2] + 1.58 * iqr / math.sqrt(n)]
    group: list[int] = []
    for i in range(len(out)):
        group.append(1)
    return BoxplotStats(int(n), conf, out, group, list(stats), sorted(vals))


def ppoints(n: int, a: float = 0.0) -> list[float]:
    """R's `ppoints`: the plotting positions of a probability plot."""
    if a <= 0.0:
        a = 0.375 if n <= 10 else 0.5
    out: list[float] = []
    for i in range(1, n + 1):
        out.append((float(i) - a) / (float(n) + 1.0 - 2.0 * a))
    return out


def qqnorm_coords(x: list[float]) -> tuple[list[float], list[float]]:
    """The coordinates of a normal quantile plot of x (R's `qqnorm`)."""
    n = len(x)
    p = ppoints(n)
    theoretical: list[float] = []
    for v in p:
        theoretical.append(qnorm0(v, True, False))
    return (theoretical, sorted(x))
