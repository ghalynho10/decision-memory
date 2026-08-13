# 0005. Runtime adapter loading rationale

## Context

Spec 0003 established a useful `SourceAdapter` protocol, but the CLI still constructs `JsmasteryAdapter` directly and passes its module level version constant separately. The application use case also rejects a corpus without `docs/specs/` before an adapter can inspect it. A third party implementation can satisfy the protocol in code and still has no runtime path into `adapt`, no way to own its source layout, and no portable source for identity and version even though version participates in fingerprints and the manifest.

The feature must preserve two shipped contracts. Canonical `validate FILE` answers whether one written record is valid. `adapt --dry-run` answers what an adaptation run would write. An adapter author needs a third question, whether an adapter can discover, fingerprint, and parse a source corpus safely, with violations separated from crashes. Folding these questions together would make failures harder to interpret.

This is a local Python CLI with small corpora and no service boundary. The existing stack already provides `importlib`, PyYAML, Pydantic, typed application outcomes, and a Clean Architecture split. The design should expose the existing boundary without creating a plugin framework, new dependency, discovery registry, or sandbox.

## Options considered

### Option 1: Extend the existing protocol with one explicit runtime loader

Keep `SourceAdapter`, add identity and version properties, and load one named instance from `package.module:attribute`. Route both the built in name and third party objects through the same use cases. (basis: spec 0003, the accepted adapter protocol; Python `importlib.import_module`; Python typing protocol limits)

**Pros**:

1. Small change around code that already works.
2. Explicit module and attribute errors need no export naming convention.
3. Identity, version, adaptation, and later conformance share one object contract.

**Cons**:

1. Importing executes trusted code.
2. Presence checks cannot prove signatures or behavior.
3. The accepted protocol gains two required properties.

### Option 2: Discover installed adapters through package entry points

Adapters register metadata in their Python distribution and the CLI discovers them by a named entry point group. This is a standard plugin discovery mechanism and removes manual module selectors. (basis: PyPA plugin discovery and entry point specification)

**Pros**:

1. Friendly stable names and automatic discovery.
2. Distribution metadata owns plugin registration.
3. Scales better when many adapters exist.

**Cons**:

1. Adds packaging work before one external adapter exists.
2. Discovery and duplicate name policy become new product behavior.
3. Still requires runtime object validation after loading.

### Option 3: Require a fixed module export or factory

Accept a module name and require `adapter` or `get_adapter()` to exist. This shortens the selector but moves part of the contract into an implicit naming convention. (basis: the current direct construction in `src/decision_memory/cli.py`; Python import package naming)

**Pros**:

1. Short selectors.
2. A factory can hide construction details.

**Cons**:

1. A different export name produces a convention failure that looks like a broken adapter.
2. Supporting instances, classes, and factories invites runtime guessing.
3. Factory arguments and lifecycle would need another contract.

### Option 4: Replace the adapter boundary with a new plugin framework

Introduce registration, discovery, lifecycle hooks, configuration schemas, and a new plugin abstraction, then migrate the built in adapter. (basis: enhancement migration practice; `AGENTS.md`, Skateboard delivery)

**Pros**:

1. Could support a broad future ecosystem.
2. Central registration could own names and versions.

**Cons**:

1. Replaces accepted working code without evidence that the larger system is needed.
2. Delays the first external adapter path.
3. Creates migration and compatibility policy before real usage can shape it.

## Rationale

Option 1 fixes the actual gap in place. The application boundary already has the right three source operations, and the infrastructure layer is already the correct home for filesystem and import behavior. Adding an explicit loader is cheaper and safer than replacing that boundary. The runner up is entry point discovery, a sound packaging standard that becomes worthwhile only when explicit selectors create measured friction. (basis: spec 0003; `AGENTS.md`, Clean Architecture and Skateboard approach; PyPA plugin discovery)

The explicit attribute is the important constraint. It avoids a hidden export name and avoids guessing whether the selected value is a class, factory, or instance. Adapter authors who need construction logic keep it in their own module and export the created object. Identity and version move onto that object because the manifest and fingerprints need the same metadata for every implementation. Format specific corpus checks move into discovery because a generic application use case cannot know whether an adapter expects `docs/specs/`, `decisions/`, or another layout. (basis: Python `importlib.import_module`; spec 0003 fingerprint, manifest, and discovery contracts)

The runtime gate stays deliberately shallow. Manual checks can prove nonempty metadata and callable presence, but signature inspection would still not prove semantic behavior. Feature 7 already exists to run deeper conformance and anti fabrication checks, so this slice names the limitation instead of presenting a weak reflection check as safety. (basis: Python runtime checkable protocol documentation; scope feature 7)

Configuration is strict because silent fallback is dangerous here. A misspelled `adapter` key could make the built in adapter run against the wrong corpus and produce plausible skips. PyYAML safe loading plus Pydantic forbidden extras reuse installed tools and keep file parsing in infrastructure. (basis: `AGENTS.md`, existing stack; Pydantic extra field behavior; PyYAML safe loading)

## References

**Project sources**:

1. `AGENTS.md`, Clean Architecture, strict types, existing dependencies, and Skateboard delivery
2. `docs/specs/0003-jsmastery-specs-adapter/index.md`, accepted adapter, fingerprint, manifest, and dry run contracts
3. `src/decision_memory/application/adapter.py`, current protocol and adapt use case
4. `src/decision_memory/cli.py`, current direct built in adapter construction and validate surface
5. `docs/scope/scope.md`, runtime loading and conformance feature boundaries

**Practices and standards**:

1. Explicit object selection over implicit export naming
2. Strict configuration parsing with safe YAML construction
3. Fix in place for a small live system enhancement
4. Python package entry points as a deferred discovery mechanism

**Links**:

1. Python `importlib.import_module`: https://docs.python.org/3.11/library/importlib.html#importlib.import_module
2. Python `ModuleNotFoundError`: https://docs.python.org/3/library/exceptions.html#ModuleNotFoundError
3. Python runtime checkable protocols: https://docs.python.org/3/library/typing.html#typing.runtime_checkable
4. PyPA distribution packages and import packages: https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/
5. PyPA plugin discovery: https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
6. PyPA entry point specification: https://packaging.python.org/en/latest/specifications/entry-points/
7. Pydantic forbidden extra fields: https://docs.pydantic.dev/latest/api/config/#extra
8. PyYAML safe loading: https://pyyaml.org/wiki/PyYAMLDocumentation
