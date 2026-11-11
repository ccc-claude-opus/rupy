"""Generators: yields in nested loops and branches, recursion, every kind of item."""
from dataclasses import dataclass
from typing import Iterator


def grid(n: int, m: int) -> Iterator[tuple[int, int]]:
    for i in range(n):
        if i == 1:
            continue
        for j in range(m):
            if (i + j) % 2 == 0:
                yield (i, j)
            else:
                yield (j, -i)


def words(text: str) -> Iterator[str]:
    word = ""
    for ch in text:
        if ch == " ":
            if word:
                yield word
            word = ""
        else:
            word += ch
    if word:
        yield word


def halves(x: float) -> Iterator[float]:
    while x > 0.1:
        x = x / 2
        if x < 0.3:
            break
        yield x
    yield -1.0


@dataclass
class Node:
    value: int
    children: list["Node"]


def walk(n: Node, depth: int) -> Iterator[str]:
    yield "  " * depth + str(n.value)
    for c in n.children:
        yield from walk(c, depth + 1)


def flags(xs: list[int]) -> Iterator[bool]:
    for x in xs:
        yield x > 2


def pairs(d: dict[str, int]) -> Iterator[str]:
    for k, v in d.items():
        try:
            if v < 0:
                raise ValueError(k)
            yield k + "=" + str(v)
        except ValueError as e:
            print("negative", e)


def nodes(n: int) -> Iterator[Node]:
    i = 0
    while True:
        if i >= n:
            return
        yield Node(i, [])
        i += 1


def take(g: Iterator[int], n: int) -> list[int]:
    out: list[int] = []
    for x in g:
        if len(out) == n:
            break
        out.append(x)
    return out


def naturals() -> Iterator[int]:
    n = 0
    while True:
        yield n
        n += 1


def main() -> None:
    print(list(grid(3, 3)))
    print(list(words("the quick  brown fox")))
    print(list(halves(5.0)))
    tree = Node(1, [Node(2, [Node(4, [])]), Node(3, [])])
    for line in walk(tree, 0):
        print(line)
    print(list(flags([1, 3, 2, 5])))
    print(list(pairs({"a": 1, "b": -2, "c": 3})))
    print([n.value for n in nodes(4)])
    print(take(naturals(), 5))
    for i, w in enumerate(words("x y z")):
        print(i, w)
    for a, b in zip(naturals(), words("p q")):
        print(a, b)
    sq = naturals()
    print(next(sq), next(sq), sum(x for x in take(sq, 3)))
    print(max(x for x in [3, 9, 2]), sorted(words("c a b")))
    g = naturals()
    total = 0
    for x in g:
        total += x
        if x == 10:
            break
    print(total, next(g))
    e = words("")
    print(next(e, "empty"))
    print(sum(1 for _ in grid(4, 4)))
    print(",".join(words("join these words")))


main()
