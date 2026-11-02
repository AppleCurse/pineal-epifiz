# Sprint 1: commander evidence storage

## Migration
Existing `.pineal_memory/learnings.json` remains the source of truth; no format
conversion is required. Quiesce all writers before rollout, back up the file,
verify it is a JSON list, then deploy all writers together. The commander and
override writers use the same advisory `.learnings.lock` when paths coincide.
Do not remove or replace this lock file while writers are running. Optional
`Idempotency-Key` values are stored as hashes alongside new entries; historical
entries are not retroactively assigned keys. Keys are scoped to this store.
Clients should reuse the same key for retries of an identical payload; a reused
key with another payload returns 409.

All workers must see the same file and lock on a filesystem with working POSIX
flock, atomic rename, and file/directory fsync semantics. Unshared container
volumes, incompatible network filesystems, independent hosts and writers that do
not acquire the lock are not supported by this guarantee. Configure a shared
transactional store before deploying such a topology. The response acknowledges
the local filesystem sync operations, not agent injection or physical durability
beyond the filesystem/storage guarantees. Failure after rename is an uncertain
outcome; retry with the same idempotency key.

## Rollback
Quiesce all writers. Back up the latest store and lock metadata. Do not run the
old unlocked multi-worker writers: keep the lock-aware writer, or use a single
writer and disable concurrent/override access. Preserve the JSON and idempotency
fields; restoring an older backup discards later acknowledged writes and requires
an explicit reconciliation of those records. Test read, retry and concurrent
write after rollback before reopening traffic.
