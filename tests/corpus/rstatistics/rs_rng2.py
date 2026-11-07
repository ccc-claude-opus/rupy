"""rstatistics: R's r* generators (gamma, beta, t, F, binomial, Poisson, hypergeometric)."""
import rstatistics as r


def p(xs: list[float]) -> None:
    print(" ".join(f"{x:.15g}" for x in xs), "")


def pi(xs: list[int]) -> None:
    print(" ".join(str(x) for x in xs), "")


g = r.set_seed(21)
p(g.rgamma(5, 2.5))
p(g.rgamma(4, 0.3))
p(g.rgamma(3, 13.022))
p(g.rgamma(4, 12.0, 2.5))
p(g.rbeta(5, 2.5, 3.0))
p(g.rbeta(4, 0.7, 0.5))
p(g.rt(4, 5.0))
p(g.rf(4, 4.0, 8.0))
p(g.rchisq(4, 12.5))
p(g.rweibull(4, 2.0, 3.0))
p(g.rcauchy(3))
p(g.rlogis(3, 5.0, 0.5))
g = r.set_seed(31)
pi(g.rbinom(8, 10, 0.3))
pi(g.rbinom(6, 1000, 0.3))
pi(g.rbinom(5, 2, 0.9))
g = r.set_seed(32)
pi(g.rpois(8, 3.0))
pi(g.rpois(6, 10.0))
pi(g.rpois(5, 500.0))
g = r.set_seed(33)
pi(g.rgeom(6, 0.3))
pi(g.rnbinom(6, 5.0, 0.3))
g = r.set_seed(34)
pi(g.rhyper(6, 10, 20, 5))
pi(g.rhyper(5, 1000, 500, 100))
