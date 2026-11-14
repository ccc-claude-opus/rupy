"""An int in a float place is fine while it is not shown as text, or once a float or / meets it."""


def scale(x: float, k: float) -> float:
    return x * k


total: float = 0
for v in [0.5, 1.25]:
    total += v
area = scale(3, 2.5)
ratio = scale(4, 2) / 3
xs: list[float] = [1, 2, 3]
print(area, ratio, sum(xs) / len(xs), f"{scale(2, 3):.2f}", float(7), max(xs) > 2.5)
