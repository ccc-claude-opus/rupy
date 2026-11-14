"""math.hypot as CPython computes it (vector_norm), on both backends."""
import math
import random
random.seed(7)
bad = 0
for i in range(500):
    e1 = random.randint(-30, 30)
    x = random.random() * 2.0 ** e1
    y = random.random() * 2.0 ** random.randint(e1 - 30, e1 + 3)
    print(math.hypot(x, y))
for x, y in [(3.0, 4.0), (0.0, 0.0), (-5.0, 12.0), (1e308, 1e308), (5e-324, 5e-324), (1e-310, 3e-310), (float("inf"), float("nan")), (float("nan"), 1.0), (1.0, 1e-300), (2.0**-1022, 2.0**-1022)]:
    print(math.hypot(x, y))
