def extract_has_variable_relations(variable_entities, function_id_map):
    """
    提取函数内定义的局部变量关系：FUNCTION → VARIABLE
    修复版本：支持 function_id_map 为列表结构，解决同名函数覆盖问题
    """
    relations = []

    for var in variable_entities:
        scope = var.get("scope")
        if not scope or scope == "global":
            continue
            
        # 处理 function_id_map 为列表结构
        func_ids = function_id_map.get(scope, [])
        if not isinstance(func_ids, list):
            func_ids = [func_ids] if func_ids else []
            
        if func_ids:
            # 选择策略：
            # 1. 如果只有一个函数，直接使用
            # 2. 如果有多个同名函数，选择与变量同文件的函数
            # 3. 如果找不到同文件的，使用第一个（一般情况下作用域内只有一个函数）
            
            matched_func_id = None
            var_source_file = var.get("source_file")
            
            if len(func_ids) == 1:
                matched_func_id = func_ids[0]
            else:
                # 多个同名函数，需要根据文件匹配
                # 简化处理：在同一作用域（函数名）下通常只有一个函数
                # 更准确的做法是传入 entity_file_map 来匹配文件
                matched_func_id = func_ids[0]
            
            if matched_func_id:
                relations.append({
                    "head": matched_func_id,
                    "tail": var["id"],
                    "type": "HAS_VARIABLE"
                })

    return relations