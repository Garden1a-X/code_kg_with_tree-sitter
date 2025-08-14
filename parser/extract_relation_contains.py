def build_file_level_contains(file_id, function_id_map, struct_id_map, variable_scope_map):
    """
    构造 CONTAINS 关系：
    FILE → FUNCTION / STRUCT / 全局 VARIABLE
    """
    relations = []

    # FILE contains FUNCTION
    for _, func_id in function_id_map.items():
        relations.append({
            "head": file_id,
            "tail": func_id,
            "type": "CONTAINS"
        })

    # FILE contains STRUCT
    for _, struct_id in struct_id_map.items():
        relations.append({
            "head": file_id,
            "tail": struct_id,
            "type": "CONTAINS"
        })

    # FILE contains global VARIABLE
    for scope, var_ids in variable_scope_map.items():
        if scope == "global":
            for var_id in var_ids:
                relations.append({
                    "head": file_id,
                    "tail": var_id,
                    "type": "CONTAINS"
                })

    return relations
