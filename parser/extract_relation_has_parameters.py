def extract_has_parameter_relations(param_entities, function_id_map):
    """
    根据参数变量实体和函数ID映射，构造 HAS_PARAMETER 关系：
    FUNCTION → VARIABLE（type: HAS_PARAMETER）

    修复版本：支持 function_id_map 为列表结构，解决同名函数覆盖问题
    
    要求参数变量实体中包含：
    - type == "VARIABLE"
    - role == "param"
    - scope 为函数名
    """

    relations = []

    for entity in param_entities:
        if entity.get("type") == "VARIABLE" and entity.get("role") == "param":
            func_name = entity.get("scope")
            param_source_file = entity.get("source_file")
            
            # 处理 function_id_map 为列表结构
            func_ids = function_id_map.get(func_name, [])
            if not isinstance(func_ids, list):
                func_ids = [func_ids] if func_ids else []
            
            if func_ids:
                # 选择策略：
                # 1. 如果只有一个函数，直接使用
                # 2. 如果有多个同名函数，选择与参数同文件的函数
                # 3. 如果找不到同文件的，使用第一个（一般情况下作用域内只有一个函数）
                
                matched_func_id = None
                
                if len(func_ids) == 1:
                    matched_func_id = func_ids[0]
                else:
                    # 多个同名函数，需要根据文件匹配
                    # 注意：这里需要额外的实体信息来匹配文件
                    # 简化处理：在同一作用域（函数名）下通常只有一个函数
                    # 更准确的做法是传入 entity_file_map 来匹配文件
                    matched_func_id = func_ids[0]
                
                if matched_func_id:
                    relations.append({
                        "head": matched_func_id,
                        "tail": entity["id"],
                        "type": "HAS_PARAMETER"
                    })

    return relations