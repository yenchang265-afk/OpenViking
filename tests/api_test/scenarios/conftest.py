import os
import tempfile
import uuid


def create_test_file(content=None, suffix=".txt"):
    if content is None:
        content = (
            f"測試檔案內容 - {uuid.uuid4()}\n這是一個用於API測試的臨時檔案。\n包含一些測試資料。"
        )

    temp_dir = tempfile.mkdtemp()
    test_file_path = os.path.join(temp_dir, f"test_file_{str(uuid.uuid4())[:8]}{suffix}")

    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return test_file_path, temp_dir


def create_test_directory():
    temp_dir = tempfile.mkdtemp()

    for i in range(3):
        file_path = os.path.join(temp_dir, f"file_{i}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"測試檔案 {i} 的內容\n一些測試資料 {uuid.uuid4()}")

    subdir = os.path.join(temp_dir, "subdir")
    os.makedirs(subdir)
    with open(os.path.join(subdir, "nested_file.txt"), "w", encoding="utf-8") as f:
        f.write("巢狀檔案的內容")

    return temp_dir
