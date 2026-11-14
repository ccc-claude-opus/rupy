class Num:
    def __init__(self, v: int | str, scale: int = 1) -> None:
        if isinstance(v, int):
            self.n: int = v * scale
        else:
            self.n = int(v) * scale
        self.label: str = "n"

    def __repr__(self) -> str:
        return "Num(" + str(self.n) + ")"


def make(s: str) -> Num:
    return Num(s, 10)


print(Num(3), Num("42"), make("7"), [Num(i) for i in range(3)])
