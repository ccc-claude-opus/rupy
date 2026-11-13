# math.fsum: exactly rounded sums, and its errors
import math

print(math.fsum([0.1] * 10), sum([0.1] * 10))
print(math.fsum([1e-16, 1.0, 1e16]))
print(math.fsum([1e100, 1.0, -1e100, 1e-100, 1e50, -1.0, -1e50]))
print(math.fsum([1, 2, 3]), math.fsum(range(10)))
print(math.fsum(x * x for x in [0.1, 0.2, 0.3]))
print(math.fsum([]), math.fsum([-0.0]))
print(math.fsum([math.inf, 1.0]), math.fsum([-math.inf, 2.0, -math.inf]))
print(math.fsum([math.nan, 1.0]))
for bad in [[math.inf, -math.inf], [1e308, 1e308]]:
    try:
        print(math.fsum(bad))
    except ValueError as e:
        print("ValueError:", e)
    except OverflowError as e:
        print("OverflowError:", e)
