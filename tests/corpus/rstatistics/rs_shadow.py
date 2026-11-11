"""rstatistics: the program's module-level names (`n`, `size`) do not leak into the package, whose functions assign locals of the same names."""
import rstatistics as r

n = 10
size = 10

print(r.mean([1.0, 2.0]), n, size)
rng = r.set_seed(42)
print(" ".join(f"{x:.15g}" for x in rng.runif(3)), rng.sample(10, 3))
g = r.Graphics(7.0, 7.0)
g.plot([1.0, 2.0, 3.0], [2.0, 1.0, 3.0], main="t", xlab="x", ylab="y")
print(len(g.svg()) > 0)
