"""rstatistics: the plots of the graphics device (the SVG must be the same everywhere)."""
import rstatistics as r

x = [1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2, 2.9, 3.1, 3.4, 3.8]

g = r.Graphics(7.0, 7.0)
g.hist(x, main="Histogram of x", xlab="x", ylab="Frequency")
print(g.svg())

g = r.Graphics(7.0, 7.0)
g.density(x, main="Density of x", xlab="x", ylab="Density")
print(g.svg())

g = r.Graphics(7.0, 7.0)
g.boxplot(x, main="Box plot of x", xlab="x", ylab="")
print(g.svg())

g = r.Graphics(7.0, 7.0)
g.qqnorm(x, main="Normal Q-Q Plot", xlab="Theoretical Quantiles", ylab="Sample Quantiles")
print(g.svg())

g = r.Graphics(7.0, 7.0)
g.plot(x, y, main="x versus y", xlab="x", ylab="y")
print(g.svg())
