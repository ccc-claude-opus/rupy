"""rupy's `io`: `io.StringIO` (CPython's), written in rupy.

A StringIO is shared like a Python object (`csv.writer(buf)` keeps `buf`)."""

from rust import shared


@shared
class StringIO:
    def __init__(self, initial_value: str = "") -> None:
        self._buf: str = initial_value
        self._len: int = len(initial_value)
        self._pos: int = 0
        self._closed: bool = False

    def _check(self) -> None:
        if self._closed:
            raise ValueError("I/O operation on closed file")

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def getvalue(self) -> str:
        self._check()
        return self._buf

    def tell(self) -> int:
        self._check()
        return self._pos

    def seek(self, pos: int, whence: int = 0) -> int:
        self._check()
        if whence == 0:
            if pos < 0:
                raise ValueError("Negative seek position " + str(pos))
            self._pos = pos
        elif whence == 1:
            if pos != 0:
                raise OSError("Can't do nonzero cur-relative seeks")
        elif whence == 2:
            if pos != 0:
                raise OSError("Can't do nonzero end-relative seeks")
            self._pos = self._len
        else:
            raise ValueError("Invalid whence (" + str(whence) + ", should be 0, 1 or 2)")
        return self._pos

    def write(self, s: str) -> int:
        self._check()
        n = len(s)
        if n == 0:
            return 0
        if self._pos == self._len:
            self._buf += s
            self._len += n
        else:
            if self._pos > self._len:
                self._buf += "\0" * (self._pos - self._len)
                self._len = self._pos
            end = self._pos + n
            self._buf = self._buf[: self._pos] + s + self._buf[end:]
            if end > self._len:
                self._len = end
        self._pos += n
        return n

    def writelines(self, lines: list[str]) -> None:
        for s in lines:
            self.write(s)

    def read(self, size: int = -1) -> str:
        self._check()
        if self._pos >= self._len:
            return ""
        end = self._len if size < 0 else min(self._len, self._pos + size)
        r = self._buf[self._pos : end]
        self._pos = end
        return r

    def readline(self, size: int = -1) -> str:
        self._check()
        if self._pos >= self._len:
            return ""
        i = self._buf.find("\n", self._pos)
        end = self._len if i < 0 else i + 1
        if size >= 0 and self._pos + size < end:
            end = self._pos + size
        r = self._buf[self._pos : end]
        self._pos = end
        return r

    def readlines(self) -> list[str]:
        out: list[str] = []
        while True:
            line = self.readline()
            if line == "":
                return out
            out.append(line)

    def truncate(self, size: int = -1) -> int:
        self._check()
        n = self._pos if size < 0 else size
        if n < self._len:
            self._buf = self._buf[:n]
            self._len = n
        return n

    def __iter__(self) -> list[str]:
        return self.readlines()
