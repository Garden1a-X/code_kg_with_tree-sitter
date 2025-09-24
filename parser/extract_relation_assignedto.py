import os

# 环境变量控制调试输出
DEBUG_MODE = os.getenv('DEBUG_MODE', '0') == '1'

def debug_print(*args, **kwargs):
    """调试输出函数，可通过环境变量控制"""
    if DEBUG_MODE:
        print(*args, **kwargs)

def skip_non_variable_start(input_string):
    if not isinstance(input_string, str):
        return ""

    without_prefix = ''  
    for i, char in enumerate(input_string):
        if char.isalpha() or char == '_':
            without_prefix = input_string[i:]
            break
    new_str = without_prefix.split('(')[0]
    
    for i in range(len(new_str)):
        sin_index = len(new_str) - i - 1
        sin_char = new_str[sin_index]
        if sin_char.isalpha() or sin_char == '_':
            without_suffix = new_str[:(sin_index+1)]
            return without_suffix

    return ""

def extract_assigned_to_relations(
    root_node,
    code_bytes,
    function_id_map,
    variable_id_map,
    field_id_map,
    current_file_path,
    file_visibility,
    entity_file_map,
    extern_functions=None,
    macro_lookup_map=None,
    file_path=None
):
    """
    基于文件可见性的赋值关系提取
    支持多值映射的变量查找，正确处理同名全局变量消歧
    """
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def find_macro_expansion(node):
        if not macro_lookup_map or not file_path:
            return None, None, None

        node_start = (node.start_point[0] + 1, node.start_point[1] + 1)
        node_end = (node.end_point[0] + 1, node.end_point[1] + 1)

        for entry in macro_lookup_map.get(file_path, []):
            (s_line, s_col), (e_line, e_col) = entry["range"]
            macro_start = (s_line, s_col)
            macro_end = (e_line, e_col)

            if node_start <= macro_start and macro_end <= node_end:
                if skip_non_variable_start(entry["expanded"]):
                    return skip_non_variable_start(entry["expanded"]), entry["original"], entry["range"]

        return None, None, None

    def resolve_entity_with_visibility(node, current_scope):
        if node is None:
            return None, False

        visible_files = file_visibility.get(current_file_path, {current_file_path})

        # 尝试宏展开
        expanded, macro_name, macro_range = find_macro_expansion(node)
        if expanded:
            expanded = expanded.strip()
            entity_id = resolve_name_with_visibility(expanded, current_scope, visible_files)
            return entity_id, True

        # 字段访问
        if node.type in ('field_expression', 'member_expression'):
            field_node = node.child_by_field_name('field')
            field_text = get_text(field_node).strip() if field_node else None
            if field_text:
                return resolve_field_with_visibility(field_text, visible_files), False

        # 标识符
        if node.type in ('identifier', 'field_identifier'):
            name = get_text(node).strip()
            entity_id = resolve_name_with_visibility(name, current_scope, visible_files)
            return entity_id, False

        # 递归子节点
        for child in node.children:
            result, flag = resolve_entity_with_visibility(child, current_scope)
            if result:
                return result, flag

        return None, False

    def resolve_name_with_visibility(name, current_scope, visible_files):
        """
        基于可见性解析名称到实体ID，支持多值映射
        """
        # 针对特定变量进行详细诊断（仅在DEBUG_MODE时生效）
        is_debug = DEBUG_MODE and name == 'shared_var' and current_scope == 'test_visibility_calls'
        
        if is_debug:
            debug_print(f"\n🔍 [DIAGNOSTIC] 诊断变量访问: {name}")
            debug_print(f"    当前文件: {current_file_path}")
            debug_print(f"    当前作用域: {current_scope}")
            debug_print(f"    可见文件数: {len(visible_files)}")
            for vf in list(visible_files)[:5]:
                debug_print(f"      -> {vf}")
        
        candidates = []
        
        # 1. 检查局部变量
        local_var_key = (name, current_scope)
        if local_var_key in variable_id_map:
            var_id_or_list = variable_id_map[local_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id, "未映射")
                if is_debug:
                    debug_print(f"    找到局部变量 {local_var_key}: id:{var_id} -> {var_file}")
                    debug_print(f"      文件可见? {var_file in visible_files if var_file else 'N/A'}")
                
                if var_file and var_file in visible_files:
                    priority = 0
                    candidates.append((var_id, "local_variable", priority, var_file))
                    if is_debug:
                        debug_print(f"      ✅ 添加局部变量候选: 优先级:{priority}")
        
        # 2. 检查全局变量 - 支持多值映射
        global_var_key = (name, 'global')
        if global_var_key in variable_id_map:
            var_id_or_list = variable_id_map[global_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            if is_debug:
                debug_print(f"    找到全局变量 {global_var_key}: {len(var_ids)} 个候选")
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id, "未映射")
                if is_debug:
                    debug_print(f"      id:{var_id} -> {var_file}")
                    debug_print(f"        是当前文件? {var_file == current_file_path}")
                    debug_print(f"        文件可见? {var_file in visible_files if var_file else 'N/A'}")
                
                if var_file and var_file in visible_files:
                    priority = 0 if var_file == current_file_path else 10
                    candidates.append((var_id, "global_variable", priority, var_file))
                    if is_debug:
                        debug_print(f"        ✅ 添加全局变量候选: 优先级:{priority}")
        
        # 3. 检查函数（支持多值映射）
        if name in function_id_map:
            func_ids = function_id_map[name]
            if not isinstance(func_ids, list):
                func_ids = [func_ids]
            
            for func_id in func_ids:
                func_file = entity_file_map.get(func_id)
                if func_file and func_file in visible_files:
                    priority = 0 if func_file == current_file_path else 1
                    candidates.append((func_id, "function", priority, func_file))
        
        # 4. 检查字段
        if name in field_id_map:
            field_ids = field_id_map[name]
            if not isinstance(field_ids, list):
                field_ids = [field_ids]
                
            for field_id in field_ids:
                field_file = entity_file_map.get(field_id)
                if field_file and field_file in visible_files:
                    priority = 0 if field_file == current_file_path else 1
                    candidates.append((field_id, "field", priority, field_file))
        
        # 调试输出（仅在DEBUG_MODE时生效）
        if is_debug:
            debug_print(f"    检查variable_id_map中所有包含'{name}'的条目:")
            count = 0
            for (var_name, var_scope), var_id_or_list in variable_id_map.items():
                if var_name == name:
                    var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
                    for var_id in var_ids:
                        var_file = entity_file_map.get(var_id, "未映射")
                        debug_print(f"      {(var_name, var_scope)}: id:{var_id} -> {var_file}")
                        count += 1
            debug_print(f"      总计找到 {count} 个同名变量")
            
            debug_print(f"    总候选数: {len(candidates)}")
            for i, (cid, ctype, cpri, cfile) in enumerate(candidates):
                debug_print(f"      候选{i+1}: id:{cid}, 类型:{ctype}, 优先级:{cpri}, 文件:{cfile}")
        
        if candidates:
            candidates.sort(key=lambda x: x[2])  # 按优先级排序
            best_match = candidates[0]
            if is_debug:
                debug_print(f"    ⭐ 最终选择: id:{best_match[0]}, 类型:{best_match[1]}, 文件:{best_match[3]}")
            return best_match[0]
        else:
            if is_debug:
                debug_print(f"    ❌ 没有找到候选")
            return None

    def resolve_field_with_visibility(field_name, visible_files):
        """解析字段访问"""
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
        return None

    def find_identifier(node):
        if node is None:
            return None
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_identifier(child)
            if result:
                return result
        return None

    def find_assignment_in_declaration(node):
        if node.type == 'init_declarator':
            return node.child_by_field_name('declarator'), node.child_by_field_name('value')
        for child in node.children:
            lhs, rhs = find_assignment_in_declaration(child)
            if lhs and rhs:
                return lhs, rhs
        return None, None

    assigned_to_relations = []

    def traverse(node, current_scope='global'):
        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_identifier(declarator)
            if func_node:
                current_scope = get_text(func_node).strip()

        # 表达式赋值
        if node.type == 'expression_statement':
            for child in node.children:
                if child.type == 'assignment_expression':
                    left = child.child_by_field_name('left')
                    right = child.child_by_field_name('right')
                    if left and right:
                        lhs_id, _ = resolve_entity_with_visibility(left, current_scope)
                        rhs_id, _ = resolve_entity_with_visibility(right, current_scope)
                        
                        if lhs_id and rhs_id:
                            relation = {
                                "head": lhs_id,
                                "tail": rhs_id,
                                "type": "ASSIGNED_TO",
                                "scope": current_scope,
                                "visibility_checked": True
                            }
                            
                            # 避免重复添加
                            if relation not in assigned_to_relations:
                                assigned_to_relations.append(relation)

        # 声明赋值
        if node.type == 'declaration':
            lhs_node, rhs_node = find_assignment_in_declaration(node)
            if lhs_node and rhs_node:
                lhs_id, _ = resolve_entity_with_visibility(lhs_node, current_scope)
                rhs_id, _ = resolve_entity_with_visibility(rhs_node, current_scope)
                
                if lhs_id and rhs_id:
                    relation = {
                        "head": lhs_id,
                        "tail": rhs_id,
                        "type": "ASSIGNED_TO",
                        "scope": current_scope,
                        "visibility_checked": True
                    }
                    
                    # 避免重复添加
                    if relation not in assigned_to_relations:
                        assigned_to_relations.append(relation)

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return assigned_to_relations