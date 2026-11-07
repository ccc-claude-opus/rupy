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
from rstatistics.distributions import dexp, dgamma, dlogis, dnorm, dunif, dweibull, qnorm0

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


def _lm_ecdf(x: list[float]) -> ECDF:
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


# ------------------------------------------------------------------ the device


def ecdf(x: list[float]) -> ECDF:
    """The empirical distribution function of x (R's `ecdf`)."""
    return _lm_ecdf(x)


class Graphics:
    """A graphics device that writes SVG, laid out as R lays a plot out.

    The device is `width` by `height` inches, the margins are the lines of
    `mar` (bottom, left, top, right) and the tick marks and their labels
    stand `mgp[2]` and `mgp[3]` lines from the axes."""

    def __init__(self, width: float = 7.0, height: float = 7.0, mfrow: list[int] | None = None) -> None:
        self.width = width
        self.height = height
        if mfrow is None:
            self.mfrow = [1, 1]
        else:
            self.mfrow = mfrow
        # the parameters of the device (R's defaults)
        self.mar = [5.1, 4.1, 4.1, 2.1]
        self.mgp = [3.0, 1.0, 0.0]
        self.cex = 1.0
        self.pch = 1
        self.lwd = 1.0
        self.col = "black"
        self.las = 0
        self.tcl = -0.5
        self.ps = 12.0
        self.font_family = "sans-serif"
        self.elements: list[str] = []
        self.panel = 0
        self.usr = [0.0, 1.0, 0.0, 1.0]
        self.plot_rect = [0.0, 0.0, 1.0, 1.0]
        # the white background of the page
        self.elements = []
        self.panel = 0
        self.usr = [0.0, 1.0, 0.0, 1.0]
        w = self.width * 72.0
        h = self.height * 72.0
        self.elements.append('<rect x="0" y="0" width="' + _svg_num(w) + '" height="' + _svg_num(h) + '" fill="white"/>')

    # ---------------------------------------------------------- the device

    def new_page(self) -> None:
        """Start a new page (a new device with the same parameters)."""
        self.elements = []
        self.panel = 0
        self.usr = [0.0, 1.0, 0.0, 1.0]
        w = self.width * 72.0
        h = self.height * 72.0
        self.elements.append('<rect x="0" y="0" width="' + _svg_num(w) + '" height="' + _svg_num(h) + '" fill="white"/>')

    def svg(self) -> str:
        """The drawing as an SVG document."""
        w = self.width * 72.0
        h = self.height * 72.0
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<svg xmlns="http://www.w3.org/2000/svg" width="' + _svg_num(w) + 'pt" height="' + _svg_num(h) + 'pt" viewBox="0 0 ' + _svg_num(w) + " " + _svg_num(h) + '">')
        for e in self.elements:
            lines.append(e)
        lines.append("</svg>")
        return "\n".join(lines) + "\n"

    def save(self, path: str) -> None:
        """Write the drawing to the file `path`."""
        with open(path, "w") as f:
            f.write(self.svg())

    def show(self) -> str:
        """The drawing (the same as `svg()`): what a browser would show."""
        return self.svg()

    # ------------------------------------------------------- the coordinates

    def _line_height(self) -> float:
        """The height of a margin line, in points."""
        return self.ps * 1.2

    def _panel_rect(self) -> list[float]:
        """The plot region of the current panel, in points (the SVG's y down)."""
        w = self.width * 72.0
        h = self.height * 72.0
        lh = self._line_height()
        nr = float(self.mfrow[0])
        nc = float(self.mfrow[1])
        left = self.mar[1] * lh
        right = self.mar[3] * lh
        bottom = self.mar[0] * lh
        top = self.mar[2] * lh
        cw = w / nc
        ch = h / nr
        col = float(self.panel % self.mfrow[1])
        row = float(self.panel // self.mfrow[1])
        # the margins of the cell (the device's margins, scaled to the cell)
        ml = self.mar[1] * lh * (cw / w) * nc
        mr = self.mar[3] * lh * (cw / w) * nc
        mb = self.mar[0] * lh * (ch / h) * nr
        mt = self.mar[2] * lh * (ch / h) * nr
        x0 = col * cw + ml
        y0 = row * ch + mt
        return [x0, y0, x0 + cw - ml - mr, y0 + ch - mt - mb]

    def next_panel(self) -> None:
        """Draw in the next panel of the grid (R's mfrow)."""
        self.panel += 1
        self.plot_rect = self._panel_rect()

    def legend(self, x: float, y: float, labels: list[str]) -> None:
        """A legend with the labels at the point (x, y) of the plot."""
        fs = self.ps * self.cex
        dx = self.device_x(x)
        dy = self.device_y(y)
        w = 0.0
        for lab in labels:
            t = len(lab) * fs * 0.6
            if t > w:
                w = t
        w += 3.0 * fs
        h = (len(labels) + 1.0) * fs * 1.2
        self.elements.append('<rect x="' + _svg_num(dx) + '" y="' + _svg_num(dy - h) + '" width="' + _svg_num(w) + '" height="' + _svg_num(h) + '" fill="white" stroke="black" stroke-width="0.75"/>')
        r = 0.225 * self.ps * self.cex
        for i in range(len(labels)):
            yy = dy - (float(i) + 1.0) * fs * 1.2
            self.elements.append('<circle cx="' + _svg_num(dx + 1.5 * fs) + '" cy="' + _svg_num(yy) + '" r="' + _svg_num(r) + '" fill="black"/>')
            self.elements.append('<text x="' + _svg_num(dx + 2.5 * fs) + '" y="' + _svg_num(yy + fs * 0.35) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="black">' + _svg_escape(labels[i]) + "</text>")

    def plot_window(self, xlim: list[float], ylim: list[float]) -> None:
        """Set the user coordinates (the ranges are extended by 4% as R does)."""
        x0, x1 = xlim[0], xlim[1]
        y0, y1 = ylim[0], ylim[1]
        if x1 == x0:
            x0 -= 0.5
            x1 += 0.5
        if y1 == y0:
            y0 -= 0.5
            y1 += 0.5
        dx = 0.04 * (x1 - x0)
        dy = 0.04 * (y1 - y0)
        self.usr = [x0 - dx, x1 + dx, y0 - dy, y1 + dy]
        self.plot_rect = self._panel_rect()

    def device_x(self, x: float) -> float:
        """The device coordinate of a user x."""
        r = self.plot_rect
        u = self.usr
        if u[1] == u[0]:
            return r[0]
        return r[0] + (x - u[0]) / (u[1] - u[0]) * (r[2] - r[0])

    def device_y(self, y: float) -> float:
        """The device coordinate of a user y."""
        r = self.plot_rect
        u = self.usr
        if u[3] == u[2]:
            return r[1]
        return r[3] - (y - u[2]) / (u[3] - u[2]) * (r[3] - r[1])

    def user_x(self, dx: float) -> float:
        """The user coordinate of a device x."""
        r = self.plot_rect
        u = self.usr
        return u[0] + (dx - r[0]) / (r[2] - r[0]) * (u[1] - u[0])

    def user_y(self, dy: float) -> float:
        """The user coordinate of a device y."""
        r = self.plot_rect
        u = self.usr
        return u[2] + (r[3] - dy) / (r[3] - r[1]) * (u[3] - u[2])

    # ------------------------------------------------------------ the drawing

    def points(self, x: list[float], y: list[float], pch: int = 0, col: str = "", lwd: float = 0.0, cex: float = 0.0) -> None:
        """The points of the plot (the default symbol is an open circle)."""
        s = pch if pch != 0 else self.pch
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        ex = cex if cex > 0.0 else self.cex
        for i in range(len(x)):
            dx = self.device_x(x[i])
            dy = self.device_y(y[i])
            if s == 1:
                r = 0.225 * self.ps * ex
                self.elements.append('<circle cx="' + _svg_num(dx) + '" cy="' + _svg_num(dy) + '" r="' + _svg_num(r) + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')
            elif s == 19:
                r = 0.225 * self.ps * ex
                self.elements.append('<circle cx="' + _svg_num(dx) + '" cy="' + _svg_num(dy) + '" r="' + _svg_num(r) + '" fill="' + c + '" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')
            else:
                r = 0.225 * self.ps * ex
                self.elements.append('<rect x="' + _svg_num(dx - r) + '" y="' + _svg_num(dy - r) + '" width="' + _svg_num(2.0 * r) + '" height="' + _svg_num(2.0 * r) + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def lines(self, x: list[float], y: list[float], col: str = "", lwd: float = 0.0, type: str = "l") -> None:
        """The line through the points."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        d = ""
        for i in range(len(x)):
            d += ("M " if i == 0 else " L ") + _svg_num(self.device_x(x[i])) + " " + _svg_num(self.device_y(y[i]))
        self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def segments(self, x0: list[float], y0: list[float], x1: list[float], y1: list[float], col: str = "", lwd: float = 0.0) -> None:
        """The line segments."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        d = ""
        for i in range(len(x0)):
            d += "M " + _svg_num(self.device_x(x0[i])) + " " + _svg_num(self.device_y(y0[i])) + " L " + _svg_num(self.device_x(x1[i])) + " " + _svg_num(self.device_y(y1[i]))
        self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def rect(self, x0: float, y0: float, x1: float, y1: float, col: str = "", fill: str = "", lwd: float = 0.0) -> None:
        """A rectangle."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        a = self.device_x(min(x0, x1))
        b = self.device_x(max(x0, x1))
        t = self.device_y(max(y0, y1))
        bt = self.device_y(min(y0, y1))
        f = fill if fill != "" else "none"
        self.elements.append('<rect x="' + _svg_num(a) + '" y="' + _svg_num(t) + '" width="' + _svg_num(b - a) + '" height="' + _svg_num(bt - t) + '" fill="' + f + '" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def polygon(self, x: list[float], y: list[float], col: str = "", fill: str = "", lwd: float = 0.0) -> None:
        """A polygon."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        d = ""
        for i in range(len(x)):
            d += ("M " if i == 0 else " L ") + _svg_num(self.device_x(x[i])) + " " + _svg_num(self.device_y(y[i]))
        if d != "":
            d += " Z"
        f = fill if fill != "" else "none"
        self.elements.append('<path d="' + d + '" fill="' + f + '" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def text(self, x: float, y: float, labels: str, adj: float = 0.0, col: str = "", cex: float = 0.0, rot: float = 0.0) -> None:
        """The text at the point (x, y)."""
        c = col if col != "" else self.col
        ex = cex if cex > 0.0 else self.cex
        size = self.ps * ex
        dx = self.device_x(x)
        dy = self.device_y(y)
        anchor = "middle"
        if adj < 0.0:
            anchor = "end"
        elif adj > 0.0:
            anchor = "start"
        baseline = "alphabetic"
        transform = ""
        if rot != 0.0:
            transform = ' transform="rotate(' + _svg_num(-rot) + " " + _svg_num(dx) + " " + _svg_num(dy) + ')"'
        self.elements.append('<text x="' + _svg_num(dx) + '" y="' + _svg_num(dy) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(size) + '" fill="' + c + '" text-anchor="' + anchor + '" dominant-baseline="' + baseline + '"' + transform + ">" + _svg_escape(labels) + "</text>")

    def axis(self, side: int, at: list[float], labels: list[str], las: int = 0, tick: bool = True, line: int = 0, col: str = "", cex: float = 0.0) -> None:
        """An axis: the line, the tick marks and their labels."""
        c = col if col != "" else self.col
        ex = cex if cex > 0.0 else self.cex
        lh = self._line_height()
        r = self.plot_rect
        u = self.usr
        tlen = self.tcl * lh
        fs = self.ps * ex
        if side == 1:
            # the bottom axis
            y = r[3]
            d = "M " + _svg_num(r[0]) + " " + _svg_num(y)
            for i in range(len(at)):
                dx = self.device_x(at[i])
                d += " M " + _svg_num(dx) + " " + _svg_num(y) + " L " + _svg_num(dx) + " " + _svg_num(y - tlen)
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="0.75"/>')
            for i in range(len(at)):
                dx = self.device_x(at[i])
                lab = labels[i] if i < len(labels) else _svg_label(at[i])
                ly = y + self.mgp[1] * lh + fs * 0.2
                self.elements.append('<text x="' + _svg_num(dx) + '" y="' + _svg_num(ly) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + c + '" text-anchor="middle">' + _svg_escape(lab) + "</text>")
        elif side == 2:
            # the left axis
            x = r[0]
            d = "M " + _svg_num(x) + " " + _svg_num(r[1])
            for i in range(len(at)):
                dy = self.device_y(at[i])
                d += " M " + _svg_num(x) + " " + _svg_num(dy) + " L " + _svg_num(x - tlen) + " " + _svg_num(dy)
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="0.75"/>')
            for i in range(len(at)):
                dy = self.device_y(at[i])
                lab = labels[i] if i < len(labels) else _svg_label(at[i])
                lx = x - self.mgp[1] * lh
                self.elements.append('<text x="' + _svg_num(lx) + '" y="' + _svg_num(dy + fs * 0.35) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + c + '" text-anchor="end">' + _svg_escape(lab) + "</text>")
        elif side == 3:
            # the top axis
            y = r[1]
            d = "M " + _svg_num(r[0]) + " " + _svg_num(y)
            for i in range(len(at)):
                dx = self.device_x(at[i])
                d += " M " + _svg_num(dx) + " " + _svg_num(y) + " L " + _svg_num(dx) + " " + _svg_num(y - tlen)
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="0.75"/>')
            for i in range(len(at)):
                dx = self.device_x(at[i])
                lab = labels[i] if i < len(labels) else _svg_label(at[i])
                ly = y - self.mgp[1] * lh
                self.elements.append('<text x="' + _svg_num(dx) + '" y="' + _svg_num(ly) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + c + '" text-anchor="middle">' + _svg_escape(lab) + "</text>")
        else:
            # the right axis
            x = r[2]
            d = "M " + _svg_num(x) + " " + _svg_num(r[1])
            for i in range(len(at)):
                dy = self.device_y(at[i])
                d += " M " + _svg_num(x) + " " + _svg_num(dy) + " L " + _svg_num(x - tlen) + " " + _svg_num(dy)
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="0.75"/>')
            for i in range(len(at)):
                dy = self.device_y(at[i])
                lab = labels[i] if i < len(labels) else _svg_label(at[i])
                lx = x + self.mgp[1] * lh
                self.elements.append('<text x="' + _svg_num(lx) + '" y="' + _svg_num(dy + fs * 0.35) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + c + '" text-anchor="start">' + _svg_escape(lab) + "</text>")

    def box(self, col: str = "", lwd: float = 0.0) -> None:
        """The box around the plot region."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        r = self.plot_rect
        d = "M " + _svg_num(r[0]) + " " + _svg_num(r[3])
        d += " L " + _svg_num(r[2]) + " " + _svg_num(r[3])
        d += " L " + _svg_num(r[2]) + " " + _svg_num(r[1])
        d += " L " + _svg_num(r[0]) + " " + _svg_num(r[1])
        d += " Z"
        self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')

    def title(self, main: str = "", xlab: str = "", ylab: str = "") -> None:
        """The title of the plot and the labels of the axes."""
        lh = self._line_height()
        r = self.plot_rect
        fs = self.ps
        if main != "":
            cx = 0.5 * (r[0] + r[2])
            self.elements.append('<text x="' + _svg_num(cx) + '" y="' + _svg_num(r[1] - self.mgp[0] * lh * 0.0 - fs * 0.6) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + self.col + '" text-anchor="middle">' + _svg_escape(main) + "</text>")
        if xlab != "":
            cx = 0.5 * (r[0] + r[2])
            self.elements.append('<text x="' + _svg_num(cx) + '" y="' + _svg_num(r[3] + self.mgp[0] * lh) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + self.col + '" text-anchor="middle">' + _svg_escape(xlab) + "</text>")
        if ylab != "":
            cy = 0.5 * (r[1] + r[3])
            self.elements.append('<text x="' + _svg_num(r[0] - self.mgp[0] * lh) + '" y="' + _svg_num(cy) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + self.col + '" text-anchor="middle" transform="rotate(-90 ' + _svg_num(r[0] - self.mgp[0] * lh) + " " + _svg_num(cy) + ')">' + _svg_escape(ylab) + "</text>")

    def mtext(self, text: str, side: int = 1, line: float = 0.0, col: str = "", cex: float = 0.0) -> None:
        """The text in the margin."""
        lh = self._line_height()
        r = self.plot_rect
        fs = self.ps * (cex if cex > 0.0 else self.cex)
        if side == 1:
            x = 0.5 * (r[0] + r[2])
            y = r[3] + (line + 1.0) * lh
            self.elements.append('<text x="' + _svg_num(x) + '" y="' + _svg_num(y) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + (col if col != "" else self.col) + '" text-anchor="middle">' + _svg_escape(text) + "</text>")
        elif side == 2:
            y = 0.5 * (r[1] + r[3])
            x = r[0] - (line + 1.0) * lh
            self.elements.append('<text x="' + _svg_num(x) + '" y="' + _svg_num(y) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + (col if col != "" else self.col) + '" text-anchor="middle" transform="rotate(-90 ' + _svg_num(x) + " " + _svg_num(y) + ')">' + _svg_escape(text) + "</text>")
        else:
            x = 0.5 * (r[0] + r[2])
            y = r[1] - (line + 1.0) * lh
            self.elements.append('<text x="' + _svg_num(x) + '" y="' + _svg_num(y) + '" font-family="' + self.font_family + '" font-size="' + _svg_num(fs) + '" fill="' + (col if col != "" else self.col) + '" text-anchor="middle">' + _svg_escape(text) + "</text>")

    def abline(self, h: float = 0.0, v: float = 0.0, col: str = "", lwd: float = 0.0) -> None:
        """A horizontal or a vertical line."""
        c = col if col != "" else self.col
        lw = lwd if lwd > 0.0 else self.lwd
        r = self.plot_rect
        if h != 0.0:
            y = self.device_y(h)
            d = "M " + _svg_num(r[0]) + " " + _svg_num(y) + " L " + _svg_num(r[2]) + " " + _svg_num(y)
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')
        if v != 0.0:
            x = self.device_x(v)
            d = "M " + _svg_num(x) + " " + _svg_num(r[1]) + " L " + _svg_num(x) + " " + _svg_num(r[3])
            self.elements.append('<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="' + _svg_num(lw * 0.75) + '"/>')


    # ------------------------------------------------------- the high level

    def _ticks(self, side: int) -> list[float]:
        """The default tick positions of an axis (R's axTicks)."""
        if side == 1 or side == 3:
            lo = self.usr[0]
            hi = self.usr[1]
        else:
            lo = self.usr[2]
            hi = self.usr[3]
        out: list[float] = []
        for v in pretty([lo, hi], 5):
            if v >= lo and v <= hi:
                out.append(v)
        return out

    def _axis_default(self, side: int) -> None:
        """The axis with its default ticks (R's axis(side) with no at)."""
        at = self._ticks(side)
        labels: list[str] = []
        for v in at:
            labels.append(_svg_label(v))
        self.axis(side, at, labels)

    def plot(
        self,
        x: list[float],
        y: list[float],
        type: str = "p",
        main: str = "",
        xlab: str = "",
        ylab: str = "",
        xlim: list[float] | None = None,
        ylim: list[float] | None = None,
        col: str = "",
        lwd: float = 0.0,
        pch: int = 0,
    ) -> None:
        """A scatter plot (the types of R's plot: p, l, b, h, s)."""
        if xlim is None:
            xl = [min(x), max(x)]
        else:
            xl = xlim
        if ylim is None:
            yl = [min(y), max(y)]
        else:
            yl = ylim
        self.plot_window(xl, yl)
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        if type == "p" or type == "b":
            self.points(x, y, pch, col, lwd)
        if type == "l" or type == "b":
            self.lines(x, y, col, lwd)
        if type == "h":
            for i in range(len(y)):
                self.segments([x[i]], [0.0], [x[i]], [y[i]], col, lwd)
        if type == "s":
            for i in range(len(y)):
                self.rect(x[i] - 0.05 * (xl[1] - xl[0]), y[i] - 0.05 * (yl[1] - yl[0]), x[i] + 0.05 * (xl[1] - xl[0]), y[i] + 0.05 * (yl[1] - yl[0]), col, "", lwd)

    def hist(
        self,
        x: list[float],
        main: str = "",
        xlab: str = "",
        ylab: str = "",
        col: str = "lightgray",
        border: str = "",
        freq: bool = True,
        breaks: str = "Sturges",
        xlim: list[float] | None = None,
        ylim: list[float] | None = None,
    ) -> Histogram:
        """A histogram (R's plot.histogram)."""
        h = hist_stats(x, breaks)
        y = h.counts if freq else h.density
        if xlim is None:
            xl = [h.breaks[0], h.breaks[len(h.breaks) - 1]]
        else:
            xl = xlim
        if ylim is None:
            yl = [min(y + [0.0]), max(y)]
        else:
            yl = ylim
        self.plot_window(xl, yl)
        if main == "":
            main = "Histogram of x"
        if ylab == "":
            ylab = "Frequency" if freq else "Density"
        self.title(main, xlab, ylab)
        self._axis_default(1)
        yt = self._ticks(2)
        if freq:
            keep: list[float] = []
            for v in yt:
                if v != float(int(v)):
                    continue
                keep.append(v)
            yt = keep
        labels: list[str] = []
        for v in yt:
            labels.append(_svg_label(v))
        self.axis(2, yt, labels)
        for i in range(len(h.counts)):
            self.rect(h.breaks[i], 0.0, h.breaks[i + 1], y[i], col, border)
        return h

    def density(self, x: list[float], main: str = "", xlab: str = "", ylab: str = "Density", col: str = "", lwd: float = 0.0) -> Density:
        """The density curve of x (R's plot.density)."""
        d = density_stats(x)
        if xlab == "":
            xlab = "N = " + str(d.n) + "  Bandwidth = " + format_num(d.bw, 7).strip()
        self.plot_window([d.x[0], d.x[len(d.x) - 1]], [0.0, max(d.y)])
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        self.lines(d.x, d.y, col if col != "" else "black", lwd)
        self.abline(0.0, 0.0, "gray", 0.25)
        return d

    def boxplot(self, x: list[float], main: str = "", xlab: str = "", ylab: str = "", col: str = "") -> BoxplotStats:
        """A box plot (R's bxp)."""
        b = boxplot_stats(x)
        self.plot_window([b.stats[0], b.stats[4]], [b.stats[0], b.stats[4]])
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        # the whiskers and the box
        self.segments([b.lower, b.upper], [b.stats[2], b.stats[2]], [b.lower, b.upper], [b.stats[2], b.stats[2]], col)
        self.segments([b.lower, b.upper], [b.stats[1], b.stats[1]], [b.lower, b.upper], [b.stats[3], b.stats[3]], col)
        self.rect(b.lower, b.stats[1], b.upper, b.stats[3], col, col if col != "" else "white")
        self.segments([b.lower, b.upper], [b.stats[2], b.stats[2]], [b.lower, b.upper], [b.stats[2], b.stats[2]], col)
        for v in b.out:
            self.points([v], [b.stats[2]], 1, col)
        return b

    def qqnorm(self, x: list[float], main: str = "", xlab: str = "", ylab: str = "", col: str = "") -> tuple[list[float], list[float]]:
        """A normal quantile plot of x (R's qqnorm)."""
        t = qqnorm_coords(x)
        lim = [min(t[0] + t[1]), max(t[0] + t[1])]
        self.plot_window(lim, lim)
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        self.points(t[0], t[1], 1, col)
        return t

    def qqline(self, x: list[float], col: str = "", lwd: float = 0.0) -> None:
        """The reference line of a quantile plot (R's qqline)."""
        t = qqnorm_coords(x)
        n = float(len(x))
        qx = quantile(t[0], [0.25, 0.75])
        qy = quantile(t[1], [0.25, 0.75])
        slope = (qy[1] - qy[0]) / (qx[1] - qx[0])
        intercept = qy[0] - slope * qx[0]
        self.lines([t[0][0], t[0][len(t[0]) - 1]], [intercept + slope * t[0][0], intercept + slope * t[0][len(t[0]) - 1]], col, lwd)

    def ecdf(self, x: list[float], main: str = "", xlab: str = "", ylab: str = "", col: str = "") -> ECDF:
        """The empirical distribution function of x (R's plot.ecdf)."""
        e = _lm_ecdf(x)
        self.plot_window([e.x[0], e.x[len(e.x) - 1]], [0.0, 1.0])
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        n = float(len(e.x))
        for i in range(len(e.x)):
            y0 = 0.0 if i == 0 else e.y[i - 1]
            self.segments([e.x[i]], [y0], [e.x[i]], [e.y[i]], col)
        if len(e.x) > 0:
            self.segments([e.x[0], e.x[len(e.x) - 1]], [e.y[0], e.y[len(e.y) - 1]], [e.x[0], e.x[len(e.x) - 1]], [e.y[0], e.y[len(e.y) - 1]], col)
        return e

    def curve(self, name: str, from_: float, to: float, n: int = 101, col: str = "", lwd: float = 0.0) -> None:
        """The curve of a distribution, named as in R ("dnorm", "dunif", ...)."""
        xs: list[float] = []
        ys: list[float] = []
        for i in range(n):
            x = from_ + (to - from_) * float(i) / float(n - 1)
            xs.append(x)
            ys.append(_lm_density(name, x))
        self.lines(xs, ys, col, lwd)

    def barplot(self, heights: list[float], labels: list[str], main: str = "", xlab: str = "", ylab: str = "", col: str = "") -> None:
        """A bar plot (R's barplot)."""
        n = float(len(heights))
        self.plot_window([0.0, n + 1.0], [0.0, max(heights)])
        self.title(main, xlab, ylab)
        self._axis_default(1)
        self._axis_default(2)
        self.box()
        for i in range(len(heights)):
            self.rect(float(i) + 0.5, 0.0, float(i) + 1.5, heights[i], col if col != "" else "black", "black")
        for i in range(len(labels)):
            self.text(float(i) + 1.0, 0.0, labels[i], 0.0, "", 0.0, 90.0)




def _svg_num(v: float) -> str:
    """A number as the SVG writes it (at most three decimals)."""
    s = format(v, ".3f")
    if s == "-0.000":
        s = "0.000"
    return s


def _svg_label(v: float) -> str:
    """The label of a tick (as R formats the tick values)."""
    if v == float(int(v)) and abs(v) < 1e15:
        return str(int(v))
    s = format(v, ".12g")
    return s


def _svg_escape(s: str) -> str:
    """The text as the SVG writes it."""
    out = ""
    for ch in s:
        if ch == "&":
            out += "&amp;"
        elif ch == "<":
            out += "&lt;"
        elif ch == ">":
            out += "&gt;"
        else:
            out += ch
    return out

def _lm_density(name: str, x: float) -> float:
    """The density of the distribution `name` at x (as R's dnorm, dunif, ...)."""
    if name == "dnorm":
        return dnorm(x, 0.0, 1.0)
    if name == "dunif":
        return dunif(x, 0.0, 1.0)
    if name == "dexp":
        return dexp(x, 1.0)
    if name == "dgamma":
        return dgamma(x, 1.0, 1.0)
    if name == "dlogis":
        return dlogis(x, 0.0, 1.0)
    if name == "dweibull":
        return dweibull(x, 1.0, 1.0)
    raise ValueError("unknown distribution '" + name + "'")
