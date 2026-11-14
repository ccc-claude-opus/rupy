"""rupy's `csv`: CPython's `csv` (the parser and writer of its `_csv`
module), written in rupy.

`reader` and `DictReader` read a text file, an `io.StringIO` or a list of
lines; `writer` and `DictWriter` write to a text file or an `io.StringIO`.
Rows are lists of str (a writer also takes lists of int, float or bool);
`QUOTE_NONNUMERIC` in a reader would give floats, and a DictReader row with
missing fields would hold None, so both raise an error instead."""

from io import StringIO
from typing import Iterator, TextIO

QUOTE_MINIMAL = 0
QUOTE_ALL = 1
QUOTE_NONNUMERIC = 2
QUOTE_NONE = 3
QUOTE_STRINGS = 4
QUOTE_NOTNULL = 5


class Error(Exception):
    pass


class _Dialect:
    def __init__(
        self,
        dialect: str,
        delimiter: str | None,
        quotechar: str | None,
        escapechar: str | None,
        doublequote: bool | None,
        skipinitialspace: bool | None,
        lineterminator: str | None,
        quoting: int | None,
        strict: bool | None,
    ) -> None:
        d = ","
        lt = "\r\n"
        q = QUOTE_MINIMAL
        if dialect == "excel-tab":
            d = "\t"
        elif dialect == "unix":
            lt = "\n"
            q = QUOTE_ALL
        elif dialect != "excel":
            raise Error("unknown dialect")
        if delimiter is not None:
            d = delimiter
        if lineterminator is not None:
            lt = lineterminator
        if quoting is not None:
            q = quoting
        if q < 0 or q > 5:
            raise TypeError("bad \"quoting\" value")
        if len(d) != 1:
            raise TypeError("\"delimiter\" must be a unicode character, not a string of length " + str(len(d)))
        qc = '"' if quotechar is None else quotechar
        if quotechar is not None and len(quotechar) != 1:
            raise TypeError("\"quotechar\" must be a unicode character or None, not a string of length " + str(len(quotechar)))
        ec = "" if escapechar is None else escapechar
        if escapechar is not None and len(escapechar) != 1:
            raise TypeError("\"escapechar\" must be a unicode character or None, not a string of length " + str(len(escapechar)))
        self.delimiter: str = d
        # "" for none: never equal to a character
        self.quotechar: str = qc
        self.escapechar: str = ec
        self.doublequote: bool = True if doublequote is None else doublequote
        self.skipinitialspace: bool = False if skipinitialspace is None else skipinitialspace
        self.lineterminator: str = lt
        self.quoting: int = q
        self.strict: bool = False if strict is None else strict


# --------------------------------------------------------------------- reading

_START_RECORD = 0
_START_FIELD = 1
_ESCAPED_CHAR = 2
_IN_FIELD = 3
_IN_QUOTED_FIELD = 4
_ESCAPE_IN_QUOTED_FIELD = 5
_QUOTE_IN_QUOTED_FIELD = 6
_EAT_CRNL = 7
_AFTER_ESCAPED_CRNL = 8

# the end of a line: not a character
_EOL = "EOL"


class _Parser:
    """CPython's `parse_process_char`."""

    def __init__(self, d: _Dialect) -> None:
        self.d: _Dialect = d
        self.state: int = _START_RECORD
        self.fields: list[str] = []
        self.field: list[str] = []

    def save_field(self) -> None:
        self.fields.append("".join(self.field))
        self.field = []

    def add_char(self, c: str) -> None:
        if len(self.field) >= 131072:
            raise Error("field larger than field limit (131072)")
        self.field.append(c)

    def end_of_line(self, c: str) -> None:
        self.save_field()
        self.state = _START_RECORD if c == _EOL else _EAT_CRNL

    def char(self, c: str) -> None:
        d = self.d
        st = self.state
        if st == _START_RECORD:
            if c == _EOL:
                return
            if c == "\n" or c == "\r":
                self.state = _EAT_CRNL
                return
            st = _START_FIELD
            self.state = _START_FIELD
        if st == _START_FIELD:
            if c == "\n" or c == "\r" or c == _EOL:
                self.end_of_line(c)
            elif c == d.quotechar and d.quoting != QUOTE_NONE:
                self.state = _IN_QUOTED_FIELD
            elif c == d.escapechar:
                self.state = _ESCAPED_CHAR
            elif c == " " and d.skipinitialspace:
                pass
            elif c == d.delimiter:
                self.save_field()
            else:
                self.add_char(c)
                self.state = _IN_FIELD
        elif st == _ESCAPED_CHAR:
            if c == "\n" or c == "\r":
                self.add_char(c)
                self.state = _AFTER_ESCAPED_CRNL
            else:
                self.add_char("\n" if c == _EOL else c)
                self.state = _IN_FIELD
        elif st == _AFTER_ESCAPED_CRNL or st == _IN_FIELD:
            if st == _AFTER_ESCAPED_CRNL and c == _EOL:
                return
            if c == "\n" or c == "\r" or c == _EOL:
                self.end_of_line(c)
            elif c == d.escapechar:
                self.state = _ESCAPED_CHAR
            elif c == d.delimiter:
                self.save_field()
                self.state = _START_FIELD
            else:
                self.add_char(c)
                self.state = _IN_FIELD
        elif st == _IN_QUOTED_FIELD:
            if c == _EOL:
                pass
            elif c == d.escapechar:
                self.state = _ESCAPE_IN_QUOTED_FIELD
            elif c == d.quotechar and d.quoting != QUOTE_NONE:
                self.state = _QUOTE_IN_QUOTED_FIELD if d.doublequote else _IN_FIELD
            else:
                self.add_char(c)
        elif st == _ESCAPE_IN_QUOTED_FIELD:
            self.add_char("\n" if c == _EOL else c)
            self.state = _IN_QUOTED_FIELD
        elif st == _QUOTE_IN_QUOTED_FIELD:
            if d.quoting != QUOTE_NONE and c == d.quotechar:
                self.add_char(c)
                self.state = _IN_QUOTED_FIELD
            elif c == d.delimiter:
                self.save_field()
                self.state = _START_FIELD
            elif c == "\n" or c == "\r" or c == _EOL:
                self.end_of_line(c)
            elif not d.strict:
                self.add_char(c)
                self.state = _IN_FIELD
            else:
                raise Error("'" + d.delimiter + "' expected after '" + d.quotechar + "'")
        elif st == _EAT_CRNL:
            if c == "\n" or c == "\r":
                pass
            elif c == _EOL:
                self.state = _START_RECORD
            else:
                raise Error("new-line character seen in unquoted field - do you need to open the file with newline=''?")

    def take(self) -> list[str]:
        r = self.fields
        self.fields = []
        return r


def _lines(csvfile: TextIO | StringIO | list[str]) -> list[str]:
    out: list[str] = []
    for line in csvfile:
        out.append(line)
    return out


def reader(
    csvfile: TextIO | StringIO | list[str],
    dialect: str = "excel",
    *,
    delimiter: str | None = None,
    quotechar: str | None = None,
    escapechar: str | None = None,
    doublequote: bool | None = None,
    skipinitialspace: bool | None = None,
    lineterminator: str | None = None,
    quoting: int | None = None,
    strict: bool | None = None,
) -> Iterator[list[str]]:
    d = _Dialect(dialect, delimiter, quotechar, escapechar, doublequote, skipinitialspace, lineterminator, quoting, strict)
    if d.quoting == QUOTE_NONNUMERIC or d.quoting == QUOTE_STRINGS or d.quoting == QUOTE_NOTNULL:
        raise ValueError("rupy's csv.reader: this quoting gives fields that are not str")
    # the lines first: a generator runs on its own thread, the file stays here
    return _rows(_lines(csvfile), d)


def _rows(lines: list[str], d: _Dialect) -> Iterator[list[str]]:
    p = _Parser(d)
    for line in lines:
        for c in line:
            p.char(c)
        p.char(_EOL)
        if p.state == _START_RECORD:
            yield p.take()
    if len(p.field) != 0 or p.state == _IN_QUOTED_FIELD:
        if d.strict:
            raise Error("unexpected end of data")
        p.save_field()
        yield p.take()


def DictReader(
    f: TextIO | StringIO | list[str],
    fieldnames: list[str] | None = None,
    restval: str | None = None,
    dialect: str = "excel",
    *,
    delimiter: str | None = None,
    quotechar: str | None = None,
    escapechar: str | None = None,
    doublequote: bool | None = None,
    skipinitialspace: bool | None = None,
    quoting: int | None = None,
    strict: bool | None = None,
) -> Iterator[dict[str, str]]:
    rows = reader(f, dialect, delimiter=delimiter, quotechar=quotechar, escapechar=escapechar, doublequote=doublequote, skipinitialspace=skipinitialspace, quoting=quoting, strict=strict)
    return _dicts(rows, fieldnames, restval)


def _dicts(rows: Iterator[list[str]], fieldnames: list[str] | None, restval: str | None) -> Iterator[dict[str, str]]:
    names: list[str] = []
    first = True
    if fieldnames is not None:
        names = fieldnames
        first = False
    for row in rows:
        if first:
            names = row
            first = False
            continue
        if len(row) == 0:
            continue
        if len(row) > len(names):
            raise ValueError("rupy's csv.DictReader: a row has more fields than fieldnames (Python keeps them under the key None)")
        d: dict[str, str] = {}
        for k in range(len(names)):
            if k < len(row):
                d[names[k]] = row[k]
            elif restval is not None:
                d[names[k]] = restval
            else:
                raise ValueError("rupy's csv.DictReader: a row has fewer fields than fieldnames (Python gives None); pass restval=")
        yield d


# --------------------------------------------------------------------- writing


def _join(d: _Dialect, fields: list[str], quoted: list[bool]) -> str:
    """CPython's `join_append` for each field, then the line terminator."""
    out: list[str] = []
    for k in range(len(fields)):
        if k > 0:
            out.append(d.delimiter)
        q = quoted[k]
        chars: list[str] = []
        for c in fields[k]:
            want_escape = False
            if c == d.delimiter or c == d.escapechar or c == d.quotechar or c == "\n" or c == "\r" or c in d.lineterminator:
                if d.quoting == QUOTE_NONE:
                    want_escape = True
                else:
                    if c == d.quotechar:
                        if d.doublequote:
                            chars.append(d.quotechar)
                        else:
                            want_escape = True
                    elif c == d.escapechar:
                        want_escape = True
                    if not want_escape:
                        q = True
                if want_escape:
                    if d.escapechar == "":
                        raise Error("need to escape, but no escapechar set")
                    chars.append(d.escapechar)
            chars.append(c)
        if q:
            out.append(d.quotechar)
        out.append("".join(chars))
        if q:
            out.append(d.quotechar)
    if len(fields) == 1 and fields[0] == "":
        if d.quoting == QUOTE_NONE:
            raise Error("single empty field record must be quoted")
        out = [d.quotechar + d.quotechar]
    out.append(d.lineterminator)
    return "".join(out)


class _Writer:
    def __init__(self, file: TextIO | None, buf: StringIO | None, d: _Dialect) -> None:
        self._file: TextIO | None = file
        self._buf: StringIO | None = buf
        self.dialect: _Dialect = d

    def _write(self, s: str) -> int:
        if self._file is not None:
            return self._file.write(s)
        if self._buf is not None:
            return self._buf.write(s)
        return 0

    def writerow(self, row: list[str] | list[int] | list[float] | list[bool]) -> int:
        fields: list[str] = []
        quoted: list[bool] = []
        q = self.dialect.quoting
        for x in row:
            fields.append(str(x))
            text = False
            if isinstance(x, str):
                text = True
            quoted.append(q == QUOTE_ALL or q == QUOTE_NOTNULL or (q == QUOTE_NONNUMERIC or q == QUOTE_STRINGS) and text)
        return self._write(_join(self.dialect, fields, quoted))

    def writerows(self, rows: list[list[str]] | list[list[int]] | list[list[float]] | list[list[bool]]) -> None:
        for row in rows:
            self.writerow(row)


def writer(
    csvfile: TextIO | StringIO,
    dialect: str = "excel",
    *,
    delimiter: str | None = None,
    quotechar: str | None = None,
    escapechar: str | None = None,
    doublequote: bool | None = None,
    skipinitialspace: bool | None = None,
    lineterminator: str | None = None,
    quoting: int | None = None,
    strict: bool | None = None,
) -> _Writer:
    d = _Dialect(dialect, delimiter, quotechar, escapechar, doublequote, skipinitialspace, lineterminator, quoting, strict)
    if isinstance(csvfile, StringIO):
        return _Writer(None, csvfile, d)
    else:
        return _Writer(csvfile, None, d)


class _DictWriter:
    def __init__(self, w: _Writer, fieldnames: list[str], restval: str, extrasaction: str) -> None:
        if extrasaction != "raise" and extrasaction != "ignore":
            raise ValueError("extrasaction (" + extrasaction + ") must be 'raise' or 'ignore'")
        self.writer: _Writer = w
        self.fieldnames: list[str] = fieldnames
        self.restval: str = restval
        self.extrasaction: str = extrasaction

    def writeheader(self) -> int:
        return self.writer.writerow(self.fieldnames)

    def writerow(self, rowdict: dict[str, str] | dict[str, int] | dict[str, float]) -> int:
        if self.extrasaction == "raise":
            wrong = [k for k in rowdict if k not in self.fieldnames]
            if len(wrong) > 0:
                raise ValueError("dict contains fields not in fieldnames: " + ", ".join([repr(k) for k in wrong]))
        row: list[str] = []
        quoted: list[bool] = []
        q = self.writer.dialect.quoting
        for k in self.fieldnames:
            if k in rowdict:
                x = rowdict[k]
                row.append(str(x))
                text = False
                if isinstance(x, str):
                    text = True
                quoted.append(q == QUOTE_ALL or q == QUOTE_NOTNULL or (q == QUOTE_NONNUMERIC or q == QUOTE_STRINGS) and text)
            else:
                row.append(self.restval)
                quoted.append(q == QUOTE_ALL or q == QUOTE_NOTNULL or q == QUOTE_NONNUMERIC or q == QUOTE_STRINGS)
        return self.writer._write(_join(self.writer.dialect, row, quoted))

    def writerows(self, rowdicts: list[dict[str, str]] | list[dict[str, int]] | list[dict[str, float]]) -> None:
        for r in rowdicts:
            self.writerow(r)


def DictWriter(
    f: TextIO | StringIO,
    fieldnames: list[str],
    restval: str = "",
    extrasaction: str = "raise",
    dialect: str = "excel",
    *,
    delimiter: str | None = None,
    quotechar: str | None = None,
    escapechar: str | None = None,
    doublequote: bool | None = None,
    skipinitialspace: bool | None = None,
    lineterminator: str | None = None,
    quoting: int | None = None,
    strict: bool | None = None,
) -> _DictWriter:
    w = writer(f, dialect, delimiter=delimiter, quotechar=quotechar, escapechar=escapechar, doublequote=doublequote, skipinitialspace=skipinitialspace, lineterminator=lineterminator, quoting=quoting, strict=strict)
    return _DictWriter(w, fieldnames, restval, extrasaction)
