def extract_returns_relations(
    root_node,
    code_bytes,
    function_id_map,
    variable_id_map,
    field_id_map
):
    """
    提取 RETURNS 关系：FUNCTION-[RETURNS]->VARIABLE / FIELD
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

    def resolve_return_target(node, current_func):
        # 🟢 字段访问：conf->level
        if node.type in ("field_expression", "pointer_expression"):
            field_node = node.child_by_field_name("field")
            if field_node:
                field_name = get_text(field_node).strip()
                if field_name in field_id_map:
                    return field_id_map[field_name]

        # 🟢 标识符（变量名）
        if node.type == 'identifier':
            name = get_text(node).strip()

            if (name, current_func) in variable_id_map:
                return variable_id_map[(name, current_func)]

            if (name, 'global') in variable_id_map:
                return variable_id_map[(name, 'global')]

        # 🔴 其他：如 return 42、return call_x() 等
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
                target_id = resolve_return_target(return_expr, current_function)
                if target_id:
                    returns_relations.append({
                        "head": function_id_map[current_function],
                        "tail": target_id,
                        "type": "RETURNS"
                    })

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return returns_relations
