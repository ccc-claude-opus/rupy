# the layout of the plots: the ranges of the axes and the positions of the
# ticks, in the coordinates of the device (R's svg() is 7 by 7 inches)
p <- function(x) cat(sprintf("%.12g\n", x), sep = "")

svg("/tmp/rstatistics-plots-layout.svg", width = 7, height = 7)
plot(1:10)
usr <- par("usr")
mai <- par("mai")
p(usr)
p(axTicks(1))
p(axTicks(2))
# the ticks in the coordinates of the device (the y axis grows upwards there)
x0 <- mai[2]
x1 <- 7 - mai[4]
y0 <- mai[1]
y1 <- 7 - mai[3]
p(x0 + (axTicks(1) - usr[1]) / (usr[2] - usr[1]) * (x1 - x0))
p(y0 + (axTicks(2) - usr[3]) / (usr[4] - usr[3]) * (y1 - y0))
p(mai)
p(par("mar"))
invisible(dev.off())
