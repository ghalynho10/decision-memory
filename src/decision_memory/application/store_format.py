"""Application: the versioned store format (spec 0008 AC-12).

Format 2 pins the Chroma cosine metric, stores ``chunk_id`` as locator
metadata, and enables exact accepted id constraints in semantic search. A
format 1 store refuses query and points to ``ingest --rebuild``. The format
lives here so application code can refuse without importing infrastructure.
"""

STORE_FORMAT_VERSION = 2
