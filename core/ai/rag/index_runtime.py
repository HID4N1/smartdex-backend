import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

import chromadb


class IndexValidationError(RuntimeError):
    """Raised when a packaged or runtime Chroma artifact is unusable."""


REQUIRED_MANIFEST_FIELDS = {
    "manifest_schema",
    "index_version",
    "collection_name",
    "document_count",
    "embedding_model",
    "artifact_created_at",
    "required_metadata_keys",
    "checksums",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def load_manifest(manifest_path):
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexValidationError(f"Cannot read Chroma manifest at {path}: {exc}") from exc

    missing = sorted(REQUIRED_MANIFEST_FIELDS - manifest.keys())
    if missing:
        raise IndexValidationError(
            f"Chroma manifest is missing required fields: {', '.join(missing)}"
        )
    if manifest["manifest_schema"] != 1:
        raise IndexValidationError("Unsupported Chroma manifest schema.")
    if not isinstance(manifest["index_version"], str) or not VERSION_RE.fullmatch(
        manifest["index_version"]
    ):
        raise IndexValidationError("Chroma manifest has an invalid index version.")
    if not isinstance(manifest["collection_name"], str) or not manifest["collection_name"]:
        raise IndexValidationError("Chroma manifest has an invalid collection name.")
    if not isinstance(manifest["document_count"], int) or manifest["document_count"] < 1:
        raise IndexValidationError("Chroma manifest has an invalid document count.")
    if not isinstance(manifest["embedding_model"], str) or not manifest["embedding_model"]:
        raise IndexValidationError("Chroma manifest has an invalid embedding model.")
    if not isinstance(manifest["artifact_created_at"], str) or not manifest["artifact_created_at"]:
        raise IndexValidationError("Chroma manifest has an invalid creation timestamp.")

    metadata_keys = manifest["required_metadata_keys"]
    if not isinstance(metadata_keys, list) or not metadata_keys or not all(
        isinstance(key, str) and key for key in metadata_keys
    ):
        raise IndexValidationError("Chroma manifest has invalid required metadata keys.")

    checksums = manifest["checksums"]
    if not isinstance(checksums, dict) or "chroma.sqlite3" not in checksums:
        raise IndexValidationError("Chroma manifest must checksum chroma.sqlite3.")
    for relative_name, digest in checksums.items():
        relative_path = Path(relative_name)
        if (
            not isinstance(relative_name, str)
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            raise IndexValidationError("Chroma manifest contains an invalid checksum entry.")
    return manifest


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact_file:
        for block in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_checksums(seed_dir, manifest):
    seed_path = Path(seed_dir)
    if not seed_path.is_dir():
        raise IndexValidationError(f"Chroma seed directory does not exist: {seed_path}")
    for relative_name, expected_digest in manifest["checksums"].items():
        artifact_path = seed_path / relative_name
        if not artifact_path.is_file():
            raise IndexValidationError(f"Chroma seed file is missing: {relative_name}")
        if _sha256(artifact_path) != expected_digest:
            raise IndexValidationError(f"Chroma seed checksum mismatch: {relative_name}")


def _open_seed_catalog(seed_dir):
    catalog_path = (Path(seed_dir) / "chroma.sqlite3").resolve()
    try:
        return sqlite3.connect(
            f"file:{catalog_path.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
    except sqlite3.Error as exc:
        raise IndexValidationError(f"Cannot open Chroma seed catalog: {exc}") from exc


def validate_seed_catalog(seed_dir, manifest):
    connection = _open_seed_catalog(seed_dir)
    try:
        row = connection.execute(
            "SELECT id FROM collections WHERE name = ?",
            (manifest["collection_name"],),
        ).fetchone()
        if row is None:
            raise IndexValidationError(
                f"Expected Chroma collection is missing: {manifest['collection_name']}"
            )

        collection_id = row[0]
        document_count = connection.execute(
            """
            SELECT COUNT(DISTINCT embeddings.id)
            FROM embeddings
            JOIN segments ON embeddings.segment_id = segments.id
            WHERE segments.collection = ?
            """,
            (collection_id,),
        ).fetchone()[0]
        if document_count != manifest["document_count"]:
            raise IndexValidationError(
                "Chroma document count mismatch: "
                f"expected {manifest['document_count']}, found {document_count}"
            )

        for metadata_key in manifest["required_metadata_keys"]:
            metadata_count = connection.execute(
                """
                SELECT COUNT(DISTINCT embedding_metadata.id)
                FROM embedding_metadata
                JOIN embeddings ON embedding_metadata.id = embeddings.id
                JOIN segments ON embeddings.segment_id = segments.id
                WHERE segments.collection = ? AND embedding_metadata.key = ?
                """,
                (collection_id, metadata_key),
            ).fetchone()[0]
            if metadata_count != document_count:
                raise IndexValidationError(
                    f"Required Chroma metadata is incomplete: {metadata_key}"
                )
    except sqlite3.Error as exc:
        raise IndexValidationError(f"Chroma seed catalog is invalid: {exc}") from exc
    finally:
        connection.close()


def validate_seed(seed_dir, manifest_path):
    manifest = load_manifest(manifest_path)
    validate_checksums(seed_dir, manifest)
    validate_seed_catalog(seed_dir, manifest)
    return manifest


def validate_runtime(runtime_dir, manifest):
    try:
        client = chromadb.PersistentClient(path=str(runtime_dir))
        collection = client.get_collection(name=manifest["collection_name"])
        document_count = collection.count()
        if document_count != manifest["document_count"]:
            raise IndexValidationError(
                "Runtime Chroma document count mismatch: "
                f"expected {manifest['document_count']}, found {document_count}"
            )

        sample = collection.get(
            limit=1,
            include=["embeddings", "documents", "metadatas"],
        )
        if not sample.get("ids") or sample.get("embeddings") is None:
            raise IndexValidationError("Runtime Chroma collection has no queryable sample.")
        metadata = (sample.get("metadatas") or [{}])[0] or {}
        missing_metadata = set(manifest["required_metadata_keys"]) - metadata.keys()
        if missing_metadata:
            raise IndexValidationError(
                "Runtime Chroma sample is missing metadata: "
                + ", ".join(sorted(missing_metadata))
            )

        query_result = collection.query(
            query_embeddings=[sample["embeddings"][0]],
            n_results=1,
            include=["documents", "metadatas", "distances"],
        )
        if not query_result.get("ids") or not query_result["ids"][0]:
            raise IndexValidationError("Runtime Chroma representative query returned no result.")
    except IndexValidationError:
        raise
    except Exception as exc:
        raise IndexValidationError(f"Runtime Chroma validation failed: {exc}") from exc


def _make_runtime_writable(runtime_dir):
    runtime_path = Path(runtime_dir)
    for directory, directory_names, file_names in os.walk(runtime_path):
        os.chmod(directory, 0o700)
        for directory_name in directory_names:
            os.chmod(Path(directory) / directory_name, 0o700)
        for file_name in file_names:
            os.chmod(Path(directory) / file_name, 0o600)


def initialize_runtime(seed_dir, runtime_dir, manifest_path):
    seed_path = Path(seed_dir).resolve()
    runtime_path = Path(runtime_dir).resolve()
    if seed_path == runtime_path:
        raise IndexValidationError("Chroma seed and runtime directories must be different.")

    manifest = validate_seed(seed_path, manifest_path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging_path = Path(
        tempfile.mkdtemp(prefix=f".{runtime_path.name}.tmp-", dir=runtime_path.parent)
    )
    backup_path = runtime_path.with_name(f".{runtime_path.name}.previous")

    try:
        shutil.copytree(seed_path, staging_path, dirs_exist_ok=True, copy_function=shutil.copy2)
        _make_runtime_writable(staging_path)
        validate_runtime(staging_path, manifest)

        if backup_path.exists():
            shutil.rmtree(backup_path)
        if runtime_path.exists():
            os.replace(runtime_path, backup_path)
        try:
            os.replace(staging_path, runtime_path)
        except Exception:
            if backup_path.exists() and not runtime_path.exists():
                os.replace(backup_path, runtime_path)
            raise
        if backup_path.exists():
            shutil.rmtree(backup_path)
        os.chmod(runtime_path, 0o700)
    except Exception:
        if staging_path.exists():
            shutil.rmtree(staging_path)
        raise

    return manifest
