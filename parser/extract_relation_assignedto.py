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
    macro_lookup_map=None,
    file_path=None
):
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def find_macro_expansion(node):
        if not macro_lookup_map or not file_path:
            return None, None, None

        node_start = (node.start_point[0] + 1, node.start_point[1] + 1)
        node_end = (node.end_point[0] + 1, node.end_point[1] + 1)

        # print(f"\n🔍 查找宏展开：{get_text(node)} @ {node_start}~{node_end}")
        for entry in macro_lookup_map.get(file_path, []):
            (s_line, s_col), (e_line, e_col) = entry["range"]
            macro_start = (s_line, s_col)
            macro_end = (e_line, e_col)

            # print(f"  📌 可用宏：{entry['original']} → {entry['expanded']} @ {macro_start}~{macro_end}")

            if node_start <= macro_start and macro_end <= node_end:
                # print(f"✅ 命中宏区间：{node_start} ⊇ {macro_start} ~ {macro_end}")
                if skip_non_variable_start(entry["expanded"]):
                    return skip_non_variable_start(entry["expanded"]), entry["original"], entry["range"]


        # print("❌ 未命中任何宏")
        return None, None, None

    assigned_to_relations = []

    def resolve_entity_id(node, current_scope):
        if node is None:
            return None, False

        expanded, macro_name, macro_range = find_macro_expansion(node)
        if expanded:
            expanded = expanded.strip()
            # print(f"➡️ 尝试通过宏解析右值：{macro_name} → {expanded}")
            entity_id = (
                function_id_map.get(expanded)
                or variable_id_map.get((expanded, current_scope))
                or variable_id_map.get((expanded, 'global'))
                or field_id_map.get(expanded)
            )
            # if entity_id:
                # print(f"✅ 宏右值命中实体：{expanded} → {entity_id}")
            # else:
                # print(f"❌ 宏右值未命中任何实体：{expanded}")

            return entity_id, True

        # 字段赋值
        if node.type in ('field_expression', 'member_expression'):
            field_node = node.child_by_field_name('field')
            field_text = get_text(field_node).strip() if field_node else "<?>"
            # print(f"➡️ 字段访问：{field_text}")
            return field_id_map.get(field_text), False

        # 普通标识符
        if node.type in ('identifier', 'field_identifier'):
            name = get_text(node).strip()
            entity_id = (
                function_id_map.get(name)
                or variable_id_map.get((name, current_scope))
                or variable_id_map.get((name, 'global'))
                or field_id_map.get(name)
            )
            # if entity_id:
                # print(f"✅ 标识符解析成功：{name} → {entity_id}")
            # else:
                # print(f"❌ 标识符未命中：{name}")
            return entity_id, False

        # 递归子节点
        for child in node.children:
            result, flag = resolve_entity_id(child, current_scope)
            if result:
                return result, flag

        return None, False

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

    def traverse(node, current_scope='global'):
        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            func_node = find_identifier(declarator)
            if func_node:
                current_scope = get_text(func_node).strip()
                # print(f"\n➡️ 进入函数：{current_scope}")

        # 表达式赋值
        if node.type == 'expression_statement':
            for child in node.children:
                if child.type == 'assignment_expression':
                    left = child.child_by_field_name('left')
                    right = child.child_by_field_name('right')
                    if left and right:
                        lhs_id, flag = resolve_entity_id(left, current_scope)
                        rhs_id, flag = resolve_entity_id(right, current_scope)
                        # print(f"\n📌 赋值语句：{get_text(left)} = {get_text(right)}")
                        # print(f"🔍 左值ID: {lhs_id}, 右值ID: {rhs_id}")
                        if lhs_id and rhs_id:
                            # if flag:
                                # print(f"🔍 左值ID: {lhs_id}, 右值ID: {rhs_id}")
                            assigned_to_relations.append({
                                "head": lhs_id,
                                "tail": rhs_id,
                                "type": "ASSIGNED_TO",
                                "scope": current_scope
                            })

        # 声明赋值
        if node.type == 'declaration':
            lhs_node, rhs_node = find_assignment_in_declaration(node)
            if lhs_node and rhs_node:
                lhs_id, flag = resolve_entity_id(lhs_node, current_scope)
                rhs_id, flag = resolve_entity_id(rhs_node, current_scope)
                # print(f"\n📌 声明赋值：{get_text(lhs_node)} = {get_text(rhs_node)}")
                # print(f"🔍 左值ID: {lhs_id}, 右值ID: {rhs_id}")
                if lhs_id and rhs_id:
                    # if flag:
                        # print(f"🔍 左值ID: {lhs_id}, 右值ID: {rhs_id}")
                    assigned_to_relations.append({
                        "head": lhs_id,
                        "tail": rhs_id,
                        "type": "ASSIGNED_TO",
                        "scope": current_scope
                    })

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return assigned_to_relations
