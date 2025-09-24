def extract_struct_entities(root_node, code_bytes, id_counter):
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    struct_entities = []
    struct_id_map = {}  # (name, scope) -> id

    def add_struct(name, scope, start_line=None, end_line=None):
        key = (name, scope)
        if key in struct_id_map:
            return struct_id_map[key]

        struct_id = str(next(id_counter))
        entity = {
            "id": struct_id,
            "name": name,
            "type": "STRUCT",
            "scope": scope
        }
        if start_line is not None and end_line is not None:
            entity["start_line"] = start_line
            entity["end_line"] = end_line

        struct_entities.append(entity)
        struct_id_map[key] = struct_id
        return struct_id

    def traverse(node, current_scope="global"):
        if node.type == 'function_definition':
            return  # 跳过函数体中的结构体定义

        # === 普通 struct 或 union ===
        if node.type in ['struct_specifier', 'union_specifier']:
            id_node = node.child_by_field_name('name')
            field_list = next((c for c in node.children if c.type == 'field_declaration_list'), None)

            if not id_node or not field_list:
                return  # 匿名 struct 或前向声明，不处理

            struct_name = get_text(id_node).strip()
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            add_struct(struct_name, current_scope, start_line, end_line)

            # 遍历其字段，设定新的作用域为该 struct 名
            for field in field_list.children:
                traverse(field, current_scope=struct_name)

        # === typedef struct {...} Name; ===
        elif node.type == 'type_definition':
            type_node = node.child_by_field_name('type')

            name_node = None
            for child in node.children:
                if child.type == 'type_identifier':
                    name_node = child
                    break

            if type_node and type_node.type in ['struct_specifier', 'union_specifier']:
                field_list = next((c for c in type_node.children if c.type == 'field_declaration_list'), None)
                if not field_list or not name_node:
                    return

                struct_name = get_text(name_node).strip()
                start_line = type_node.start_point[0] + 1
                end_line = type_node.end_point[0] + 1
                add_struct(struct_name, current_scope, start_line, end_line)

                for field in field_list.children:
                    traverse(field, current_scope=struct_name)

        # 处理字段内嵌的 struct
        elif node.type == 'field_declaration':
            for child in node.children:
                traverse(child, current_scope)

        # 继续递归
        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)
    return struct_entities, struct_id_map
