"""R's random numbers: the Mersenne-Twister seeded as `set.seed` seeds it,
`unif_rand`, normal numbers by inversion, exponential numbers by Ahrens and
Dieter's algorithm, and `sample`'s rejection sampling (R ≥ 3.6). A seeded
RNG gives the numbers R gives after `set.seed` with the same seed:

    rng = rstat.set_seed(42)
    rng.rnorm(3)        # R: set.seed(42); rnorm(3)

(R keeps one generator in the session; rstat passes it explicitly.)"""

import math

from rstat.special import qnorm0

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
        # q[k - 1] = sum of log(2)^i / i!, i = 1..k
        q: list[float] = []
        ln2 = math.log(2.0)
        term = 1.0
        total = 0.0
        for i in range(1, 17):
            term = term * ln2 / float(i)
            total += term
            q.append(total)
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
        return a + umin * q[0]

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
        return [mean + sd * self.norm_rand() for _ in range(n)]

    def rexp(self, n: int, rate: float = 1.0) -> list[float]:
        return [self.exp_rand() / rate for _ in range(n)]

    def rlnorm(self, n: int, meanlog: float = 0.0, sdlog: float = 1.0) -> list[float]:
        return [math.exp(meanlog + sdlog * self.norm_rand()) for _ in range(n)]

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


def set_seed(seed: int) -> RNG:
    """The generator R has after `set.seed(seed)`."""
    return RNG(seed)
