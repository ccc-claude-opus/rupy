"""random: CPython's numbers for a seed, on every backend (wasm: the Mersenne Twister in the host)."""
import random

random.seed(42)
print(random.random(), random.random())
print([random.randint(1, 6) for _ in range(10)])
print(random.randrange(10), random.randrange(5, 50, 5), random.randrange(10, 0, -3))
print(random.uniform(1.0, 2.0))
xs = list(range(20))
random.shuffle(xs)
print(xs)
print(random.choice(["a", "b", "c", "d"]), random.choice([1.5, 2.5]))
print(random.sample(range(100), 10))
print(random.sample(["x", "y", "z", "w"], 2))
print(random.sample(list(range(1000)), 30))
random.seed(-7)
print(random.random())
random.seed(2 ** 40 + 3)
print(random.randint(0, 2 ** 40))
words = ["apple", "pear"]
random.shuffle(words)
print(words)
try:
    random.choice([])
except IndexError as e:
    print("IndexError", e)
try:
    random.sample([1, 2], 3)
except ValueError as e:
    print("ValueError", e)
try:
    random.randrange(5, 5)
except ValueError as e:
    print("ValueError", e)
