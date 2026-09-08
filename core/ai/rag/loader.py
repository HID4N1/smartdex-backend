import os

def load_txt_files(folder_path: str):
    """
    Loads all .txt and .md files from a folder recursively.
    Returns dict: {filename: content}
    """

    documents = {}

    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.endswith((".txt", ".md")):
                continue

            path = os.path.join(root, file)
            relative_path = os.path.relpath(path, folder_path)

            with open(path, "r", encoding="utf-8") as f:
                documents[relative_path] = f.read()

    return documents
