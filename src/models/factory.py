"""Resolves the ``model:`` name in run.yaml to a model class."""
from __future__ import annotations

from typing import Type

from prevalence.models.base import PrevalenceModel
from prevalence.models.conjugate import ConjugateBetaModel


class ModelFactory:
    _registry: dict[str, Type[PrevalenceModel]] = {
        "conjugate_beta": ConjugateBetaModel,
    }

    @classmethod
    def register(cls, name: str, model_cls: Type[PrevalenceModel]) -> None:
        cls._registry[name] = model_cls

    @classmethod
    def create(cls, name: str) -> PrevalenceModel:
        try:
            return cls._registry[name]()
        except KeyError:
            raise ValueError(
                f"Unknown model '{name}'. Available: {sorted(cls._registry)}"
            ) from None
