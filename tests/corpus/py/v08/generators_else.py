"""Generators: yield in the else of a for and a while loop."""
from typing import Iterator


def g(xs: list[int]) -> Iterator[int]:
    for x in xs:
        if x < 0:
            break
        yield x
    else:
        yield 99
        yield 100
    n = 3
    while n > 0:
        yield -n
        n -= 1
    else:
        yield 7


print(list(g([1, 2])), list(g([1, -1, 2])))
