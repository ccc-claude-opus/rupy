"""numpy: np.linalg.det as NumPy computes it (sign · exp(sum of log |u_ii|), from slogdet)."""
# wasm: skip (ln / exp of wasm32 are not correctly rounded: det([[1, 2], [3, 4]]) is -2.0, not -2.0000000000000004)
import numpy as np

for m in [[[1.0, 2.0], [3.0, 4.0]], [[2.0, 1.0, 1.0], [1.0, 3.0, 2.0], [1.0, 0.0, 0.0]], [[4.0, 3.0], [6.0, 3.0]], [[1.0, 2.0], [2.0, 4.0]], [[0.5, 0.25, 3.0], [1.5, -2.0, 0.1], [7.0, 1.0, 1.0]]]:
    print(repr(np.linalg.det(np.array(m))))
