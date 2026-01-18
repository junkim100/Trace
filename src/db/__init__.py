"""
Trace Database Module

This module provides database initialization, migration management,
connection handling, and vector storage for the Trace application.
"""

from .migrations import (
    MigrationRunner,
    get_connection,
    get_current_version,
    init_database,
)
from .vectors import (
    DEFAULT_DIMENSIONS,
    VEC_TABLE_NAME,
    VectorStore,
    count_embeddings,
    delete_embedding,
    deserialize_float32,
    get_embedding_by_source,
    get_embedding_vector,
    init_vector_table,
    load_sqlite_vec,
    query_similar,
    serialize_float32,
    store_embedding,
)

__all__ = [
    # Migrations
    "MigrationRunner",
    "get_connection",
    "get_current_version",
    "init_database",
    # Vectors
    "DEFAULT_DIMENSIONS",
    "VEC_TABLE_NAME",
    "VectorStore",
    "count_embeddings",
    "delete_embedding",
    "deserialize_float32",
    "get_embedding_by_source",
    "get_embedding_vector",
    "init_vector_table",
    "load_sqlite_vec",
    "query_similar",
    "serialize_float32",
    "store_embedding",
]
