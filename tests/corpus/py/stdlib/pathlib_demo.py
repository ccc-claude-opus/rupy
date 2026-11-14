from pathlib import Path

for s in ["foo.", ".bashrc", "a.tar.gz", "a/b/", "//x/y", "///x", "", ".", "a/./b/../c", "/", "/usr/lib/python3.14/os.py"]:
    p = Path(s)
    print(repr(s), repr(p), str(p), repr(p.name), repr(p.suffix), repr(p.stem), p.suffixes, str(p.parent), p.root, p.is_absolute())
p = Path("/usr") / "lib" / "x.txt"
print(p, Path("a", "b", "c.py"), Path("a", "/b", "c"), "top" / Path("x"), Path("a") / Path("/abs"), p.joinpath("y", "z"))
print([str(q) for q in p.parents], p.parents[0], p.with_name("y.md"), p.with_suffix(".csv"), p.with_suffix(""), p.with_stem("w"))
print(p.relative_to("/usr"), Path("/a/b/c").relative_to(Path("/a")), Path("/a/b").relative_to("/a/x", walk_up=True), p.is_relative_to("/usr/lib"), p.is_relative_to("/etc"))
print(Path("a/b.py").match("*.py"), Path("/a/b/c.py").match("b/*.py"), Path("/a/b/c.py").match("/*.py"), Path("x.txt").match("[a-x].t?t"), Path("data1.csv").match("data[!0-9].csv"))
print(Path("a") == Path("a/"), Path("a") != Path("b"), sorted([Path("b"), Path("a/c"), Path("a")]), Path("/a") < Path("a"))

