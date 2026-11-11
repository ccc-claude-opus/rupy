# error: assigned more than once
from typing import Callable


def main() -> None:
    fs: list[Callable[[int], int]] = []
    for i in range(3):
        fs.append(lambda x: x + i)
    print([f(0) for f in fs])


main()
