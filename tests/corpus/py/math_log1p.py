"""math.log1p and math.expm1, accurate near zero, and their errors."""
import math

for x in [1e-10, 0.5, -0.5, 3.0]:
    print(math.log1p(x), math.expm1(x))
print(math.isnan(math.nan))
try:
    math.log1p(-1.0)
except ValueError as e:
    print(e)
try:
    math.expm1(1000.0)
except OverflowError as e:
    print(e)
