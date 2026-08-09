# Adapter author guide

This guide explains how to write a decision-memory adapter that runs through the
real CLI without forking this repository. It is a companion to the starter
package in `examples/starter-adapter`, which you can read as a complete working
example. The starter reads a tiny neutral Markdown format under `decisions/`.
Everything the contract needs lives in one module,
`starter_adapter/adapter.py`.

A deeper proof of the protocol is feature 7, the adapter conformance suite and
`test-adapter` command. That suite checks method signatures, protocol behavior,
anti fabrication guarantees, and format drift fixtures. This guide covers how
to build and run an adapter today.

## What an adapter is

An adapter turns project native artifacts into canonical decision records. It
reads; it never writes. One adapter instance is loaded by the CLI and run
through the same `adapt` and `validate` use cases as the built in
`jsmastery-specs` adapter.

An adapter is a plain Python object with three methods and two metadata
properties:

- `adapter_id`: a nonempty string naming the adapter.
- `adapter_version`: a nonempty string naming this version. It lands in the
  manifest and in every fingerprint this adapter produces.
- `discover(corpus_root)`: return what this corpus holds as decision sources,
  plus skips and collisions.
- `parse(spec)`: turn one discovered source into a canonical record, with
  violations and attempted fields.
- `fingerprint(spec)`: a stable digest over everything that contributes to the
  record, so a second run rewrites only what changed.

## Package setup

Make a small installable package. The starter shows the minimal shape:

```text
starter-adapter/
  pyproject.toml
  starter_adapter/
    __init__.py
    adapter.py
  decisions/          # fixtures, optional in your own package
```

The `pyproject.toml` is minimal: a name, a version, a description, and a build
backend. The package must be importable in the same environment as
decision-memory. Install it there, for example from a checkout:

```bash
uv pip install -e ./examples/starter-adapter
```

The module must import cleanly at load time, because the CLI imports it. Any
module level code runs when the selector is loaded.

## Selector syntax

The CLI names an adapter with a selector:

```text
package.module:attribute
```

The module is an absolute dotted Python name, like `starter_adapter.adapter`.
The attribute is one Python identifier naming an already created instance. The
built in name is `jsmastery-specs`; it contains a hyphen, so it can never be a
valid module name and can never collide.

The selector parser rejects relative modules, missing colons, empty parts,
dotted attribute traversal, file paths, and non identifier parts. A malformed
selector is a usage error and exits with code 2. The attribute must be an
instance, never a class and never a factory function.

## The instance contract

The loader checks the contract before any corpus access. It checks three
things only: both metadata values are nonempty strings, and `discover`, `parse`,
and `fingerprint` are present and callable. It does not check method signatures
or behavior. A wrong signature or broken behavior shows up when the method runs,
which is what the conformance suite in feature 7 will catch.

The loader reads the attribute as an already created instance. It never calls
it. So export the instance itself:

```python
adapter = StarterAdapter()
```

## Result types

`discover` returns a `DiscoveryResult`:

- `specs`: the discovered sources, each with an `id`, a `root`, the
  `corpus_root`, and `contributing_files` (every file that feeds the record).
- `skipped`: sources you decided not to adapt, each with a path and a reason.
- `collisions`: two or more sources that derived the same id.
- `corpus_error`: an optional string naming a missing required layout. Set it
  when the corpus root is a directory but lacks the structure your adapter
  needs. The run maps it to exit code 3 and prints the message. The built in
  adapter uses it when `docs/specs/` is absent; the starter uses it when
  `decisions/` is absent.

`parse` returns an `AdaptationResult`:

- `record`: the canonical record, or `None` when the source cannot be adapted.
- `violations`: every rule the adapter emits plus what the record validator
  returns.
- `attempted_fields`: every canonical field whose source section you tried to
  fill and found absent or empty.
- `unresolved_mention_count`: a count of code path mentions that did not
  resolve, for the `evidence.mentions_unresolved` warning.
- `fingerprint`: the same value `fingerprint(spec)` returns.

## The no fabrication rule

The core guarantee is that an adapter never invents a value. Degrade rather
than guess:

- A source that is not a decision produces no record, and is skipped with a
  stated reason (the starter skips files with no Decision section).
- A field whose source section is absent is left unset and named in
  `attempted_fields`, so the validator can flag it.
- A missing rejection reason is reported as missing, not invented.

## Exception behavior

The loader does not catch exceptions from your methods for you. What happens
when a method raises is contained by the use case, not retried:

- If `discover` raises, the run stops, reports the failed phase and the
  exception, and exits with code 1.
- If `fingerprint` raises for one source, `parse` is skipped for that source,
  the source is reported as failed, and later sources still run.
- If `parse` raises, that source is reported as failed and later sources still
  run.
- Either source failure records the failed operation plus the exception type
  and message. A source violation (your adapter completed and found bad data)
  and an unexpected exception (your adapter failed) are different result kinds.

Prefer returning violations over raising for bad source data. Reserve raising
for genuine implementation failures.

## Config use

A project can persist settings in `.decision-memory.yml`, searched from the
current directory upward and stopping at the nearest Git root:

```yaml
adapter: starter_adapter.adapter:adapter
corpus_root: ./project
output: ./project/.decision-memory/records
```

Each key is optional. Command input wins, then config, then the default
(`jsmastery-specs` for the adapter; the resolved corpus root's
`.decision-memory/records` for output). Relative paths resolve from the config
file directory. An invalid config file fails the command with exit code 1 and
names the path and the error.

## Trusted code

A third party adapter is trusted executable Python code. Importing it runs its
module code with the same filesystem, environment, and process permissions as
`decision-memory`. The CLI does not sandbox it, does not change the import
path, and does not load direct files. Only install and run adapters you trust.

## Commands

Validate an adapter against a corpus without writing anything:

```bash
decision-memory validate ./project --adapter starter_adapter.adapter:adapter
```

The report names the adapter, the discovery totals, every skip and collision,
every source result, and violations with their rule ids. It writes nothing.

Adapt a corpus into records:

```bash
decision-memory adapt ./project --adapter starter_adapter.adapter:adapter
```

Records land under the resolved output directory, and the manifest records the
adapter version you reported. Use `--dry-run` to preview without writing.

With config in place, the `--adapter` and corpus arguments can be omitted:

```bash
decision-memory adapt
decision-memory validate
```

## Where to go next

Read the starter package end to end, then write your own adapter and run it
against a real corpus. When you want a stronger proof, feature 7 provides the
conformance suite and the `test-adapter` command, which check signatures,
protocol behavior, anti fabrication behavior, and format drift fixtures.
