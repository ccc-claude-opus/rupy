"""rstat: R's random numbers after set.seed (Mersenne-Twister, inversion, sample)."""
import rstat as r


def p(xs: list[float]) -> None:
    print(" ".join(f"{x:.15g}" for x in xs), "")


def pi(xs: list[int]) -> None:
    print(" ".join(str(x) for x in xs), "")


g = r.set_seed(42)
p(g.runif(5))
p(g.rnorm(5))
p(g.rexp(5))
pi(g.sample(10, 5))
pi(g.sample(100, 8, replace=True))
g = r.set_seed(2026)
p(g.rnorm(3, 10.0, 2.0))
p(g.sample_from([3.5, 1.25, 7.0, 9.5], 4))
p(g.runif(2, -1.0, 1.0))
g = r.set_seed(-7)
p(g.rnorm(4))
p(g.rexp(3, 2.0))
