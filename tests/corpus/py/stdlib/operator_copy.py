import copy
import operator
from functools import reduce
from operator import attrgetter, itemgetter, methodcaller
from dataclasses import dataclass


@dataclass
class P:
    name: str
    age: int


rows = [("b", 3, 2.5), ("a", 1, 9.0), ("c", 2, 0.5)]
print(sorted(rows, key=itemgetter(1)), sorted(rows, key=operator.itemgetter(2), reverse=True))
print(sorted(rows, key=itemgetter(0, 2)), max(rows, key=itemgetter(2)))
people = [P("ann", 31), P("bob", 25), P("cy", 40)]
print([p.name for p in sorted(people, key=attrgetter("age"))], min(people, key=operator.attrgetter("name")))
words = ["Banana", "apple", "Cherry"]
print(sorted(words, key=methodcaller("lower")), sorted(words, key=methodcaller("count", "a")))
print(operator.add(2, 3), operator.mul(2.5, 4), operator.sub(10, 4), operator.truediv(7, 2), operator.floordiv(7, 2), operator.mod(-7, 3), operator.pow(2, 10))
print(operator.neg(5), operator.not_(True), operator.abs(-3.5), operator.eq(1, 1), operator.lt("a", "b"), operator.contains([1, 2], 2), operator.getitem("hello", 1), operator.concat([1], [2]))
print(reduce(operator.mul, [1, 2, 3, 4, 5]), reduce(operator.add, ["a", "b", "c"]), reduce(operator.or_, [1, 2, 4]))
grid = [[1, 2], [3, 4]]
shallow = copy.copy(grid)
deep = copy.deepcopy(grid)
deep[0].append(99)
print(grid, deep, shallow == grid, copy.copy("text"), copy.copy({"a": 1}), copy.deepcopy([P("x", 1)]))
