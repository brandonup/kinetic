"""
RAG retrieval service package.

Implements the MVP retrieval pipeline:
  Embed query → Vector search → MMR selection → Similarity threshold → Citation assembly

See docs/rag-architecture.md for architecture decisions.
See docs/db-schema-spec.md §13 for knowledge_base_chunks schema.
"""
