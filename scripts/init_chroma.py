import os
import sys

from core.ai.rag.index_runtime import IndexValidationError, initialize_runtime


def main():
    seed_dir = os.environ.get("CHROMA_SEED_DIR", "/app/chroma_seed")
    runtime_dir = os.environ.get("CHROMA_DIR", "/tmp/smartdex/chroma_runtime")
    manifest_path = os.environ.get(
        "CHROMA_MANIFEST_PATH",
        os.path.join(seed_dir, "manifest.json"),
    )
    try:
        manifest = initialize_runtime(seed_dir, runtime_dir, manifest_path)
    except IndexValidationError as exc:
        print(f"Chroma runtime initialization failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Chroma runtime initialization failed unexpectedly: {exc}", file=sys.stderr)
        return 1

    print(
        "Chroma runtime initialized: "
        f"version={manifest['index_version']} "
        f"collection={manifest['collection_name']} "
        f"documents={manifest['document_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
