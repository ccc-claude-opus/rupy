p <- function(x) cat(sprintf("%.12g\n", x), sep = "")
q <- function(x) cat(sprintf("%.17g\n", x), sep = "")

# the pretty ticks
p(pretty(c(1, 10)))
p(pretty(c(0, 1)))
p(pretty(c(-3.2, 17.8)))
p(pretty(c(0.001, 0.009)))
p(pretty(c(0, 100), n = 10))
p(pretty(c(2, 3)))

# the histogram
x1 <- c(1, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9)
h1 <- hist(x1, plot = FALSE)
p(h1$breaks)
p(h1$counts)
p(h1$density)
p(h1$mids)
x2 <- c(1.1, 2.3, 2.7, 3.2, 3.3, 3.9, 4.1, 4.4, 5.0, 5.2, 5.5, 6.0, 7.1, 8.9, 9.0)
h2 <- hist(x2, plot = FALSE)
p(h2$breaks)
p(h2$counts)
p(h2$density)
h3 <- hist(x1, breaks = "FD", plot = FALSE)
p(h3$breaks)
p(h3$counts)

# the density
d1 <- density(x1)
q(d1$bw)
p(d1$x[1:5])
p(d1$y[1:5])
p(d1$y[250:255])
d2 <- density(x2, bw = "nrd")
q(d2$bw)
p(d2$x[1:3])
p(d2$y[1:3])
d3 <- density(x1, bw = 0.8, n = 128)
q(d3$bw)
p(d3$x[1:3])
p(d3$y[1:3])

# the empirical distribution
e1 <- ecdf(x1)
q(e1(x1))

# the box plot
b1 <- boxplot(x1, plot = FALSE)
q(b1$stats)
q(b1$conf)
q(b1$n)
b2 <- boxplot(c(x1, 20), plot = FALSE)
q(b2$stats)
q(b2$out)
b3 <- boxplot(c(1, 1, 2, 3, 5, 8, 13, 21), plot = FALSE)
q(b3$stats)
q(b3$out)
q(b3$conf)

# the probability points
q(ppoints(5))
q(ppoints(20))
q(ppoints(3, a = 0.4))

# the normal quantile plot
t1 <- qqnorm(x1, plot = FALSE)
q(t1$x[1:5])
q(t1$y[1:5])
