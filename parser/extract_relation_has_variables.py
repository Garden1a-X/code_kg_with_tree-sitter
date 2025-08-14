def extract_has_variable_relations(variable_entities, function_id_map):
    """
    提取函数内定义的局部变量关系：FUNCTION → VARIABLE
    """
    relations = []

    for var in variable_entities:
        scope = var.get("scope")
        if not scope or scope == "global":
            continue
        if scope in function_id_map:
            func_id = function_id_map[scope]
            relations.append({
                "head": func_id,
                "tail": var["id"],
                "type": "HAS_VARIABLE"
            })

    return relations
