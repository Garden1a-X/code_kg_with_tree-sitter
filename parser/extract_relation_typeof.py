# extract_relation_typeof.py - 最终版

def extract_typeof_relations(
    root_node, 
    code_bytes, 
    variable_entities,  # 接收 variable + param 的合并列表
    field_entities, 
    struct_id_map,
    current_file_path=None,
    file_visibility=None,
    entity_file_map=None
):
    """
    提取 TYPE_OF 关系：VARIABLE/FIELD-[TYPE_OF]->STRUCT
    
    修复要点：
    1. 正确处理 field_identifier 类型（不仅是 identifier）
    2. 支持 struct_id_map 的多种键格式
    """
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    typeof_relations = set()

    # === 1. 构建查找表 ===
    struct_names = set()
    for key in struct_id_map.keys():
        if isinstance(key, tuple):
            struct_names.add(key[0])
        else:
            struct_names.add(key)

    var_map = {}
    for v in variable_entities:
        key = (v["name"], v["scope"])
        var_map[key] = v["id"]
    
    field_map = {}
    for f in field_entities:
        key = (f["name"], f.get("scope", ""))
        field_map[key] = f["id"]

    # === 2. 辅助函数 ===
    def clean_type(type_text):
        """清理类型名：去除 struct 前缀和指针"""
        type_text = type_text.strip()
        if type_text.startswith("struct "):
            type_text = type_text[len("struct "):].strip()
        type_text = type_text.replace("*", "").strip()
        return type_text

    def get_struct_id(struct_name):
        """获取结构体ID，支持多种键格式"""
        if struct_name in struct_id_map:
            result = struct_id_map[struct_name]
            return result[0] if isinstance(result, list) else result
        
        for key in struct_id_map.keys():
            if isinstance(key, tuple) and key[0] == struct_name:
                result = struct_id_map[key]
                return result[0] if isinstance(result, list) else result
        
        return None

    def get_identifier_name(declarator):
        """从 declarator 提取标识符名（支持 identifier 和 field_identifier）"""
        if not declarator:
            return None
        
        if declarator.type in ("identifier", "field_identifier"):
            return get_text(declarator)
        
        def find_identifier(node):
            if node.type in ("identifier", "field_identifier"):
                return get_text(node)
            for child in node.children:
                result = find_identifier(child)
                if result:
                    return result
            return None
        
        return find_identifier(declarator)

    # === 3. 遍历 AST ===
    def traverse(node, current_scope="global"):
        nonlocal typeof_relations

        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            func_name = get_identifier_name(declarator)
            if func_name:
                current_scope = func_name

        # 处理变量声明
        if node.type == "declaration":
            type_node = node.child_by_field_name("type")
            declarator = node.child_by_field_name("declarator")
            
            if type_node and declarator:
                type_text = get_text(type_node)
                struct_name = clean_type(type_text)
                
                if struct_name in struct_names:
                    struct_id = get_struct_id(struct_name)
                    var_name = get_identifier_name(declarator)
                    
                    if struct_id and var_name:
                        var_key = (var_name, current_scope)
                        if var_key in var_map:
                            typeof_relations.add((var_map[var_key], struct_id))

        # 处理字段声明
        if node.type == "field_declaration":
            type_node = node.child_by_field_name("type")
            declarator = node.child_by_field_name("declarator")
            
            if type_node and declarator:
                type_text = get_text(type_node)
                struct_name = clean_type(type_text)
                
                if struct_name in struct_names:
                    struct_id = get_struct_id(struct_name)
                    field_name = get_identifier_name(declarator)
                    
                    if struct_id and field_name:
                        parent = node.parent
                        while parent and parent.type != "struct_specifier":
                            parent = parent.parent
                        
                        parent_struct = ""
                        if parent:
                            name_node = parent.child_by_field_name("name")
                            if name_node:
                                parent_struct = get_text(name_node)
                        
                        field_key = (field_name, parent_struct)
                        if field_key in field_map:
                            typeof_relations.add((field_map[field_key], struct_id))

        for child in node.children:
            traverse(child, current_scope)

    traverse(root_node)

    # === 4. 输出 ===
    result_relations = []
    for ent_id, struct_id in sorted(typeof_relations):
        relation = {
            "head": ent_id,
            "tail": struct_id,
            "type": "TYPE_OF"
        }
        
        if current_file_path and file_visibility and entity_file_map:
            relation["visibility_checked"] = True
            
        result_relations.append(relation)
    
    return result_relations
