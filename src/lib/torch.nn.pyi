# crate: pyrt/torch
# rust: rupy::pyrt::lib::torch::nn
"""rupy package `torch.nn` (`import torch.nn as nn`, `from torch import nn`): see torch.pyi."""

from torch import Loss, Module
from rust import Result

@rust("rupy::pyrt::lib::torch::nn::linear")
def Linear(in_features: int, out_features: int, bias: bool = True) -> Result[Module, RuntimeError]: ...

@rust("rupy::pyrt::lib::torch::nn::relu")
def ReLU() -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::sigmoid")
def Sigmoid() -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::tanh")
def Tanh() -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::softmax")
def Softmax(dim: int) -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::flatten")
def Flatten() -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::identity")
def Identity() -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::sequential")
def Sequential(*modules: Module) -> Module: ...

@rust("rupy::pyrt::lib::torch::nn::mse")
def MSELoss() -> Loss: ...

@rust("rupy::pyrt::lib::torch::nn::l1")
def L1Loss() -> Loss: ...

@rust("rupy::pyrt::lib::torch::nn::cross_entropy_loss")
def CrossEntropyLoss() -> Loss: ...
