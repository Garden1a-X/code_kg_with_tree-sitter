def extract_returns_relations(
    root_node,
    code_bytes,
    function_id_map,
    variable_id_map,
    field_id_map,
    current_file_path=None,
    file_visibility=None,
    entity_file_map=None
):
    """
    提取 RETURNS 关系：FUNCTION-[RETURNS]->VARIABLE / FIELD
    修复版本：支持 function_id_map 和 variable_id_map 为列表结构，解决同名函数和变量覆盖问题
    
    支持：
        - return 局部变量或参数
        - return 全局变量
        - return 结构体字段（conf->field）
    忽略：
        - return 字面量 / 宏函数 / 宏变量（应已在预处理阶段展开为常量）
    """

    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    def find_deep_identifier(node):
        if node is None:
            return None
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_deep_identifier(child)
            if result:
                return result
        return None

    def resolve_return_target_with_visibility(node, current_func):
        """基于可见性解析返回目标"""
        if not current_file_path or not file_visibility or not entity_file_map:
            # 回退到原始逻辑
            return resolve_return_target_fallback(node, current_func)
        
        visible_files = file_visibility.get(current_file_path, {current_file_path})
        
        # 字段访问：conf->level
        if node.type in ("field_expression", "pointer_expression"):
            field_node = node.child_by_field_name("field")
            if field_node:
                field_name = get_text(field_node).strip()
                if field_name in field_id_map:
                    field_ids = field_id_map[field_name]
                    if isinstance(field_ids, list):
                        for field_id in field_ids:
                            field_file = entity_file_map.get(field_id)
                            if field_file and field_file in visible_files:
                                return field_id
                    else:
                        field_id = field_ids
                        field_file = entity_file_map.get(field_id)
                        if field_file and field_file in visible_files:
                            return field_id

        # 标识符（变量名）
        if node.type == 'identifier':
            name = get_text(node).strip()

            # 🔧 修复：局部变量优先，支持多值映射
            if (name, current_func) in variable_id_map:
                var_id_or_list = variable_id_map[(name, current_func)]
                
                # 处理多值映射情况
                if isinstance(var_id_or_list, list):
                    for var_id in var_id_or_list:
                        var_file = entity_file_map.get(var_id)
                        if var_file and var_file in visible_files:
                            return var_id
                else:
                    var_id = var_id_or_list
                    var_file = entity_file_map.get(var_id)
                    if var_file and var_file in visible_files:
                        return var_id

            # 🔧 修复：全局变量，支持多值映射
            if (name, 'global') in variable_id_map:
                var_id_or_list = variable_id_map[(name, 'global')]
                
                # 处理多值映射情况
                if isinstance(var_id_or_list, list):
                    # 优先选择当前文件中的全局变量
                    for var_id in var_id_or_list:
                        var_file = entity_file_map.get(var_id)
                        if var_file == current_file_path:
                            return var_id
                    
                    # 如果没找到当前文件的，选择可见的第一个
                    for var_id in var_id_or_list:
                        var_file = entity_file_map.get(var_id)
                        if var_file and var_file in visible_files:
                            return var_id
                else:
                    var_id = var_id_or_list
                    var_file = entity_file_map.get(var_id)
                    if var_file and var_file in visible_files:
                        return var_id

        return None

    def resolve_return_target_fallback(node, current_func):
        """原始的返回目标解析逻辑（向后兼容）"""
        # 字段访问：conf->level
        if node.type in ("field_expression", "pointer_expression"):
            field_node = node.child_by_field_name("field")
            if field_node:
                field_name = get_text(field_node).strip()
                if field_name in field_id_map:
                    field_ids = field_id_map[field_name]
                    if isinstance(field_ids, list):
                        return field_ids[0] if field_ids else None  # 取第一个
                    return field_ids

        # 🔧 修复：标识符处理，支持多值映射
        if node.type == 'identifier':
            name = get_text(node).strip()

            # 局部变量
            if (name, current_func) in variable_id_map:
                var_id_or_list = variable_id_map[(name, current_func)]
                if isinstance(var_id_or_list, list):
                    return var_id_or_list[0] if var_id_or_list else None
                return var_id_or_list

            # 全局变量
            if (name, 'global') in variable_id_map:
                var_id_or_list = variable_id_map[(name, 'global')]
                if isinstance(var_id_or_list, list):
                    return var_id_or_list[0] if var_id_or_list else None
                return var_id_or_list

        return None

    returns_relations = []
    current_function = None

    def traverse(node):
        nonlocal current_function, returns_relations

        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_deep_identifier(declarator)
            if func_node:
                current_function = get_text(func_node).strip()

        if node.type == 'return_statement' and current_function:
            return_expr = next((c for c in node.children if c.type not in ('return', ';')), None)
            if return_expr:
                target_id = resolve_return_target_with_visibility(return_expr, current_function)
                if target_id:
                    # 🔧 修复：处理 function_id_map 列表结构
                    func_ids = function_id_map.get(current_function, [])
                    if not isinstance(func_ids, list):
                        func_ids = [func_ids] if func_ids else []
                    
                    # 选择当前文件中的函数
                    matched_func_id = None
                    for func_id in func_ids:
                        if entity_file_map:
                            func_file = entity_file_map.get(func_id)
                            if func_file == current_file_path:
                                matched_func_id = func_id
                                break
                    
                    # 如果没找到当前文件的，使用第一个
                    if not matched_func_id and func_ids:
                        matched_func_id = func_ids[0]
                    
                    if matched_func_id:
                        relation = {
                            "head": matched_func_id,
                            "tail": target_id,
                            "type": "RETURNS"
                        }
                        
                        # 添加可见性标记
                        if current_file_path and file_visibility and entity_file_map:
                            relation["visibility_checked"] = True
                        
                        returns_relations.append(relation)

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return returns_relations