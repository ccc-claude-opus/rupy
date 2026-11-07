"""rstatistics: the contingency table of R's table()."""
import rstatistics as r

x = ["a", "b", "a", "c"]
y = ["p", "q", "p", "q"]
print(r.table(x, y))
print(r.table(x))
print(r.table(["aa", "bb", "aa"], ["pp", "qq", "pp"], "", ""))
