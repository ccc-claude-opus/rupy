"""Functions as values: closures over locals, functions in lists and dicts, callbacks."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Button:
    label: str
    on_click: Callable[[str], str]


def make_adder(n: int) -> Callable[[int], int]:
    return lambda x: x + n


def shout(s: str) -> str:
    return s.upper() + "!"


def whisper(s: str) -> str:
    return s.lower() + "..."


def apply_all(fs: list[Callable[[int], int]], x: int) -> list[int]:
    return [f(x) for f in fs]


def pick(name: str) -> Callable[[float, float], float]:
    ops: dict[str, Callable[[float, float], float]] = {"add": lambda a, b: a + b, "mul": lambda a, b: a * b}
    return ops[name]


def main() -> None:
    add3 = make_adder(3)
    add10 = make_adder(10)
    print(add3(1), add10(1), apply_all([add3, add10, lambda v: v * v], 4))
    buttons = [Button("ok", shout), Button("cancel", whisper)]
    for b in buttons:
        click = b.on_click
        print(b.label, click(b.label))
    add = pick("add")
    mul = pick("mul")
    print(add(2.0, 3.5), mul(2.0, 3.5))
    fs: list[Callable[[str], str]] = [shout, whisper, lambda s: s.strip()]
    print([f("  Hi ") for f in fs])
    prefix = ">> "
    show: Callable[[int], str] = lambda n: prefix + str(n)
    print(show(5))


main()
