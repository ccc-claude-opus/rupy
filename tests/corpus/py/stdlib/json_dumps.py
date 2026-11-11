"""json.dumps: CPython's separators, ensure_ascii, Infinity, int keys."""
import json

print(json.dumps({"a": "é\n\"x\"", "b": "z"}), json.dumps(True))
print(json.dumps([(1, "x"), (2, "😀")]))
print(json.dumps({1: 0.1, 2: float("inf")}), json.dumps(-0.0))
xs: list[int | None] = [1, None]
print(json.dumps(xs), json.dumps("tab\there"), json.dumps(1e100))
