def extract_has_parameter_relations(variable_entities, function_id_map):
    """
    根据参数变量实体和函数ID映射，构造 HAS_PARAMETER 关系：
    FUNCTION → VARIABLE（type: HAS_PARAMETER）

    要求参数变量实体中包含：
    - type == "VARIABLE"
    - role == "param"
    - scope 为函数名
    """

    relations = []

    for entity in variable_entities:
        if entity.get("type") == "VARIABLE" and entity.get("role") == "param":
            func_name = entity.get("scope")
            func_id = function_id_map.get(func_name)
            if func_id:
                relations.append({
                    "head": func_id,
                    "tail": entity["id"],
                    "type": "HAS_PARAMETER"
                })

    return relations
