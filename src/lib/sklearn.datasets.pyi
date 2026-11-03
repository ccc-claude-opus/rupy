# crate: pyrt/sklearn
# rust: rupy::pyrt::lib::sklearn
"""rupy package `sklearn.datasets` (a subset of scikit-learn, in Rust)."""

from numpy import ndarray


@rust("rupy::pyrt::lib::sklearn::Bunch")
class Bunch:
    @property
    def data(self) -> ndarray: ...
    @property
    def target(self) -> ndarray: ...
    @property
    def feature_names(self) -> list[str]: ...
    @property
    def target_names(self) -> list[str]: ...


def load_iris() -> Bunch: ...
