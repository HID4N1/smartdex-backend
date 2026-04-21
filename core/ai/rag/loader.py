import os

def load_txt_files(folder_path: str):
    """
    Loads all .txt files from a folder.
    Returns dict: {filename: content}
    """

    documents = {}

    for file in os.listdir(folder_path):
        if file.endswith(".txt"):
            path = os.path.join(folder_path, file)

            with open(path, "r", encoding="utf-8") as f:
                documents[file] = f.read()

    return documents