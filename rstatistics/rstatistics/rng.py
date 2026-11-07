"""R's random numbers: the Mersenne-Twister seeded as `set.seed` seeds it,
`unif_rand`, normal numbers by inversion, exponential numbers by Ahrens and
Dieter's algorithm, and `sample`'s rejection sampling (R ≥ 3.6). A seeded
RNG gives the numbers R gives after `set.seed` with the same seed:

    rng = rstatistics.set_seed(42)
    rng.rnorm(3)        # R: set.seed(42); rnorm(3)

(R keeps one generator in the session; rstatistics passes it explicitly.)"""

import math

from rstatistics.special import qnorm0

N = 624
M = 397
MASK32 = 4294967295
I2_32M1 = 2.328306437080797e-10
BIG = 134217728.0


class RNG:
    """A generator in the state `set.seed(seed)` leaves R's default generator in."""

    def __init__(self, seed: int) -> None:
        s = seed & MASK32
        # R's initial scrambling, then one seed per state word
        for _ in range(50):
            s = (69069 * s + 1) & MASK32
        self.mt: list[int] = []
        s = (69069 * s + 1) & MASK32  # the word that holds the position
        for _ in range(N):
            s = (69069 * s + 1) & MASK32
            self.mt.append(s)
        self.mti = N
        # per-generator caches of the r* algorithms (R keeps statics)
        self._ga_a = -1.0
        self._ga_aa = -1.0
        self._ga_s2 = 0.0
        self._ga_s = 0.0
        self._ga_d = 0.0
        self._ga_q0 = 0.0
        self._ga_b = 0.0
        self._ga_si = 0.0
        self._ga_c = 0.0
        self._rb_olda = -1.0
        self._rb_oldb = -1.0
        self._rb_beta = 0.0
        self._rb_delta = 0.0
        self._rb_k1 = 0.0
        self._rb_k2 = 0.0
        self._rb_gamma = 0.0
        self._bo_psave = -1.0
        self._bo_nsave = -1
        self._bo_qn = 0.0
        self._bo_p1 = 0.0
        self._bo_p2 = 0.0
        self._bo_p3 = 0.0
        self._bo_p4 = 0.0
        self._bo_xm = 0.0
        self._bo_xl = 0.0
        self._bo_xr = 0.0
        self._bo_c = 0.0
        self._bo_xll = 0.0
        self._bo_xlr = 0.0
        self._bo_m = 0
        self._bo_n = 0
        self._bo_npq = 0.0
        self._bo_g = 0.0
        self._bo_r = 0.0
        self._bo_p = 0.0
        self._bo_q = 0.0
        self._pp_muprev = -1.0
        self._pp_muprev2 = -1.0
        self._pp_m = 0
        self._pp_l = 0
        self._pp_s = 0.0
        self._pp_d = 0.0
        self._pp_big_l = 0.0
        self._pp_p0 = 0.0
        self._pp_p = 0.0
        self._pp_q = 0.0
        self._pp_table = [0.0] * 36
        self._pp_omega = 0.0
        self._pp_b1 = 0.0
        self._pp_b2 = 0.0
        self._pp_c0 = 0.0
        self._pp_c1 = 0.0
        self._pp_c2 = 0.0
        self._pp_c3 = 0.0
        self._pp_c = 0.0
        self._hy_ks = -1
        self._hy_n1s = -1
        self._hy_n2s = -1
        self._hy_n1 = 0
        self._hy_n2 = 0
        self._hy_k = 0
        self._hy_m = 0
        self._hy_minjx = 0
        self._hy_maxjx = 0
        self._hy_w = 0.0
        self._hy_xl = 0.0
        self._hy_xr = 0.0
        self._hy_a = 0.0
        self._hy_lamdl = 0.0
        self._hy_lamdr = 0.0
        self._hy_p1 = 0.0
        self._hy_p2 = 0.0
        self._hy_p3 = 0.0

    def _genrand(self) -> float:
        """MT19937: the next 32 bits as a number in [0, 1)."""
        if self.mti >= N:
            mt = self.mt
            for k in range(N):
                y = (mt[k] & 2147483648) | (mt[(k + 1) % N] & 2147483647)
                v = mt[(k + M) % N] ^ (y >> 1)
                if y & 1:
                    v ^= 2567483615
                mt[k] = v
            self.mti = 0
        y = self.mt[self.mti]
        self.mti += 1
        y ^= y >> 11
        y ^= (y << 7) & 2636928640
        y ^= (y << 15) & 4022730752
        y ^= y >> 18
        return float(y) * 2.3283064365386963e-10

    def unif_rand(self) -> float:
        """A uniform number in (0, 1), as R's `unif_rand`."""
        x = self._genrand()
        if x <= 0.0:
            return 0.5 * I2_32M1
        if 1.0 - x <= 0.0:
            return 1.0 - 0.5 * I2_32M1
        return x

    def norm_rand(self) -> float:
        """A standard normal number (inversion, R's default)."""
        u = self.unif_rand()
        u = float(int(BIG * u)) + self.unif_rand()
        return qnorm0(u / BIG, True, False)

    def exp_rand(self) -> float:
        """A standard exponential number (Ahrens and Dieter, 1972)."""
        # q[k - 1] = sum of log(2)^i / i!, i = 1..k, as the constants in R
        q: list[float] = [0.6931471805599453, 0.9333736875190459, 0.9888777961838675, 0.9984959252914960, 0.9998292811061389, 0.9999833164100727, 0.9999985691438767, 0.9999998906925558, 0.9999999924734159, 0.9999999995283275, 0.9999999999728814, 0.9999999999985598, 0.9999999999999289, 0.9999999999999968, 0.9999999999999999, 1.0]
        a = 0.0
        u = self.unif_rand()
        while u <= 0.0 or u >= 1.0:
            u = self.unif_rand()
        while True:
            u += u
            if u > 1.0:
                break
            a += q[0]
        u -= 1.0
        if u <= q[0]:
            return a + u
        i = 0
        ustar = self.unif_rand()
        umin = ustar
        while True:
            ustar = self.unif_rand()
            if umin > ustar:
                umin = ustar
            i += 1
            if u <= q[i]:
                break
        return math.fma(umin, q[0], a)

    def _rbits(self, bits: int) -> int:
        v = 0
        n = 0
        while n <= bits:
            v1 = int(math.floor(self.unif_rand() * 65536.0))
            v = 65536 * v + v1
            n += 16
        return v & ((1 << bits) - 1)

    def unif_index(self, dn: float) -> int:
        """A uniform integer in [0, dn), by rejection (R ≥ 3.6's `sample`)."""
        if dn <= 0.0:
            return 0
        bits = int(math.ceil(math.log2(dn)))
        while True:
            dv = self._rbits(bits)
            if float(dv) < dn:
                return dv

    # ------------------------------------------------------------ R's r* functions

    def runif(self, n: int, min: float = 0.0, max: float = 1.0) -> list[float]:
        return [min + (max - min) * self.unif_rand() for _ in range(n)]

    def rnorm(self, n: int, mean: float = 0.0, sd: float = 1.0) -> list[float]:
        return [math.fma(sd, self.norm_rand(), mean) for _ in range(n)]

    def rexp(self, n: int, rate: float = 1.0) -> list[float]:
        scale = 1.0 / rate
        return [scale * self.exp_rand() for _ in range(n)]

    def rlnorm(self, n: int, meanlog: float = 0.0, sdlog: float = 1.0) -> list[float]:
        return [math.exp(math.fma(sdlog, self.norm_rand(), meanlog)) for _ in range(n)]

    def sample(self, n: int, size: int, replace: bool = False) -> list[int]:
        """`sample(n, size, replace)`: numbers from 1 to n."""
        if replace:
            return [self.unif_index(float(n)) + 1 for _ in range(size)]
        if size > n:
            raise ValueError("cannot take a sample larger than the population when 'replace = FALSE'")
        pool = list(range(n))
        out: list[int] = []
        m = n
        for _ in range(size):
            j = self.unif_index(float(m))
            out.append(pool[j] + 1)
            m -= 1
            pool[j] = pool[m]
        return out

    def sample_from(self, x: list[float], size: int, replace: bool = False) -> list[float]:
        """`sample(x, size, replace)` of a numeric vector."""
        return [x[i - 1] for i in self.sample(len(x), size, replace)]

    # ------------------------------------------------------ continuous distributions

    def rgamma(self, n: int, shape: float, scale: float = 1.0) -> list[float]:
        return [self._rgamma1(shape, scale) for _ in range(n)]

    def rchisq(self, n: int, df: float) -> list[float]:
        return [self._rgamma1(df / 2.0, 2.0) for _ in range(n)]

    def rbeta(self, n: int, shape1: float, shape2: float) -> list[float]:
        return [self._rbeta1(shape1, shape2) for _ in range(n)]

    def rt(self, n: int, df: float) -> list[float]:
        return [self._rt1(df) for _ in range(n)]

    def rf(self, n: int, df1: float, df2: float) -> list[float]:
        return [self._rf1(df1, df2) for _ in range(n)]

    def rcauchy(self, n: int, location: float = 0.0, scale: float = 1.0) -> list[float]:
        return [math.fma(scale, math.tan(math.pi * self.unif_rand()), location) for _ in range(n)]

    def rlogis(self, n: int, location: float = 0.0, scale: float = 1.0) -> list[float]:
        out: list[float] = []
        for _ in range(n):
            u = self.unif_rand()
            out.append(math.fma(scale, math.log(u / (1.0 - u)), location))
        return out

    def rweibull(self, n: int, shape: float, scale: float = 1.0) -> list[float]:
        return [scale * (-math.log(self.unif_rand())) ** (1.0 / shape) for _ in range(n)]

    # ------------------------------------------------------ discrete distributions

    def rbinom(self, n: int, size: float, prob: float) -> list[int]:
        return [self._rbinom1(size, prob) for _ in range(n)]

    def rpois(self, n: int, lambda_: float) -> list[int]:
        return [self._rpois1(lambda_) for _ in range(n)]

    def rgeom(self, n: int, prob: float) -> list[int]:
        out: list[int] = []
        for _ in range(n):
            lam = self.exp_rand() * ((1.0 - prob) / prob)
            out.append(self._rpois1(lam))
        return out

    def rnbinom(self, n: int, size: float, prob: float) -> list[int]:
        return [self._rnbinom1(size, prob) for _ in range(n)]

    def rhyper(self, n: int, m: float, n_: float, k: float) -> list[int]:
        return [self._rhyper1(m, n_, k) for _ in range(n)]

    # ------------------------------------------------------ scalar generators (R's src/nmath)

    def _rgamma1(self, a: float, scale: float) -> float:
        """R's rgamma: GS for a < 1, Ahrens and Dieter's (1982) GD for a >= 1."""
        sqrt32 = 5.656854
        exp_m1 = 0.36787944117144232159
        if a <= 0.0 or scale <= 0.0:
            if scale == 0.0 or a == 0.0:
                return 0.0
            raise ValueError("invalid arguments to rgamma")
        if math.isinf(a) or math.isinf(scale):
            return math.inf
        if a < 1.0:
            # GS algorithm
            e = math.fma(exp_m1, a, 1.0)
            while True:
                p = e * self.unif_rand()
                if p >= 1.0:
                    x = -math.log((e - p) / a)
                    if self.exp_rand() >= (1.0 - a) * math.log(x):
                        break
                else:
                    x = math.exp(math.log(p) / a)
                    if self.exp_rand() >= x:
                        break
            return scale * x
        # GD algorithm
        if a != self._ga_a:
            self._ga_a = a
            self._ga_s2 = a - 0.5
            self._ga_s = math.sqrt(self._ga_s2)
            self._ga_d = math.fma(-self._ga_s, 12.0, sqrt32)
        # step 2: t normal, x (s, 1/2)-normal
        t = self.norm_rand()
        x = math.fma(0.5, t, self._ga_s)
        ret_val = x * x
        if t >= 0.0:
            return scale * ret_val
        # step 3: squeeze acceptance
        u = self.unif_rand()
        if self._ga_d * u <= t * t * t:
            return scale * ret_val
        # step 4: recalculation of q0, b, si, c
        if a != self._ga_aa:
            self._ga_aa = a
            r = 1.0 / a
            q0 = math.fma(r, 2.424e-4, 2.4511e-4)
            q0 = math.fma(q0, r, -7.388e-5)
            q0 = math.fma(q0, r, 0.00144121)
            q0 = math.fma(q0, r, 0.00801191)
            q0 = math.fma(q0, r, 0.02083148)
            q0 = math.fma(q0, r, 0.04166669)
            self._ga_q0 = q0 * r
            if a <= 3.686:
                self._ga_b = math.fma(0.178, self._ga_s2, 0.463 + self._ga_s)
                self._ga_si = 1.235
                self._ga_c = math.fma(0.16, self._ga_s, 0.195 / self._ga_s - 0.079)
            elif a <= 13.022:
                self._ga_b = math.fma(0.0076, self._ga_s2, 1.654)
                self._ga_si = 1.68 / self._ga_s + 0.275
                self._ga_c = 0.062 / self._ga_s + 0.024
            else:
                self._ga_b = 1.77
                self._ga_si = 0.75
                self._ga_c = 0.1515 / self._ga_s
        # step 5: no quotient test if x not positive
        if x > 0.0:
            # step 6: calculation of v and quotient q
            v = t / (self._ga_s + self._ga_s)
            if abs(v) <= 0.25:
                poly = math.fma(v, 0.1233795, -0.1367177)
                poly = math.fma(poly, v, 0.1423657)
                poly = math.fma(poly, v, -0.1662921)
                poly = math.fma(poly, v, 0.2000062)
                poly = math.fma(poly, v, -0.250003)
                poly = math.fma(poly, v, 0.3333333)
                q = math.fma(0.5 * t * t * poly, v, self._ga_q0)
            else:
                q = math.fma(0.25 * t, t, math.fma(-self._ga_s, t, self._ga_q0)) + (self._ga_s2 + self._ga_s2) * math.log(1.0 + v)
            # step 7: quotient acceptance
            if math.log(1.0 - u) <= q:
                return scale * ret_val
        while True:
            # steps 8 to 11: hat acceptance
            e = self.exp_rand()
            u = self.unif_rand()
            u = u + u - 1.0
            if u < 0.0:
                t = math.fma(self._ga_si, -e, self._ga_b)
            else:
                t = math.fma(self._ga_si, e, self._ga_b)
            if t >= -0.71874483771719:
                v = t / (self._ga_s + self._ga_s)
                if abs(v) <= 0.25:
                    poly = math.fma(v, 0.1233795, -0.1367177)
                    poly = math.fma(poly, v, 0.1423657)
                    poly = math.fma(poly, v, -0.1662921)
                    poly = math.fma(poly, v, 0.2000062)
                    poly = math.fma(poly, v, -0.250003)
                    poly = math.fma(poly, v, 0.3333333)
                    q = math.fma(0.5 * t * t * poly, v, self._ga_q0)
                else:
                    q = math.fma(0.25 * t, t, math.fma(-self._ga_s, t, self._ga_q0)) + (self._ga_s2 + self._ga_s2) * math.log(1.0 + v)
                if q > 0.0:
                    w = math.expm1(q)
                    if self._ga_c * abs(u) <= w * math.exp(math.fma(-0.5 * t, t, e)):
                        break
        x = math.fma(0.5, t, self._ga_s)
        return scale * x * x

    def _rbeta1(self, aa: float, bb: float) -> float:
        """R's rbeta: Cheng's (1978) algorithms BB (a > 1) and BC (a <= 1)."""
        expmax = 1024.0 * 0.6931471805599453  # log(DBL_MAX)
        a = min(aa, bb)
        b = max(aa, bb)
        alpha = a + b
        qsame = self._rb_olda == aa and self._rb_oldb == bb
        if not qsame:
            self._rb_olda = aa
            self._rb_oldb = bb

        def _vw(u1: float, aa_: float) -> tuple[float, float]:
            # R's v_w_from__u1_bet macro
            v = self._rb_beta * math.log(u1 / (1.0 - u1))
            if v <= expmax:
                w = aa_ * math.exp(v)
                if math.isinf(w):
                    w = 1.7976931348623157e308
            else:
                w = 1.7976931348623157e308
            return (v, w)

        def _w(u1: float, aa_: float) -> float:
            v = self._rb_beta * math.log(u1 / (1.0 - u1))
            if v <= expmax:
                w = aa_ * math.exp(v)
                if math.isinf(w):
                    w = 1.7976931348623157e308
            else:
                w = 1.7976931348623157e308
            return w

        if a <= 1.0:
            # Algorithm BC
            if not qsame:
                self._rb_beta = 1.0 / a
                self._rb_delta = 1.0 + b - a
                self._rb_k1 = self._rb_delta * math.fma(0.0416667, a, 0.0138889) / math.fma(b, self._rb_beta, -0.777778)
                self._rb_k2 = math.fma(0.5 + 0.25 / self._rb_delta, a, 0.25)
            while True:
                u1 = self.unif_rand()
                u2 = self.unif_rand()
                if u1 < 0.5:
                    y = u1 * u2
                    z = u1 * y
                    if math.fma(0.25, u2, z) - y >= self._rb_k1:
                        continue
                else:
                    z = u1 * u1 * u2
                    if z <= 0.25:
                        w = _w(u1, b)
                        break
                    if z >= self._rb_k2:
                        continue
                v, w = _vw(u1, b)
                if math.fma(alpha, math.log(alpha / (a + w)) + v, -1.3862944) >= math.log(z):
                    break
            return a / (a + w) if aa == a else w / (a + w)
        # Algorithm BB
        if not qsame:
            self._rb_beta = math.sqrt((alpha - 2.0) / math.fma(2.0 * a, b, -alpha))
            self._rb_gamma = a + 1.0 / self._rb_beta
        while True:
            u1 = self.unif_rand()
            u2 = self.unif_rand()
            v, w = _vw(u1, a)
            z = u1 * u1 * u2
            r = math.fma(self._rb_gamma, v, -1.3862944)
            s = a + r - w
            if s + 2.609438 >= 5.0 * z:
                break
            tv = math.log(z)
            if s > tv:
                break
            if math.fma(alpha, math.log(alpha / (b + w)), r) >= tv:
                break
        return b / (b + w) if aa != a else w / (b + w)

    def _rt1(self, df: float) -> float:
        """R's rt: rnorm / sqrt(rchisq / df) (rchisq drawn second)."""
        num = self.norm_rand()
        return num / math.sqrt(self._rgamma1(df / 2.0, 2.0) / df)

    def _rf1(self, n1: float, n2: float) -> float:
        """R's rf: (chisq1 / df1) / (chisq2 / df2)."""
        v1 = self._rgamma1(n1 / 2.0, 2.0) / n1
        v2 = self._rgamma1(n2 / 2.0, 2.0) / n2
        return v1 / v2

    def _rbinom1(self, nin: float, pp: float) -> int:
        """R's rbinom: Kachitvichyanukul and Schmeiser's (1988) BTPE."""
        n = int(nin)
        p = min(pp, 1.0 - pp)
        q = 1.0 - p
        np_ = n * p
        r = p / q
        g = r * (float(n) + 1.0)
        if pp != self._bo_psave or n != self._bo_nsave:
            self._bo_psave = pp
            self._bo_nsave = n
            self._bo_g = g
            self._bo_r = r
            if np_ < 30.0:
                self._bo_qn = _pow_di(q, n)
                return self._binom_small(n)
            ffm = np_ + p
            m = int(ffm)
            fm = float(m)
            npq = np_ * q
            self._bo_p1 = int(2.195 * math.sqrt(npq) - 4.6 * q) + 0.5
            self._bo_xm = fm + 0.5
            self._bo_xl = self._bo_xm - self._bo_p1
            self._bo_xr = self._bo_xm + self._bo_p1
            self._bo_c = 0.134 + 20.5 / (15.3 + fm)
            al = (ffm - self._bo_xl) / math.fma(-self._bo_xl, p, ffm)
            self._bo_xll = al * math.fma(0.5, al, 1.0)
            al = (self._bo_xr - ffm) / (self._bo_xr * q)
            self._bo_xlr = al * math.fma(0.5, al, 1.0)
            self._bo_p2 = self._bo_p1 * (1.0 + self._bo_c + self._bo_c)
            self._bo_p3 = self._bo_p2 + self._bo_c / self._bo_xll
            self._bo_p4 = self._bo_p3 + self._bo_c / self._bo_xlr
            self._bo_m = m
            self._bo_npq = npq
            self._bo_g = g
            self._bo_r = r
            self._bo_p = p
            self._bo_q = q
            self._bo_n = n
        else:
            if np_ < 30.0:
                return self._binom_small(n)
        # np = n*p >= 30
        n_ = self._bo_n
        m = self._bo_m
        fm = float(m)
        npq = self._bo_npq
        p = self._bo_p
        q = self._bo_q
        r = self._bo_r
        g = self._bo_g
        while True:
            u = self.unif_rand() * self._bo_p4
            v = self.unif_rand()
            if u <= self._bo_p1:
                ix = int(math.fma(-self._bo_p1, v, self._bo_xm) + u)
                break
            if u <= self._bo_p2:
                x = self._bo_xl + (u - self._bo_p1) / self._bo_c
                v = math.fma(v, self._bo_c, 1.0) - abs(self._bo_xm - x) / self._bo_p1
                if v > 1.0 or v <= 0.0:
                    continue
                ix = int(x)
            else:
                if u > self._bo_p3:
                    ix = int(self._bo_xr - math.log(v) / self._bo_xlr)
                    if ix > n_:
                        continue
                    v = v * (u - self._bo_p3) * self._bo_xlr
                else:
                    ix = int(self._bo_xl + math.log(v) / self._bo_xll)
                    if ix < 0:
                        continue
                    v = v * (u - self._bo_p2) * self._bo_xll
            k = abs(ix - m)
            if k <= 20 or float(k) >= npq / 2.0 - 1.0:
                f = 1.0
                if m < ix:
                    for i in range(m + 1, ix + 1):
                        f *= (g / float(i) - r)
                elif m != ix:
                    for i in range(ix + 1, m + 1):
                        f /= (g / float(i) - r)
                if v <= f:
                    break
            else:
                amaxp = (float(k) / npq) * (math.fma(float(k), float(k) / 3.0 + 0.625, 0.1666666666666) / npq + 0.5)
                ynorm = -float(k) * float(k) / (2.0 * npq)
                alv = math.log(v)
                if alv < ynorm - amaxp:
                    break
                if alv <= ynorm + amaxp:
                    x1 = float(ix + 1)
                    f1 = fm + 1.0
                    z = float(n_ + 1) - fm
                    w = float(n_ - ix + 1)
                    z2 = z * z
                    x2 = x1 * x1
                    f2 = f1 * f1
                    w2 = w * w
                    corr = math.fma(float(n_ - m) + 0.5, math.log(z / w), self._bo_xm * math.log(f1 / x1))
                    corr = math.fma(float(ix - m), math.log(w * p / (x1 * q)), corr)
                    corr += (13860.0 - (462.0 - (132.0 - (99.0 - 140.0 / f2) / f2) / f2) / f2) / f1 / 166320.0
                    corr += (13860.0 - (462.0 - (132.0 - (99.0 - 140.0 / z2) / z2) / z2) / z2) / z / 166320.0
                    corr += (13860.0 - (462.0 - (132.0 - (99.0 - 140.0 / x2) / x2) / x2) / x2) / x1 / 166320.0
                    corr += (13860.0 - (462.0 - (132.0 - (99.0 - 140.0 / w2) / w2) / w2) / w2) / w / 166320.0
                    if alv <= corr:
                        break
        if self._bo_psave > 0.5:
            ix = self._bo_n - ix
        return ix

    def _binom_small(self, n: int) -> int:
        """The inverse cdf branch of BTPE (np < 30)."""
        g = self._bo_g
        r = self._bo_r
        while True:
            ix = 0
            f = self._bo_qn
            u = self.unif_rand()
            while True:
                if u < f:
                    if self._bo_psave > 0.5:
                        ix = n - ix
                    return ix
                if ix > 110:
                    break
                u -= f
                ix += 1
                f *= (g / float(ix) - r)

    def _rpois1(self, mu: float) -> int:
        """R's rpois: Ahrens and Dieter's (1982) tables for mu < 10, their
        modified normal rejection for larger mu."""
        fact: list[float] = [1.0, 1.0, 2.0, 6.0, 24.0, 120.0, 720.0, 5040.0, 40320.0, 362880.0]
        if mu <= 0.0:
            return 0
        big_mu = mu >= 10.0
        if big_mu:
            if not (mu == self._pp_muprev):
                s = math.sqrt(mu)
                self._pp_s = s
                self._pp_d = 6.0 * mu * mu
                self._pp_big_l = float(math.floor(mu - 1.1484))
                self._pp_muprev = mu
            s = self._pp_s
            d = self._pp_d
            big_l = self._pp_big_l
        else:
            if mu != self._pp_muprev:
                self._pp_muprev = mu
                self._pp_m = max(1, int(mu))
                self._pp_l = 0
                q0 = math.exp(-mu)
                self._pp_p0 = q0
                self._pp_p = q0
                self._pp_q = q0
                self._pp_table = [0.0] * 36
            m = self._pp_m
            l = self._pp_l
            while True:
                u = self.unif_rand()
                if u <= self._pp_p0:
                    return 0
                if self._pp_l != 0:
                    start = 1 if u <= 0.458 else min(self._pp_l, m)
                    for k in range(start, self._pp_l + 1):
                        if u <= self._pp_table[k]:
                            return k
                    if self._pp_l == 35:
                        continue
                self._pp_l += 1
                k = self._pp_l
                found = False
                while k <= 35:
                    self._pp_p *= mu / float(k)
                    self._pp_q += self._pp_p
                    self._pp_table[k] = self._pp_q
                    if u <= self._pp_q:
                        self._pp_l = k
                        found = True
                        break
                    k += 1
                if found:
                    return k
                self._pp_l = 35
            # unreachable
        # mu >= 10
        s = self._pp_s
        d = self._pp_d
        big_l = self._pp_big_l
        g = math.fma(s, self.norm_rand(), mu)
        pois = -1.0
        u = 0.0
        if g >= 0.0:
            pois = math.floor(g)
            if pois >= big_l:
                return int(pois)
            fk = pois
            difmuk = mu - fk
            u = self.unif_rand()
            if d * u >= difmuk * difmuk * difmuk:
                return int(pois)
        if mu != self._pp_muprev2:
            self._pp_muprev2 = mu
            self._pp_omega = 0.398942280401432677939946059934 / s
            b1 = 0.0416666666666666667 / mu
            b2 = 0.3 * b1 * b1
            c3 = 0.1428571428571428571 * b1 * b2
            self._pp_b1 = b1
            self._pp_b2 = b2
            self._pp_c3 = c3
            self._pp_c2 = math.fma(-15.0, c3, b2)
            self._pp_c1 = math.fma(45.0, c3, math.fma(-6.0, b2, b1))
            self._pp_c0 = math.fma(-15.0, c3, math.fma(3.0, b2, 1.0 - b1))
            self._pp_c = 0.1069 / mu
        omega = self._pp_omega
        b1 = self._pp_b1
        c0 = self._pp_c0
        c1 = self._pp_c1
        c2 = self._pp_c2
        c3 = self._pp_c3
        cc = self._pp_c
        if g >= 0.0:
            px, py, fx, fy = self._pois_f(pois, mu, s, omega)
            if math.fma(-u, fy, fy) <= py * math.exp(px - fx):
                return int(pois)
        while True:
            e = self.exp_rand()
            u = 2.0 * self.unif_rand() - 1.0
            t = 1.8 + e if u >= 0.0 else 1.8 - abs(e)
            if t > -0.6744:
                pois = math.floor(math.fma(s, t, mu))
                px, py, fx, fy = self._pois_f(pois, mu, s, omega)
                if cc * abs(u) <= py * math.exp(px + e) - fy * math.exp(fx + e):
                    return int(pois)

    def _pois_f(self, pois: float, mu: float, s: float, omega: float) -> tuple[float, float, float, float]:
        """R's 'subroutine F' of rpois: the probability terms and hat terms."""
        fact: list[float] = [1.0, 1.0, 2.0, 6.0, 24.0, 120.0, 720.0, 5040.0, 40320.0, 362880.0]
        fk = pois
        difmuk = mu - fk
        if pois < 10.0:
            px = -mu
            py = mu ** pois / fact[int(pois)]
        else:
            del_ = 0.0833333333333333333 / fk
            del_ = del_ * math.fma(-4.8 * del_, del_, 1.0)
            v = difmuk / fk
            if abs(v) <= 0.25:
                poly = math.fma(v, 0.1250060, -0.1384794)
                poly = math.fma(poly, v, 0.1421878)
                poly = math.fma(poly, v, -0.1661269)
                poly = math.fma(poly, v, 0.2000118)
                poly = math.fma(poly, v, -0.2500068)
                poly = math.fma(poly, v, 0.3333333)
                poly = math.fma(poly, v, -0.5)
                px = math.fma(fk * v * v, poly, -del_)
            else:
                px = math.fma(fk, math.log(1.0 + v), -difmuk) - del_
            py = 0.398942280401432677939946059934 / math.sqrt(fk)
        x = (0.5 - difmuk) / s
        x *= x
        fx = -0.5 * x
        c3 = self._pp_c3
        c2 = self._pp_c2
        c1 = self._pp_c1
        c0 = self._pp_c0
        chain = math.fma(c3, x, c2)
        chain = math.fma(chain, x, c1)
        chain = math.fma(chain, x, c0)
        fy = omega * chain
        return (px, py, fx, fy)

    def _rnbinom1(self, size: float, prob: float) -> int:
        """R's rnbinom: a Poisson number with gamma mean."""
        if prob == 1.0:
            return 0
        lam = self._rgamma1(size, (1.0 - prob) / prob)
        return self._rpois1(lam)

    def _rhyper1(self, nn1in: float, nn2in: float, kkin: float) -> int:
        """R's rhyper: Kachitvichyanukul and Schmeiser's (1985) algorithm, with
        R's fix of their bug (PR#7314)."""
        nn1 = int(nn1in)
        nn2 = int(nn2in)
        kk = int(kkin)
        nd = nn1in + nn2in
        n_ = 0
        n2 = 0
        k = 0
        m = 0
        minjx = 0
        maxjx = 0
        setup1 = nn1 != self._hy_n1s or nn2 != self._hy_n2s
        setup2 = kk != self._hy_ks
        if setup1:
            self._hy_n1s = nn1
            self._hy_n2s = nn2
            if nn1 <= nn2:
                n_ = nn1
                n2 = nn2
            else:
                n_ = nn2
                n2 = nn1
        else:
            n_ = self._hy_n1
            n2 = self._hy_n2
        if setup2:
            self._hy_ks = kk
            if float(kk) + float(kk) >= nd:
                k = int(nd) - kk
            else:
                k = kk
        else:
            k = self._hy_k
        if setup1 or setup2:
            self._hy_n1 = n_
            self._hy_n2 = n2
            self._hy_k = k
            m = int((float(k) + 1.0) * (float(n_) + 1.0) / (nd + 2.0))
            self._hy_m = m
            minjx = max(0, k - n2)
            maxjx = min(n_, k)
            self._hy_minjx = minjx
            self._hy_maxjx = maxjx
        else:
            m = self._hy_m
            minjx = self._hy_minjx
            maxjx = self._hy_maxjx
        if minjx == maxjx:
            ix = maxjx
        elif m - minjx < 10:
            # II: inverse transformation (scaled)
            con = 57.5646273248511421
            if setup1 or setup2:
                if k < n2:
                    lw = _afc(n2) + _afc(n_ + n2 - k) - _afc(n2 - k) - _afc(n_ + n2)
                else:
                    lw = _afc(n_) + _afc(k) - _afc(k - n2) - _afc(n_ + n2)
                self._hy_w = math.exp(lw + con)
            w = self._hy_w
            while True:
                p = w
                ix = minjx
                u = self.unif_rand() * 1e25
                retry = False
                while u > p:
                    u -= p
                    p *= (float(n_) - float(ix)) * float(k - ix)
                    ix += 1
                    p = p / float(ix) / float(n2 - k + ix)
                    if ix > maxjx:
                        retry = True
                        break
                if not retry:
                    break
        else:
            # III: H2PE
            if setup1 or setup2:
                s = math.sqrt((nd - float(k)) * float(k) * float(n_) * float(n2) / (nd - 1.0) / nd / nd)
                d = int(1.5 * s) + 0.5
                self._hy_xl = m - d + 0.5
                self._hy_xr = m + d + 0.5
                a = _afc(m) + _afc(n_ - m) + _afc(k - m) + _afc(n2 - k + m)
                self._hy_a = a
                xl = self._hy_xl
                xr = self._hy_xr
                kl = math.exp(a - _afc(int(xl)) - _afc(int(n_ - xl)) - _afc(int(k - xl)) - _afc(int(n2 - k + xl)))
                kr = math.exp(a - _afc(int(xr - 1.0)) - _afc(int(n_ - xr + 1.0)) - _afc(int(k - xr + 1.0)) - _afc(int(n2 - k + xr - 1.0)))
                self._hy_lamdl = -math.log(xl * float(n2 - k + xl) / (n_ - xl + 1.0) / (k - xl + 1.0))
                self._hy_lamdr = -math.log((n_ - xr + 1.0) * (k - xr + 1.0) / xr / float(n2 - k + xr))
                self._hy_p1 = d + d
                self._hy_p2 = self._hy_p1 + kl / self._hy_lamdl
                self._hy_p3 = self._hy_p2 + kr / self._hy_lamdr
            xl = self._hy_xl
            xr = self._hy_xr
            a = self._hy_a
            lamdl = self._hy_lamdl
            lamdr = self._hy_lamdr
            p1 = self._hy_p1
            p2 = self._hy_p2
            p3 = self._hy_p3
            while True:
                u = self.unif_rand() * p3
                v = self.unif_rand()
                if u < p1:
                    ix = int(xl + u)
                elif u <= p2:
                    ix = int(xl + math.log(v) / lamdl)
                    if ix < minjx:
                        continue
                    v = v * (u - p1) * lamdl
                else:
                    ix = int(xr - math.log(v) / lamdr)
                    if ix > maxjx:
                        continue
                    v = v * (u - p2) * lamdr
                accept = False
                if m < 100 or ix <= 50:
                    f = 1.0
                    if m < ix:
                        for i in range(m + 1, ix + 1):
                            f = f * float(n_ - i + 1) * float(k - i + 1) / float(n2 - k + i) / float(i)
                    elif m > ix:
                        for i in range(ix + 1, m + 1):
                            f = f * float(i) * float(n2 - k + i) / float(n_ - i + 1) / float(k - i + 1)
                    if v <= f:
                        accept = True
                else:
                    deltal = 0.0078
                    deltau = 0.0034
                    y = float(ix)
                    y1 = y + 1.0
                    ym = y - float(m)
                    yn = float(n_) - y + 1.0
                    yk = float(k) - y + 1.0
                    nk = float(n2 - k) + y1
                    r = -ym / y1
                    s2 = ym / yn
                    t2 = ym / yk
                    e2 = -ym / nk
                    g2 = yn * yk / (y1 * nk) - 1.0
                    dg = 1.0 if g2 >= 0.0 else 1.0 + g2
                    gu = g2 * math.fma(g2, -0.5 + g2 / 3.0, 1.0)
                    gl = gu - 0.25 * g2 * g2 * g2 * g2 / dg
                    xm = float(m) + 0.5
                    xn = float(n_ - m) + 0.5
                    xk = float(k - m) + 0.5
                    nm = float(n2 - k) + xm
                    ub = math.fma(-float(m), gl, y * gu) + deltau
                    ub = math.fma(xm * r, math.fma(r, -0.5 + r / 3.0, 1.0), ub)
                    ub = math.fma(xn * s2, math.fma(s2, -0.5 + s2 / 3.0, 1.0), ub)
                    ub = math.fma(xk * t2, math.fma(t2, -0.5 + t2 / 3.0, 1.0), ub)
                    ub = math.fma(nm * e2, math.fma(e2, -0.5 + e2 / 3.0, 1.0), ub)
                    alv = math.log(v)
                    if alv > ub:
                        accept = False
                    else:
                        dr = xm * (r * r * r * r)
                        if r < 0.0:
                            dr /= 1.0 + r
                        ds = xn * (s2 * s2 * s2 * s2)
                        if s2 < 0.0:
                            ds /= 1.0 + s2
                        dt = xk * (t2 * t2 * t2 * t2)
                        if t2 < 0.0:
                            dt /= 1.0 + t2
                        de = nm * (e2 * e2 * e2 * e2)
                        if e2 < 0.0:
                            de /= 1.0 + e2
                        if alv < math.fma(y + float(m), gl - gu, math.fma(-0.25, dr + ds + dt + de, ub)) - deltal:
                            accept = True
                        elif alv <= (a - _afc(ix) - _afc(n_ - ix) - _afc(k - ix) - _afc(n2 - k + ix)):
                            accept = True
                if accept:
                    break
        # L_finis
        if float(kk) + float(kk) >= nd:
            if nn1 > nn2:
                ix = kk - nn2 + ix
            else:
                ix = nn1 - ix
        elif nn1 > nn2:
            ix = kk - ix
        return ix


def _pow_di(x: float, n: int) -> float:
    """R's R_pow_di: the square-and-multiply integer power."""
    powv = 1.0
    if n != 0:
        if n < 0:
            n = -n
            x = 1.0 / x
        while True:
            if n & 1:
                powv *= x
            n >>= 1
            if n == 0:
                break
            x *= x
    return powv


def _afc(i: int) -> float:
    """log(i!) as R's rhyper computes it (its own Stirling for i >= 8)."""
    if i <= 7:
        al = [0.0, 0.0, 0.69314718055994530941723212145817, 1.79175946922805500081247735838070, 3.17805383034794561964694160129705, 4.78749174278204599424770093452324, 6.57925121201010099506017829290394, 8.52516136106541430016553103634712]
        return al[i]
    di = float(i)
    i2 = di * di
    return (di + 0.5) * math.log(di) - di + 0.9189385332046727418 + (0.0833333333333333 - 0.00277777777777778 / i2) / di


def set_seed(seed: int) -> RNG:
    """The generator R has after `set.seed(seed)`."""
    return RNG(seed)
