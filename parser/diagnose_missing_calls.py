#!/usr/bin/env python3
"""
诊断缺失的 CALLS 关系

专门用于诊断为什么某些调用关系没有被提取到
重点关注：dw_mci_init_slot -> mmc_add_host
"""

import json
import os
from collections import defaultdict

# 输出目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MMC_OUTPUT_DIR = os.path.join(ROOT_DIR, '..', 'output', 'mmc')
ENTITY_PATH = os.path.join(MMC_OUTPUT_DIR, 'entity.json')
RELATION_PATH = os.path.join(MMC_OUTPUT_DIR, 'relation.json')


def load_json(filepath):
    """加载JSON文件"""
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_short_path(filepath):
    """获取相对于 drivers/mmc 的短路径"""
    if 'drivers/mmc' in filepath:
        return filepath.split('drivers/mmc/')[-1]
    return os.path.basename(filepath)


def build_file_visibility_map(relations, id_to_file):
    """构建文件可见性映射"""
    file_visibility = defaultdict(set)

    # 从 INCLUDES 关系构建
    for rel in relations:
        if rel['type'] == 'INCLUDES':
            includer_file = id_to_file.get(rel['head'])
            included_file = id_to_file.get(rel['tail'])
            if includer_file and included_file:
                file_visibility[includer_file].add(included_file)

    # 添加传递闭包
    # 简化版：只做一层传递（完整版需要多轮迭代）
    for file, visible_files in list(file_visibility.items()):
        for visible_file in list(visible_files):
            if visible_file in file_visibility:
                file_visibility[file].update(file_visibility[visible_file])

    return file_visibility


def main():
    print("=" * 80)
    print("诊断缺失的 CALLS 关系")
    print("=" * 80)
    print("目标：dw_mci_init_slot -> mmc_add_host")
    print("=" * 80)

    # 加载数据
    print("\n📂 加载数据...")
    entities = load_json(ENTITY_PATH)
    relations = load_json(RELATION_PATH)

    if entities is None or relations is None:
        return

    print(f"✅ 加载完成: {len(entities)} 个实体, {len(relations)} 个关系")

    # 构建映射
    print("\n🗂️  构建映射表...")

    id_to_entity = {e['id']: e for e in entities}
    id_to_file = {}
    function_name_to_entities = defaultdict(list)

    for entity in entities:
        if entity['type'] == 'FILE':
            # FILE 实体的 source_file 就是自己
            filepath = entity.get('source_file') or entity.get('name')
            id_to_file[entity['id']] = os.path.abspath(filepath)
        elif entity.get('source_file'):
            id_to_file[entity['id']] = os.path.abspath(entity['source_file'])

        if entity['type'] == 'FUNCTION':
            function_name_to_entities[entity['name']].append(entity)

    # 找到目标函数
    caller_name = 'dw_mci_init_slot'
    callee_name = 'mmc_add_host'

    caller_entities = function_name_to_entities.get(caller_name, [])
    callee_entities = function_name_to_entities.get(callee_name, [])

    if not caller_entities:
        print(f"\n❌ 找不到调用者函数: {caller_name}")
        return

    if not callee_entities:
        print(f"\n❌ 找不到被调用函数: {callee_name}")
        return

    caller = caller_entities[0]
    callee = callee_entities[0]

    caller_file = caller.get('source_file')
    callee_file = callee.get('source_file')

    print(f"\n✅ 找到调用者: {caller_name}")
    print(f"   ID: {caller['id']}")
    print(f"   文件: {get_short_path(caller_file)}")

    print(f"\n✅ 找到被调用者: {callee_name}")
    print(f"   ID: {callee['id']}")
    print(f"   文件: {get_short_path(callee_file)}")

    # === 检查1: 是否存在 CALLS 关系 ===
    print("\n" + "=" * 80)
    print("检查 1: 是否存在 CALLS 关系？")
    print("=" * 80)

    calls_found = False
    for rel in relations:
        if rel['type'] == 'CALLS' and rel['head'] == caller['id'] and rel['tail'] == callee['id']:
            calls_found = True
            print(f"✅ 找到 CALLS 关系!")
            print(f"   {json.dumps(rel, indent=2)}")
            break

    if not calls_found:
        print(f"❌ 未找到 CALLS 关系: {caller['id']} -> {callee['id']}")

    # === 检查2: INCLUDES 关系 ===
    print("\n" + "=" * 80)
    print("检查 2: caller 文件的 INCLUDES 关系")
    print("=" * 80)

    # 找到 caller 文件的 FILE 实体
    caller_file_entities = [e for e in entities if e['type'] == 'FILE' and
                           os.path.abspath(e.get('source_file', e.get('name', ''))) == os.path.abspath(caller_file)]

    if caller_file_entities:
        caller_file_entity = caller_file_entities[0]
        print(f"✅ Caller 文件实体 ID: {caller_file_entity['id']}")

        # 找出所有从这个文件发出的 INCLUDES 关系
        includes = [rel for rel in relations if rel['type'] == 'INCLUDES' and rel['head'] == caller_file_entity['id']]

        print(f"\n📄 {get_short_path(caller_file)} 的 INCLUDES 关系 (共 {len(includes)} 个):")
        for inc in includes[:20]:  # 只显示前20个
            included_file_id = inc['tail']
            included_file = id_to_file.get(included_file_id, 'unknown')
            print(f"   → {get_short_path(included_file)}")

        if len(includes) > 20:
            print(f"   ... 还有 {len(includes) - 20} 个")

        # 检查是否包含 callee 的文件
        includes_callee_file = any(
            os.path.abspath(id_to_file.get(inc['tail'], '')) == os.path.abspath(callee_file)
            for inc in includes
        )

        if includes_callee_file:
            print(f"\n✅ 直接 include 了 callee 文件: {get_short_path(callee_file)}")
        else:
            print(f"\n❌ 未直接 include callee 文件: {get_short_path(callee_file)}")
    else:
        print(f"❌ 找不到 caller 文件实体")

    # === 检查3: 文件可见性映射 ===
    print("\n" + "=" * 80)
    print("检查 3: 文件可见性映射")
    print("=" * 80)

    file_visibility = build_file_visibility_map(relations, id_to_file)

    caller_file_abs = os.path.abspath(caller_file)
    callee_file_abs = os.path.abspath(callee_file)

    visible_files = file_visibility.get(caller_file_abs, set())

    print(f"\n📋 {get_short_path(caller_file)} 可见的文件 (共 {len(visible_files)} 个):")
    for vf in sorted(visible_files)[:20]:
        print(f"   - {get_short_path(vf)}")

    if len(visible_files) > 20:
        print(f"   ... 还有 {len(visible_files) - 20} 个")

    if callee_file_abs in visible_files:
        print(f"\n✅ callee 文件在可见列表中: {get_short_path(callee_file)}")
    else:
        print(f"\n❌ callee 文件不在可见列表中: {get_short_path(callee_file)}")

    # === 检查4: extern 函数列表 ===
    print("\n" + "=" * 80)
    print("检查 4: extern 函数声明")
    print("=" * 80)

    # 从关系中找出所有 extern 函数的蛛丝马迹
    # 注意：我们没有直接保存 extern 列表，但可以从提取逻辑推断

    # 检查 callee 是否是 static 函数
    is_static = 'static' in callee.get('name', '') or callee.get('scope') == 'static'

    print(f"\n函数 {callee_name} 的属性:")
    print(f"   - ID: {callee['id']}")
    print(f"   - 文件: {get_short_path(callee_file)}")
    print(f"   - 是否 static: {is_static}")

    # 在 caller 文件中查找是否有对 callee 的声明
    print(f"\n🔍 在 {get_short_path(caller_file)} 中查找对 {callee_name} 的引用...")

    # 统计从 caller 文件发出的所有 CALLS 关系
    calls_from_caller_file = [
        rel for rel in relations
        if rel['type'] == 'CALLS' and
        id_to_file.get(rel['head']) == caller_file_abs
    ]

    print(f"\n📊 从 {get_short_path(caller_file)} 发出的 CALLS 关系: {len(calls_from_caller_file)} 个")

    # 统计跨文件调用
    cross_file_calls = [
        rel for rel in calls_from_caller_file
        if id_to_file.get(rel['tail']) != caller_file_abs
    ]

    print(f"   - 跨文件调用: {len(cross_file_calls)} 个")
    print(f"   - 文件内调用: {len(calls_from_caller_file) - len(cross_file_calls)} 个")

    # 显示部分跨文件调用示例
    if cross_file_calls:
        print(f"\n   跨文件调用示例 (前10个):")
        for rel in cross_file_calls[:10]:
            callee_func = id_to_entity.get(rel['tail'])
            if callee_func:
                target_file = id_to_file.get(rel['tail'], 'unknown')
                print(f"      → {callee_func['name']} (在 {get_short_path(target_file)})")

    # === 检查5: 查看 caller 函数内的所有 CALLS ===
    print("\n" + "=" * 80)
    print("检查 5: caller 函数内的所有 CALLS 关系")
    print("=" * 80)

    calls_from_caller = [rel for rel in relations if rel['type'] == 'CALLS' and rel['head'] == caller['id']]

    print(f"\n📞 从 {caller_name} 发出的 CALLS 关系 (共 {len(calls_from_caller)} 个):")
    for rel in calls_from_caller:
        target = id_to_entity.get(rel['tail'])
        if target:
            target_file = id_to_file.get(rel['tail'], 'unknown')
            visibility_checked = rel.get('visibility_checked', False)
            print(f"   → {target['name']:<30} (文件: {get_short_path(target_file):<40} 可见性检查: {visibility_checked})")

    # === 总结 ===
    print("\n" + "=" * 80)
    print("诊断总结")
    print("=" * 80)

    print(f"\n目标调用: {caller_name} -> {callee_name}")
    print(f"调用者文件: {get_short_path(caller_file)}")
    print(f"被调用者文件: {get_short_path(callee_file)}")
    print()
    print(f"✓/✗ 检查项:")
    print(f"  {'✅' if not calls_found else '✅'} CALLS 关系存在: {calls_found}")
    print(f"  {'✅' if caller_file_entities else '❌'} Caller 文件实体存在")
    if caller_file_entities:
        includes_callee = any(
            os.path.abspath(id_to_file.get(inc['tail'], '')) == os.path.abspath(callee_file)
            for inc in [rel for rel in relations if rel['type'] == 'INCLUDES' and rel['head'] == caller_file_entities[0]['id']]
        )
        print(f"  {'✅' if includes_callee else '❌'} 直接 INCLUDES callee 文件")
        print(f"  {'✅' if callee_file_abs in visible_files else '❌'} Callee 文件在可见性列表中")

    print("\n💡 可能的原因:")
    if not calls_found:
        if caller_file_entities and callee_file_abs not in visible_files:
            print("  ⚠️  callee 文件不在 caller 的可见性列表中")
            print("     → 可能是 include 路径解析问题")
            print("     → 或者可见性检查过于严格")
        else:
            print("  ⚠️  其他未知原因，需要进一步调试提取代码")

    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
