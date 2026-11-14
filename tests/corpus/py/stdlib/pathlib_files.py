# wasm: skip (directories: the wasm host has files only, no os.listdir / os.makedirs)
import os
from pathlib import Path

d = Path("rupy_pathlib_demo_" + str(os.getpid()))
d.mkdir()
(d / "sub").mkdir(parents=True, exist_ok=True)
f = d / "notes.txt"
print(f.write_text("one\ntwo\n"), f.exists(), f.is_file(), f.is_dir(), d.is_dir(), repr(f.read_text()))
with f.open("a") as h:
    h.write("three\n")
with f.open() as h:
    print([line.strip() for line in h])
(d / "b.csv").write_text("x")
(d / "a.csv").write_text("y")
print(sorted([q.name for q in d.iterdir()]), sorted([q.name for q in d.glob("*.csv")]), [str(q.relative_to(d)) for q in d.glob("*/")])
g = f.rename(d / "renamed.txt")
print(g.name, f.exists(), g.exists())
for k in range(5):
    try:
        if k == 0:
            d.mkdir()
        elif k == 1:
            Path(str(d) + "/x/y").mkdir()
        elif k == 2:
            Path("a").with_suffix("txt")
        elif k == 3:
            Path("/a/b").relative_to("/c")
        else:
            Path("").with_name("x")
    except FileExistsError as e:
        print("FileExistsError", str(e).replace(str(d), "D"))
    except FileNotFoundError as e:
        print("FileNotFoundError", str(e).replace(str(d), "D"))
    except ValueError as e:
        print("ValueError", e)
for q in d.glob("*.*"):
    q.unlink()
(d / "missing").unlink(missing_ok=True)
(d / "sub").rmdir()
d.rmdir()
print(d.exists(), Path.cwd().is_absolute(), Path("x").absolute().is_absolute(), Path.home().is_absolute())
