"""rupy's `pathlib`: CPython's `Path` on POSIX (a `PosixPath`), written in rupy.

`Path(...)` takes strings; `/` joins strings and paths. `parents`, `iterdir()`
and `glob()` are lists (CPython: a sequence and generators); `parts` is not
provided (a tuple of any length)."""

import os
from typing import TextIO


def _parse(s: str) -> tuple[str, list[str]]:
    """posixpath's root ("", "/" or "//") and the parts without "" and "."."""
    root = ""
    if s.startswith("/"):
        root = "//" if s.startswith("//") and not s.startswith("///") else "/"
    tail = [x for x in s.split("/") if x != "" and x != "."]
    return root, tail


class Path:
    def __init__(self, *args: str) -> None:
        root = ""
        tail: list[str] = []
        for a in args:
            r, t = _parse(a)
            if r != "":
                root = r
                tail = t
            else:
                tail = tail + t
        self._root: str = root
        self._tail: list[str] = tail

    @staticmethod
    def cwd() -> Path:
        return Path(os.getcwd())

    @staticmethod
    def home() -> Path:
        return Path(os.path.expanduser("~"))

    def _with(self, root: str, tail: list[str]) -> Path:
        p = Path()
        p._root = root
        p._tail = tail
        return p

    def __str__(self) -> str:
        if self._root == "" and len(self._tail) == 0:
            return "."
        return self._root + "/".join(self._tail)

    def as_posix(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return "PosixPath(" + repr(str(self)) + ")"

    def __truediv__(self, other: str | Path) -> Path:
        if isinstance(other, str):
            return self.joinpath(other)
        else:
            if other._root != "":
                return self._with(other._root, list(other._tail))
            return self._with(self._root, self._tail + other._tail)

    def __rtruediv__(self, other: str) -> Path:
        return Path(other).joinpath(str(self))

    def joinpath(self, *others: str) -> Path:
        root = self._root
        tail = list(self._tail)
        for a in others:
            r, t = _parse(a)
            if r != "":
                root = r
                tail = t
            else:
                tail = tail + t
        return self._with(root, tail)

    @property
    def root(self) -> str:
        return self._root

    @property
    def anchor(self) -> str:
        return self._root

    @property
    def name(self) -> str:
        if len(self._tail) == 0:
            return ""
        return self._tail[-1]

    @property
    def stem(self) -> str:
        name = self.name
        i = name.rfind(".")
        if i != -1:
            stem = name[:i]
            if stem.lstrip(".") != "":
                return stem
        return name

    @property
    def suffix(self) -> str:
        name = self.name.lstrip(".")
        i = name.rfind(".")
        if i != -1:
            return name[i:]
        return ""

    @property
    def suffixes(self) -> list[str]:
        return ["." + ext for ext in self.name.lstrip(".").split(".")[1:]]

    @property
    def parent(self) -> Path:
        if len(self._tail) == 0:
            return self._with(self._root, [])
        return self._with(self._root, self._tail[:-1])

    @property
    def parents(self) -> list[Path]:
        return [self._with(self._root, self._tail[:k]) for k in range(len(self._tail) - 1, -1, -1)]

    def with_name(self, name: str) -> Path:
        if name == "" or "/" in name or name == ".":
            raise ValueError("Invalid name " + repr(name))
        if len(self._tail) == 0:
            raise ValueError(repr(self) + " has an empty name")
        return self._with(self._root, self._tail[:-1] + [name])

    def with_stem(self, stem: str) -> Path:
        suffix = self.suffix
        if suffix == "":
            return self.with_name(stem)
        if stem == "":
            raise ValueError(repr(self) + " has a non-empty suffix")
        return self.with_name(stem + suffix)

    def with_suffix(self, suffix: str) -> Path:
        stem = self.stem
        if stem == "":
            raise ValueError(repr(self) + " has an empty name")
        if suffix != "" and not suffix.startswith("."):
            raise ValueError("Invalid suffix " + repr(suffix))
        return self.with_name(stem + suffix)

    def is_absolute(self) -> bool:
        return self._root != ""

    def _key(self) -> list[str]:
        return str(self).split("/")

    def __eq__(self, other: Path) -> bool:
        return str(self) == str(other)

    def __ne__(self, other: Path) -> bool:
        return str(self) != str(other)

    def __lt__(self, other: Path) -> bool:
        return self._key() < other._key()

    def __le__(self, other: Path) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: Path) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: Path) -> bool:
        return self._key() >= other._key()

    def _inside(self, other: Path) -> bool:
        """Is other self or one of its parents?"""
        return other._root == self._root and len(other._tail) <= len(self._tail) and self._tail[: len(other._tail)] == other._tail

    def is_relative_to(self, other: str | Path) -> bool:
        if isinstance(other, str):
            return self._inside(Path(other))
        else:
            return self._inside(other)

    def relative_to(self, other: str | Path, walk_up: bool = False) -> Path:
        o = Path()
        if isinstance(other, str):
            o = Path(other)
        else:
            o = other
        if self._inside(o):
            return self._with("", self._tail[len(o._tail) :])
        if not walk_up:
            raise ValueError(repr(str(self)) + " is not in the subpath of " + repr(str(o)))
        if o._root != self._root:
            raise ValueError(repr(str(self)) + " and " + repr(str(o)) + " have different anchors")
        step = 0
        base = o
        while not self._inside(base):
            if base.name == "..":
                raise ValueError("'..' segment in " + repr(str(o)) + " cannot be walked")
            base = base.parent
            step += 1
        return self._with("", [".."] * step + self._tail[len(base._tail) :])

    def match(self, pattern: str) -> bool:
        proot, pparts = _parse(pattern)
        if len(pparts) == 0 and proot == "":
            raise ValueError("empty pattern")
        mine = self._tail
        if len(mine) < len(pparts):
            return False
        if proot != "" and (len(mine) > len(pparts) or self._root != proot):
            return False
        for k in range(1, len(pparts) + 1):
            if not _fnmatch(mine[-k], pparts[-k]):
                return False
        return True

    # ------------------------------------------------------------ the files

    def exists(self) -> bool:
        return os.path.exists(str(self))

    def is_dir(self) -> bool:
        return os.path.isdir(str(self))

    def is_file(self) -> bool:
        return os.path.isfile(str(self))

    def open(self, mode: str = "r") -> TextIO:
        if mode == "r":
            return open(str(self))
        if mode == "w":
            return open(str(self), "w")
        if mode == "a":
            return open(str(self), "a")
        raise ValueError("rupy's Path.open: mode " + repr(mode) + " is not supported (r, w, a)")

    def read_text(self) -> str:
        text = ""
        with open(str(self)) as f:
            text = f.read()
        return text

    def write_text(self, data: str) -> int:
        n = 0
        with open(str(self), "w") as f:
            n = f.write(data)
        return n

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        s = str(self)
        if os.path.exists(s):
            if exist_ok and os.path.isdir(s):
                return
            raise FileExistsError("[Errno 17] File exists: " + repr(s))
        if not parents and not os.path.isdir(str(self.parent)):
            raise FileNotFoundError("[Errno 2] No such file or directory: " + repr(s))
        os.makedirs(s, exist_ok=True)

    def unlink(self, missing_ok: bool = False) -> None:
        s = str(self)
        if missing_ok and not os.path.exists(s):
            return
        os.remove(s)

    def rmdir(self) -> None:
        os.rmdir(str(self))

    def rename(self, target: str | Path) -> Path:
        t = str(target)
        os.rename(str(self), t)
        return Path(t)

    def iterdir(self) -> list[Path]:
        s = str(self)
        return [self.joinpath(n) for n in os.listdir(s)]

    def glob(self, pattern: str) -> list[Path]:
        """Patterns of names and directories, without `**`."""
        if "**" in pattern:
            raise ValueError("rupy's Path.glob: `**` is not supported")
        _, parts = _parse(pattern)
        found = [self._with(self._root, list(self._tail))]
        for part in parts:
            nxt: list[Path] = []
            for d in found:
                if not d.is_dir():
                    continue
                for n in sorted(os.listdir(str(d))):
                    if n.startswith(".") and not part.startswith("."):
                        continue
                    if _fnmatch(n, part):
                        nxt.append(d.joinpath(n))
            found = nxt
        if pattern.endswith("/"):
            # a trailing slash: directories only
            return [q for q in found if q.is_dir()]
        return found

    def absolute(self) -> Path:
        if self._root != "":
            return self._with(self._root, list(self._tail))
        return Path(os.getcwd()).joinpath(str(self))

    def resolve(self) -> Path:
        return Path(os.path.realpath(str(self)))

    def expanduser(self) -> Path:
        return Path(os.path.expanduser(str(self)))


def _fnmatch(name: str, pat: str) -> bool:
    """fnmatch.fnmatchcase: *, ? and [seq] / [!seq]."""
    return _fm(name, 0, pat, 0)


def _fm(s: str, i: int, p: str, j: int) -> bool:
    while j < len(p):
        c = p[j]
        if c == "*":
            while j < len(p) and p[j] == "*":
                j += 1
            if j == len(p):
                return True
            for k in range(i, len(s) + 1):
                if _fm(s, k, p, j):
                    return True
            return False
        if i >= len(s):
            return False
        if c == "?":
            i += 1
            j += 1
            continue
        if c == "[":
            end = p.find("]", j + 2 if j + 1 < len(p) and p[j + 1] == "!" else j + 1)
            if end < 0:
                if s[i] != "[":
                    return False
                i += 1
                j += 1
                continue
            body = p[j + 1 : end]
            neg = body.startswith("!")
            if neg:
                body = body[1:]
            hit = False
            k = 0
            while k < len(body):
                if k + 2 < len(body) and body[k + 1] == "-":
                    ch = s[i]
                    if body[k] <= ch <= body[k + 2]:
                        hit = True
                    k += 3
                else:
                    if body[k] == s[i]:
                        hit = True
                    k += 1
            if hit == neg:
                return False
            i += 1
            j = end + 1
            continue
        if s[i] != c:
            return False
        i += 1
        j += 1
    return i == len(s)
