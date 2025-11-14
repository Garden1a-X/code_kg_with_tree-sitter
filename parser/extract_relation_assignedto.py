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
    新增：支持结构体初始化器中的字段赋值
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
        """基于可见性解析名称到实体ID，支持多值映射"""
        is_debug = DEBUG_MODE and name == 'shared_var' and current_scope == 'test_visibility_calls'
        
        if is_debug:
            debug_print(f"\n🔍 [DIAGNOSTIC] 诊断变量访问: {name}")
            debug_print(f"    当前文件: {current_file_path}")
            debug_print(f"    当前作用域: {current_scope}")
        
        candidates = []
        
        # 1. 检查局部变量
        local_var_key = (name, current_scope)
        if local_var_key in variable_id_map:
            var_id_or_list = variable_id_map[local_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id)
                if var_file and var_file in visible_files:
                    priority = 0
                    candidates.append((var_id, "local_variable", priority, var_file))
        
        # 2. 检查全局变量
        global_var_key = (name, 'global')
        if global_var_key in variable_id_map:
            var_id_or_list = variable_id_map[global_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id)
                if var_file and var_file in visible_files:
                    priority = 0 if var_file == current_file_path else 10
                    candidates.append((var_id, "global_variable", priority, var_file))
        
        # 3. 检查函数
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
        
        if candidates:
            candidates.sort(key=lambda x: x[2])
            return candidates[0][0]
        
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
        # 进入函数定义
        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_identifier(declarator)
            if func_node:
                current_scope = get_text(func_node).strip()

        # 辅助函数：处理初始化器列表
        def handle_initializer_list(init_list_node, parent_struct_name, context_var_id=None, context_var_name=None):
            """处理 { .field = value, ... } 形式的初始化器"""
            if not init_list_node or init_list_node.type != 'initializer_list':
                return
            
            for child in init_list_node.children:
                if child.type == 'initializer_pair':
                    field_name = None
                    value_node = None
                    
                    # 提取字段名和值
                    for subchild in child.children:
                        if subchild.type == 'field_designator':
                            for gchild in subchild.children:
                                if gchild.type in ('identifier', 'field_identifier'):
                                    field_name = get_text(gchild).strip()
                                    break
                        elif subchild.type not in (',', '=', '.', '{', '}'):
                            if not value_node:
                                value_node = subchild
                    
                    if not value_node:
                        value_node = child.child_by_field_name('value')
                    
                    if field_name and value_node:
                        # 查找字段 ID
                        candidate_ids = field_id_map.get(field_name, [])
                        if not isinstance(candidate_ids, list):
                            candidate_ids = [candidate_ids]
                        
                        field_id = None
                        visible_files = file_visibility.get(current_file_path, {current_file_path})
                        
                        for fid in candidate_ids:
                            fid_file = entity_file_map.get(fid)
                            if fid_file == current_file_path:
                                field_id = fid
                                break
                        
                        if not field_id and candidate_ids:
                            for fid in candidate_ids:
                                fid_file = entity_file_map.get(fid)
                                if fid_file in visible_files:
                                    field_id = fid
                                    break
                        
                        if field_id:
                            rhs_id, _ = resolve_entity_with_visibility(value_node, current_scope)
                            
                            if rhs_id:
                                relation = {
                                    "head": field_id,
                                    "tail": rhs_id,
                                    "type": "ASSIGNED_TO",
                                    "scope": parent_struct_name,
                                    "visibility_checked": True
                                }
                                
                                if context_var_id:
                                    relation["context_var_id"] = context_var_id
                                if context_var_name:
                                    relation["context_var_name"] = context_var_name
                                
                                if relation not in assigned_to_relations:
                                    assigned_to_relations.append(relation)

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
                    
                    if relation not in assigned_to_relations:
                        assigned_to_relations.append(relation)

        # 处理结构体初始化器
        if node.type == 'init_declarator':
            declarator = node.child_by_field_name('declarator')
            value = node.child_by_field_name('value')
            
            if declarator and value and value.type == 'initializer_list':
                var_name_node = find_identifier(declarator)
                if var_name_node:
                    var_name = get_text(var_name_node).strip()
                    
                    # 获取变量 ID
                    var_key = (var_name, current_scope)
                    if var_key not in variable_id_map:
                        var_key = (var_name, 'global')
                    
                    var_id = variable_id_map.get(var_key)
                    if isinstance(var_id, list):
                        var_id = var_id[0] if var_id else None
                    
                    # 从父节点获取类型
                    parent = node.parent
                    if parent and parent.type == 'declaration':
                        type_node = parent.child_by_field_name('type')
                        if type_node:
                            type_text = get_text(type_node).strip()
                            
                            # 提取结构体名
                            struct_name = None
                            if 'struct ' in type_text:
                                type_text = type_text.replace('const ', '').replace('static ', '').strip()
                                if type_text.startswith('struct '):
                                    struct_name = type_text[len('struct '):].strip()
                            
                            if struct_name and var_id:
                                handle_initializer_list(
                                    init_list_node=value,
                                    parent_struct_name=struct_name,
                                    context_var_id=var_id,
                                    context_var_name=var_name
                                )

        # 递归遍历
        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return assigned_to_relations
