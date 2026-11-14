"""repr of a float: the shortest digits that read back, and of those the nearest (ties to even)."""
import random

random.seed(5)
print(1770740270910798.25, 19354496021356.562, 2.0**53 + 2.0, 0.30000000000000004)
for i in range(1500):
    x = random.random() * 2.0 ** random.randint(-60, 70)
    print(x, -x / 3.0)
