"""rupy's `string`: CPython's constants, `capwords` and `Template`, written
in rupy. `Template.substitute` takes a dict (no keyword arguments)."""

whitespace = " \t\n\r\x0b\x0c"
ascii_lowercase = "abcdefghijklmnopqrstuvwxyz"
ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ascii_letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
digits = "0123456789"
hexdigits = "0123456789abcdefABCDEF"
octdigits = "01234567"
punctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
printable = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ \t\n\r\x0b\x0c"


def capwords(s: str, sep: str | None = None) -> str:
    if sep is None:
        return " ".join([w.capitalize() for w in s.split()])
    return sep.join([w.capitalize() for w in s.split(sep)])


def _ident_start(c: str) -> bool:
    return c == "_" or c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _ident(c: str) -> bool:
    return _ident_start(c) or c in "0123456789"


class Template:
    """$name, ${name} and $$, as CPython's (ASCII identifiers)."""

    def __init__(self, template: str) -> None:
        self.template: str = template

    def _sub(self, mapping: dict[str, str], safe: bool) -> str:
        t = self.template
        out: list[str] = []
        i = 0
        n = len(t)
        while i < n:
            c = t[i]
            if c != "$":
                out.append(c)
                i += 1
                continue
            if i + 1 < n and t[i + 1] == "$":
                out.append("$")
                i += 2
                continue
            name = ""
            end = i + 1
            if i + 1 < n and t[i + 1] == "{":
                j = i + 2
                if j < n and _ident_start(t[j]):
                    j += 1
                    while j < n and _ident(t[j]):
                        j += 1
                    if j < n and t[j] == "}":
                        name = t[i + 2 : j]
                        end = j + 1
            elif i + 1 < n and _ident_start(t[i + 1]):
                j = i + 2
                while j < n and _ident(t[j]):
                    j += 1
                name = t[i + 1 : j]
                end = j
            if name == "":
                if safe:
                    out.append("$")
                    i += 1
                    continue
                # CPython's _invalid, column included
                # (the regex's `invalid` group starts after the $)
                lines = _lines_keepends(t[: i + 1])
                lineno = 1
                colno = 1
                if len(lines) > 0:
                    lineno = len(lines)
                    colno = i + 1 - len("".join(lines[:-1]))
                raise ValueError("Invalid placeholder in string: line " + str(lineno) + ", col " + str(colno))
            if name in mapping:
                out.append(mapping[name])
            elif safe:
                out.append(t[i:end])
            else:
                raise KeyError(name)
            i = end
        return "".join(out)

    def substitute(self, mapping: dict[str, str]) -> str:
        return self._sub(mapping, False)

    def safe_substitute(self, mapping: dict[str, str]) -> str:
        return self._sub(mapping, True)

    def get_identifiers(self) -> list[str]:
        out: list[str] = []
        t = self.template
        i = 0
        while i < len(t):
            if t[i] == "$" and i + 1 < len(t):
                if t[i + 1] == "$":
                    i += 2
                    continue
                j = i + 1
                brace = t[j] == "{"
                if brace:
                    j += 1
                k = j
                if k < len(t) and _ident_start(t[k]):
                    k += 1
                    while k < len(t) and _ident(t[k]):
                        k += 1
                    if not brace or k < len(t) and t[k] == "}":
                        name = t[j:k]
                        if name not in out:
                            out.append(name)
            i += 1
        return out


def _lines_keepends(s: str) -> list[str]:
    """str.splitlines(True)"""
    out: list[str] = []
    start = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in "\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029":
            if c == "\r" and i + 1 < n and s[i + 1] == "\n":
                i += 1
            out.append(s[start : i + 1])
            start = i + 1
        i += 1
    if start < n:
        out.append(s[start:])
    return out
