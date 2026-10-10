# Chroma Index Deployment and Release Lifecycle

## Production architecture

SmartDex deploys Chroma as a versioned application artifact:

1. `chroma_db/` is the locally validated source artifact used as Docker build input.
2. The image packages it once at `/app/chroma_seed/` with root ownership and read-only permissions.
3. `/app/chroma_seed/manifest.json` identifies and authenticates the artifact.
4. On every container start, `scripts/init_chroma.py` validates the seed and creates a fresh writable copy at `/tmp/smartdex/chroma_runtime/`.
5. Gunicorn starts only after the runtime copy passes collection, document-count, metadata, and offline similarity-query checks.
6. API retrieval uses `get_collection`; it cannot silently create a missing collection.

The runtime copy is disposable. It must not be mounted or treated as durable state. Each
container owns an independent copy, and a restart deliberately replaces any previous
runtime contents from the immutable seed.

Current artifact identity:

- index version: `chroma-index-v1`
- collection: `smartdex_kb`
- documents: `101`
- embedding model: `text-embedding-3-small`
- manifest: `chroma_index_manifest.json`

The count is artifact metadata, not an application constant. A later intentionally
released index may declare a different count in its manifest.

## Runtime validation sequence

The startup initializer performs these operations without network access:

1. Parses and validates the versioned manifest.
2. Verifies SHA-256 checksums for every declared seed file.
3. Opens `chroma.sqlite3` using SQLite immutable/read-only mode.
4. Verifies the named collection, exact declared count, and required metadata coverage.
5. Copies the seed into a temporary sibling of the runtime directory.
6. Makes the copy owner-writable while leaving the seed unchanged.
7. Opens the copied Chroma index and verifies its count and metadata.
8. Uses a stored vector as an offline representative similarity query.
9. Atomically promotes the candidate directory and removes the old runtime copy.
10. Exits successfully so the entrypoint can `exec` Gunicorn.

Any failure stops container startup with an actionable error. The initializer never
imports ingestion code, contacts OpenAI, creates embeddings, or creates a collection.

## Controlled index regeneration

Index regeneration is a maintenance release operation. Never point ingestion at
`chroma_db/`, `/app/chroma_seed/`, or a running container's `CHROMA_DIR`.

1. Update the source documents under `static/documents/` and review those changes.
2. Create a new empty candidate directory outside the validated artifact.
3. In an explicitly authorized maintenance environment with the approved OpenAI key,
   set `CHROMA_DIR` to that candidate and run `venv/bin/python scripts/ingest_docs.py`.
   This is the only workflow permitted to create the collection and add documents.
4. Inspect `smartdex_kb`, verify its exact document count, required metadata, source
   coverage, and 1536-dimensional `text-embedding-3-small` vectors.
5. Run representative retrieval queries and review their returned sources and distances.
6. Copy the candidate to a separate release-candidate location. Do not replace the
   current `chroma_db/` yet.
7. Assign an intentional version such as `chroma-index-v2`. Never derive the version
   solely from a timestamp and never increment it during startup.
8. Create a new manifest using the existing schema, record the approved count/model/time,
   and calculate SHA-256 for every Chroma file relative to the artifact root. Do not put
   the manifest itself in its checksum map.
9. Run `validate_seed(candidate, manifest)` and initialize a disposable runtime copy.
   Confirm the candidate seed checksums remain identical before and after validation.
10. After approval, replace the repository's ignored local `chroma_db/` artifact and
    tracked `chroma_index_manifest.json` together. Preserve the previous artifact in a
    protected release location; do not merge only one half of the pair.
11. Build a newly tagged application image. No build step may invoke ingestion.
12. Run Django regressions and the complete container health, Chroma, RAG, static-file,
    restart, recreate, invalid-seed, and multi-container smoke tests.
13. Deploy a new application revision only after approval. Retain the prior image digest
    and index version for rollback.

Example offline validation (this does not ingest or call OpenAI):

```bash
CHROMA_SEED_DIR=/path/to/candidate \
CHROMA_DIR=/tmp/smartdex/candidate-runtime \
CHROMA_MANIFEST_PATH=/path/to/candidate-manifest.json \
venv/bin/python -m scripts.init_chroma
```

## Rollback

Rollback is image-based. Redeploy the prior immutable application image by its known
tag or digest. Its entrypoint reconstructs the matching runtime index from its packaged
seed. Do not copy files backward into a running container and do not edit the seed in
place. After rollback, verify the startup log reports the expected old index version,
then repeat the health and representative retrieval checks.

## Security and operational rules

- Secrets are runtime environment values and are excluded from the image build context.
- `/app/chroma_seed/` is owned by root, directories are `0555`, and files are `0444`.
- `/tmp/smartdex/chroma_runtime/` is owned by the non-root application user and uses
  owner-only permissions.
- Chroma's SQLite writes are allowed only in the disposable runtime copy.
- `scripts/ingest_docs.py` is manual maintenance tooling, never a Docker build or startup step.
- No runtime API path imports or invokes ingestion.
- Independent containers never share a runtime directory.
