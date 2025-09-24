# extract_relation_typeof.py 的修复
def extract_typeof_relations(
    root_node, 
    code_bytes, 
    variable_entities, 
    field_entities, 
    struct_id_map,
    current_file_path=None,
    file_visibility=None,
    entity_file_map=None
):
    """
    提取 TYPE_OF 关系：VARIABLE/FIELD-[TYPE_OF]->STRUCT
    新增了可见性参数，保持向后兼容
    """
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    typeof_relations = set()

    # 创建结构体名集合
    struct_names = set(struct_id_map.keys())

    # 构建变量/字段映射
    var_scope_map = {(v["name"], v["scope"]): v["id"] for v in variable_entities}
    field_scope_map = {(f["name"], f["scope"]): f["id"] for f in field_entities}

    def clean_struct_name(type_text):
        """统一清洗类型名：去除 struct 前缀和多余空格"""
        type_text = type_text.strip()
        if type_text.startswith("struct "):
            type_text = type_text[len("struct "):].strip()
        return type_text

    def resolve_struct_with_visibility(type_text):
        """基于可见性解析结构体"""
        if not current_file_path or not file_visibility or not entity_file_map:
            # 回退到原始逻辑
            return struct_id_map.get(type_text)
        
        visible_files = file_visibility.get(current_file_path, {current_file_path})
        
        # 查找可见的结构体
        if isinstance(struct_id_map.get(type_text), str):
            # 单个结构体
            struct_id = struct_id_map[type_text]
            struct_file = entity_file_map.get(struct_id)
            if struct_file and struct_file in visible_files:
                return struct_id
        elif isinstance(struct_id_map.get(type_text), list):
            # 多个同名结构体，按可见性优先级选择
            for struct_id in struct_id_map[type_text]:
                struct_file = entity_file_map.get(struct_id)
                if struct_file and struct_file in visible_files:
                    return struct_id
        
        return None

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
                    struct_id = resolve_struct_with_visibility(type_text)
                    if struct_id:
                        var_node = decl_node
                        while var_node and var_node.type != "identifier":
                            var_node = var_node.child_by_field_name("declarator")
                        if var_node:
                            var_name = get_text(var_node)
                            key = (var_name, current_function)
                            if key in var_scope_map:
                                typeof_relations.add((var_scope_map[key], struct_id))

        # struct 类型字段定义
        if node.type == "field_declaration":
            type_node = node.child_by_field_name("type")
            decl_node = node.child_by_field_name("declarator")
            if type_node and decl_node:
                type_text = clean_struct_name(get_text(type_node))
                if type_text in struct_names:
                    struct_id = resolve_struct_with_visibility(type_text)
                    if struct_id:
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
                                typeof_relations.add((field_scope_map[key], struct_id))

        for child in node.children:
            traverse(child, current_function)

    traverse(root_node)

    # 输出标准格式关系
    result_relations = []
    for ent_id, struct_id in sorted(typeof_relations):
        relation = {
            "head": ent_id,
            "tail": struct_id,
            "type": "TYPE_OF"
        }
        
        # 添加可见性标记
        if current_file_path and file_visibility and entity_file_map:
            relation["visibility_checked"] = True
            
        result_relations.append(relation)
    
    return result_relations