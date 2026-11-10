// Example programs, seeded into a new workspace (from web/playground.mjs).
export const EXAMPLES = {
  "Hello": `def greet(name: str, times: int = 2) -> str:
    return ", ".join([f"hello {name}"] * times)


print(greet("wasm"))
print([n * n for n in range(10) if n % 2 == 0])
`,
  "Classes": `from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float

    def norm(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5


class Shape:
    def area(self) -> float:
        return 0.0

    def __str__(self) -> str:
        return "Shape"


class Rect(Shape):
    def __init__(self, w: float, h: float) -> None:
        self.w = w
        self.h = h

    def area(self) -> float:
        return self.w * self.h

    def __str__(self) -> str:
        return f"Rect({self.w} x {self.h})"


p = Point(3.0, 4.0)
print(p, p.norm())
shapes: list[Shape] = [Rect(2.0, 3.5), Rect(1.0, 1.0)]
for s in shapes:
    print(s, f"area={s.area():.2f}")
`,
  "Words": `text = """the quick brown fox jumps over the lazy dog
the dog barks and the fox runs"""
counts: dict[str, int] = {}
for w in text.split():
    counts[w] = counts.get(w, 0) + 1
top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
for word, n in top:
    print(f"{word:>6} {'#' * n} {n}")
print(len(counts), "distinct words;", sum(counts.values()), "in all")
`,
  "Exceptions": `def parse(s: str) -> int:
    try:
        return int(s)
    except ValueError as e:
        print("bad input:", e)
        return -1
    finally:
        print("parsed", repr(s))


print(parse("42"), parse("4x2"))
xs = [1, 2, 3]
try:
    print(xs[10])
except IndexError as e:
    print("IndexError:", e)
print(10 // 3, -7 % 3, 2 ** 62, 1 / 3)
`,
  "NumPy": `import numpy as np

a = np.arange(12).reshape((3, 4))
print(a)
print(a.sum(axis=0), a.mean(), a[:, 1:3])
b = np.linspace(0.0, 1.0, 5)
print(b * 2 + 1, np.sqrt(b))
rng = np.random.default_rng(42)
print(rng.random(3))
`,
  "Primes": `def primes(n: int) -> list[int]:
    sieve = [True] * (n + 1)
    sieve[0] = False
    sieve[1] = False
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            for j in range(i * i, n + 1, i):
                sieve[j] = False
    return [i for i, p in enumerate(sieve) if p]


ps = primes(200000)
print(len(ps), ps[:10], ps[-3:])
`,
};
