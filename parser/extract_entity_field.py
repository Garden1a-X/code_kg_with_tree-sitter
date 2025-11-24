def extract_field_entities(root_node, code_bytes, id_counter, struct_id_map):
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    def extract_full_declarator_name(decl_node):
        if decl_node is None:
            return None
        if decl_node.type in ('identifier', 'field_identifier'):
            return get_text(decl_node)
        child = decl_node.child_by_field_name('declarator')
        if child:
            return extract_full_declarator_name(child)
        for child in decl_node.children:
            result = extract_full_declarator_name(child)
            if result:
                return result
        return None

    field_entities = []
    field_id_map = {}

    def traverse_field_list(field_list_node, parent_scope):
        for field in field_list_node.children:
            if field.type != 'field_declaration':
                continue

            # ⚠️ 检查是否为匿名 struct/union 字段
            type_node = field.child_by_field_name('type')
            if type_node and type_node.type in ('struct_specifier', 'union_specifier'):
                inner_field_list = next((c for c in type_node.children if c.type == 'field_declaration_list'), None)
                if inner_field_list:
                    # 使用匿名作用域名（parent_scope + 内嵌 struct）
                    traverse_field_list(inner_field_list, parent_scope)

            # 否则处理普通字段
            decl = field.child_by_field_name('declarator')
            if not decl:
                continue
            field_name = extract_full_declarator_name(decl)
            if not field_name:
                continue

            field_id = str(next(id_counter))
            start_line = field.start_point[0] + 1  # 转为从1开始的行号
            end_line = field.end_point[0] + 1

            node_type = None
            for sub_node in field.children:
                if sub_node.type == 'primitive_type':
                    node_type = get_text(sub_node)
                    break
                elif sub_node.type == 'sized_type_specifier':
                    node_type = get_text(sub_node)
                    break

            field_entities.append({
                "id": field_id,
                "name": field_name,
                "type": "FIELD",
                "style": node_type,
                "scope": parent_scope,
                "start_line": start_line,
                "end_line": end_line
            })
            field_id_map.setdefault(field_name, []).append(field_id)

    def traverse(node, current_scope="global"):
        if node.type == 'function_definition':
            return

        if node.type in ('struct_specifier', 'union_specifier'):
            name_node = node.child_by_field_name('name')
            field_list = next((c for c in node.children if c.type == 'field_declaration_list'), None)

            if not name_node or not field_list:
                return

            struct_name = get_text(name_node)
            key_candidates = [
                (struct_name, current_scope),
                (struct_name, 'global')
            ]
            struct_id = None
            for k in key_candidates:
                if k in struct_id_map:
                    struct_id = struct_id_map[k]
                    break
            if not struct_id:
                return

            # ✅ 提取字段，包括嵌套的匿名结构体
            traverse_field_list(field_list, struct_name)

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return field_entities, field_id_map