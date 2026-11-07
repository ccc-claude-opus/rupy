# the plots of rstatistics, to compare them with R's
import rstatistics as r

x = [1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2, 2.9, 3.1, 3.4, 3.8]

g = r.Graphics(7.0, 7.0)
g.hist(x, main="Histogram of x", xlab="x", ylab="Frequency")
g.save("tests/plots/hist_rstatistics.svg")

g = r.Graphics(7.0, 7.0)
g.density(x, main="Density of x", xlab="x", ylab="Density")
g.save("tests/plots/density_rstatistics.svg")

g = r.Graphics(7.0, 7.0)
g.boxplot(x, main="Box plot of x", xlab="x", ylab="")
g.save("tests/plots/boxplot_rstatistics.svg")

g = r.Graphics(7.0, 7.0)
g.qqnorm(x, main="Normal Q-Q Plot", xlab="Theoretical Quantiles", ylab="Sample Quantiles")
g.save("tests/plots/qqnorm_rstatistics.svg")

g = r.Graphics(7.0, 7.0)
g.plot(x, y, main="x versus y", xlab="x", ylab="y")
g.save("tests/plots/scatter_rstatistics.svg")
