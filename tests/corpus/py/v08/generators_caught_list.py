"""int() failing inside a generator that list() runs is caught around list()."""
from typing import Iterator


def parse(xs: list[str]) -> Iterator[int]:
    for x in xs:
        yield int(x)


try:
    print(list(parse(["1", "x"])))
except ValueError:
    print("bad")
