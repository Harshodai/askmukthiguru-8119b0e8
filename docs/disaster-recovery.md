# Disaster Recovery

Backup utilities exist for Qdrant, Neo4j, LightRAG checkpoints, retention, cleanup, and encryption-key operations. No backup/restore or destructive operation was run against production or user data. No measured RPO/RTO is available.

A release drill must snapshot all stores in an isolated topology, terminate services and workers, restore in dependency order, replay idempotent jobs, and verify counts, tenant isolation, job ownership, vault behavior, and cross-store deletion. Include partial restore, key-loss expectations, and worker interruption. Until this is completed, disaster recovery is a release blocker.
