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
| Distributions (`d`, `p`, `q`) | `norm`, `unif`, `exp`, `gamma`, `chisq`, `beta`, `t`, `f` (`df`, `pf`, `qf`), `lnorm`, `weibull`, `cauchy`, `logis`, `binom`, `pois`, `geom`, `nbinom` (`d`, `p`), `hyper` (`d`, `p`); `lower_tail` and `log_p` as in R |
| Random numbers | `set_seed(seed)` returns a generator with R's numbers: `runif`, `rnorm`, `rexp`, `rlnorm`, `sample`, `sample_from` |
| Descriptive | `mean`, `var`, `sd`, `cov`, `cor` (pearson, spearman, kendall), `median`, `quantile` (types 1–9), `IQR`, `mad`, `fivenum`, `rank`, `scale`, `weighted_mean`, `summary` |
| Tests | `t_test` (one-sample, Welch, pooled, paired), `var_test`, `chisq_test`, `chisq_test_table`, `binom_test`, `prop_test`, `cor_test`; each returns an `HTest` that prints as R's `htest` and has `statistic`, `parameter`, `p_value`, `conf_int`, `estimate` |
| Special functions | `gamma`, `lgamma`, `beta`, `lbeta`, `choose`, `lchoose` |
| Printing | `format` (R's `format` of a numeric vector), `format_num`, `format_pval`, `print_vector`, `signif` |

### Random numbers

R keeps one generator for the session; rstatistics passes it explicitly. After
`set_seed(n)` the numbers are R's after `set.seed(n)` (Mersenne-Twister, normal
numbers by inversion, R ≥ 3.6's rejection sampling):

```python
g = r.set_seed(42)
print(r.print_vector(g.rnorm(5)))
# [1]  1.3709584 -0.5646982  0.3631284  0.6328626  0.4042683
```

## How close to R

`tests/` holds R scripts, their output in R 4.6, and the same programs in Python;
`python tests/run.py` compares them (`--regen` reruns R first). The printed output
of the tests, `format`, `summary`, `quantile` and the random numbers is identical
to R's; distribution functions agree with R to a relative 1e-12. One difference:
R names the data of a test from the call (`data:  c(20, 30, 25, 25)`), rstatistics from
the `data_name` argument (default `x`, `x and y`, ...).

## rupy

rstatistics is written in [rupy](https://github.com/ccc-claude-opus/rupy)'s typed subset
of Python, and rupy has it built in: `rupy run` compiles a program that imports
rstatistics to Rust, `rupy wasm` to WebAssembly, with the same output as CPython.

## License

MIT
