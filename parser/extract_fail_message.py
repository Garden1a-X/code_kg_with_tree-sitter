import re
from tree_sitter import Language, Parser
import tree_sitter_c as tsc
import json
import os
from tqdm import tqdm

id = 0
entities = []
relations = []
temp = {}

def write_json(data, savepath):
    with open(savepath, 'w', encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_parser():
    language = Language(tsc.language())
    parser = Parser(language)
    return parser

def get_c_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.c', '.h')):
                yield os.path.join(root, file)

def extract_template_regex(printf_str):
    """使用正则表达式提取模板"""
    # 提取双引号内的内容
    if not printf_str:
        return ""

    # 移除所有格式化占位符 (%后面跟数字、字母的组合)
    clean_template = re.sub(r'%[-+ #0]*\d*\.?\d*[a-zA-Z]+', 'xxx ', printf_str)
    result = clean_template.replace('\\\n', ' ').replace('\\\t', ' ').replace('\\n', ' ').replace('\\t', ' ').replace('\n', ' ').replace('\t', ' ').strip()
    result = result.replace('\"', " ").replace("\\", " ").strip()
    result = re.sub(r' +', ' ', result)
    # result = re.sub(r'([^a-zA-Z])\1+', r'\1', result)
    # result = re.sub(r'([^a-zA-Z])\1+', r'\1', clean_template.replace('\\n', '').replace('\\t', '').replace('\n', '').replace('\t', '')).strip()
    return result

def extract_print_template(root, source_path, id_counter, con_dir):

    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def find_deep_identifier(node):
        if node is None:
            return None
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_deep_identifier(child)
            if result:
                return result
        return None

    global temp, entities, relations
    with open(source_path, 'rb') as f:
        code_bytes = f.read()
    for child in root.children:
        child_text = get_text(child)

    def traverse(node, current_scope):
        node_text = get_text(node).strip()
        if 'printf' not in node_text:
            return
        if node.type == 'function_definition':
            func_decl = node.child_by_field_name('declarator')
            func_node = find_deep_identifier(func_decl)
            if func_node is None:
                return
            func_name = get_text(func_node)
            func_body = node.child_by_field_name('body')
            if func_body:
                traverse(func_body, current_scope=func_name)
            return

        pattern = r'^\s*\w*printf\s*\('
        if re.search(pattern, node_text) and node.type in ['call_expression', 'expression_statement']:
            str_content = ""
            if node.type == 'call_expression':
                call_node = node
            elif node.type == 'expression_statement':
                for sub_node in node.children:
                    if sub_node.type in ['concatenated_string', 'string_literal']:
                        call_node = node
                    if sub_node.type in ['call_expression', 'comma_expression']:
                        call_node = sub_node
                        break

            for sub_node in call_node.children[1].children[1:]:
                if sub_node.type in ['concatenated_string', 'string_literal']:
                    str_content = get_text(sub_node)
                    break
            value = extract_template_regex(str_content)
            if value:
                # 添加模板
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                if not temp.get(value):
                    var_id = str(next(id_counter))
                    temp[value] = var_id
                    entity = {
                        "id": var_id,
                        "name": value,
                        "type": "FAIL_TEMPLATE"
                    }
                    entities.append(entity)
                var_id = temp[value]
                # 添加实例
                en_id = str(next(id_counter))
                entity = {
                    "id": en_id,
                    "name": node_text,
                    "type": "FAIL_MESSAGE",
                    "scope": current_scope,
                    "start_line": start_line,
                    "end_line": end_line
                }
                entities.append(entity)

                # 添加模板-实例关系
                relations.append({
                    "head": var_id,
                    "tail": en_id,
                    "type": "HAS_INSTANCE"
                })

                # 添加实例-scope关系
                scope_id = con_dir[current_scope]
                relations.append({
                    "head": scope_id,
                    "tail": en_id,
                    "type": "HAS_MESSAGE"
                })
            return

        for child in node.children:
            traverse(child, current_scope)
    traverse(root, current_scope=source_path)

def extarct_mes(parser, c_files, id_counter, file2entity):

    for source_path in tqdm(c_files, desc="🔍 提取print模板"):
        contain_list = file2entity[source_path]
        con_dir = {}
        for value in contain_list:
            if value.get('type') == 'FUNCTION':
                con_dir[value['name']] = value['id']
            elif value.get('type') == 'FILE':
                con_dir[value['source_file']] = value['id']

        abs_source_path = os.path.abspath(source_path)
        
        with open(abs_source_path, 'rb') as f:
            code_bytes = f.read()
        tree = parser.parse(code_bytes)
        root = tree.root_node
        extract_print_template(root, source_path, id_counter, con_dir)
    
    global temp, entities, relations
    return entities, relations



