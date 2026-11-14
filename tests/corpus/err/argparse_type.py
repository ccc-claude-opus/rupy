# error: type= is int, float or str
import argparse

p = argparse.ArgumentParser(prog="x")
p.add_argument("--when", type=len)
print(p.parse_args([]))
