"""rupy's `textwrap`: CPython's `TextWrapper`, `wrap`, `fill`, `shorten`,
`dedent` and `indent`, written in rupy. The word splitter is CPython's
`wordsep_re` written out by hand (lookbehinds included)."""

from typing import Callable

_WHITESPACE = "\t\n\x0b\x0c\r "


def _ws(c: str) -> bool:
    return c in _WHITESPACE


def _w(c: str) -> bool:
    """\\w"""
    return c.isalnum() or c == "_"


def _letter(c: str) -> bool:
    """[^\\d\\W]: a word character that is not a digit"""
    return _w(c) and not c.isdigit()


def _wp(c: str) -> bool:
    """word_punct: [\\w!"'&.,?]"""
    return _w(c) or c in "!\"'&.,?"


def _at(text: str, i: int) -> str:
    return text[i] if 0 <= i < len(text) else ""


def _dashes_then_word(text: str, i: int) -> bool:
    """(?=-{2,}\\w) at i"""
    k = i
    while k < len(text) and text[k] == "-":
        k += 1
    return k - i >= 2 and k < len(text) and _w(text[k])


def _split_hyphens(text: str) -> list[str]:
    """wordsep_re.split(text) without the empty strings."""
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if _ws(text[i]):
            j = i
            while j < n and _ws(text[j]):
                j += 1
            chunks.append(text[i:j])
            i = j
            continue
        # an em-dash between words
        if i > 0 and _wp(text[i - 1]) and _dashes_then_word(text, i):
            j = i
            while text[j] == "-":
                j += 1
            chunks.append(text[i:j])
            i = j
            continue
        # a word, possibly hyphenated: the shortest run of non-space ending well
        e = i + 1
        end = n
        while e <= n:
            if _ws(text[e - 1]):
                end = e - 1
                break
            c = _at(text, e)
            if c == "-":
                behind = _letter(_at(text, e - 2)) and _letter(_at(text, e - 1)) or _letter(_at(text, e - 3)) and _at(text, e - 2) == "-" and _letter(_at(text, e - 1))
                ahead = _letter(_at(text, e + 1)) and (_letter(_at(text, e + 2)) or _at(text, e + 2) == "-" and _letter(_at(text, e + 3)))
                if behind and ahead:
                    end = e + 1
                    break
            if e == n or _ws(c):
                end = e
                break
            if _wp(text[e - 1]) and _dashes_then_word(text, e):
                end = e
                break
            e += 1
        chunks.append(text[i:end])
        i = end
    return chunks


def _split_simple(text: str) -> list[str]:
    """wordsep_simple_re.split(text) without the empty strings."""
    chunks: list[str] = []
    i = 0
    while i < len(text):
        j = i
        space = _ws(text[i])
        while j < len(text) and _ws(text[j]) == space:
            j += 1
        chunks.append(text[i:j])
        i = j
    return chunks


def _sentence_end(chunk: str) -> bool:
    """[a-z][\\.\\!\\?][\\"\\']?\\z, searched"""
    n = len(chunk)
    if n >= 2 and chunk[n - 1] in ".!?" and chunk[n - 2] in "abcdefghijklmnopqrstuvwxyz":
        return True
    return n >= 3 and chunk[n - 1] in "\"'" and chunk[n - 2] in ".!?" and chunk[n - 3] in "abcdefghijklmnopqrstuvwxyz"


def _expandtabs(text: str, tabsize: int) -> str:
    """str.expandtabs: columns restart after \n and \r."""
    out: list[str] = []
    col = 0
    for c in text:
        if c == "\t":
            if tabsize > 0:
                k = tabsize - col % tabsize
                out.append(" " * k)
                col += k
        else:
            out.append(c)
            col = 0 if c == "\n" or c == "\r" else col + 1
    return "".join(out)


class TextWrapper:
    def __init__(
        self,
        width: int = 70,
        initial_indent: str = "",
        subsequent_indent: str = "",
        expand_tabs: bool = True,
        replace_whitespace: bool = True,
        fix_sentence_endings: bool = False,
        break_long_words: bool = True,
        drop_whitespace: bool = True,
        break_on_hyphens: bool = True,
        tabsize: int = 8,
        *,
        max_lines: int | None = None,
        placeholder: str = " [...]",
    ) -> None:
        self.width: int = width
        self.initial_indent: str = initial_indent
        self.subsequent_indent: str = subsequent_indent
        self.expand_tabs: bool = expand_tabs
        self.replace_whitespace: bool = replace_whitespace
        self.fix_sentence_endings: bool = fix_sentence_endings
        self.break_long_words: bool = break_long_words
        self.drop_whitespace: bool = drop_whitespace
        self.break_on_hyphens: bool = break_on_hyphens
        self.tabsize: int = tabsize
        self.max_lines: int | None = max_lines
        self.placeholder: str = placeholder

    def _munge_whitespace(self, text: str) -> str:
        if self.expand_tabs:
            text = _expandtabs(text, self.tabsize)
        if self.replace_whitespace:
            text = "".join([" " if _ws(c) else c for c in text])
        return text

    def _split_chunks(self, text: str) -> list[str]:
        text = self._munge_whitespace(text)
        if self.break_on_hyphens:
            return _split_hyphens(text)
        return _split_simple(text)

    def _handle_long_word(self, chunks: list[str], cur_line: list[str], cur_len: int, width: int) -> None:
        space_left = 1 if width < 1 else width - cur_len
        if self.break_long_words and space_left > 0:
            end = space_left
            chunk = chunks[-1]
            if self.break_on_hyphens and len(chunk) > space_left:
                hyphen = chunk[:space_left].rfind("-")
                if hyphen > 0 and any([c != "-" for c in chunk[:hyphen]]):
                    end = hyphen + 1
            cur_line.append(chunk[:end])
            chunks[-1] = chunk[end:]
        elif len(cur_line) == 0:
            cur_line.append(chunks.pop())

    def _wrap_chunks(self, chunks: list[str]) -> list[str]:
        lines: list[str] = []
        if self.width <= 0:
            raise ValueError("invalid width " + repr(self.width) + " (must be > 0)")
        # -1: no limit
        max_lines = -1
        if self.max_lines is not None:
            max_lines = self.max_lines
            ind = self.subsequent_indent if max_lines > 1 else self.initial_indent
            if len(ind) + len(self.placeholder.lstrip()) > self.width:
                raise ValueError("placeholder too large for max width")
        chunks.reverse()
        while len(chunks) > 0:
            cur_line: list[str] = []
            cur_len = 0
            indent = self.subsequent_indent if len(lines) > 0 else self.initial_indent
            width = self.width - len(indent)
            if self.drop_whitespace and chunks[-1].strip() == "" and len(lines) > 0:
                chunks.pop()
            while len(chunks) > 0:
                n = len(chunks[-1])
                if cur_len + n <= width:
                    cur_line.append(chunks.pop())
                    cur_len += n
                else:
                    break
            if len(chunks) > 0 and len(chunks[-1]) > width:
                self._handle_long_word(chunks, cur_line, cur_len, width)
                cur_len = sum([len(c) for c in cur_line])
            if self.drop_whitespace and len(cur_line) > 0 and cur_line[-1].strip() == "":
                cur_len -= len(cur_line[-1])
                cur_line.pop()
            if len(cur_line) > 0:
                last_ok = len(chunks) == 0 or self.drop_whitespace and len(chunks) == 1 and chunks[0].strip() == ""
                if max_lines < 0 or len(lines) + 1 < max_lines or last_ok and cur_len <= width:
                    lines.append(indent + "".join(cur_line))
                else:
                    placed = False
                    while len(cur_line) > 0:
                        if cur_line[-1].strip() != "" and cur_len + len(self.placeholder) <= width:
                            cur_line.append(self.placeholder)
                            lines.append(indent + "".join(cur_line))
                            placed = True
                            break
                        cur_len -= len(cur_line[-1])
                        cur_line.pop()
                    if not placed:
                        done = False
                        if len(lines) > 0:
                            prev_line = lines[-1].rstrip()
                            if len(prev_line) + len(self.placeholder) <= self.width:
                                lines[-1] = prev_line + self.placeholder
                                done = True
                        if not done:
                            lines.append(indent + self.placeholder.lstrip())
                    break
        return lines

    def wrap(self, text: str) -> list[str]:
        chunks = self._split_chunks(text)
        if self.fix_sentence_endings:
            i = 0
            while i < len(chunks) - 1:
                if chunks[i + 1] == " " and _sentence_end(chunks[i]):
                    chunks[i + 1] = "  "
                    i += 2
                else:
                    i += 1
        return self._wrap_chunks(chunks)

    def fill(self, text: str) -> str:
        return "\n".join(self.wrap(text))


def wrap(
    text: str,
    width: int = 70,
    *,
    initial_indent: str = "",
    subsequent_indent: str = "",
    expand_tabs: bool = True,
    replace_whitespace: bool = True,
    fix_sentence_endings: bool = False,
    break_long_words: bool = True,
    drop_whitespace: bool = True,
    break_on_hyphens: bool = True,
    tabsize: int = 8,
    max_lines: int | None = None,
    placeholder: str = " [...]",
) -> list[str]:
    w = TextWrapper(width, initial_indent, subsequent_indent, expand_tabs, replace_whitespace, fix_sentence_endings, break_long_words, drop_whitespace, break_on_hyphens, tabsize, max_lines=max_lines, placeholder=placeholder)
    return w.wrap(text)


def fill(
    text: str,
    width: int = 70,
    *,
    initial_indent: str = "",
    subsequent_indent: str = "",
    expand_tabs: bool = True,
    replace_whitespace: bool = True,
    fix_sentence_endings: bool = False,
    break_long_words: bool = True,
    drop_whitespace: bool = True,
    break_on_hyphens: bool = True,
    tabsize: int = 8,
    max_lines: int | None = None,
    placeholder: str = " [...]",
) -> str:
    w = TextWrapper(width, initial_indent, subsequent_indent, expand_tabs, replace_whitespace, fix_sentence_endings, break_long_words, drop_whitespace, break_on_hyphens, tabsize, max_lines=max_lines, placeholder=placeholder)
    return w.fill(text)


def shorten(
    text: str,
    width: int,
    *,
    initial_indent: str = "",
    subsequent_indent: str = "",
    break_long_words: bool = True,
    break_on_hyphens: bool = True,
    placeholder: str = " [...]",
) -> str:
    w = TextWrapper(width, initial_indent, subsequent_indent, True, True, False, break_long_words, True, break_on_hyphens, 8, max_lines=1, placeholder=placeholder)
    return w.fill(" ".join(text.strip().split()))


def dedent(text: str) -> str:
    lines = text.split("\n")
    non_blank = [ln for ln in lines if ln != "" and not ln.isspace()]
    l1 = min(non_blank) if len(non_blank) > 0 else ""
    l2 = max(non_blank) if len(non_blank) > 0 else ""
    margin = 0
    for k in range(len(l1)):
        margin = k
        c = l1[k]
        if c != l2[k] or c not in " \t":
            break
    else:
        margin = len(l1) - 1 if len(l1) > 0 else 0
    return "\n".join([ln[margin:] if not ln.isspace() else "" for ln in lines])


def indent(text: str, prefix: str, predicate: Callable[[str], bool] | None = None) -> str:
    out: list[str] = []
    if predicate is None:
        for line in _lines_keepends(text):
            if not line.isspace():
                out.append(prefix)
            out.append(line)
    else:
        pred: Callable[[str], bool] = predicate
        for line in _lines_keepends(text):
            if pred(line):
                out.append(prefix)
            out.append(line)
    return "".join(out)


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
