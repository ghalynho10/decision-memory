"""Pipeline signature tests (spec 0007 AC-5, AC-8).

The signature must be stable across calls and change when any pipeline input
changes, so a store built with different settings can never be silently read.
"""

from __future__ import annotations

from dataclasses import replace

from decision_memory.application.pipeline import (
    DEFAULT_PIPELINE_CONFIG,
    pipeline_signature,
)


def test_signature_is_stable_across_calls() -> None:
    assert pipeline_signature() == pipeline_signature()
    assert pipeline_signature(DEFAULT_PIPELINE_CONFIG) == pipeline_signature()


def test_signature_changes_with_any_pipeline_input() -> None:
    base = pipeline_signature()
    variants = [
        replace(DEFAULT_PIPELINE_CONFIG, model="other"),
        replace(DEFAULT_PIPELINE_CONFIG, dimensions=768),
        replace(DEFAULT_PIPELINE_CONFIG, encoding="other"),
        replace(DEFAULT_PIPELINE_CONFIG, chunker_version="v2"),
        replace(DEFAULT_PIPELINE_CONFIG, prefix_version="v2"),
        replace(DEFAULT_PIPELINE_CONFIG, target=500),
        replace(DEFAULT_PIPELINE_CONFIG, overlap="0.2"),
        replace(DEFAULT_PIPELINE_CONFIG, atomic_paths=("x",)),
    ]
    for config in variants:
        assert pipeline_signature(config) != base


def test_signature_is_lowercase_hex() -> None:
    signature = pipeline_signature()
    assert len(signature) == 64
    assert signature == signature.lower()
