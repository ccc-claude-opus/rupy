import rstatistics as r

x = ["a", "b", "a", "c"]
y = ["p", "q", "p", "q"]
print(r.table(x, y))
print(r.table(x))
print(r.table(["aa", "bb", "aa"], ["pp", "qq", "pp"], "", ""))
print(r.table(["a", "b", "c", "d"], ["x", "y", "z", "w"], "", ""))
print(r.table(["aa", "b", "cc", "dddd"], None, "", ""))
