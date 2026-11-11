"""itertools in CPython's order (wasm: built in the module)."""
import itertools
from itertools import combinations, permutations, product

print(list(itertools.chain([1, 2], [3], [])))
print(list(itertools.chain("ab", "cd")))
print(list(itertools.accumulate([1, 2, 3, 4])))
print(list(itertools.accumulate([0.5, 0.25, 2.0])))
print(list(itertools.pairwise([1, 2, 3, 4])))
print(list(itertools.pairwise("abc")))
print(list(product([1, 2], ["a", "b"])))
print(list(product([1, 2], [True, False], [0.5])))
print(list(product("ab", repeat=3)))
print(list(permutations([1, 2, 3])))
print(list(permutations("abcd", 2)))
print(list(permutations([1, 2], 3)))
print(list(combinations([1, 2, 3, 4], 2)))
print(list(combinations("abcde", 3)))
print(sum(1 for _ in combinations(range(10), 4)))
for a, b in product(range(2), range(2)):
    print(a, b, end="; ")
print()
best = max(permutations([3, 1, 2]), key=lambda p: p[0] * 10 + p[1])
print(best)
