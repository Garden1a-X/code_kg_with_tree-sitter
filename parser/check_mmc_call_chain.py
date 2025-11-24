#!/usr/bin/env python3
"""
MMC 调用链完整性检查工具

检查 MMC 驱动初始化到 tuning 的完整调用链是否被正确提取
调用链：
dw_mci_pltfm_probe -> dw_mci_pltfm_register -> dw_mci_probe -> dw_mci_init_slot
-> mmc_add_host -> mmc_start_host -> _mmc_detect_change
-> mmc_schedule_delayed_work(&host->detect, delay)
host->detect 在 mmc_alloc_host 里挂接为 mmc_rescan
mmc_rescan -> mmc_rescan_try_freq -> mmc_attach_mmc -> mmc_init_card
-> mmc_hs200_tuning -> mmc_execute_tuning
mmc_execute_tuning 执行 host->ops->execute_tuning(host, opcode)
execute_tuning 在 mmc_host_ops 结构体中挂接为 dw_mci_execute_tuning
-> dw_mci_execute_tuning -> dw_mci_hi3660_execute_tuning
"""

import json
import os
from collections import defaultdict

# 输出目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MMC_OUTPUT_DIR = os.path.join(ROOT_DIR, '..', 'output', 'mmc')
ENTITY_PATH = os.path.join(MMC_OUTPUT_DIR, 'entity.json')
RELATION_PATH = os.path.join(MMC_OUTPUT_DIR, 'relation.json')

# 定义调用链
CALL_CHAINS = [
    # 主调用链
    ("dw_mci_pltfm_probe", "dw_mci_pltfm_register"),
    ("dw_mci_pltfm_register", "dw_mci_probe"),
    ("dw_mci_probe", "dw_mci_init_slot"),
    ("dw_mci_init_slot", "mmc_add_host"),
    ("mmc_add_host", "mmc_start_host"),
    ("mmc_start_host", "_mmc_detect_change"),
    ("_mmc_detect_change", "mmc_schedule_delayed_work"),

    # mmc_rescan 链
    ("mmc_rescan", "mmc_rescan_try_freq"),
    ("mmc_rescan_try_freq", "mmc_attach_mmc"),
    ("mmc_attach_mmc", "mmc_init_card"),
    ("mmc_init_card", "mmc_hs200_tuning"),
    ("mmc_hs200_tuning", "mmc_execute_tuning"),

    # execute_tuning 链
    ("mmc_execute_tuning", "dw_mci_execute_tuning"),
    ("dw_mci_execute_tuning", "dw_mci_hi3660_execute_tuning"),
]

# 重要的赋值关系（函数指针挂接）
ASSIGNMENT_CHAINS = [
    # host->detect 挂接为 mmc_rescan (在 mmc_alloc_host 中)
    {
        "description": "host->detect 挂接为 mmc_rescan (在 mmc_alloc_host 中)",
        "field": "detect",
        "target_function": "mmc_rescan",
        "context_function": "mmc_alloc_host"
    },
    # host->ops->execute_tuning 挂接为 dw_mci_execute_tuning (在 mmc_host_ops 结构体中)
    {
        "description": "host->ops->execute_tuning 挂接为 dw_mci_execute_tuning",
        "field": "execute_tuning",
        "target_function": "dw_mci_execute_tuning",
        "struct": "mmc_host_ops"  # 结构体类型，不是变量名
    },
    # drv_data->execute_tuning 挂接为 dw_mci_hi3660_execute_tuning (在某个 dw_mci 特定 ops 中)
    {
        "description": "drv_data->execute_tuning 挂接为 dw_mci_hi3660_execute_tuning",
        "field": "execute_tuning",
        "target_function": "dw_mci_hi3660_execute_tuning",
    },
]

# 所有需要检查的函数
ALL_FUNCTIONS = [
    "dw_mci_pltfm_probe",
    "dw_mci_pltfm_register",
    "dw_mci_probe",
    "dw_mci_init_slot",
    "mmc_add_host",
    "mmc_start_host",
    "_mmc_detect_change",
    "mmc_schedule_delayed_work",
    "mmc_alloc_host",
    "mmc_rescan",
    "mmc_rescan_try_freq",
    "mmc_attach_mmc",
    "mmc_init_card",
    "mmc_hs200_tuning",
    "mmc_execute_tuning",
    "dw_mci_execute_tuning",
    "dw_mci_hi3660_execute_tuning",
]

# 重要的字段和结构体
IMPORTANT_FIELDS = ["detect", "execute_tuning"]
IMPORTANT_STRUCTS = ["mmc_host_ops"]  # dw_mci_ops 是变量不是结构体，应该检查 mmc_host_ops


def load_json(filepath):
    """加载JSON文件"""
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_entity_maps(entities):
    """构建实体映射表"""
    function_map = {}  # name -> [entity1, entity2, ...]
    struct_map = {}
    field_map = {}
    id_to_entity = {}

    for entity in entities:
        id_to_entity[entity['id']] = entity

        if entity['type'] == 'FUNCTION':
            name = entity['name']
            if name not in function_map:
                function_map[name] = []
            function_map[name].append(entity)

        elif entity['type'] == 'STRUCT':
            name = entity['name']
            if name not in struct_map:
                struct_map[name] = []
            struct_map[name].append(entity)

        elif entity['type'] == 'FIELD':
            name = entity['name']
            if name not in field_map:
                field_map[name] = []
            field_map[name].append(entity)

    return function_map, struct_map, field_map, id_to_entity


def build_relation_maps(relations):
    """构建关系映射表"""
    calls_map = defaultdict(list)  # (head_id, tail_id) -> [relation1, relation2, ...]
    assigned_map = defaultdict(list)

    for rel in relations:
        head = rel['head']
        tail = rel['tail']
        rel_type = rel['type']

        if rel_type == 'CALLS':
            calls_map[(head, tail)].append(rel)
        elif rel_type == 'ASSIGNED_TO':
            assigned_map[(head, tail)].append(rel)

    return calls_map, assigned_map


def check_entity_exists(name, entity_map, entity_type="FUNCTION"):
    """检查实体是否存在"""
    if name in entity_map and len(entity_map[name]) > 0:
        entities = entity_map[name]
        print(f"  ✅ {entity_type} '{name}' 存在 (共 {len(entities)} 个定义)")
        for i, entity in enumerate(entities):
            source_file = entity.get('source_file', 'unknown')
            # 只显示相对于 drivers/mmc 的路径
            if 'drivers/mmc' in source_file:
                short_path = source_file.split('drivers/mmc/')[-1]
            else:
                short_path = os.path.basename(source_file)
            print(f"     [{i+1}] ID={entity['id']}, file={short_path}")
        return True, entities
    else:
        print(f"  ❌ {entity_type} '{name}' 不存在")
        return False, []


def check_call_relation(caller_name, callee_name, function_map, calls_map, id_to_entity, assigned_map=None):
    """
    检查函数调用关系是否存在
    支持直接调用和间接调用（通过函数指针）
    """
    caller_entities = function_map.get(caller_name, [])
    callee_entities = function_map.get(callee_name, [])

    if not caller_entities:
        print(f"  ❌ 调用者 '{caller_name}' 不存在")
        return False

    if not callee_entities:
        print(f"  ❌ 被调用者 '{callee_name}' 不存在")
        return False

    # 检查是否存在直接调用关系 (FUNCTION -> FUNCTION)
    found_direct = False
    for caller in caller_entities:
        for callee in callee_entities:
            key = (caller['id'], callee['id'])
            if key in calls_map:
                rels = calls_map[key]
                # 检查是否为直接调用
                for rel in rels:
                    if rel.get('call_type') == 'direct' or rel.get('target_type') == 'FUNCTION':
                        found_direct = True
                        caller_file = caller.get('source_file', '')
                        callee_file = callee.get('source_file', '')

                        if 'drivers/mmc' in caller_file:
                            caller_short = caller_file.split('drivers/mmc/')[-1]
                        else:
                            caller_short = os.path.basename(caller_file)

                        if 'drivers/mmc' in callee_file:
                            callee_short = callee_file.split('drivers/mmc/')[-1]
                        else:
                            callee_short = os.path.basename(callee_file)

                        print(f"  ✅ CALLS 关系存在: {caller_name} -> {callee_name}")
                        print(f"     调用者: {caller_short}")
                        print(f"     被调用: {callee_short}")
                        print(f"     关系数: {len([r for r in rels if r.get('call_type') == 'direct'])}")
                        return True

    # 检查是否存在间接调用关系 (FUNCTION -> FIELD -> FUNCTION)
    if assigned_map:
        found_indirect = False
        for caller in caller_entities:
            # 查找所有从该函数出发的 CALLS 关系
            for (head, tail), rels in calls_map.items():
                if head == caller['id']:
                    for rel in rels:
                        # 检查是否为间接调用
                        if rel.get('call_type') == 'indirect' and rel.get('target_type') == 'FIELD':
                            field_id = tail
                            field_entity = id_to_entity.get(field_id)

                            # 查找该字段的 ASSIGNED_TO 关系
                            for (assign_head, assign_tail), assign_rels in assigned_map.items():
                                if assign_head == field_id:
                                    # 检查 assign_tail 是否是我们要找的 callee
                                    for callee in callee_entities:
                                        if assign_tail == callee['id']:
                                            found_indirect = True
                                            caller_file = caller.get('source_file', '')
                                            callee_file = callee.get('source_file', '')

                                            if 'drivers/mmc' in caller_file:
                                                caller_short = caller_file.split('drivers/mmc/')[-1]
                                            else:
                                                caller_short = os.path.basename(caller_file)

                                            if 'drivers/mmc' in callee_file:
                                                callee_short = callee_file.split('drivers/mmc/')[-1]
                                            else:
                                                callee_short = os.path.basename(callee_file)

                                            field_name = field_entity.get('name', 'unknown') if field_entity else 'unknown'
                                            field_pattern = rel.get('field_pattern', '')

                                            print(f"  ✅ CALLS 关系存在 (间接调用): {caller_name} -> {callee_name}")
                                            print(f"     调用者: {caller_short}")
                                            print(f"     被调用: {callee_short}")
                                            print(f"     调用方式: 函数指针 ({field_pattern})")
                                            print(f"     字段名: {field_name}")
                                            return True

        if found_indirect:
            return True

    print(f"  ❌ CALLS 关系不存在: {caller_name} -> {callee_name}")
    print(f"     调用者实体数: {len(caller_entities)}")
    print(f"     被调用实体数: {callee_entities}")

    return False


def check_assignment_relation(assign_info, function_map, field_map, assigned_map, id_to_entity):
    """检查赋值关系（函数指针挂接）"""
    print(f"\n🔍 检查赋值关系: {assign_info['description']}")

    field_name = assign_info.get('field')
    target_func_name = assign_info.get('target_function')

    # 查找字段实体
    field_entities = field_map.get(field_name, [])
    if not field_entities:
        print(f"  ❌ 字段 '{field_name}' 不存在")
        return False

    print(f"  ✅ 字段 '{field_name}' 存在 (共 {len(field_entities)} 个)")

    # 查找目标函数实体
    target_func_entities = function_map.get(target_func_name, [])
    if not target_func_entities:
        print(f"  ❌ 目标函数 '{target_func_name}' 不存在")
        return False

    print(f"  ✅ 目标函数 '{target_func_name}' 存在 (共 {len(target_func_entities)} 个)")

    # 检查是否存在 ASSIGNED_TO 关系
    found = False
    for field in field_entities:
        for func in target_func_entities:
            key = (field['id'], func['id'])
            if key in assigned_map:
                found = True
                rels = assigned_map[key]
                print(f"  ✅ ASSIGNED_TO 关系存在: {field_name} -> {target_func_name}")
                print(f"     关系数: {len(rels)}")
                for rel in rels[:3]:  # 只显示前3个
                    context_var = rel.get('context_var_id', 'N/A')
                    print(f"     - context_var_id: {context_var}")
                return True

    if not found:
        print(f"  ❌ ASSIGNED_TO 关系不存在: {field_name} -> {target_func_name}")

    return found


def main():
    print("=" * 80)
    print("MMC 调用链完整性检查")
    print("=" * 80)
    print(f"实体文件: {ENTITY_PATH}")
    print(f"关系文件: {RELATION_PATH}")
    print("=" * 80)

    # 加载数据
    print("\n📂 加载数据...")
    entities = load_json(ENTITY_PATH)
    relations = load_json(RELATION_PATH)

    if entities is None or relations is None:
        print("❌ 无法加载数据文件，请先运行 run_extract_mmc.py")
        return

    print(f"✅ 加载完成: {len(entities)} 个实体, {len(relations)} 个关系")

    # 构建映射表
    print("\n🗂️  构建映射表...")
    function_map, struct_map, field_map, id_to_entity = build_entity_maps(entities)
    calls_map, assigned_map = build_relation_maps(relations)

    print(f"✅ 函数: {len(function_map)}")
    print(f"✅ 结构体: {len(struct_map)}")
    print(f"✅ 字段: {len(field_map)}")
    print(f"✅ CALLS 关系: {len(calls_map)}")
    print(f"✅ ASSIGNED_TO 关系: {len(assigned_map)}")

    # === 阶段 1: 检查所有函数实体是否存在 ===
    print("\n" + "=" * 80)
    print("阶段 1: 检查所有函数实体")
    print("=" * 80)

    missing_functions = []
    for func_name in ALL_FUNCTIONS:
        exists, _ = check_entity_exists(func_name, function_map, "FUNCTION")
        if not exists:
            missing_functions.append(func_name)

    if missing_functions:
        print(f"\n⚠️  缺失的函数 ({len(missing_functions)}):")
        for func in missing_functions:
            print(f"  - {func}")
    else:
        print(f"\n✅ 所有 {len(ALL_FUNCTIONS)} 个函数都存在！")

    # === 阶段 2: 检查调用链关系 ===
    print("\n" + "=" * 80)
    print("阶段 2: 检查调用链关系 (CALLS)")
    print("=" * 80)

    missing_calls = []
    for caller, callee in CALL_CHAINS:
        print(f"\n🔗 检查: {caller} -> {callee}")
        exists = check_call_relation(caller, callee, function_map, calls_map, id_to_entity, assigned_map)
        if not exists:
            missing_calls.append((caller, callee))

    if missing_calls:
        print(f"\n⚠️  缺失的 CALLS 关系 ({len(missing_calls)}):")
        for caller, callee in missing_calls:
            print(f"  - {caller} -> {callee}")
    else:
        print(f"\n✅ 所有 {len(CALL_CHAINS)} 个调用关系都存在！")

    # === 阶段 3: 检查赋值关系（函数指针挂接）===
    print("\n" + "=" * 80)
    print("阶段 3: 检查赋值关系 (ASSIGNED_TO)")
    print("=" * 80)

    missing_assignments = []
    for assign_info in ASSIGNMENT_CHAINS:
        exists = check_assignment_relation(assign_info, function_map, field_map, assigned_map, id_to_entity)
        if not exists:
            missing_assignments.append(assign_info['description'])

    if missing_assignments:
        print(f"\n⚠️  缺失的 ASSIGNED_TO 关系 ({len(missing_assignments)}):")
        for desc in missing_assignments:
            print(f"  - {desc}")
    else:
        print(f"\n✅ 所有 {len(ASSIGNMENT_CHAINS)} 个赋值关系都存在！")

    # === 阶段 4: 检查重要的结构体和字段 ===
    print("\n" + "=" * 80)
    print("阶段 4: 检查重要的结构体和字段")
    print("=" * 80)

    for struct_name in IMPORTANT_STRUCTS:
        print(f"\n🏗️  检查结构体: {struct_name}")
        check_entity_exists(struct_name, struct_map, "STRUCT")

    for field_name in IMPORTANT_FIELDS:
        print(f"\n🔧 检查字段: {field_name}")
        check_entity_exists(field_name, field_map, "FIELD")

    # === 最终总结 ===
    print("\n" + "=" * 80)
    print("📊 检查总结")
    print("=" * 80)

    total_checks = len(ALL_FUNCTIONS) + len(CALL_CHAINS) + len(ASSIGNMENT_CHAINS)
    total_missing = len(missing_functions) + len(missing_calls) + len(missing_assignments)

    print(f"\n总检查项: {total_checks}")
    print(f"  - 函数实体: {len(ALL_FUNCTIONS)} (缺失: {len(missing_functions)})")
    print(f"  - 调用关系: {len(CALL_CHAINS)} (缺失: {len(missing_calls)})")
    print(f"  - 赋值关系: {len(ASSIGNMENT_CHAINS)} (缺失: {len(missing_assignments)})")

    if total_missing == 0:
        print(f"\n🎉 完美！所有检查项都通过！")
    else:
        print(f"\n⚠️  发现 {total_missing} 个问题需要解决")

    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
