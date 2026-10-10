import gc
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import chromadb
from django.test import SimpleTestCase, override_settings

from core.ai.rag.index_runtime import (
    IndexValidationError,
    initialize_runtime,
    validate_seed,
)
from core.ai.rag.retriever import Retriever


class ChromaRuntimeInitializationTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.seed = self.root / "seed"
        self.runtime = self.root / "runtime"
        self.manifest_path = self.seed / "manifest.json"

    def tearDown(self):
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        gc.collect()
        self.temporary_directory.cleanup()

    def _create_seed(self, collection_name="smartdex_kb", document_count=2):
        client = chromadb.PersistentClient(path=str(self.seed))
        collection = client.create_collection(name=collection_name)
        collection.add(
            ids=[f"doc-{index}" for index in range(document_count)],
            documents=[f"SmartDex test document {index}" for index in range(document_count)],
            embeddings=[[float(index + 1), 0.5, 0.25] for index in range(document_count)],
            metadatas=[
                {
                    "source": "fixture.txt",
                    "doc_type": "test",
                    "chunk_index": index,
                    "total_chunks": document_count,
                }
                for index in range(document_count)
            ],
        )
        del collection
        del client
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        gc.collect()
        self._write_manifest(collection_name, document_count)

    def _checksums(self):
        checksums = {}
        for path in sorted(self.seed.rglob("*")):
            if path.is_file() and path != self.manifest_path:
                checksums[path.relative_to(self.seed).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return checksums

    def _write_manifest(self, collection_name="smartdex_kb", document_count=2):
        self.seed.mkdir(parents=True, exist_ok=True)
        manifest = {
            "manifest_schema": 1,
            "index_version": "chroma-index-test-v1",
            "collection_name": collection_name,
            "document_count": document_count,
            "embedding_model": "text-embedding-3-small",
            "artifact_created_at": "2026-10-10T00:00:00Z",
            "required_metadata_keys": [
                "source",
                "doc_type",
                "chunk_index",
                "total_chunks",
            ],
            "checksums": self._checksums(),
        }
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_missing_seed_directory_fails(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "manifest_schema": 1,
                    "index_version": "chroma-index-test-v1",
                    "collection_name": "smartdex_kb",
                    "document_count": 1,
                    "embedding_model": "text-embedding-3-small",
                    "artifact_created_at": "2026-10-10T00:00:00Z",
                    "required_metadata_keys": ["source"],
                    "checksums": {"chroma.sqlite3": "0" * 64},
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(IndexValidationError, "seed directory does not exist"):
            initialize_runtime(self.seed, self.runtime, manifest)

    def test_corrupted_seed_database_fails(self):
        self.seed.mkdir()
        (self.seed / "chroma.sqlite3").write_bytes(b"not a sqlite database")
        self._write_manifest(document_count=1)
        with self.assertRaisesRegex(IndexValidationError, "catalog is invalid"):
            validate_seed(self.seed, self.manifest_path)

    def test_invalid_manifest_fails(self):
        self.seed.mkdir()
        self.manifest_path.write_text('{"manifest_schema": 1}', encoding="utf-8")
        with self.assertRaisesRegex(IndexValidationError, "missing required fields"):
            validate_seed(self.seed, self.manifest_path)

    def test_checksum_mismatch_fails(self):
        self._create_seed()
        catalog = self.seed / "chroma.sqlite3"
        catalog.write_bytes(catalog.read_bytes() + b"tampered")
        with self.assertRaisesRegex(IndexValidationError, "checksum mismatch"):
            validate_seed(self.seed, self.manifest_path)

    def test_wrong_collection_name_fails(self):
        self._create_seed()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["collection_name"] = "wrong_collection"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(IndexValidationError, "collection is missing"):
            validate_seed(self.seed, self.manifest_path)

    def test_incorrect_document_count_fails(self):
        self._create_seed()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["document_count"] = 999
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(IndexValidationError, "document count mismatch"):
            validate_seed(self.seed, self.manifest_path)

    def test_successful_copy_is_writable_and_does_not_mutate_seed(self):
        self._create_seed()
        seed_checksums_before = self._checksums()

        manifest = initialize_runtime(self.seed, self.runtime, self.manifest_path)

        self.assertEqual(manifest["index_version"], "chroma-index-test-v1")
        self.assertTrue((self.runtime / "chroma.sqlite3").is_file())
        self.assertTrue(os.access(self.runtime, os.W_OK))
        self.assertTrue(stat.S_IMODE(self.runtime.stat().st_mode) & stat.S_IWUSR)
        self.assertTrue(stat.S_IMODE((self.runtime / "chroma.sqlite3").stat().st_mode) & stat.S_IWUSR)
        self.assertEqual(seed_checksums_before, self._checksums())

    def test_repeated_initialization_replaces_runtime_from_seed(self):
        self._create_seed()
        initialize_runtime(self.seed, self.runtime, self.manifest_path)
        marker = self.runtime / "runtime-only-marker"
        marker.write_text("discard me", encoding="utf-8")

        initialize_runtime(self.seed, self.runtime, self.manifest_path)

        self.assertFalse(marker.exists())
        self.assertTrue((self.runtime / "chroma.sqlite3").is_file())

    @patch("openai.OpenAI")
    def test_initialization_makes_no_openai_calls(self, openai_client):
        self._create_seed()
        initialize_runtime(self.seed, self.runtime, self.manifest_path)
        openai_client.assert_not_called()

    def test_entrypoint_never_runs_ingestion(self):
        root = Path(__file__).resolve().parents[2]
        entrypoint = (root / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
        initializer = (root / "scripts" / "init_chroma.py").read_text(encoding="utf-8")
        self.assertNotIn("ingest_docs", entrypoint)
        self.assertNotIn("ingest_docs", initializer)
        self.assertIn("python -m scripts.init_chroma", entrypoint)


class RetrievalOnlyCollectionTests(SimpleTestCase):
    @override_settings(CHROMA_DIR="/temporary/runtime-index")
    @patch("core.ai.rag.retriever.OpenAI")
    @patch("core.ai.rag.retriever.chromadb.PersistentClient")
    def test_retriever_loads_existing_collection_without_creation(
        self, persistent_client, openai_client
    ):
        collection = Mock()
        persistent_client.return_value.get_collection.return_value = collection

        retriever = Retriever()

        self.assertIs(retriever.collection, collection)
        persistent_client.return_value.get_collection.assert_called_once_with(
            name="smartdex_kb"
        )
        self.assertFalse(persistent_client.return_value.get_or_create_collection.called)
        openai_client.assert_called_once()

    @override_settings(CHROMA_DIR="/temporary/runtime-index")
    @patch("core.ai.rag.retriever.OpenAI")
    @patch("core.ai.rag.retriever.chromadb.PersistentClient")
    def test_missing_collection_fails_cleanly(self, persistent_client, _openai_client):
        persistent_client.return_value.get_collection.side_effect = ValueError(
            "Collection smartdex_kb does not exist"
        )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            Retriever()
