def extract_typeof_relations(root_node, code_bytes, variable_entities, field_entities, struct_id_map):
    """
    提取 TYPE_OF 关系：
    - VARIABLE-[TYPE_OF]->STRUCT
    - FIELD-[TYPE_OF]->STRUCT

    要求：
    - variable_entities: 包含变量名 + scope（函数名或 'global'）
    - field_entities: 包含字段名 + scope（结构体名）
    - struct_id_map: 名称 → id，名称应为结构体名，不含 'struct ' 前缀
    """

    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    typeof_relations = set()

    # 创建结构体名集合
    struct_names = set(struct_id_map.keys())

    # 构建变量/字段映射，方便定位实体 id
    var_scope_map = {(v["name"], v["scope"]): v["id"] for v in variable_entities}
    field_scope_map = {(f["name"], f["scope"]): f["id"] for f in field_entities}

    def clean_struct_name(type_text):
        """统一清洗类型名：去除 struct 前缀和多余空格"""
        type_text = type_text.strip()
        if type_text.startswith("struct "):
            type_text = type_text[len("struct "):].strip()
        return type_text

    def traverse(node, current_function="global"):
        nonlocal typeof_relations

        # 进入函数定义，设置当前作用域
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            id_node = declarator
            while id_node and id_node.type != "identifier":
                id_node = id_node.child_by_field_name("declarator")
            if id_node:
                current_function = get_text(id_node)

        # struct 类型变量定义
        if node.type == "declaration":
            type_node = node.child_by_field_name("type")
            decl_node = node.child_by_field_name("declarator")
            if type_node and decl_node:
                type_text = clean_struct_name(get_text(type_node))
                if type_text in struct_names:
                    var_node = decl_node
                    while var_node and var_node.type != "identifier":
                        var_node = var_node.child_by_field_name("declarator")
                    if var_node:
                        var_name = get_text(var_node)
                        key = (var_name, current_function)
                        if key in var_scope_map:
                            typeof_relations.add((var_scope_map[key], struct_id_map[type_text]))

        # struct 类型字段定义
        if node.type == "field_declaration":
            type_node = node.child_by_field_name("type")
            decl_node = node.child_by_field_name("declarator")
            if type_node and decl_node:
                type_text = clean_struct_name(get_text(type_node))
                if type_text in struct_names:
                    ident = decl_node
                    while ident and ident.type != "identifier":
                        ident = ident.child_by_field_name("declarator")
                    if ident:
                        field_name = get_text(ident)
                        # 查找其所属 struct
                        parent = node.parent
                        while parent and parent.type != "struct_specifier":
                            parent = parent.parent
                        struct_scope = None
                        if parent:
                            name_node = parent.child_by_field_name("name")
                            if name_node:
                                struct_scope = get_text(name_node)
                        key = (field_name, struct_scope)
                        if key in field_scope_map:
                            typeof_relations.add((field_scope_map[key], struct_id_map[type_text]))

        for child in node.children:
            traverse(child, current_function)

    traverse(root_node)

    # 输出标准格式关系
    return [
        {
            "head": ent_id,
            "tail": struct_id,
            "type": "TYPE_OF"
        }
        for ent_id, struct_id in sorted(typeof_relations)
    ]
