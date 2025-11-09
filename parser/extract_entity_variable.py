def extract_variable_entities(root_node, code_bytes, id_counter):
    """
    提取局部变量和全局变量实体，不包括函数参数。
    返回 id_map[(var_name, scope)] = var_id
    """

    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    def find_deep_identifier(node):
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_deep_identifier(child)
            if result:
                return result
        return None

    entities = []
    id_map = {}  # key = (var_name, scope)
    scope_map = {}

    def traverse(node, current_scope="global"):
        nonlocal entities, id_map, scope_map

        # 处理函数定义，更新作用域
        if node.type == 'function_definition':
            func_decl = node.child_by_field_name('declarator')
            func_node = find_deep_identifier(func_decl)
            if func_node is None:
                return
            func_name = get_text(func_node)
            func_body = node.child_by_field_name('body')
            if func_body:
                traverse(func_body, current_scope=func_name)
            return

        # 处理变量声明
        if node.type == 'declaration':
            id_node = find_deep_identifier(node)
            if id_node:
                var_name = get_text(id_node)
                var_id = str(next(id_counter))
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                node_type = None
                for sub_node in node.children:
                    if sub_node.type == 'primitive_type':
                        node_type = get_text(sub_node)
                        break
                    elif sub_node.type == 'sized_type_specifier':
                        node_type = get_text(sub_node)
                        break
                entity = {
                    "id": var_id,
                    "name": var_name,
                    "type": "VARIABLE",
                    "style": node_type,
                    "scope": current_scope,
                    "start_line": start_line,
                    "end_line": end_line
                }
                entities.append(entity)
                id_map[(var_name, current_scope)] = var_id
                scope_map.setdefault(current_scope, []).append(var_id)

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return entities, id_map, scope_map
def extract_function_parameters(root_node, code_bytes, id_counter, function_id_map):
    """
    抽取函数参数变量（role=param），每个参数作为一个 VARIABLE 实体，
    scope 设为函数名，附加属性 role="param"
    返回 param_id_map[(name, scope)] = id
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

    def find_node_by_type(node, target_type):
        if node is None:
            return None
        if node.type == target_type:
            return node
        for child in node.children:
            result = find_node_by_type(child, target_type)
            if result:
                return result
        return None

    param_entities = []
    param_id_map = {}  # key = (param_name, function_name)

    def traverse(node, current_function=None):
        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_deep_identifier(declarator)
            if func_node is None:
                return
            func_name = get_text(func_node)
            current_function = func_name

            params_node = find_node_by_type(declarator, 'parameter_list')
            if params_node:
                for param in params_node.children:
                    if param.type == 'parameter_declaration':
                        declarator_node = param.child_by_field_name('declarator')
                        id_node = find_deep_identifier(declarator_node)
                        if id_node:
                            param_name = get_text(id_node)
                            param_id = str(next(id_counter))
                            start_line = param.start_point[0] + 1
                            end_line = param.end_point[0] + 1
                            node_type = None
                            for sub_node in param.children:
                                if sub_node.type == 'primitive_type':
                                    node_type = get_text(sub_node)
                                    break
                                elif sub_node.type == 'sized_type_specifier':
                                    node_type = get_text(sub_node)
                                    break
                            param_entities.append({
                                "id": param_id,
                                "name": param_name,
                                "type": "VARIABLE",
                                "style": node_type,
                                "scope": current_function,
                                "role": "param",
                                "start_line": start_line,
                                "end_line": end_line
                            })
                            param_id_map[(param_name, current_function)] = param_id

        for child in node.children:
            traverse(child, current_function)

    traverse(root_node)
    return param_entities, param_id_map