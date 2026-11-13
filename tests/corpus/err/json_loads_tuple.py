# error: json.loads() into tuple[int, int] is not supported
import json

p: tuple[int, int] = json.loads("[1, 2]")
print(p)
