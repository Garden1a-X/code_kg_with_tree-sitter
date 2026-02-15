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
    struct_fields_ordered = {}  # struct_name -> [(field_id, field_name), ...]

    def traverse_field_list(field_list_node, parent_scope):
        field_index = 0  # Track field declaration order
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

            # 提取字段类型信息（包括结构体类型）
            node_type = None
            struct_type_name = None  # 用于记录结构体类型名
            for sub_node in field.children:
                if sub_node.type == 'primitive_type':
                    node_type = get_text(sub_node)
                    break
                elif sub_node.type == 'sized_type_specifier':
                    node_type = get_text(sub_node)
                    break
                elif sub_node.type in ('struct_specifier', 'union_specifier'):
                    # 结构体或联合体类型字段
                    struct_name_node = sub_node.child_by_field_name('name')
                    if struct_name_node:
                        struct_type_name = get_text(struct_name_node).strip()
                        node_type = f"struct {struct_type_name}"
                elif sub_node.type == 'type_identifier':
                    # typedef 类型（可能是 typedef 的结构体）
                    node_type = get_text(sub_node).strip()

            field_entities.append({
                "id": field_id,
                "name": field_name,
                "type": "FIELD",
                "style": node_type,
                "scope": parent_scope,
                "start_line": start_line,
                "end_line": end_line,
                "field_index": field_index,  # Add field order
                "struct_type": struct_type_name  # 记录结构体类型名（如果是结构体字段）
            })
            field_id_map.setdefault(field_name, []).append(field_id)

            # Track ordered fields for positional initialization
            if parent_scope not in struct_fields_ordered:
                struct_fields_ordered[parent_scope] = []
            struct_fields_ordered[parent_scope].append((field_id, field_name, struct_type_name))

            field_index += 1

    def traverse(node, current_scope="global"):
        if node.type == 'function_definition':
            return

        # 处理普通的 struct/union 定义
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

        # 处理 typedef struct {...} Name; (匿名结构体 typedef)
        elif node.type == 'type_definition':
            type_node = node.child_by_field_name('type')

            # 查找 typedef 的别名名称
            name_node = None
            for child in node.children:
                if child.type == 'type_identifier':
                    name_node = child
                    break

            if type_node and type_node.type in ('struct_specifier', 'union_specifier'):
                field_list = next((c for c in type_node.children if c.type == 'field_declaration_list'), None)

                if not field_list or not name_node:
                    return

                # 使用 typedef 别名作为结构体名
                struct_name = get_text(name_node).strip()

                # 检查这个 typedef 名是否在 struct_id_map 中
                key_candidates = [
                    (struct_name, current_scope),
                    (struct_name, 'global')
                ]
                struct_id = None
                for k in key_candidates:
                    if k in struct_id_map:
                        struct_id = struct_id_map[k]
                        break

                if struct_id:
                    # 提取字段，使用 typedef 别名作为 scope
                    traverse_field_list(field_list, struct_name)

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return field_entities, field_id_map, struct_fields_ordered