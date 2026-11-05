"""rstatistics: R's probability and statistics functions in Python.

The names are R's, with `_` for `.` (`t.test` is `t_test`); arguments are R's
too (`lower.tail` is `lower_tail`). Printed results look as in R. The package
is written in rupy's typed subset of Python, so rupy compiles it to Rust or
WebAssembly as well."""

from rstatistics.distributions import (
    dbeta, dbinom, dcauchy, dchisq, dexp, df, dgamma, dgeom, dhyper, dlnorm, dlogis, dnbinom, dnorm, dpois, dt,
    dunif, dweibull, pbeta, pbinom, pcauchy, pchisq, pexp, pf, pgamma, pgeom, phyper, plnorm, plogis, pnbinom,
    pnorm, ppois, pt, punif, pweibull, qbeta, qbinom, qcauchy, qchisq, qexp, qf, qgamma, qgeom, qlnorm, qlogis,
    qnorm, qpois, qt, qunif, qweibull,
)
from rstatistics.describe import IQR, Named, Summary, cor, cov, fivenum, mad, mean, median, quantile, rank, scale, sd, summary, var, weighted_mean
from rstatistics.htest import HTest, binom_test, chisq_test, chisq_test_table, cor_test, prop_test, t_test, var_test
from rstatistics.rformat import format_vec, format_vec as format, format_num, format_pval, print_vector, signif
from rstatistics.rng import RNG, set_seed
from rstatistics.special import beta, choose, gamma, lbeta, lchoose, lgamma

__version__ = "0.1.1"
