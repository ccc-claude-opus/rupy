p <- function(x) cat(sprintf("%.15g", x), "\n")
set.seed(42); p(runif(5)); p(rnorm(5)); p(rexp(5)); p(sample(10, 5)); p(sample(100, 8, replace=TRUE))
set.seed(2026); p(rnorm(3, 10, 2)); p(sample(c(3.5, 1.25, 7, 9.5), 4)); p(runif(2, -1, 1))
set.seed(-7); p(rnorm(4)); p(rexp(3, 2))
