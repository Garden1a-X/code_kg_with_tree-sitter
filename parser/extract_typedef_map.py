def extract_typedef_map(root_node, code_bytes):
    """
    提取 typedef 类型别名映射
    返回: typedef_map: {alias_name -> original_struct_name}

    支持的模式:
    1. typedef struct original_name AliasName;
    2. typedef struct { ... } AliasName;  (匿名结构体)
    """
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    typedef_map = {}  # alias -> struct_name

    def traverse(node):
        if node.type == 'type_definition':
            # typedef struct xxx YYY;
            type_node = node.child_by_field_name('type')

            # 查找别名名称 (type_identifier)
            alias_name = None
            for child in node.children:
                if child.type == 'type_identifier':
                    alias_name = get_text(child).strip()
                    break

            if not alias_name:
                return

            # 查找原始结构体名称
            if type_node:
                if type_node.type in ('struct_specifier', 'union_specifier'):
                    # Case 1: typedef struct original_name { ... } AliasName;
                    struct_name_node = type_node.child_by_field_name('name')
                    if struct_name_node:
                        original_name = get_text(struct_name_node).strip()
                        typedef_map[alias_name] = original_name
                    else:
                        # Case 2: typedef struct { ... } AliasName; (匿名结构体)
                        # 使用别名作为结构体名
                        typedef_map[alias_name] = alias_name

                elif type_node.type == 'type_identifier':
                    # Case 3: typedef existing_type AliasName;
                    original_type = get_text(type_node).strip()
                    typedef_map[alias_name] = original_type

        # 递归遍历
        for child in node.children:
            traverse(child)

    traverse(root_node)
    return typedef_map
