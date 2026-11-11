"""Callable fields, call results and dict entries called directly; closures returning closures."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Button:
    label: str
    on_click: Callable[[str], str]


class Counter:
    def __init__(self, step: int) -> None:
        self.step = step
        self.f: Callable[[int], int] = lambda x: x * 2

    def bump(self, n: int) -> int:
        g: Callable[[int], int] = lambda x: x + self.step
        return g(n) + self.f(n)


def pick(name: str) -> Callable[[float, float], float]:
    ops: dict[str, Callable[[float, float], float]] = {"add": lambda a, b: a + b, "mul": lambda a, b: a * b}
    return ops[name]


def make_adder(n: int) -> Callable[[int], int]:
    return lambda x: x + n


def compose(f: Callable[[int], int], g: Callable[[int], int]) -> Callable[[int], int]:
    return lambda x: g(f(x))


def greet(name: str) -> Callable[[str], str]:
    return lambda greeting: greeting + ", " + name


def main() -> None:
    b = Button("ok", lambda s: s + "!")
    print(b.on_click("hi"), pick("add")(2.0, 3.5), make_adder(5)(1))
    ops: dict[str, Callable[[float, float], float]] = {"sub": lambda a, b: a - b}
    print(ops["sub"](5.0, 1.5))
    h = compose(make_adder(1), make_adder(10))
    print(h(0), compose(h, h)(1))
    print(greet("Ann")("Hello"))
    c = Counter(3)
    print(c.bump(4))
    fs = [make_adder(i) for i in range(3)]
    print([f(10) for f in fs])
    b2 = Button("x", b.on_click)
    print(b2.label, b2.on_click("y"))


if __name__ == "__main__":
    main()
