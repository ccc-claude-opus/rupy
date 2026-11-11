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
  "Plot": `# Graphics in R's style (rstatistics): a printed SVG shows as a picture,
# and g.save() writes a file to the workspace.
import rstatistics as r

x = [1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0]
y = [1.2, 1.4, 2.1, 1.9, 2.3, 1.7, 1.5, 2.2, 2.9, 3.1, 3.4, 3.8]

g = r.Graphics(6.0, 4.5)
g.plot(x, y, main="x versus y", xlab="x", ylab="y")
print(g.svg())

g = r.Graphics(6.0, 4.5)
g.boxplot(x, main="Box plot of x", xlab="x", ylab="")
g.save("boxplot.svg")
print("wrote boxplot.svg")
`,
};

// A notebook: text with TeX, and code cells that use the cells above them.
export const NOTEBOOK = {
  cells: [
    {
      type: "markdown",
      source: `# rupy 筆記本

程式格用 **Shift + Enter** 執行並到下一格，Ctrl/⌘ + Enter 只執行。執行第 $k$ 格時，第 $1..k$ 格會當成一支程式重新編譯執行，所以後面的格子看得到前面定義的變數和函式。

文字格可以寫 TeX，例如 $\\sum_{i=1}^{n} i^2 = \\frac{n(n+1)(2n+1)}{6}$。點兩下編輯。`,
    },
    { type: "code", source: `def squares(n: int) -> list[int]:\n    return [i * i for i in range(1, n + 1)]\n` },
    { type: "code", source: `last_n = 10\nxs = squares(last_n)\nprint(xs)\nprint(sum(xs), last_n * (last_n + 1) * (2 * last_n + 1) // 6)\n` },
    { type: "markdown", source: "## NumPy\n\n$A$ 是 $3 \\times 4$ 的矩陣，$A^\\top A$ 是 $4 \\times 4$。" },
    { type: "code", source: `import numpy as np\n\na = np.arange(12).reshape((3, 4))\nprint(a.T @ a)\n` },
    { type: "markdown", source: "## 圖形\n\n印出 SVG（rstatistics 的 `g.svg()`）就會顯示成圖，也會存在筆記本裡。" },
    {
      type: "code",
      source: `import rstatistics as r\n\nx = [4.2, 5.1, 3.9, 6.3, 5.5, 4.8, 5.0, 6.8, 4.4, 5.9, 5.2, 4.6]\ng = r.Graphics(6.0, 4.0)\ng.hist(x, main="Histogram of x", xlab="x", ylab="Frequency")\nprint(g.svg())\n`,
    },
  ].map((c) => ({ ...c, outputs: [], count: null })),
  metadata: {},
};
