"""rstatistics against R: every tests/<name>.py prints what tests/<name>.R prints in
R (the R output is kept in tests/<name>.out). Printed results must match
exactly; dist.py's 17-digit numbers within a relative 1e-12.

    python tests/run.py          # compare with the stored R output
    python tests/run.py --regen  # rerun the R scripts first (needs Rscript)
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ["dist", "format", "rng", "rng2", "htest", "table", "lm"]


def close(a: str, b: str) -> bool:
    try:
        x, y = float(a), float(b)
    except ValueError:
        return a == b
    return x == y or abs(x - y) <= 1e-12 * max(abs(x), abs(y))


def main() -> int:
    env = dict(os.environ, PYTHONPATH=os.path.dirname(HERE))
    bad = 0
    for name in NAMES:
        r_out = os.path.join(HERE, name + ".out")
        if "--regen" in sys.argv:
            with open(r_out, "w") as f:
                subprocess.run(["Rscript", os.path.join(HERE, name + ".R")], stdout=f, check=True)
        want = open(r_out).read().splitlines()
        got = subprocess.run([sys.executable, os.path.join(HERE, name + ".py")], env=env, capture_output=True, text=True, check=True).stdout.splitlines()
        same = close if name == "dist" else str.__eq__
        diffs = [i for i in range(max(len(want), len(got))) if i >= len(want) or i >= len(got) or not same(want[i], got[i])]
        print(f"{name}: {'ok' if not diffs else str(len(diffs)) + ' lines differ'}")
        for i in diffs[:5]:
            print(f"  line {i + 1}: R {want[i] if i < len(want) else '-'!r}, rstatistics {got[i] if i < len(got) else '-'!r}")
        bad += len(diffs) > 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
