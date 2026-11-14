"""An exception raised inside a generator reaches the try around its for loop or next(), which then ends the generator."""
from typing import Iterator


class BadRow(ValueError):
    pass


def rows(xs: list[str]) -> Iterator[int]:
    for x in xs:
        if x == "":
            raise BadRow("empty row")
        yield int(x)


def total(xs: list[str]) -> int:
    t = 0
    try:
        for v in rows(xs):
            print("got", v)
            t += v
    except ValueError as e:
        print("stopped:", e)
    return t


print(total(["1", "2", "", "4"]), total(["5", "x"]), total(["7"]))
g = rows(["3", ""])
try:
    print(next(g))
    print(next(g))
except BadRow as e:
    print("BadRow", e)
try:
    print(next(g))
except StopIteration:
    print("finished")
