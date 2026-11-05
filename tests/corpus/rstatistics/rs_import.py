"""rstatistics: imported as a module (`import rstatistics as r`) and by name; its names do not clash with the program's."""
import rstatistics as r
from rstatistics import dnorm as density


def mean(xs: list[int]) -> int:
    return sum(xs)


x = [1.0, 2.0, 4.0]
print(r.mean(x), mean([1, 2]))
print(r.dnorm(0.5), density(1.0, mean=1.0, sd=2.0))
print(r.summary(x))
