"""Application: the immutable pipeline signature (spec 0007 AC-5, AC-8).

The signature hashes every input that changes what an embedding means: the
embedding model and dimensions, the tiktoken encoding, the chunker and prefix
versions, the token target, the overlap string, the paragraph and sentence
rule versions, and the atomic path set. Any change forces an explicit rebuild;
ingest compares it before mutation and query compares it before question
embedding, so a store built with different settings can never be silently read.
"""

from __future__ import annotations

from dataclasses import dataclass

from decision_memory.application.canonical import canonical_json, sha256_hex

# The embedding model and dimensions settled by spec 0001 and kept in force by
# spec 0007's configuration section.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
TIKTOKEN_ENCODING = "cl100k_base"

# Chunker constants from spec 0007 AC-4 and AC-5.
CHUNKER_VERSION = "field-boundary-v1"
PREFIX_VERSION = "embedding-prefix-v1"
TOKEN_TARGET = 400
OVERLAP_STRING = "0.15"
PARAGRAPH_RULE_VERSION = "paragraph-v1"
SENTENCE_RULE_VERSION = "sentence-v1"
ATOMIC_PATHS = ("decision.alternatives[i]",)

# The embedding model's hard input limit in tokens (pinned in spec 0007).
MODEL_TOKEN_LIMIT = 8191

SIGNATURE_SCHEMA = 1


@dataclass(frozen=True)
class PipelineConfig:
    """Every value the pipeline signature hashes."""

    model: str = EMBEDDING_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS
    encoding: str = TIKTOKEN_ENCODING
    chunker_version: str = CHUNKER_VERSION
    prefix_version: str = PREFIX_VERSION
    target: int = TOKEN_TARGET
    overlap: str = OVERLAP_STRING
    paragraph_rule_version: str = PARAGRAPH_RULE_VERSION
    sentence_rule_version: str = SENTENCE_RULE_VERSION
    atomic_paths: tuple[str, ...] = ATOMIC_PATHS


# A module singleton so function defaults never call a constructor (B008).
DEFAULT_PIPELINE_CONFIG = PipelineConfig()


def pipeline_signature(config: PipelineConfig = DEFAULT_PIPELINE_CONFIG) -> str:
    """Lowercase SHA256 hex over canonical JSON of the pipeline inputs."""
    mapping = {
        "signature_schema": SIGNATURE_SCHEMA,
        "model": config.model,
        "dimensions": config.dimensions,
        "encoding": config.encoding,
        "chunker_version": config.chunker_version,
        "prefix_version": config.prefix_version,
        "target": config.target,
        "overlap": config.overlap,
        "paragraph_rule_version": config.paragraph_rule_version,
        "sentence_rule_version": config.sentence_rule_version,
        "atomic_paths": list(config.atomic_paths),
    }
    return sha256_hex(canonical_json(mapping))
