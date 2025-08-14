def extract_function_entities(root_node, code_bytes, id_counter):
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    entities = []
    id_map = {}

    def find_identifier(node):
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_identifier(child)
            if result is not None:
                return result
        return None

    def traverse(node):
        nonlocal entities, id_map

        if node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            if declarator is None:
                return
            func_node = find_identifier(declarator)
            if func_node is None:
                return  # 未找到函数名，跳过

            func_name = get_text(func_node)
            func_id = str(next(id_counter))
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1


            entity = {
                "id": func_id,
                "name": func_name,
                "type": "FUNCTION",
                "start_line": start_line,
                "end_line": end_line
            }
            entities.append(entity)
            id_map[func_name] = func_id

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return entities, id_map
