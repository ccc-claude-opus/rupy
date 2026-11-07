import rstatistics as r


def p(xs: list[float]) -> None:
    for x in xs:
        print(format(x, ".12g"))


# the layout of the plots: the ranges of the axes and the positions of the
# ticks, in the coordinates of the device (the device is 7 by 7 inches)
g = r.Graphics(7.0, 7.0)
g.plot([float(i) for i in range(1, 11)], [float(i) for i in range(1, 11)])
p(g.usr)
at1 = g._ticks(1)
at2 = g._ticks(2)
p(at1)
p(at2)
# the ticks in the coordinates of the device (the y axis grows upwards there)
p([g.device_x(v) / 72.0 for v in at1])
p([7.0 - g.device_y(v) / 72.0 for v in at2])
p([g.mar[0] * g.ps * 1.2 / 72.0, g.mar[1] * g.ps * 1.2 / 72.0, g.mar[2] * g.ps * 1.2 / 72.0, g.mar[3] * g.ps * 1.2 / 72.0])
p(g.mar)
