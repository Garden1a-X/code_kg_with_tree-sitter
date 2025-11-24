import os

def extract_file_entity(source_path, id_counter):
    file_name = os.path.basename(source_path)
    file_id = str(next(id_counter))

    entity = {
        "id": file_id,
        "name": os.path.basename(source_path),   # ✅ 使用完整路径，或保留 file_name 也可视需要替换
        "type": "FILE",
        "source_file": source_path
    }

    return [entity], file_id  # ✅ 直接返回真正的 file_id