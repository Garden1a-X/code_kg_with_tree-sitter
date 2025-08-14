import os
import json
import time
import tracemalloc
from collections import defaultdict, Counter
from tqdm import tqdm
from tree_sitter import Language, Parser

# === 实体提取模块 ===
from extract_entity_file import extract_file_entity
from extract_entity_variable import extract_variable_entities, extract_function_parameters
from extract_entity_function import extract_function_entities
from extract_entity_struct import extract_struct_entities
from extract_entity_field import extract_field_entities

# === 关系提取模块 ===
from extract_relation_calls import extract_calls_relations
from extract_relation_assignedto import extract_assigned_to_relations
from extract_relation_contains import build_file_level_contains
from extract_relation_has_members import extract_has_member_relations
from extract_relation_has_parameters import extract_has_parameter_relations
from extract_relation_has_variables import extract_has_variable_relations
from extract_relation_returns import extract_returns_relations
from extract_relation_typeof import extract_typeof_relations

# === 配置路径 ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LANG_SO_PATH = os.path.join(ROOT_DIR, '..', 'build', 'my-languages.so')
OUTPUT_BASE = os.path.join(ROOT_DIR, '..', 'output')
MACRO_JSON_PATH = "/data/xuao/code_kg/data/glibc_data/macro.json"

def id_generator(start=1):
    while True:
        yield start
        start += 1

def get_parser():
    language = Language(LANG_SO_PATH, 'c')
    parser = Parser()
    parser.set_language(language)
    return parser

def get_c_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.c', '.h')):
                yield os.path.join(root, file)

def load_macro_lookup_map(json_path):
    with open(json_path, 'r') as f:
        macro_json = json.load(f)
    macro_lookup_map = defaultdict(list)
    for entry in macro_json:
        file = os.path.abspath(entry["file"])
        start_line, start_col, end_line, end_col = entry["location"]
        macro_lookup_map[file].append({
            "range": ((start_line, start_col), (end_line, end_col)),
            "expanded": entry["macro"],
            "original": entry["name"]
        })
    return macro_lookup_map

def extract_all(source_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    entity_path = os.path.join(output_dir, 'entity.json')
    relation_path = os.path.join(output_dir, 'relation.json')

    id_counter = id_generator()
    parser = get_parser()

    all_entities = []
    all_relations = []

    # 映射表与实体容器
    function_id_map = {}
    variable_id_map = {}
    param_id_map = {}
    struct_id_map = {}
    field_id_map = {}
    variable_scope_map = {}
    file_id_map = {}

    function_entities = []
    param_entities = []
    variable_entities = []
    struct_entities = []
    field_entities = []

    file_trees = []

    # === 源码与宏信息读取 ===
    c_files = list(get_c_files(source_dir))
    macro_lookup_map = load_macro_lookup_map(MACRO_JSON_PATH)
    print("✅ 读取宏展开信息完成，共包含文件数：", len(macro_lookup_map))

    # === 阶段 1：提取所有实体 ===
    for source_path in tqdm(c_files, desc="🔍 阶段 1：提取实体"):
        with open(source_path, 'rb') as f:
            code_bytes = f.read()
        tree = parser.parse(code_bytes)
        root = tree.root_node
        file_trees.append((source_path, root, code_bytes))

        file_entities, file_id = extract_file_entity(source_path, id_counter)
        file_id_map[source_path] = file_id
        all_entities.extend(file_entities)

        functions, f_map = extract_function_entities(root, code_bytes, id_counter)
        for e in functions: e["source_file"] = source_path
        function_entities.extend(functions)
        function_id_map.update(f_map)

        structs, s_map = extract_struct_entities(root, code_bytes, id_counter)
        for e in structs: e["source_file"] = source_path
        struct_entities.extend(structs)
        struct_id_map.update(s_map)

        variables, v_map, scope_map = extract_variable_entities(root, code_bytes, id_counter)
        for e in variables: e["source_file"] = source_path
        variable_entities.extend(variables)
        variable_id_map.update(v_map)
        variable_scope_map.update(scope_map)

        params, p_map = extract_function_parameters(root, code_bytes, id_counter, f_map)
        for e in params: e["source_file"] = source_path
        param_entities.extend(params)
        param_id_map.update(p_map)

        fields, f_map2 = extract_field_entities(root, code_bytes, id_counter, s_map)
        for e in fields: e["source_file"] = source_path
        field_entities.extend(fields)
        for name, ids in f_map2.items():
            field_id_map.setdefault(name, []).extend(ids)

    all_entities.extend(function_entities + struct_entities + variable_entities + param_entities + field_entities)

    # === 阶段 2：提取 CALLS 关系 ===
    for source_path, root, code_bytes in tqdm(file_trees, desc="🔗 阶段 2：提取 CALLS"):
        abs_path = os.path.abspath(source_path)
        rels = extract_calls_relations(
            root,
            code_bytes,
            function_id_map,
            {**variable_id_map, **param_id_map},
            field_id_map,
            macro_lookup_map,
            abs_path
        )
        all_relations.extend(rels)

    # === 阶段 3：提取 ASSIGNED_TO 关系 ===
    for source_path, root, code_bytes in tqdm(file_trees, desc="🔗 阶段 3：提取 ASSIGNED_TO"):
        abs_path = os.path.abspath(source_path)
        rels = extract_assigned_to_relations(
            root,
            code_bytes,
            function_id_map,
            {**variable_id_map, **param_id_map},
            field_id_map,
            macro_lookup_map,
            abs_path
        )
        all_relations.extend(rels)

    # === 阶段 4：静态关系（包含/成员） ===
    for source_path in c_files:
        file_id = file_id_map.get(source_path)
        if file_id is None:
            continue
        rels = build_file_level_contains(file_id, function_id_map, struct_id_map, variable_scope_map)
        all_relations.extend(rels)

    rels = extract_has_member_relations(field_entities, struct_id_map)
    all_relations.extend(rels)

    # === 阶段 5：基于函数的内部语义关系 ===
    for _, root, code_bytes in tqdm(file_trees, desc="🔗 阶段 5：提取 RETURNS / HAS_PARAM / HAS_VAR / TYPE_OF"):
        # HAS_PARAMETER
        rels = extract_has_parameter_relations(param_entities, function_id_map)
        all_relations.extend(rels)

        # HAS_VARIABLE
        rels = extract_has_variable_relations(variable_entities, function_id_map)
        all_relations.extend(rels)

        # RETURNS
        rels = extract_returns_relations(
            root,
            code_bytes,
            function_id_map,
            {**variable_id_map, **param_id_map},
            field_id_map
        )
        all_relations.extend(rels)

        # TYPE_OF
        rels = extract_typeof_relations(
            root,
            code_bytes,
            variable_entities + param_entities,
            field_entities,
            struct_id_map
        )
        all_relations.extend(rels)

    # === 输出 JSON ===
    with open(entity_path, 'w') as f:
        json.dump(all_entities, f, indent=2)
    with open(relation_path, 'w') as f:
        json.dump(all_relations, f, indent=2)

    print(f"\n✅ 提取完成：实体 {len(all_entities)} 个，关系 {len(all_relations)} 条。")
    relation_types = Counter([r['type'] for r in all_relations])
    print("\n📊 关系类型统计：")
    for k, v in relation_types.items():
        print(f"  - {k}: {v}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, required=True, help="C 源码目录路径")
    parser.add_argument("--output", type=str, required=True, help="输出目录路径")
    args = parser.parse_args()

    tracemalloc.start()
    start_time = time.time()
    extract_all(args.source, args.output)
    current, peak = tracemalloc.get_traced_memory()
    end_time = time.time()
    print(f"\n⏱️ 总耗时：{end_time - start_time:.2f} 秒")
    print(f"🧠 当前内存：{current / 1024 / 1024:.2f} MB；峰值：{peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()
