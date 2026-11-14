"""rupy's `argparse`: the parser and help of CPython's `argparse`, written in
rupy. The translator turns `parser.add_argument(...)` calls into `_add` calls
and the result of `parse_args()` into a dataclass of the arguments (its
fields typed from `type=`, `action=`, `nargs=` and `default=`); this module
reads the command line into strings, checks them and prints usage, help and
errors as CPython does."""

import os
import sys
import textwrap
from dataclasses import dataclass


@dataclass(frozen=True)
class _Arg:
    names: list[str]
    dest: str
    # store, store_true, store_false, count, append, help
    action: str
    # str, int, float
    conv: str
    # "": one value; "?", "*", "+" or a number
    nargs: str
    choices: list[str]
    required: bool
    help: str
    metavar: str
    # the default's text, for %(default)s
    default: str

    def positional(self) -> bool:
        return not self.names[0].startswith("-")

    def takes(self) -> bool:
        return self.action == "store" or self.action == "append"


class Parsed:
    """The command line as strings: the values of each dest, and how often each was given."""

    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}
        self.seen: dict[str, int] = {}

    def has(self, dest: str) -> bool:
        return dest in self.seen

    def count(self, dest: str) -> int:
        return self.seen[dest] if dest in self.seen else 0

    def one(self, dest: str) -> str:
        return self.values[dest][-1]

    def all(self, dest: str) -> list[str]:
        return self.values[dest] if dest in self.values else []


def _width() -> int:
    """shutil.get_terminal_size().columns - 2 (COLUMNS, else 80)."""
    c = os.environ.get("COLUMNS")
    if c is not None and c.isdigit() and int(c) > 0:
        return int(c) - 2
    return 78


class ArgumentParser:
    def __init__(self, prog: str | None = None, description: str | None = None, epilog: str | None = None, add_help: bool = True) -> None:
        self.prog: str = prog if prog is not None else sys.argv[0][sys.argv[0].rfind("/") + 1 :]
        self.description: str = description if description is not None else ""
        self.epilog: str = epilog if epilog is not None else ""
        self.args: list[_Arg] = []
        if add_help:
            self.args.append(_Arg(["-h", "--help"], "help", "help", "str", "", [], False, "show this help message and exit", "", ""))

    def _add(self, names: list[str], dest: str, action: str, conv: str, nargs: str, choices: list[str], required: bool, help: str, metavar: str, default: str) -> None:
        self.args.append(_Arg(names, dest, action, conv, nargs, choices, required, help, metavar, default))

    # ---------------------------------------------------------------- usage

    def _metavar(self, a: _Arg) -> str:
        if a.metavar != "":
            return a.metavar
        if len(a.choices) > 0:
            return "{" + ",".join(a.choices) + "}"
        return a.dest if a.positional() else a.dest.upper()

    def _args_text(self, a: _Arg) -> str:
        m = self._metavar(a)
        n = a.nargs
        if n == "":
            return m
        if n == "?":
            return "[" + m + "]"
        if n == "*":
            return "[" + m + " ...]"
        if n == "+":
            return m + " [" + m + " ...]"
        return " ".join([m] * int(n))

    def _usage_part(self, a: _Arg) -> str:
        if a.positional():
            return self._args_text(a)
        part = a.names[0]
        if a.takes():
            part += " " + self._args_text(a)
        return part if a.required else "[" + part + "]"

    def format_usage(self) -> str:
        opts = [self._usage_part(a) for a in self.args if not a.positional()]
        pos = [self._usage_part(a) for a in self.args if a.positional()]
        prefix = "usage: "
        line = prefix + self.prog
        parts = opts + pos
        if len(parts) > 0:
            line += " " + " ".join(parts)
        text_width = _width()
        if len(line) <= text_width:
            return line + "\n"
        # too long: the optionals and the positionals wrapped under the program
        indent = " " * (len(prefix) + len(self.prog) + 1)
        lines: list[str] = []
        if len(prefix) + len(self.prog) <= 0.75 * text_width:
            first = self.prog
            lines = _wrap_parts(opts, indent, text_width, prefix + first + " ")
            if len(pos) > 0:
                lines += _wrap_parts(pos, indent, text_width, indent) if len(opts) > 0 else []
                if len(opts) == 0:
                    lines = _wrap_parts(pos, indent, text_width, prefix + first + " ")
        else:
            indent = " " * len(prefix)
            lines = [prefix + self.prog] + _wrap_parts(opts + pos, indent, text_width, indent)
        return "\n".join(lines) + "\n"

    # ----------------------------------------------------------------- help

    def _invocation(self, a: _Arg) -> str:
        if a.positional():
            return self._metavar(a)
        text = ", ".join(a.names)
        if a.takes():
            text += " " + self._args_text(a)
        return text

    def _help_text(self, a: _Arg) -> str:
        h = a.help.replace("%(default)s", a.default).replace("%(prog)s", self.prog).replace("%(dest)s", a.dest)
        return h.replace("%%", "%")

    def format_help(self) -> str:
        width = _width()
        max_help = min(24, max(width - 20, 4))
        longest = 0
        for a in self.args:
            longest = max(longest, len(self._invocation(a)) + 2)
        help_position = min(longest + 2, max_help)
        help_width = max(width - help_position, 11)
        action_width = help_position - 2 - 2
        out = self.format_usage()
        if self.description != "":
            out += "\n" + _fill(self.description, width) + "\n"
        for title, positional in [("positional arguments", True), ("options", False)]:
            group = [a for a in self.args if a.positional() == positional]
            if len(group) == 0:
                continue
            out += "\n" + title + ":\n"
            for a in group:
                header = self._invocation(a)
                if a.help == "":
                    out += "  " + header + "\n"
                    continue
                lines = textwrap.wrap(" ".join(self._help_text(a).split()), help_width)
                if len(header) <= action_width:
                    out += "  " + header + " " * (action_width - len(header)) + "  " + (lines[0] if len(lines) > 0 else "") + "\n"
                else:
                    out += "  " + header + "\n" + " " * help_position + (lines[0] if len(lines) > 0 else "") + "\n"
                for ln in lines[1:]:
                    out += " " * help_position + ln + "\n"
        if self.epilog != "":
            out += "\n" + _fill(self.epilog, width) + "\n"
        return out

    def print_usage(self) -> None:
        print(self.format_usage(), end="")

    def print_help(self) -> None:
        print(self.format_help(), end="")

    def error(self, message: str) -> None:
        sys.stderr.write(self.format_usage())
        sys.stderr.write(self.prog + ": error: " + message + "\n")
        sys.exit(2)

    # -------------------------------------------------------------- parsing

    def _name(self, a: _Arg) -> str:
        return "/".join(a.names) if not a.positional() else self._metavar(a)

    def _check(self, a: _Arg, v: str) -> None:
        if a.conv == "int":
            t = v.strip().replace("_", "")
            body = t[1:] if t.startswith("-") or t.startswith("+") else t
            if not body.isdigit():
                self.error("argument " + self._name(a) + ": invalid int value: " + repr(v))
        elif a.conv == "float":
            if not _is_float(v):
                self.error("argument " + self._name(a) + ": invalid float value: " + repr(v))
        if len(a.choices) > 0 and v not in a.choices:
            self.error("argument " + self._name(a) + ": invalid choice: " + repr(v) + " (choose from " + ", ".join([repr(c) for c in a.choices]) + ")")

    def _store(self, r: Parsed, a: _Arg, vals: list[str]) -> None:
        for v in vals:
            self._check(a, v)
        if a.action == "append" or a.nargs != "" and a.nargs != "?":
            if a.action == "append":
                old = r.values[a.dest] if a.dest in r.values else []
                r.values[a.dest] = old + vals
            else:
                r.values[a.dest] = vals
        else:
            r.values[a.dest] = vals
        r.seen[a.dest] = r.count(a.dest) + 1

    def _find(self, opt: str) -> _Arg | None:
        for a in self.args:
            if opt in a.names:
                return a
        # a unique prefix of a long option
        if opt.startswith("--"):
            hits = [a for a in self.args if any([n.startswith(opt) and n.startswith("--") for n in a.names])]
            if len(hits) == 1:
                return hits[0]
        return None

    def parse_args(self, args: list[str] | None = None) -> Parsed:
        argv = args if args is not None else sys.argv[1:]
        r = Parsed()
        positionals: list[str] = []
        unknown: list[str] = []
        i = 0
        while i < len(argv):
            tok = argv[i]
            i += 1
            if tok == "--":
                positionals += argv[i:]
                break
            if not tok.startswith("-") or tok == "-" or _is_float(tok):
                positionals.append(tok)
                continue
            value: str | None = None
            name = tok
            if tok.startswith("--") and "=" in tok:
                name = tok[: tok.index("=")]
                value = tok[tok.index("=") + 1 :]
            a = self._find(name)
            if a is None and not tok.startswith("--") and len(tok) > 2:
                # -nVALUE, or -vq: short options together
                a = self._find(tok[:2])
                name = tok[:2]
                if a is not None:
                    rest = tok[2:]
                    if a.takes():
                        value = rest
                    else:
                        self._flag(r, a)
                        for c in rest:
                            b = self._find("-" + c)
                            if b is not None and not b.takes():
                                self._flag(r, b)
                            else:
                                self.error("argument " + self._name(a) + ": ignored explicit argument " + repr(rest))
                        continue
            if a is None:
                unknown.append(tok)
            else:
                i = self._consume(r, a, value, argv, i)
        # the positionals, left to right: each takes what the later ones leave
        # (indices: the arguments stay in self.args)
        pos = [q for q in range(len(self.args)) if self.args[q].positional()]
        k = 0
        for j in range(len(pos)):
            pa = self.args[pos[j]]
            later = 0
            for q in pos[j + 1 :]:
                nxt = self.args[q]
                if nxt.nargs == "" or nxt.nargs == "+":
                    later += 1
                elif nxt.nargs.isdigit():
                    later += int(nxt.nargs)
            left = len(positionals) - k - later
            n = pa.nargs
            take = 0
            if n == "":
                take = 1
            elif n == "?":
                take = 1 if left >= 1 else 0
            elif n == "*":
                take = max(left, 0)
            elif n == "+":
                take = max(left, 1)
            else:
                take = int(n)
            if k + take > len(positionals):
                continue
            self._store(r, pa, positionals[k : k + take])
            k += take
        missing = [self._name(a) for a in self.args if (a.required or a.positional() and a.nargs != "?" and a.nargs != "*") and a.dest not in r.seen]
        if len(missing) > 0:
            self.error("the following arguments are required: " + ", ".join(missing))
        extra = unknown + positionals[k:]
        if len(extra) > 0:
            self.error("unrecognized arguments: " + " ".join(extra))
        return r

    def _consume(self, r: Parsed, a: _Arg, value: str | None, argv: list[str], i: int) -> int:
        """Option a (its `=value`, if any) at argv[i - 1]: where the next one starts."""
        if not a.takes():
            if value is not None:
                self.error("argument " + self._name(a) + ": ignored explicit argument " + repr(value))
            self._flag(r, a)
            return i
        vals: list[str] = []
        if value is not None:
            vals = [value]
        else:
            n = a.nargs
            while i < len(argv) and (not argv[i].startswith("-") or argv[i] == "-" or _is_float(argv[i])) and (n == "*" or n == "+" or len(vals) < (1 if n == "" or n == "?" else int(n))):
                vals.append(argv[i])
                i += 1
            if (n == "" or n.isdigit()) and len(vals) < (1 if n == "" else int(n)):
                self.error("argument " + self._name(a) + ": expected " + ("one argument" if n == "" or n == "1" else n + " arguments"))
            if n == "+" and len(vals) == 0:
                self.error("argument " + self._name(a) + ": expected at least one argument")
        self._store(r, a, vals)
        return i

    def _flag(self, r: Parsed, a: _Arg) -> None:
        if a.action == "help":
            self.print_help()
            sys.exit(0)
        r.seen[a.dest] = r.count(a.dest) + 1


def _is_float(s: str) -> bool:
    t = s.strip().lower()
    if t.startswith("-") or t.startswith("+"):
        t = t[1:]
    if t in ["inf", "infinity", "nan"]:
        return True
    mant = t
    e = t.find("e")
    if e >= 0:
        ex = t[e + 1 :]
        if ex.startswith("-") or ex.startswith("+"):
            ex = ex[1:]
        if not ex.isdigit():
            return False
        mant = t[:e]
    parts = mant.split(".")
    if len(parts) > 2 or mant.replace(".", "") == "":
        return False
    return all([p == "" or p.isdigit() for p in parts])


def _fill(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(" ".join(text.split()), width))


def _wrap_parts(parts: list[str], indent: str, width: int, first: str) -> list[str]:
    lines: list[str] = []
    line: list[str] = []
    length = len(first) - 1
    head = first
    for p in parts:
        if length + 1 + len(p) > width and len(line) > 0:
            lines.append(head + " ".join(line))
            head = indent
            line = []
            length = len(indent) - 1
        line.append(p)
        length += len(p) + 1
    if len(line) > 0:
        lines.append(head + " ".join(line))
    return lines
