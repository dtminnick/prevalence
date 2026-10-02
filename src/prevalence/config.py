"""Configuration models and loading from YAML / CSV.

All run parameters live in YAML and are validated here, so a typo or an
impossible value fails at load time with a clear message.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal, Optional, Type, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from prevalence.domain import BetaPrior, Observation, Variant

StratumView = Literal["by_stratum", "combined", "both"]
M = TypeVar("M", bound=BaseModel)


class ConfigError(Exception):
    """Raised when a config or data file is missing, malformed, or inconsistent."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SampleSizeGrid(_Strict):
    """Sample sizes to evaluate: start, start + step, ... up to and including stop."""

    start: int = Field(gt=0)
    stop: int = Field(gt=0)
    step: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_order(self) -> "SampleSizeGrid":
        if self.stop < self.start:
            raise ValueError("sample_sizes.stop must be >= start")
        return self

    def values(self) -> list[int]:
        return list(range(self.start, self.stop + 1, self.step))


class RecommendationConfig(_Strict):
    """Thresholds for the recommendation flag.

    A variant whose minimum sample size is within ``borderline_multiple`` times
    the practical limit is flagged Borderline rather than Synthetic / targeted.
    """

    borderline_multiple: float = Field(ge=1)


class OutputConfig(_Strict):
    excel: bool = False


class RunConfig(_Strict):
    pilot: str = Field(min_length=1)
    model: str = Field(min_length=1)
    target_n: int = Field(ge=1)
    target_prob: float = Field(gt=0, lt=1)
    sample_sizes: SampleSizeGrid
    max_practical_sample_size: int = Field(gt=0)
    population_per_window: int = Field(gt=0)
    recommendation: RecommendationConfig
    stratum_view: StratumView = "combined"
    # One stratification dimension in v1: {dimension_name: {stratum: share}}.
    strata: dict[str, dict[str, float]] = Field(default_factory=dict)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def _check_consistency(self) -> "RunConfig":
        if self.max_practical_sample_size > self.population_per_window:
            raise ValueError("max_practical_sample_size cannot exceed population_per_window")
        if len(self.strata) > 1:
            raise ValueError(
                f"v1 supports a single stratification dimension, got {sorted(self.strata)}"
            )
        for dimension, shares in self.strata.items():
            if not shares:
                raise ValueError(f"strata.{dimension} has no strata listed")
            if any(s <= 0 for s in shares.values()):
                raise ValueError(f"strata.{dimension}: every share must be > 0")
            total = sum(shares.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"strata.{dimension}: shares must sum to 1 (got {total})")
        if self.stratum_view in ("by_stratum", "both") and not self.strata:
            raise ValueError(f"stratum_view '{self.stratum_view}' requires strata to be defined")
        return self

    @property
    def stratum_dimension(self) -> Optional[str]:
        return next(iter(self.strata), None)

    @property
    def stratum_shares(self) -> dict[str, float]:
        dimension = self.stratum_dimension
        return dict(self.strata[dimension]) if dimension else {}


class VariantConfig(_Strict):
    name: str = Field(min_length=1)
    prior: BetaPrior
    parent: Optional[str] = None
    target_n: Optional[int] = Field(default=None, ge=1)
    target_prob: Optional[float] = Field(default=None, gt=0, lt=1)


class VariantsFile(_Strict):
    variants: list[VariantConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_hierarchy(self) -> "VariantsFile":
        names = [v.name for v in self.variants]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"duplicate variant names: {duplicates}")
        parents = {v.name: v.parent for v in self.variants}
        for name, parent in parents.items():
            if parent is not None and parent not in parents:
                raise ValueError(f"variant '{name}' has unknown parent '{parent}'")
        for start in parents:
            seen: set[str] = set()
            node: Optional[str] = start
            while node is not None:
                if node in seen:
                    raise ValueError(f"cycle in parent chain involving '{start}'")
                seen.add(node)
                node = parents[node]
        return self


class ConfigLoader:
    """Reads and validates run config, variant config, and count data."""

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError as exc:
            raise ConfigError(f"File not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: expected a mapping at the top level")
        return data

    @classmethod
    def _validate(cls, model: Type[M], data: dict, path: Path) -> M:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"{path}: {exc}") from exc

    @classmethod
    def load_run(cls, path: str | Path) -> RunConfig:
        path = Path(path)
        return cls._validate(RunConfig, cls._read_yaml(path), path)

    @classmethod
    def load_variants(cls, path: str | Path) -> list[VariantConfig]:
        path = Path(path)
        return cls._validate(VariantsFile, cls._read_yaml(path), path).variants

    @classmethod
    def load_observations(cls, path: str | Path) -> list[Observation]:
        """Read counts CSV with columns variant, stratum, k, n (stratum may be blank)."""
        path = Path(path)
        required = {"variant", "stratum", "k", "n"}
        try:
            f = open(path, newline="", encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigError(f"File not found: {path}") from exc
        with f:
            reader = csv.DictReader(f)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ConfigError(f"{path}: missing columns {sorted(missing)}")
            observations = []
            for line_no, row in enumerate(reader, start=2):
                try:
                    stratum = (row["stratum"] or "").strip() or None
                    observations.append(
                        Observation(
                            variant=row["variant"].strip(),
                            stratum=stratum,
                            k=int(row["k"]),
                            n=int(row["n"]),
                        )
                    )
                except (ValueError, TypeError) as exc:
                    raise ConfigError(f"{path} line {line_no}: {exc}") from exc
        return observations

    @classmethod
    def build_variants(
        cls,
        run: RunConfig,
        variant_configs: list[VariantConfig],
        observations: list[Observation],
    ) -> list[Variant]:
        """Resolve per-variant targets and attach observations, checking consistency."""
        variants = {
            vc.name: Variant(
                name=vc.name,
                prior=vc.prior,
                parent=vc.parent,
                target_n=vc.target_n if vc.target_n is not None else run.target_n,
                target_prob=vc.target_prob if vc.target_prob is not None else run.target_prob,
            )
            for vc in variant_configs
        }
        known_strata = set(run.stratum_shares)
        for obs in observations:
            if obs.variant not in variants:
                raise ConfigError(f"Counts reference unknown variant '{obs.variant}'")
            if known_strata:
                if obs.stratum is None:
                    raise ConfigError(
                        f"Counts for '{obs.variant}' have no stratum, but the run defines strata"
                    )
                if obs.stratum not in known_strata:
                    raise ConfigError(
                        f"Counts for '{obs.variant}' use unknown stratum '{obs.stratum}' "
                        f"(known: {sorted(known_strata)})"
                    )
            elif obs.stratum is not None:
                raise ConfigError(
                    f"Counts for '{obs.variant}' have stratum '{obs.stratum}', "
                    "but the run defines no strata"
                )
            variants[obs.variant].add_observation(obs)
        return list(variants.values())
