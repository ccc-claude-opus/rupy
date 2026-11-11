"""Generators: yield in except, finally and else of try, one item at a time."""
from typing import Iterator


def parse(xs: list[str]) -> Iterator[int]:
    for x in xs:
        try:
            v = int(x)
        except ValueError as e:
            print("  bad", x, e)
            yield -1
            yield -2
        else:
            yield v
        finally:
            print("  checked", x)
            yield 0


def nested(n: int) -> Iterator[str]:
    try:
        for i in range(n):
            try:
                if i % 2:
                    raise KeyError(i)
                yield "even " + str(i)
            except KeyError as k:
                yield "odd " + str(k)
    finally:
        yield "end"


for v in parse(["1", "x", "3"]):
    print("got", v)
print(list(nested(3)))
