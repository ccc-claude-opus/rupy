# the plots of R and of rstatistics, to compare them side by side
x <- c(1, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9)
set.seed(42)
y <- c(1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2, 2.9, 3.1, 3.4, 3.8)

svg("tests/plots/hist_R.svg", width = 7, height = 7)
hist(x, main = "Histogram of x", xlab = "x", ylab = "Frequency")
invisible(dev.off())

svg("tests/plots/density_R.svg", width = 7, height = 7)
plot(density(x), main = "Density of x", xlab = "x", ylab = "Density")
invisible(dev.off())

svg("tests/plots/boxplot_R.svg", width = 7, height = 7)
boxplot(x, main = "Box plot of x", xlab = "x", ylab = "")
invisible(dev.off())

svg("tests/plots/qqnorm_R.svg", width = 7, height = 7)
qqnorm(x, main = "Normal Q-Q Plot", xlab = "Theoretical Quantiles", ylab = "Sample Quantiles")
invisible(dev.off())

svg("tests/plots/scatter_R.svg", width = 7, height = 7)
plot(x, y, main = "x versus y", xlab = "x", ylab = "y")
invisible(dev.off())
