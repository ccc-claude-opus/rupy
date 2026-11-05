"""rstat: imported as a module (`import rstat as r`) and by name; its names do not clash with the program's."""
import rstat as r
from rstat import dnorm as density


def mean(xs: list[int]) -> int:
    return sum(xs)


x = [1.0, 2.0, 4.0]
print(r.mean(x), mean([1, 2]))
print(r.dnorm(0.5), density(1.0, mean=1.0, sd=2.0))
print(r.summary(x))
