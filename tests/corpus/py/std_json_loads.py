# json.loads into the declared type, and its errors
import json
from typing import Optional


def scores(s: str) -> dict[str, list[float]]:
    return json.loads(s)


def main() -> None:
    xs: list[int] = json.loads("[1, 2, 3, -40]")
    print(xs, sum(xs))
    d: dict[str, int] = json.loads('{"b": 2, "a": 1, "b": 3}')
    print(d, list(d.keys()))
    print(scores('{"ann": [9.5, 8.25], "bo": [], "zh\\u4e2d": [1e3, -0.5]}'))
    names: list[str] = json.loads('["x", "\\ud83d\\ude00", "tab\\there", "\\u00e9"]')
    print(names, len(names[1]))
    flags: list[Optional[bool]] = json.loads("[true, false, null]")
    print(flags)
    nested: list[list[dict[str, Optional[str]]]] = json.loads('[[{"k": "v", "n": null}], []]')
    print(nested)
    one: float = json.loads(" 2.5e-3 ")
    t: str = json.loads('"plain"')
    big: int = json.loads("9007199254740993")
    print(one, t, big)
    inf: list[float] = json.loads("[Infinity, -Infinity, NaN, 1.0]")
    print(inf)
    print(json.dumps(scores('{"a": [0.1, 2.0]}')))
    for bad in ["", "[1,", '{"a" 1}', "[1] x", '"abc', "{'a': 1}", "[01]", "nul"]:
        try:
            ys: list[int] = json.loads(bad)
            print("parsed", ys)
        except ValueError as e:
            print("ValueError:", e)


main()
