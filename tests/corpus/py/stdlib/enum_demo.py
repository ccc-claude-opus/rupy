from enum import Enum, auto


class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3
    CRIMSON = 1


class Planet(Enum):
    MERCURY = "mercury"
    VENUS = "venus"


class Step(Enum):
    START = auto()
    MIDDLE = auto()
    END = 10
    AFTER = auto()

    def describe(self) -> str:
        return self.name.lower() + "=" + str(self.value)


def warm(c: Color) -> bool:
    return c == Color.RED


c = Color.GREEN
print(c, repr(c), c.name, c.value, Color.CRIMSON, Color.CRIMSON == Color.RED, warm(Color.RED), warm(c))
print(list(Color), len(Color), [m.name for m in Color], Color(3), Color["BLUE"], Color["CRIMSON"])
print(repr(Planet.VENUS), Planet("mercury"), f"{Planet.MERCURY} / {Planet.MERCURY.value}")
print([s.describe() for s in Step], Step.AFTER.value, Step.START != Step.END)
counts: dict[Color, int] = {Color.RED: 1}
counts[Color.BLUE] = 5
print(counts[Color.BLUE], Color.RED in counts, sorted([m.value for m in Color]))
for k in range(2):
    try:
        if k == 0:
            print(Color(7))
        else:
            print(Color["PINK"])
    except ValueError as e:
        print("ValueError", e)
    except KeyError as e:
        print("KeyError", e)
