"""re: groups, spans, sub, split, finditer, flags (wasm: the regex crate in rupy_lib.wasm)."""
import re

text = "2024-01-15 and 2023-12-31, café 42"
print(re.findall(r"\d+", text))
print(re.findall(r"(\d{4})-(\d{2})-(\d{2})", text))
m = re.search(r"(?P<year>\d{4})-(\d{2})", text)
if m is not None:
    print(m.group(), m.group(1), m.group("year"), m.start(), m.end(), m.span(2), m.groups())
print(re.match(r"\d+", text) is not None, re.match(r"[a-z]+", text) is None)
print(re.fullmatch(r"\w+", "café") is not None)
print(re.sub(r"(\d+)-(\d+)", r"\2/\1", text))
print(re.sub(r"\s+", " ", "a   b \t c", count=1))
print(re.split(r"[,\s]+", "a, b  c,d"))
p = re.compile(r"(\w+)@(\w+)\.com", re.IGNORECASE)
for mm in p.finditer("Ann@X.com bob@y.COM"):
    print(mm.group(1), mm.group(2), mm.span())
print(p.findall("Ann@X.com bob@y.COM"))
s2 = p.search("contact: Zed@Q.com")
print(s2.group(0) if s2 is not None else "none")
print(re.escape("a.b*c (d)"))
words = [w for w in re.findall(r"[A-Za-zé]+", text) if len(w) > 2]
print(words)
