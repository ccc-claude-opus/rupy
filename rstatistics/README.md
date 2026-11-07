# rstatistics

R's probability and statistics functions in pure Python, with R's numbers and R's
printed output. There are no dependencies: vectors are plain `list[float]`.

```
pip install rstatistics
```

```python
import rstatistics as r

x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
print(r.t_test(x, mu=5.0))
print(r.summary(x))
```

```
	One Sample t-test

data:  x
t = 3.5696, df = 7, p-value = 0.009101
alternative hypothesis: true mean is not equal to 5
95 percent confidence interval:
 5.206762 6.018238
sample estimates:
mean of x 
   5.6125 

   Min. 1st Qu.  Median    Mean 3rd Qu.    Max. 
  4.900   5.250   5.650   5.612   6.025   6.200 
```

That is what R prints for `t.test(x, mu = 5)` and `summary(x)`.

## Names

R's names, with `_` for `.`: `t.test` is `t_test`, `lower.tail` is `lower_tail`,
`var.equal` is `var_equal`. R's `range`, `round` and `signif` of vectors are
`range_`, `round_` and `signif_`.

## What there is

| Area | Functions |
| --- | --- |
| Distributions (`d`, `p`, `q`) | `norm`, `unif`, `exp`, `gamma`, `chisq`, `beta`, `t`, `f` (`df`, `pf`, `qf`), `lnorm`, `weibull`, `cauchy`, `logis`, `binom`, `pois`, `geom`, `nbinom`, `hyper`; `lower_tail` and `log_p` as in R; `dnbinom_mu` for the negative binomial with a mean |
| Random numbers | `set_seed(seed)` returns a generator with R's numbers: `runif`, `rnorm`, `rexp`, `rlnorm`, `rgamma`, `rbeta`, `rt`, `rf`, `rchisq`, `rcauchy`, `rlogis`, `rweibull`, `rbinom`, `rpois`, `rgeom`, `rnbinom`, `rhyper`, `sample`, `sample_from` |
| Descriptive | `mean`, `var`, `sd`, `cov`, `cor` (pearson, spearman, kendall), `median`, `quantile` (types 1–9), `IQR`, `mad`, `fivenum`, `rank`, `scale`, `weighted_mean`, `summary` |
| Tests | `t_test` (one-sample, Welch, pooled, paired), `var_test`, `chisq_test`, `chisq_test_table`, `binom_test`, `prop_test`, `cor_test`, `wilcox_test` (rank sum and signed rank), `ks_test` (Kolmogorov-Smirnov), `shapiro_test`, `fisher_test`, `kruskal_test`; each returns an `HTest` that prints as R's `htest` and has `statistic`, `parameter`, `p_value`, `conf_int`, `estimate` |
| Multiple testing | `p_adjust` (holm, hochberg, hommel, bonferroni, BH, BY, none) |
| Linear models | `lm` (the Householder QR of R's `lm.fit`), `anova` (of a model), `aov` (one-way), `predict` (with the confidence and prediction intervals); the summary of a model prints as `summary(lm(...))` does |
| Tables | `table` (the contingency table of two vectors, printed as R prints it) |
| Graphics | `graphics()` opens a device that writes SVG with R's layout: `plot`, `hist`, `density`, `boxplot`, `qqnorm`, `qqline`, `ecdf`, `curve`, `barplot`, and the primitives (`points`, `lines`, `segments`, `rect`, `polygon`, `text`, `axis`, `box`, `title`, `mtext`, `abline`, `legend`); the numbers of the plots come from `pretty`, `hist_stats`, `density_stats`, `ecdf`, `boxplot_stats` and `ppoints` |
| Special functions | `gamma`, `lgamma`, `beta`, `lbeta`, `choose`, `lchoose` |
| Printing | `format` (R's `format` of a numeric vector), `format_num`, `format_pval`, `print_vector`, `signif` |

### Random numbers

R keeps one generator for the session; rstatistics passes it explicitly. After
`set_seed(n)` the numbers are R's after `set.seed(n)` (Mersenne-Twister, normal
numbers by inversion, R ≥ 3.6's rejection sampling), and the other generators are R's
own (Ahrens and Dieter's gamma and exponential, Cheng's beta, the BTPE binomial, the
normal rejection Poisson, Kachitvichyanukul and Schmeiser's hypergeometric), to the
last bit:

```python
g = r.set_seed(42)
print(r.print_vector(g.rnorm(5)))
# [1]  1.3709584 -0.5646982  0.3631284  0.6328626  0.4042683
```

### Linear models

`lm(y, X)` fits `y` on the columns of `X` (one column per predictor) with the
Householder QR of R's `lm.fit`, so the coefficients, the standard errors and the
rank of a rank deficient fit are R's:

```python
x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2]
m = r.lm(y, [x], ["x"])
print(m.summary())
```

```
Call:
lm(formula = y ~ x)

Residuals:
     Min       1Q   Median       3Q      Max 
-0.18923 -0.06950 -0.01664  0.06679  0.21137 

Coefficients:
            Estimate Std. Error t value Pr(>|t|)    
(Intercept)  -2.5740     0.6531  -3.941 0.007615 ** 
x             0.7771     0.1160   6.700 0.000537 ***
---
Signif. codes:  0 ‘***’ 0.001 ‘**’ 0.01 ‘*’ 0.05 ‘.’ 0.1 ‘ ’ 1

Residual standard error: 0.1489 on 6 degrees of freedom
Multiple R-squared:  0.8821,	Adjusted R-squared:  0.8624 
F-statistic: 44.89 on 1 and 6 DF,  p-value: 0.0005366
```

### Plots

```python
g = r.graphics(width=7, height=7)
g.hist(x, main="Histogram of x", xlab="x", ylab="Frequency")
g.save("hist.svg")
```

The device writes SVG: the margins are the lines of R's `mar`, the ticks
and their labels stand `mgp[2]` lines from the axes, the ranges of the
axes are extended by 4% at both ends (as R does) and the ticks come from
`pretty()`.  `tests/plots/` holds the plots of R and of rstatistics side
by side, and `tests/plots.py` compares the ranges of the axes and the
positions of the ticks with R's `svg()`.

## How close to R

`tests/` holds R scripts, their output in R 4.6, and the same programs in Python;
`python tests/run.py` compares them (`--regen` reruns R first). The printed output
of the tests, `format`, `summary`, `quantile`, `table`, the linear models and the
random numbers is identical to R's; the distribution functions and the nonparametric tests agree with
R to a relative 1e-12 (the quantiles are R's, except where p is exactly a value of
the distribution function, where the two incomplete betas differ by an ulp). One difference:
R names the data of a test from the call (`data:  c(20, 30, 25, 25)`), rstatistics from
the `data_name` argument (default `x`, `x and y`, ...).

## rupy

rstatistics is written in [rupy](https://github.com/ccc-claude-opus/rupy)'s typed subset
of Python, and rupy has it built in: `rupy run` compiles a program that imports
rstatistics to Rust, `rupy wasm` to WebAssembly, with the same output as CPython.

## License

MIT
