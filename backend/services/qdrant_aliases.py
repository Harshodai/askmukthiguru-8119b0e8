"""
Mukthi Guru — Qdrant Alias & Blue-Green Collection Management

Provides atomic collection alias operations and blue-green shadow collection
lifecycle management for zero-downtime corpus updates and safe rollbacks.
Follows Delta Lake / Apache Iceberg snapshot isolation principles:
  1. Ingest/re-index into a fresh timestamped shadow collection (e.g. spiritual_wisdom_v20260925_120000).
  2. Execute post-ingestion verification gates (NDCG, tamper audit, point count check).
  3. Atomically swap the alias pointer using Qdrant's `update_collection_aliases`.
  4. Preserve previous collections for instant rollback.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from services.qdrant.client import QdrantClientManager

logger = logging.getLogger(__name__)

_DEFAULT_LEDGER_PATH = Path.home() / "mukthiguru_attribution_data" / "qdrant_alias_ledger.json"


class QdrantAliasError(Exception):
    """Base exception for Qdrant alias management errors."""

    pass


class QdrantAliasManager:
    """
    Manages Qdrant collection aliases and blue-green shadow deployments.
    """

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        ledger_path: Optional[str] = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = QdrantClientManager().client
        self._ledger_path = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER_PATH

    @property
    def client(self) -> QdrantClient:
        return self._client

    def _append_ledger_entry(self, alias: str, from_collection: Optional[str], to_collection: str) -> None:
        """Record a completed alias swap so rollback_alias can find the
        previous target without the caller having to remember it."""
        entry = {
            "alias": alias,
            "from": from_collection,
            "to": to_collection,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        entries: list[dict[str, Any]] = []
        if self._ledger_path.exists():
            try:
                entries = json.loads(self._ledger_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[QdrantAliasManager] Ledger unreadable, starting fresh: {e}")
                entries = []
        entries.append(entry)
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ledger_path.write_text(json.dumps(entries, indent=2))

    def _last_ledger_entry(self, alias: str) -> Optional[dict[str, Any]]:
        if not self._ledger_path.exists():
            return None
        try:
            entries = json.loads(self._ledger_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[QdrantAliasManager] Ledger unreadable: {e}")
            return None
        for entry in reversed(entries):
            if entry.get("alias") == alias:
                return entry
        return None

    def list_aliases(self) -> dict[str, str]:
        """
        Return a mapping of alias_name -> collection_name for all existing aliases.
        """
        try:
            resp = self._client.get_aliases()
            return {item.alias_name: item.collection_name for item in resp.aliases}
        except Exception as e:
            logger.error(f"[QdrantAliasManager] Failed to list aliases: {e}")
            raise QdrantAliasError(f"Failed to list aliases: {e}") from e

    def get_alias_target(self, alias_name: str) -> Optional[str]:
        """
        Get the collection name currently pointed to by alias_name, or None if not found.
        """
        aliases = self.list_aliases()
        return aliases.get(alias_name)

    def get_aliases_for_collection(self, collection_name: str) -> list[str]:
        """
        Return all alias names that point to the specified collection.
        """
        try:
            resp = self._client.get_collection_aliases(collection_name)
            return [item.alias_name for item in resp.aliases]
        except Exception as e:
            logger.error(f"[QdrantAliasManager] Failed to get aliases for {collection_name}: {e}")
            raise QdrantAliasError(f"Failed to get aliases for {collection_name}: {e}") from e

    def create_shadow_collection(
        self,
        base_collection_or_alias: str,
        suffix: Optional[str] = None,
    ) -> str:
        """
        Create a new timestamped shadow collection inheriting schema, vector configs,
        and payload indexes from base_collection_or_alias.

        Returns the newly created collection name.
        """
        # Resolve target collection if base is an alias
        target_name = self.get_alias_target(base_collection_or_alias) or base_collection_or_alias

        try:
            col_info = self._client.get_collection(target_name)
        except Exception as e:
            logger.error(f"[QdrantAliasManager] Base collection {target_name} not found: {e}")
            raise QdrantAliasError(f"Base collection {target_name} does not exist: {e}") from e

        # Determine shadow collection name
        if not suffix:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            suffix = f"v{now_str}"

        # Clean base name (strip existing _v<timestamp> if present to prevent stacking)
        base_clean = re.sub(r"_v\d{8}(?:_\d{6})?$", "", base_collection_or_alias)
        shadow_name = f"{base_clean}_{suffix}"

        # Extract vector and configuration from existing collection
        params = col_info.config.params
        vectors_config = params.vectors
        sparse_config = params.sparse_vectors
        quantization_config = col_info.config.quantization_config

        # Convert read-side config models to their create-side Diff equivalents.
        # create_collection() expects HnswConfigDiff / OptimizersConfigDiff / WalConfigDiff;
        # passing the raw read models raises a validation error at runtime.
        _hnsw = col_info.config.hnsw_config
        hnsw_config_diff: Optional[models.HnswConfigDiff] = (
            models.HnswConfigDiff(
                m=_hnsw.m,
                ef_construct=_hnsw.ef_construct,
                full_scan_threshold=_hnsw.full_scan_threshold,
                max_indexing_threads=_hnsw.max_indexing_threads,
                on_disk=_hnsw.on_disk,
                payload_m=_hnsw.payload_m,
            )
            if _hnsw is not None
            else None
        )

        _opt = col_info.config.optimizer_config
        optimizer_config_diff: Optional[models.OptimizersConfigDiff] = (
            models.OptimizersConfigDiff(
                deleted_threshold=_opt.deleted_threshold,
                vacuum_min_vector_number=_opt.vacuum_min_vector_number,
                default_segment_number=_opt.default_segment_number,
                max_segment_size=_opt.max_segment_size,
                memmap_threshold=_opt.memmap_threshold,
                indexing_threshold=_opt.indexing_threshold,
                flush_interval_sec=_opt.flush_interval_sec,
                max_optimization_threads=_opt.max_optimization_threads,
            )
            if _opt is not None
            else None
        )

        _wal = col_info.config.wal_config
        wal_config_diff: Optional[models.WalConfigDiff] = (
            models.WalConfigDiff(
                wal_capacity_mb=_wal.wal_capacity_mb,
                wal_segments_ahead=_wal.wal_segments_ahead,
            )
            if _wal is not None
            else None
        )

        logger.info(
            f"[QdrantAliasManager] Creating shadow collection {shadow_name} matching {target_name}"
        )

        try:
            self._client.create_collection(
                collection_name=shadow_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_config,
                quantization_config=quantization_config,
                hnsw_config=hnsw_config_diff,
                optimizers_config=optimizer_config_diff,
                wal_config=wal_config_diff,
            )
        except Exception as e:
            logger.error(f"[QdrantAliasManager] Failed to create shadow collection {shadow_name}: {e}")
            raise QdrantAliasError(f"Failed to create collection {shadow_name}: {e}") from e

        # Replicate standard payload indexes
        for field_name, schema_type in QdrantClientManager._PAYLOAD_INDEXES:
            try:
                self._client.create_payload_index(
                    collection_name=shadow_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception as e:
                logger.warning(
                    f"[QdrantAliasManager] Failed to create payload index on {shadow_name}.{field_name}: {e}"
                )

        logger.info(f"[QdrantAliasManager] Successfully created shadow collection {shadow_name}")
        return shadow_name

    def atomic_alias_swap(
        self,
        alias_name: str,
        new_target_collection: str,
    ) -> dict[str, Any]:
        """
        Atomically points alias_name to new_target_collection.
        If alias_name already points to an existing collection, the delete and create
        operations are executed in a single atomic transaction.
        """
        # Validate that the target collection exists
        try:
            self._client.get_collection(new_target_collection)
        except Exception as e:
            raise ValueError(
                f"Target collection '{new_target_collection}' does not exist: {e}"
            ) from e

        current_target = self.get_alias_target(alias_name)
        if current_target == new_target_collection:
            logger.info(
                f"[QdrantAliasManager] Alias '{alias_name}' already points to '{new_target_collection}'. No-op."
            )
            return {
                "status": "unchanged",
                "alias_name": alias_name,
                "collection_name": new_target_collection,
                "previous_collection": current_target,
            }

        operations: list[models.ChangeAliasesOperation] = []
        if current_target:
            operations.append(
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=alias_name)
                )
            )

        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=new_target_collection,
                    alias_name=alias_name,
                )
            )
        )

        logger.info(
            f"[QdrantAliasManager] Swapping alias '{alias_name}': {current_target} -> {new_target_collection}"
        )

        try:
            res = self._client.update_collection_aliases(change_aliases_operations=operations)
            if not res:
                raise QdrantAliasError(f"update_collection_aliases returned false for {alias_name}")
        except Exception as e:
            logger.error(f"[QdrantAliasManager] Failed atomic alias swap for {alias_name}: {e}")
            raise QdrantAliasError(f"Atomic alias swap failed: {e}") from e

        # Post-condition verification
        verified_target = self.get_alias_target(alias_name)
        if verified_target != new_target_collection:
            raise QdrantAliasError(
                f"Alias swap verification failed! Expected '{new_target_collection}', got '{verified_target}'"
            )

        self._append_ledger_entry(alias_name, current_target, new_target_collection)

        return {
            "status": "success",
            "alias_name": alias_name,
            "collection_name": new_target_collection,
            "previous_collection": current_target,
            "swapped_at": datetime.now(timezone.utc).isoformat(),
        }

    def rollback_alias(
        self,
        alias_name: str,
        previous_collection: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Roll back alias_name to previous_collection atomically.

        If previous_collection is not given, it is read from the last swap
        ledger entry for this alias.
        """
        if previous_collection is None:
            last_entry = self._last_ledger_entry(alias_name)
            if not last_entry or not last_entry.get("from"):
                raise QdrantAliasError(
                    f"No ledger entry with a previous collection found for alias "
                    f"'{alias_name}'; pass previous_collection explicitly."
                )
            previous_collection = last_entry["from"]

        logger.warning(
            f"[QdrantAliasManager] Executing ROLLBACK for alias '{alias_name}' to '{previous_collection}'"
        )
        return self.atomic_alias_swap(
            alias_name=alias_name,
            new_target_collection=previous_collection,
        )

    def cleanup_old_collections(
        self,
        alias_name: str,
        prefix: Optional[str] = None,
        keep_last_n: int = 3,
        dry_run: bool = True,
    ) -> list[str]:
        """
        List or delete historical shadow collections matching the prefix.

        SAFETY INVARIANT:
        The collection currently pointed to by alias_name is strictly protected
        and will never be deleted, even if keep_last_n is 0.
        """
        if keep_last_n < 1:
            raise ValueError("keep_last_n must be >= 1 to ensure rollback safety.")

        all_cols = [c.name for c in self._client.get_collections().collections]

        match_prefix = prefix or f"{alias_name}_v"
        matching_cols = [c for c in all_cols if c.startswith(match_prefix)]
        # Sort lexicographically by version timestamp
        matching_cols.sort()

        if len(matching_cols) <= keep_last_n:
            return []

        # Candidate collections to remove (oldest first)
        candidates = matching_cols[:-keep_last_n]
        # Guarantee any collection that ANY alias currently points to is
        # never deleted, not just this alias_name's own current target.
        protected_targets = set(self.list_aliases().values())
        candidates = [c for c in candidates if c not in protected_targets]

        deleted: list[str] = []
        for col_name in candidates:
            if dry_run:
                logger.info(f"[QdrantAliasManager] [DRY RUN] Would delete stale collection: {col_name}")
                deleted.append(col_name)
            else:
                logger.warning(f"[QdrantAliasManager] Deleting stale shadow collection: {col_name}")
                try:
                    self._client.delete_collection(col_name)
                    deleted.append(col_name)
                except Exception as e:
                    logger.error(f"[QdrantAliasManager] Failed to delete {col_name}: {e}")

        return deleted
