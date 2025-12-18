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
from extract_typedef_map import extract_typedef_map

# === 关系提取模块 ===
from extract_relation_calls import extract_calls_relations
from extract_relation_assignedto import extract_assigned_to_relations
from extract_relation_contains import build_file_level_contains
from extract_relation_has_members import extract_has_member_relations
from extract_relation_has_parameters import extract_has_parameter_relations
from extract_relation_has_variables import extract_has_variable_relations
from extract_relation_returns import extract_returns_relations
from extract_relation_typeof import extract_typeof_relations

# === 包含关系提取模块 ===
from extract_relation_includes import extract_include_relations, build_transitive_includes, extract_extern_declarations

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
    if not os.path.exists(json_path):
        print(f"Warning: Macro file not found: {json_path}")
        return defaultdict(list)
        
    with open(json_path, 'r') as f:
        macro_json = json.load(f)
    macro_lookup_map = defaultdict(list)
    
    # 🔧 修复：获取 macro.json 的目录作为基础路径
    macro_dir = os.path.dirname(json_path)
    
    for entry in macro_json:
        relative_file = entry["file"]  # "./test_1.c"
        
        # 🔧 修复：基于 macro.json 的目录解析相对路径
        if relative_file.startswith("./"):
            file = os.path.abspath(os.path.join(macro_dir, relative_file[2:]))
        else:
            file = os.path.abspath(os.path.join(macro_dir, relative_file))
            
        start_line, start_col, end_line, end_col = entry["location"]
        macro_lookup_map[file].append({
            "range": ((start_line, start_col), (end_line, end_col)),
            "expanded": entry["macro"],
            "original": entry["name"]
        })
    return macro_lookup_map

def build_entity_file_mapping(all_entities):
    """构建实体ID到文件路径的映射"""
    entity_file_map = {}
    
    for entity in all_entities:
        if entity.get('source_file'):
            abs_path = os.path.abspath(entity['source_file'])
            entity_file_map[entity['id']] = abs_path
        elif entity.get('type') == 'FILE':
            if entity.get('source_file'):
                abs_path = os.path.abspath(entity['source_file'])
            else:
                abs_path = os.path.abspath(entity['name'])
            entity_file_map[entity['id']] = abs_path
    
    return entity_file_map

def build_file_to_entities_mapping(all_entities):
    """🚀 新增：构建文件到实体的映射，用于快速查找"""
    file_to_entities = defaultdict(list)
    
    for entity in all_entities:
        if entity.get('source_file'):
            abs_path = os.path.abspath(entity['source_file'])
            file_to_entities[abs_path].append(entity)
    
    return file_to_entities

def deduplicate_relations(relations):
    """去重关系列表 - 考虑上下文信息"""
    seen = set()
    unique_relations = []
    
    for rel in relations:
        # 基础关系键
        rel_key = (rel['head'], rel['tail'], rel['type'])
        
        # 🆕 如果有上下文信息，加入到键中
        if 'context_var_id' in rel:
            rel_key = rel_key + (rel['context_var_id'],)
        
        if rel_key not in seen:
            seen.add(rel_key)
            unique_relations.append(rel)
    
    return unique_relations

def extract_all(source_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    entity_path = os.path.join(output_dir, 'entity.json')
    relation_path = os.path.join(output_dir, 'relation.json')

    id_counter = id_generator()
    parser = get_parser()

    all_entities = []
    all_relations = []

    # === 映射表：支持多值映射 ===
    function_id_map = {}      # name -> [id1, id2, ...] 支持同名函数
    variable_id_map = {}      # (name, scope) -> id 或 [id1, id2, ...] 支持同名全局变量
    param_id_map = {}         # (name, scope) -> id
    struct_id_map = {}        # (name, scope) -> [id1, id2, ...] 支持同名结构体
    field_id_map = {}         # name -> [id1, id2, ...]
    variable_scope_map = {}
    struct_fields_ordered = {} # struct_name -> [(field_id, field_name), ...] 字段顺序
    typedef_map = {}          # alias_name -> original_struct_name typedef 映射

    function_entities = []
    param_entities = []
    variable_entities = []
    struct_entities = []
    field_entities = []

    file_trees = []
    file_id_map = {}

    # === 源码与宏信息读取 ===
    c_files = list(get_c_files(source_dir))
    macro_lookup_map = load_macro_lookup_map(MACRO_JSON_PATH)
    print(f"✅ 读取宏展开信息完成，共包含文件数：{len(macro_lookup_map)}")

    # === 阶段 1：提取所有实体 ===
    print(f"\n" + "="*60)
    print("阶段 1：提取所有实体")
    
    for source_path in tqdm(c_files, desc="阶段 1：提取实体"):
        abs_source_path = os.path.abspath(source_path)
        
        with open(abs_source_path, 'rb') as f:
            code_bytes = f.read()
        tree = parser.parse(code_bytes)
        root = tree.root_node
        file_trees.append((abs_source_path, root, code_bytes))

        file_entities, file_id = extract_file_entity(abs_source_path, id_counter)
        file_id_map[abs_source_path] = file_id
        all_entities.extend(file_entities)

        # === 函数映射：支持同名函数 ===
        functions, f_map = extract_function_entities(root, code_bytes, id_counter)
        for e in functions: 
            e["source_file"] = abs_source_path
        function_entities.extend(functions)
        
        for func_name, func_id in f_map.items():
            function_id_map.setdefault(func_name, []).append(func_id)

        # === 结构体映射：支持同名结构体 ===
        structs, s_map = extract_struct_entities(root, code_bytes, id_counter)
        for e in structs: 
            e["source_file"] = abs_source_path
        struct_entities.extend(structs)
        
        for struct_key, struct_id in s_map.items():
            struct_id_map.setdefault(struct_key, []).append(struct_id)

        # === 变量映射：支持同名全局变量 ===
        variables, v_map, scope_map = extract_variable_entities(root, code_bytes, id_counter)
        for e in variables: 
            e["source_file"] = abs_source_path
        variable_entities.extend(variables)
        variable_scope_map.update(scope_map)

        # 关键修复：变量映射支持多值
        for var_key, var_id in v_map.items():
            var_name, var_scope = var_key
            
            # 全局变量支持多值映射（可能同名）
            if var_scope == 'global':
                if var_key in variable_id_map:
                    existing = variable_id_map[var_key]
                    if isinstance(existing, list):
                        existing.append(var_id)
                    else:
                        variable_id_map[var_key] = [existing, var_id]
                else:
                    variable_id_map[var_key] = var_id
            else:
                # 局部变量通常不会冲突，保持单值映射
                variable_id_map[var_key] = var_id

        # === 参数映射 ===
        params, p_map = extract_function_parameters(root, code_bytes, id_counter, f_map)
        for e in params: 
            e["source_file"] = abs_source_path
        param_entities.extend(params)
        param_id_map.update(p_map)

        # === 字段映射 ===
        fields, f_map2, struct_fields_ordered_temp = extract_field_entities(root, code_bytes, id_counter, s_map)
        for e in fields:
            e["source_file"] = abs_source_path
        field_entities.extend(fields)
        for name, ids in f_map2.items():
            field_id_map.setdefault(name, []).extend(ids)

        # === Typedef 映射 ===
        typedef_map_temp = extract_typedef_map(root, code_bytes)
        typedef_map.update(typedef_map_temp)

        # === 合并字段顺序映射 ===
        for struct_name, fields_list in struct_fields_ordered_temp.items():
            if struct_name not in struct_fields_ordered:
                struct_fields_ordered[struct_name] = []
            struct_fields_ordered[struct_name].extend(fields_list)

    all_entities.extend(function_entities + struct_entities + variable_entities + param_entities + field_entities)

    # === 🚀 优化：预计算映射表，提前完成静态关系准备 ===
    print(f"\n" + "="*60)
    print("预计算映射表...")
    
    # 构建实体文件映射
    entity_file_map = build_entity_file_mapping(all_entities)
    
    # 🚀 关键优化：构建文件到实体的反向映射
    file_to_entities = build_file_to_entities_mapping(all_entities)
    print(f"✅ 文件-实体映射完成，覆盖 {len(file_to_entities)} 个文件")

    # === 阶段 2：文件可见性映射和include关系 ===
    print(f"\n" + "="*60)
    print("阶段 2：构建文件可见性映射...")
    
    # 提取所有include关系和extern声明
    all_include_relations = []
    all_extern_functions = set()

    # 使用优化后的BFS算法进行可见性计算
    for source_path, root, code_bytes in tqdm(file_trees, desc="构建可见性映射"):
        include_rels, direct_includes = extract_include_relations(root, code_bytes, file_id_map, source_path)
        all_include_relations.extend(include_rels)
        
        extern_funcs = extract_extern_declarations(root, code_bytes)
        all_extern_functions.update(extern_funcs)

    # 构建传递包含关系（文件可见性映射）
    file_visibility = build_transitive_includes(all_include_relations, file_id_map)

    all_relations.extend(all_include_relations)
    print(f"✅ 提取到 {len(all_include_relations)} 个 INCLUDES 关系")
    print(f"✅ 识别到 {len(all_extern_functions)} 个 extern 函数声明")

    # === 阶段 3：优化后的静态关系提取 ===
    print(f"\n" + "="*60)
    print("阶段 3：静态关系（包含/成员）...")

    # 🚀 优化：使用预计算的映射直接生成CONTAINS关系
    for source_path in tqdm(c_files, desc="阶段 3：CONTAINS关系"):
        abs_path = os.path.abspath(source_path)
        file_id = file_id_map.get(abs_path)
        if file_id is None:
            continue
        
        # 🚀 优化：O(1)查找替代O(N)遍历
        entities_in_file = file_to_entities.get(abs_path, [])
        
        # 过滤需要的实体类型
        contain_list = [
            entity for entity in entities_in_file
            if (entity['type'] in ('FUNCTION', 'STRUCT') or 
                (entity['type'] == 'VARIABLE' and entity.get('scope') == 'global'))
        ]
        
        if contain_list:  # 只有在有实体时才创建关系
            rels = build_file_level_contains(file_id, contain_list)
            all_relations.extend(rels)

    # HAS_MEMBER关系提取
    print(f"\n提取 HAS_MEMBER 关系...")
    rels = extract_has_member_relations(field_entities, struct_id_map)
    all_relations.extend(rels)

    # HAS_PARAMETER  
    rels = extract_has_parameter_relations(param_entities, function_id_map)
    all_relations.extend(rels)

    # HAS_VARIABLE
    rels = extract_has_variable_relations(variable_entities, function_id_map)
    all_relations.extend(rels)

    # === 阶段 4：函数调用关系 ===
    print(f"\n" + "="*60)
    print("阶段 4：提取 CALLS 关系...")

    for source_path, root, code_bytes in tqdm(file_trees, desc="阶段 4：提取 CALLS"):
        rels = extract_calls_relations(
            root, code_bytes, function_id_map, {**variable_id_map, **param_id_map}, field_id_map,
            source_path, file_visibility, entity_file_map, all_extern_functions, macro_lookup_map, source_path, all_entities
        )
        all_relations.extend(rels)

    # === 阶段 5：赋值关系 ===
    print(f"\n" + "="*60)
    print("阶段 5：提取 ASSIGNED_TO 关系...")
    
    for source_path, root, code_bytes in tqdm(file_trees, desc="阶段 5：提取 ASSIGNED_TO"):
        rels = extract_assigned_to_relations(
            root, code_bytes, function_id_map, {**variable_id_map, **param_id_map}, field_id_map,
            source_path, file_visibility, entity_file_map, all_extern_functions, macro_lookup_map, source_path,
            struct_fields_ordered, typedef_map
        )
        all_relations.extend(rels)

    # === 阶段 6：语义关系 ===
    print(f"\n" + "="*60)
    print("阶段 6：提取 RETURNS / TYPE_OF...")
    
    for source_path, root, code_bytes in tqdm(file_trees, desc="阶段 6：提取 RETURNS / TYPE_OF"):
        # RETURNS
        rels = extract_returns_relations(
            root, code_bytes, function_id_map, {**variable_id_map, **param_id_map}, field_id_map,
            source_path, file_visibility, entity_file_map
        )
        all_relations.extend(rels)

        # TYPE_OF
        rels = extract_typeof_relations(
            root, code_bytes, variable_entities + param_entities, field_entities, struct_id_map,
            source_path, file_visibility, entity_file_map
        )
        all_relations.extend(rels)

    # 清理内存
    del file_trees
    del file_to_entities

    # === 最终去重和统计 ===
    print(f"\n" + "="*60)
    print("去重关系...")
    original_count = len(all_relations)
    all_relations = deduplicate_relations(all_relations)
    deduplicated_count = len(all_relations)
    print(f"✅ 去重完成：{original_count} -> {deduplicated_count} (移除 {original_count - deduplicated_count} 个重复)")

    # === 输出 JSON ===
    with open(entity_path, 'w') as f:
        json.dump(all_entities, f, indent=2)
    with open(relation_path, 'w') as f:
        json.dump(all_relations, f, indent=2)

    print(f"\n✅ 提取完成：实体 {len(all_entities)} 个，关系 {len(all_relations)} 条。")
    
    # 关系统计
    relation_types = Counter([r['type'] for r in all_relations])
    print(f"\n关系类型统计：")
    for k, v in relation_types.items():
        print(f"  - {k}: {v}")
    
    # 可见性检查统计
    visibility_checked = sum(1 for r in all_relations if r.get('visibility_checked'))
    print(f"\n可见性检查覆盖：{visibility_checked}/{len(all_relations)} ({visibility_checked/len(all_relations)*100:.1f}%)")

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
    print(f"\n总耗时：{end_time - start_time:.2f} 秒")
    print(f"当前内存：{current / 1024 / 1024:.2f} MB；峰值：{peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()
