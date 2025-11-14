#!/usr/bin/env python3
"""
MMC驱动代码知识图谱提取工具

专门用于提取 Linux drivers/mmc 子系统的代码知识图谱
源码路径: /data/xuao/code_kg/data/linux_data/drivers/mmc
输出路径: output/mmc/
"""

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

# === 包含关系提取模块 ===
from extract_relation_includes import extract_include_relations, build_transitive_includes, extract_extern_declarations

# === MMC 专用配置路径 ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LANG_SO_PATH = os.path.join(ROOT_DIR, '..', 'build', 'my-languages.so')

# MMC 驱动源码路径（固定）
MMC_SOURCE_DIR = "/data/xuao/code_kg/data/linux_data/drivers/mmc"

# MMC 输出路径（固定）
MMC_OUTPUT_DIR = os.path.join(ROOT_DIR, '..', 'output', 'mmc')

# MMC 宏展开信息路径（如果有的话）
MMC_MACRO_JSON_PATH = "/data/xuao/code_kg/data/linux_data/drivers/mmc/macro.json"

def id_generator(start=1):
    """ID生成器"""
    while True:
        yield start
        start += 1

def get_parser():
    """初始化Tree-sitter解析器"""
    language = Language(LANG_SO_PATH, 'c')
    parser = Parser()
    parser.set_language(language)
    return parser

def get_c_files(directory):
    """递归获取目录下所有.c和.h文件"""
    c_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.c', '.h')):
                c_files.append(os.path.join(root, file))
    return c_files

def load_macro_lookup_map(json_path):
    """加载宏展开信息"""
    if not os.path.exists(json_path):
        print(f"⚠️  宏文件未找到: {json_path}")
        print(f"   将跳过宏展开分析，继续提取其他信息...")
        return defaultdict(list)

    with open(json_path, 'r') as f:
        macro_json = json.load(f)
    macro_lookup_map = defaultdict(list)

    macro_dir = os.path.dirname(json_path)

    for entry in macro_json:
        relative_file = entry["file"]

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

    print(f"✅ 读取宏展开信息完成，共包含文件数：{len(macro_lookup_map)}")
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
    """构建文件到实体的映射，用于快速查找"""
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

        # 如果有上下文信息，加入到键中
        if 'context_var_id' in rel:
            rel_key = rel_key + (rel['context_var_id'],)

        if rel_key not in seen:
            seen.add(rel_key)
            unique_relations.append(rel)

    return unique_relations

def extract_mmc_knowledge_graph():
    """提取MMC驱动的代码知识图谱"""

    print("=" * 80)
    print("MMC 驱动代码知识图谱提取工具")
    print("=" * 80)
    print(f"📂 源码路径: {MMC_SOURCE_DIR}")
    print(f"📁 输出路径: {MMC_OUTPUT_DIR}")
    print("=" * 80)

    # 检查源码目录是否存在
    if not os.path.exists(MMC_SOURCE_DIR):
        print(f"❌ 错误：源码目录不存在: {MMC_SOURCE_DIR}")
        print(f"   请确保已正确挂载或下载 Linux 源码")
        return

    # 创建输出目录
    os.makedirs(MMC_OUTPUT_DIR, exist_ok=True)
    entity_path = os.path.join(MMC_OUTPUT_DIR, 'entity.json')
    relation_path = os.path.join(MMC_OUTPUT_DIR, 'relation.json')

    id_counter = id_generator()
    parser = get_parser()

    all_entities = []
    all_relations = []

    # === 映射表：支持多值映射 ===
    function_id_map = {}
    variable_id_map = {}
    param_id_map = {}
    struct_id_map = {}
    field_id_map = {}
    variable_scope_map = {}

    function_entities = []
    param_entities = []
    variable_entities = []
    struct_entities = []
    field_entities = []

    file_trees = []
    file_id_map = {}

    # === 获取所有C文件 ===
    c_files = get_c_files(MMC_SOURCE_DIR)
    print(f"\n📊 找到 {len(c_files)} 个C/H文件")

    if len(c_files) == 0:
        print(f"❌ 错误：未在 {MMC_SOURCE_DIR} 找到任何C/H文件")
        return

    # 显示部分文件路径示例
    print(f"\n示例文件路径：")
    for f in c_files[:5]:
        print(f"  - {f}")
    if len(c_files) > 5:
        print(f"  ... 还有 {len(c_files) - 5} 个文件")

    # === 加载宏信息 ===
    macro_lookup_map = load_macro_lookup_map(MMC_MACRO_JSON_PATH)

    # === 阶段 1：提取所有实体 ===
    print(f"\n" + "="*80)
    print("阶段 1：提取所有实体")
    print("="*80)

    for source_path in tqdm(c_files, desc="提取实体"):
        abs_source_path = os.path.abspath(source_path)

        try:
            with open(abs_source_path, 'rb') as f:
                code_bytes = f.read()
        except Exception as e:
            print(f"\n⚠️  跳过文件 {abs_source_path}: {e}")
            continue

        tree = parser.parse(code_bytes)
        root = tree.root_node
        file_trees.append((abs_source_path, root, code_bytes))

        file_entities, file_id = extract_file_entity(abs_source_path, id_counter)
        file_id_map[abs_source_path] = file_id
        all_entities.extend(file_entities)

        # === 函数提取 ===
        functions, f_map = extract_function_entities(root, code_bytes, id_counter)
        for e in functions:
            e["source_file"] = abs_source_path
        function_entities.extend(functions)

        for func_name, func_id in f_map.items():
            function_id_map.setdefault(func_name, []).append(func_id)

        # === 结构体提取 ===
        structs, s_map = extract_struct_entities(root, code_bytes, id_counter)
        for e in structs:
            e["source_file"] = abs_source_path
        struct_entities.extend(structs)

        for struct_key, struct_id in s_map.items():
            struct_id_map.setdefault(struct_key, []).append(struct_id)

        # === 变量提取 ===
        variables, v_map, scope_map = extract_variable_entities(root, code_bytes, id_counter)
        for e in variables:
            e["source_file"] = abs_source_path
        variable_entities.extend(variables)
        variable_scope_map.update(scope_map)

        for var_key, var_id in v_map.items():
            var_name, var_scope = var_key

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
                variable_id_map[var_key] = var_id

        # === 参数提取 ===
        params, p_map = extract_function_parameters(root, code_bytes, id_counter, f_map)
        for e in params:
            e["source_file"] = abs_source_path
        param_entities.extend(params)
        param_id_map.update(p_map)

        # === 字段提取 ===
        fields, f_map2 = extract_field_entities(root, code_bytes, id_counter, s_map)
        for e in fields:
            e["source_file"] = abs_source_path
        field_entities.extend(fields)
        for name, ids in f_map2.items():
            field_id_map.setdefault(name, []).extend(ids)

    all_entities.extend(function_entities + struct_entities + variable_entities + param_entities + field_entities)

    print(f"\n✅ 实体提取完成：")
    print(f"   - 文件：{len(file_id_map)}")
    print(f"   - 函数：{len(function_entities)}")
    print(f"   - 结构体：{len(struct_entities)}")
    print(f"   - 变量：{len(variable_entities)}")
    print(f"   - 参数：{len(param_entities)}")
    print(f"   - 字段：{len(field_entities)}")

    # === 预计算映射表 ===
    print(f"\n" + "="*80)
    print("预计算映射表...")

    entity_file_map = build_entity_file_mapping(all_entities)
    file_to_entities = build_file_to_entities_mapping(all_entities)
    print(f"✅ 文件-实体映射完成，覆盖 {len(file_to_entities)} 个文件")

    # === 阶段 2：文件可见性映射和include关系 ===
    print(f"\n" + "="*80)
    print("阶段 2：构建文件可见性映射")
    print("="*80)

    all_include_relations = []
    all_extern_functions = set()

    for source_path, root, code_bytes in tqdm(file_trees, desc="构建可见性映射"):
        include_rels, direct_includes = extract_include_relations(root, code_bytes, file_id_map, source_path)
        all_include_relations.extend(include_rels)

        extern_funcs = extract_extern_declarations(root, code_bytes)
        all_extern_functions.update(extern_funcs)

    file_visibility = build_transitive_includes(all_include_relations, file_id_map)

    all_relations.extend(all_include_relations)
    print(f"✅ 提取到 {len(all_include_relations)} 个 INCLUDES 关系")
    print(f"✅ 识别到 {len(all_extern_functions)} 个 extern 函数声明")

    # === 阶段 3：静态关系提取 ===
    print(f"\n" + "="*80)
    print("阶段 3：静态关系（包含/成员）")
    print("="*80)

    for source_path in tqdm(c_files, desc="CONTAINS关系"):
        abs_path = os.path.abspath(source_path)
        file_id = file_id_map.get(abs_path)
        if file_id is None:
            continue

        entities_in_file = file_to_entities.get(abs_path, [])

        contain_list = [
            entity for entity in entities_in_file
            if (entity['type'] in ('FUNCTION', 'STRUCT') or
                (entity['type'] == 'VARIABLE' and entity.get('scope') == 'global'))
        ]

        if contain_list:
            rels = build_file_level_contains(file_id, contain_list)
            all_relations.extend(rels)

    # HAS_MEMBER关系
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
    print(f"\n" + "="*80)
    print("阶段 4：提取 CALLS 关系")
    print("="*80)

    for source_path, root, code_bytes in tqdm(file_trees, desc="提取 CALLS"):
        rels = extract_calls_relations(
            root, code_bytes, function_id_map, {**variable_id_map, **param_id_map}, field_id_map,
            source_path, file_visibility, entity_file_map, all_extern_functions, macro_lookup_map, source_path, all_entities
        )
        all_relations.extend(rels)

    # === 阶段 5：赋值关系 ===
    print(f"\n" + "="*80)
    print("阶段 5：提取 ASSIGNED_TO 关系")
    print("="*80)

    for source_path, root, code_bytes in tqdm(file_trees, desc="提取 ASSIGNED_TO"):
        rels = extract_assigned_to_relations(
            root, code_bytes, function_id_map, {**variable_id_map, **param_id_map}, field_id_map,
            source_path, file_visibility, entity_file_map, all_extern_functions, macro_lookup_map, source_path
        )
        all_relations.extend(rels)

    # === 阶段 6：语义关系 ===
    print(f"\n" + "="*80)
    print("阶段 6：提取 RETURNS / TYPE_OF")
    print("="*80)

    for source_path, root, code_bytes in tqdm(file_trees, desc="提取 RETURNS / TYPE_OF"):
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
    print(f"\n" + "="*80)
    print("去重关系...")
    original_count = len(all_relations)
    all_relations = deduplicate_relations(all_relations)
    deduplicated_count = len(all_relations)
    print(f"✅ 去重完成：{original_count} -> {deduplicated_count} (移除 {original_count - deduplicated_count} 个重复)")

    # === 输出 JSON ===
    print(f"\n" + "="*80)
    print("保存结果...")

    with open(entity_path, 'w', encoding='utf-8') as f:
        json.dump(all_entities, f, indent=2, ensure_ascii=False)
    with open(relation_path, 'w', encoding='utf-8') as f:
        json.dump(all_relations, f, indent=2, ensure_ascii=False)

    print(f"\n" + "="*80)
    print("✅ MMC 驱动知识图谱提取完成！")
    print("="*80)
    print(f"📊 统计信息：")
    print(f"   - 实体总数：{len(all_entities)}")
    print(f"   - 关系总数：{len(all_relations)}")
    print(f"\n📁 输出文件：")
    print(f"   - 实体文件：{entity_path}")
    print(f"   - 关系文件：{relation_path}")

    # 关系类型统计
    relation_types = Counter([r['type'] for r in all_relations])
    print(f"\n📈 关系类型统计：")
    for k, v in sorted(relation_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {k:20s}: {v:6d}")

    # 可见性检查统计
    visibility_checked = sum(1 for r in all_relations if r.get('visibility_checked'))
    print(f"\n🔍 可见性检查覆盖：{visibility_checked}/{len(all_relations)} ({visibility_checked/len(all_relations)*100:.1f}%)")
    print("="*80)

if __name__ == "__main__":
    tracemalloc.start()
    start_time = time.time()

    try:
        extract_mmc_knowledge_graph()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
    except Exception as e:
        print(f"\n\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        current, peak = tracemalloc.get_traced_memory()
        end_time = time.time()
        print(f"\n⏱️  总耗时：{end_time - start_time:.2f} 秒")
        print(f"💾 内存使用：当前 {current / 1024 / 1024:.2f} MB；峰值 {peak / 1024 / 1024:.2f} MB")
        tracemalloc.stop()
