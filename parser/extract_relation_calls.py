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

def extract_calls_relations(
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
    file_path=None,
    all_entities=None
):
    """
    基于文件可见性的函数调用关系提取
    性能优化版本：预计算映射表，避免重复搜索
    """
    
    # 🔧 性能优化1：预计算函数声明映射表
    function_declaration_map = {}
    if all_entities:
        for entity in all_entities:
            if entity.get("type") == "FUNCTION":
                func_id = entity.get("id")
                if func_id:
                    function_declaration_map[func_id] = entity.get("is_declaration", False)
    
    # 🔧 性能优化2：预计算可见文件集合
    current_visible_files = file_visibility.get(current_file_path, {current_file_path})
    
    # 🔧 性能优化3：预计算extern函数集合
    extern_functions_set = set(extern_functions) if extern_functions else set()
    
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def find_identifier(node):
        if node is None:
            return None
        if node.type == "identifier":
            return node
        for child in node.children:
            result = find_identifier(child)
            if result:
                return result
        return None

    def extract_field_path(node):
        """
        提取字段访问路径
        例如: host->ops->execute_tuning -> ["host", "ops", "execute_tuning"]
        """
        if node is None:
            return []

        if node.type == "identifier":
            return [get_text(node)]

        if node.type == "field_expression":
            # field_expression 有两个部分: argument (对象) 和 field (字段名)
            argument = node.child_by_field_name("argument")
            field = node.child_by_field_name("field")

            if argument and field:
                # 递归提取前面的路径
                prefix_path = extract_field_path(argument)
                field_name = get_text(field)
                return prefix_path + [field_name]

        return []

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

    def is_function_declaration_fast(func_id):
        """快速查找函数是否为声明（O(1)时间复杂度）"""
        return function_declaration_map.get(func_id, False)

    def resolve_callee_with_visibility(callee_name, current_function):
        """
        优化版本：减少重复计算，提高查找效率

        优化策略：
        - 如果只有1个候选（唯一匹配），直接建立关系，跳过可见性检查
        - 如果有多个候选，使用可见性筛选解决歧义
        """

        candidates = []
        all_candidates = []  # 记录所有候选（不考虑可见性）

        # 1. 查找函数定义 - 优化的多值映射处理
        func_ids = function_id_map.get(callee_name, [])
        if not isinstance(func_ids, list):
            func_ids = [func_ids] if func_ids else []

        # 🎯 优化：如果只有1个函数候选，直接返回（跳过可见性检查）
        if len(func_ids) == 1:
            func_id = func_ids[0]
            func_file = entity_file_map.get(func_id)
            if func_file:
                # 唯一候选，直接返回
                return func_id, "function_unique"

        # 有多个候选时，使用可见性筛选
        for func_id in func_ids:
            func_file = entity_file_map.get(func_id)
            if func_file:
                all_candidates.append((func_id, "function", func_file))

                if func_file in current_visible_files:
                    # 优先级计算：当前文件(0) > 其他文件(10) + 声明惩罚(100)
                    base_priority = 0 if func_file == current_file_path else 10
                    decl_penalty = 100 if is_function_declaration_fast(func_id) else 0
                    final_priority = base_priority + decl_penalty

                    candidates.append((func_id, "function", final_priority, func_file))
        
        # 2. 检查 extern 函数声明 - 优化查找
        if callee_name in extern_functions_set:
            best_extern_id = None
            best_extern_priority = float('inf')
            
            for func_id in func_ids:
                func_file = entity_file_map.get(func_id)
                if func_file:  # extern函数不需要严格的可见性检查
                    decl_penalty = 100 if is_function_declaration_fast(func_id) else 0
                    if decl_penalty < best_extern_priority:
                        best_extern_id = func_id
                        best_extern_priority = decl_penalty
            
            if best_extern_id:
                return best_extern_id, "extern_function"
        
        # 3. 查找局部函数指针变量
        local_var_key = (callee_name, current_function)
        if local_var_key in variable_id_map:
            var_id_or_list = variable_id_map[local_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id)
                if var_file and var_file in current_visible_files:
                    return var_id, "local_func_ptr"
        
        # 4. 查找全局函数指针变量
        global_var_key = (callee_name, 'global')
        if global_var_key in variable_id_map:
            var_id_or_list = variable_id_map[global_var_key]
            var_ids = var_id_or_list if isinstance(var_id_or_list, list) else [var_id_or_list]
            
            for var_id in var_ids:
                var_file = entity_file_map.get(var_id)
                if var_file and var_file in current_visible_files:
                    priority = 200 if var_file == current_file_path else 210
                    candidates.append((var_id, "global_func_ptr", priority, var_file))
        
        # 5. 查找字段函数指针
        field_ids = field_id_map.get(callee_name, [])
        if not isinstance(field_ids, list):
            field_ids = [field_ids] if field_ids else []
            
        for field_id in field_ids:
            field_file = entity_file_map.get(field_id)
            if field_file and field_file in current_visible_files:
                return field_id, "field_func_ptr"
        
        # 选择最佳候选（按优先级排序）
        if candidates:
            candidates.sort(key=lambda x: x[2])
            return candidates[0][0], candidates[0][1]
        
        return None, None

    relations = []

    def traverse(node, current_function=None):
        nonlocal relations

        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            id_node = find_identifier(declarator)
            if id_node:
                current_function = get_text(id_node)

        # 检查调用表达式
        if node.type == "call_expression" and current_function:
            callee_node = node.child_by_field_name("function")

            # 获取调用者ID - 优化的多值映射处理
            caller_ids = function_id_map.get(current_function, [])
            if not isinstance(caller_ids, list):
                caller_ids = [caller_ids] if caller_ids else []

            # 选择当前文件中的函数作为调用者
            caller_id = None
            for cid in caller_ids:
                caller_file = entity_file_map.get(cid)
                if caller_file == current_file_path:
                    caller_id = cid
                    break

            if not caller_id and caller_ids:
                caller_id = caller_ids[0]

            if not caller_id:
                return

            # 获取调用发生的行号
            call_line = node.start_point[0] + 1  # +1 因为行号从1开始

            # 判断是直接调用还是间接调用
            is_indirect_call = callee_node and callee_node.type == "field_expression"

            if is_indirect_call:
                # === 间接调用：通过字段（函数指针）调用 ===
                field_path = extract_field_path(callee_node)

                if field_path and len(field_path) > 0:
                    # 最后一个元素是字段名
                    field_name = field_path[-1]

                    # 查找所有同名的 FIELD 实体
                    field_ids = field_id_map.get(field_name, [])
                    if not isinstance(field_ids, list):
                        field_ids = [field_ids] if field_ids else []

                    # 为每个同名字段建立 CALLS 关系
                    for field_id in field_ids:
                        relation = {
                            "head": caller_id,
                            "tail": field_id,
                            "type": "CALLS",
                            "call_line": call_line,
                            "call_type": "indirect",  # 标记为间接调用
                            "target_type": "FIELD",   # tail 指向 FIELD
                            "field_path": field_path,  # 完整字段路径
                            "field_pattern": get_text(callee_node)  # 原始代码片段
                        }

                        # 避免重复添加
                        if relation not in relations:
                            relations.append(relation)
            else:
                # === 直接调用：普通函数调用 ===
                callee_name = None

                # 优先尝试匹配宏展开
                expanded, original_macro, macro_range = find_macro_expansion(node)

                if expanded:
                    callee_name = expanded
                else:
                    id_node = find_identifier(callee_node)
                    if id_node:
                        callee_name = get_text(id_node)

                if callee_name:
                    resolved_id, resolved_type = resolve_callee_with_visibility(callee_name, current_function)

                    if resolved_id:
                        relation = {
                            "head": caller_id,
                            "tail": resolved_id,
                            "type": "CALLS",
                            "call_line": call_line,
                            "call_type": "direct",    # 标记为直接调用
                            "target_type": "FUNCTION", # tail 指向 FUNCTION
                            "resolution_type": resolved_type,
                            "visibility_checked": True
                        }

                        # 避免重复添加
                        if relation not in relations:
                            relations.append(relation)

        for child in node.children:
            traverse(child, current_function)

    traverse(root_node)
    return relations