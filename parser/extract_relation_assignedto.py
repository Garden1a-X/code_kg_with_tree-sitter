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
    file_path=None,
    struct_fields_ordered=None,
    typedef_map=None
):
    """
    基于文件可见性的赋值关系提取
    支持多值映射的变量查找，正确处理同名全局变量消歧
    新增：支持结构体初始化器中的字段赋值
    新增：支持位置初始化（positional initializer）
    新增：支持 typedef 类型别名
    """
    if struct_fields_ordered is None:
        struct_fields_ordered = {}
    if typedef_map is None:
        typedef_map = {}
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

    def infer_struct_type(declaration_node):
        """
        从变量声明中推断结构体类型名称
        支持: struct xxx var, typedef 别名 var
        返回: struct_name or None
        """
        if not declaration_node:
            return None

        # 查找 type specifier
        type_node = declaration_node.child_by_field_name('type')
        if not type_node:
            return None

        # Case 1: struct xxx var;
        if type_node.type in ('struct_specifier', 'union_specifier'):
            name_node = type_node.child_by_field_name('name')
            if name_node:
                return get_text(name_node).strip()

        # Case 2: TypedefName var;  (使用 typedef 别名)
        elif type_node.type == 'type_identifier':
            typedef_name = get_text(type_node).strip()
            # 查找 typedef 映射
            if typedef_name in typedef_map:
                original_name = typedef_map[typedef_name]
                # 递归解析多级 typedef（防止循环引用）
                visited = {typedef_name}
                max_depth = 10  # 防止过深的 typedef 链
                depth = 0
                while original_name in typedef_map and depth < max_depth:
                    if original_name in visited:
                        # 检测到循环引用，停止解析
                        debug_print(f"⚠️ Typedef 循环引用检测: {original_name}")
                        break
                    visited.add(original_name)
                    original_name = typedef_map[original_name]
                    depth += 1
                return original_name
            # 如果没有映射，可能是匿名 struct typedef
            return typedef_name

        return None

    def traverse(node, current_scope='global'):
        # 进入函数定义
        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_identifier(declarator)
            if func_node:
                current_scope = get_text(func_node).strip()

        # 辅助函数：处理初始化器列表
        def handle_initializer_list(init_list_node, parent_struct_name, context_var_id=None, context_var_name=None):
            """
            处理初始化器列表
            支持:
            1. Designated initializer: {.field = value, ...}
            2. Positional initializer: {value1, value2, ...}
            """
            if not init_list_node or init_list_node.type != 'initializer_list':
                return

            # 获取结构体的有序字段列表
            ordered_fields = struct_fields_ordered.get(parent_struct_name, [])
            positional_index = 0  # 位置初始化索引

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

                # 处理位置初始化（positional initializer）
                elif child.type not in (',', '{', '}', 'comment'):
                    # 这是一个直接的值节点（不是 initializer_pair）
                    value_node = child

                    debug_print(f"🔍 位置初始化: index={positional_index}, child.type={child.type}")

                    # 处理嵌套的 initializer_list（如嵌套结构体或数组元素）
                    if child.type == 'initializer_list':
                        if positional_index < len(ordered_fields):
                            # 获取当前位置对应字段的类型信息
                            if len(ordered_fields[positional_index]) >= 3:
                                field_id, field_name, nested_struct_type = ordered_fields[positional_index]
                            else:
                                # 兼容旧格式（只有 field_id 和 field_name）
                                field_id, field_name = ordered_fields[positional_index]
                                nested_struct_type = None

                            if nested_struct_type:
                                # 这是嵌套结构体字段，递归处理
                                debug_print(f"🔄 递归处理嵌套结构体: {field_name} -> {nested_struct_type}")
                                handle_initializer_list(
                                    child,
                                    nested_struct_type,
                                    context_var_id,
                                    context_var_name
                                )
                            else:
                                debug_print(f"⏭️ 跳过未知类型的嵌套 initializer_list")

                        positional_index += 1
                        continue

                    # 使用位置索引获取对应的字段
                    if positional_index < len(ordered_fields):
                        # 兼容新旧格式
                        if len(ordered_fields[positional_index]) >= 3:
                            field_id, field_name, _ = ordered_fields[positional_index]
                        else:
                            field_id, field_name = ordered_fields[positional_index]
                        debug_print(f"📌 匹配字段: {field_name} (index {positional_index})")

                        # 解析赋值的右侧值
                        try:
                            rhs_id, _ = resolve_entity_with_visibility(value_node, current_scope)
                        except Exception as e:
                            debug_print(f"❌ 解析实体失败: {e}")
                            positional_index += 1
                            continue

                        if rhs_id:
                            debug_print(f"✅ 创建关系: {field_name} -> {rhs_id}")
                            relation = {
                                "head": field_id,
                                "tail": rhs_id,
                                "type": "ASSIGNED_TO",
                                "scope": parent_struct_name,
                                "visibility_checked": True,
                                "init_style": "positional"  # 标记为位置初始化
                            }

                            if context_var_id:
                                relation["context_var_id"] = context_var_id
                            if context_var_name:
                                relation["context_var_name"] = context_var_name

                            if relation not in assigned_to_relations:
                                assigned_to_relations.append(relation)
                        else:
                            debug_print(f"⚠️ 未找到右值实体")

                        positional_index += 1
                    else:
                        debug_print(f"⚠️ 索引超出字段范围: {positional_index} >= {len(ordered_fields)}")
                        break  # 超出字段范围，停止处理

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
                    
                    # 从父节点获取类型（支持 struct 和 typedef）
                    parent = node.parent
                    if parent and parent.type == 'declaration':
                        struct_name = infer_struct_type(parent)

                        if struct_name and var_id:
                            # 检查是否是数组初始化 vs 嵌套结构体初始化
                            # 数组：所有值节点都是 initializer_list，如 {{...}, {...}}
                            # 嵌套结构体：混合了 initializer_list 和其他值，如 {{...}, value}

                            # 收集所有非分隔符的子节点
                            value_nodes = [
                                child for child in value.children
                                if child.type not in (',', '{', '}', 'comment')
                            ]

                            # 收集其中的 initializer_list 节点
                            child_initializers = [
                                child for child in value_nodes
                                if child.type == 'initializer_list'
                            ]

                            # 判断：只有当所有值都是 initializer_list 且数量>1 时，才是数组
                            is_array = (
                                len(child_initializers) > 1 and
                                len(child_initializers) == len(value_nodes)
                            )

                            if is_array:
                                # 数组初始化：遍历每个数组元素
                                debug_print(f"📦 数组初始化: {var_name}[{len(child_initializers)}]")
                                for idx, element_init in enumerate(child_initializers):
                                    debug_print(f"  处理数组元素 [{idx}]")
                                    handle_initializer_list(
                                        init_list_node=element_init,
                                        parent_struct_name=struct_name,
                                        context_var_id=var_id,
                                        context_var_name=f"{var_name}[{idx}]"
                                    )
                            else:
                                # 普通结构体初始化（包括嵌套结构体）
                                debug_print(f"🏗️ 结构体初始化: {var_name}")
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
