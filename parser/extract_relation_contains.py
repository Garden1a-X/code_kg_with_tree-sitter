def build_file_level_contains(file_id, contain_list):
    """
    构造 CONTAINS 关系：
    FILE → FUNCTION / STRUCT / 全局 VARIABLE
    """
    relations = []
    for entity in contain_list:
        if entity["type"] in ("FUNCTION", "STRUCT") or (entity["type"] == 'VARIABLE' and entity.get('scope')== 'global'):
            relations.append({
                "head": file_id,
                "tail": entity['id'],
                "type": "CONTAINS"
            })

    return relations