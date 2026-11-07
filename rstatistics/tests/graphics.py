import rstatistics as r
from rstatistics.graphics import boxplot_stats, density_stats, ecdf, hist_stats, ppoints, pretty, qqnorm_coords


def p(xs: list[float]) -> None:
    for x in xs:
        print(format(x, ".12g"))


def q(xs: list[float]) -> None:
    for x in xs:
        print(format(x, ".17g"))


p(pretty([1.0, 10.0]))
p(pretty([0.0, 1.0]))
p(pretty([-3.2, 17.8]))
p(pretty([0.001, 0.009]))
p(pretty([0.0, 100.0], 10))
p(pretty([2.0, 3.0]))

x1 = [1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0]
h1 = hist_stats(x1)
p(h1.breaks)
p(h1.counts)
p(h1.density)
p(h1.mids)
x2 = [1.1, 2.3, 2.7, 3.2, 3.3, 3.9, 4.1, 4.4, 5.0, 5.2, 5.5, 6.0, 7.1, 8.9, 9.0]
h2 = hist_stats(x2)
p(h2.breaks)
p(h2.counts)
p(h2.density)
h3 = hist_stats(x1, "FD")
p(h3.breaks)
p(h3.counts)

d1 = density_stats(x1)
q([d1.bw])
p(d1.x[0:5])
p(d1.y[0:5])
p(d1.y[249:255])
d2 = density_stats(x2, "nrd")
q([d2.bw])
p(d2.x[0:3])
p(d2.y[0:3])
d3 = density_stats(x1, "0.8", 128)
q([d3.bw])
p(d3.x[0:3])
p(d3.y[0:3])

e1 = ecdf(x1)
q(e1.y)

b1 = boxplot_stats(x1)
q(b1.stats)
q(b1.conf)
q([float(b1.n)])
b2 = boxplot_stats(x1 + [20.0])
q(b2.stats)
q(b2.out)
b3 = boxplot_stats([1.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0])
q(b3.stats)
q(b3.out)
q(b3.conf)

q(ppoints(5))
q(ppoints(20))
q(ppoints(3, 0.4))

t1 = qqnorm_coords(x1)
q(t1[0][0:5])
q(t1[1][0:5])
