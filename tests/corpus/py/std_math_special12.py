# math.gamma, lgamma, erf, erfc, asinh, acosh, atanh to 12 digits, with their errors
import math


def show(name: str, xs: list[float]) -> None:
    for x in xs:
        try:
            if name == "gamma":
                r = math.gamma(x)
            elif name == "lgamma":
                r = math.lgamma(x)
            elif name == "erf":
                r = math.erf(x)
            elif name == "erfc":
                r = math.erfc(x)
            elif name == "asinh":
                r = math.asinh(x)
            elif name == "acosh":
                r = math.acosh(x)
            else:
                r = math.atanh(x)
            print(name, x, format(r, ".12g"))
        except ValueError as e:
            print(name, x, "ValueError:", e)
        except OverflowError as e:
            print(name, x, "OverflowError:", e)


show("gamma", [1.0, 5.0, 23.0, 24.0, 0.5, 1.5, 2.5, 4.75, 10.1, 30.3, 141.5, 171.5, -0.5, -1.5, -2.25, -150.5, -250.5, 1e-25, 0.0, -3.0, 172.0, math.inf, -math.inf])
show("lgamma", [1.0, 2.0, 3.0, 0.5, 2.5, 10.0, 100.0, 1e10, -0.5, -2.5, 1e-25, 0.0, -4.0, math.inf, -math.inf, 1e308])
show("erf", [0.0, 1e-30, 0.1, 0.5, 0.84375, 1.0, 1.2, 2.0, 2.5, 3.0, 5.0, 7.0, -0.3, -1.5, math.inf, -math.inf])
show("erfc", [0.0, 0.1, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 27.0, 30.0, -0.5, -2.0, -7.0, math.inf])
show("asinh", [0.0, 0.5, 1.0, -2.0, 100.0, 1e-10])
show("acosh", [1.0, 1.5, 2.0, 10.0, 1e6, 0.5, -1.0])
show("atanh", [0.0, 0.25, -0.5, 0.9, 1.0, -1.0, 2.0])
