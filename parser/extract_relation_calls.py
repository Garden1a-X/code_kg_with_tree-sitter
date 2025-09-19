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

def extract_calls_relations(
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

    def find_identifier(node):
        if node is None:
            return None
        if node.type == "identifier":
            return node
        for child in node.children:
            result = find_identifier(child)
            if result:
                return result
        return None

    def find_macro_expansion(node):
        if not macro_lookup_map or not file_path:
            return None, None, None

        # ✅ Tree-sitter 的行号从 0 开始，需要 +1 与宏匹配
        node_start = (node.start_point[0] + 1, node.start_point[1] + 1)
        node_end = (node.end_point[0] + 1, node.end_point[1] + 1)
        node_type = node.type
        node_text = get_text(node)

        # print(f"\n🔍 [节点信息] type: {node_type}")
        # print(f"  🧭 范围: {node_start} → {node_end}")
        # print(f"  📄 内容: {repr(node_text)}")

        for entry in macro_lookup_map.get(file_path, []):
            (s_line, s_col), (e_line, e_col) = entry["range"]
            macro_start = (s_line, s_col)
            macro_end = (e_line, e_col)

            # print(f"  ⏱️ 当前宏: {macro_start} → {macro_end} ({entry['original']} → {entry['expanded']})")

            # ✅ 判断该宏是否被这个 AST 节点完整包裹
            if node_start <= macro_start and macro_end <= node_end:
                # print("  ✅ 命中该节点范围")
                if skip_non_variable_start(entry["expanded"]):
                    return skip_non_variable_start(entry["expanded"]), entry["original"], entry["range"]

        # print("  ❌ 未命中任何宏范围")
        return None, None, None

    relations = []

    def traverse(node, current_function=None):
        nonlocal relations

        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            id_node = find_identifier(declarator)
            if id_node:
                current_function = get_text(id_node)

        # ✅ 检查调用表达式
        if node.type == "call_expression" and current_function:
            callee_node = node.child_by_field_name("function")
            caller_id = function_id_map.get(current_function)

            callee_name = None
            resolved_type = None
            resolved_id = None

            # ✅ 优先尝试匹配宏展开
            expanded, original_macro, macro_range = find_macro_expansion(node)

            if expanded:
                callee_name = expanded
                # print(f"\n[宏调用] {file_path}:{macro_range} 原始: {original_macro} → 展开为: {expanded}")
            else:
                id_node = find_identifier(callee_node)
                if id_node:
                    callee_name = get_text(id_node)
                    # print(f"\n[直接调用] {file_path} 中函数 {current_function} 调用了 {callee_name}")

            if callee_name:
                if callee_name in function_id_map:
                    resolved_id = function_id_map[callee_name]
                    resolved_type = "function"
                elif (callee_name, current_function) in variable_id_map:
                    resolved_id = variable_id_map[(callee_name, current_function)]
                    resolved_type = "local_func_ptr"
                elif callee_name in field_id_map:
                    resolved_id = field_id_map[callee_name]
                    resolved_type = "field_func_ptr"

                if resolved_id:
                    # if expanded:
                        # print(f"  ✅ 识别宏调用 {caller_id} 调用 → id: {resolved_id}")
                    # print(f"  ✅ 识别为 {resolved_type} 调用 → id: {resolved_id}")
                    relations.append({
                        "head": caller_id,
                        "tail": resolved_id,
                        "type": "CALLS"
                    })
                # else:
                #     print(f"  ⚠️ 未能解析调用目标 {callee_name}")

        for child in node.children:
            traverse(child, current_function)

    traverse(root_node)
    return relations
