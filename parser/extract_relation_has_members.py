def extract_has_member_relations(field_entities, struct_id_map):
    """
    构造 HAS_MEMBER 关系：
    STRUCT → FIELD
    - field_entities: 所有字段实体，包含其 scope（即所属 struct 名）
    - struct_id_map: 映射 struct 名 → id
    """
    relations = []

    for field in field_entities:
        struct_name = field.get("scope")
        field_id = field["id"]
        if struct_name in struct_id_map:
            struct_id = struct_id_map[struct_name]
            relations.append({
                "head": struct_id,
                "tail": field_id,
                "type": "HAS_MEMBER"
            })

    return relations
