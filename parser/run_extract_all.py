import os
import json
import time
import tracemalloc
from collections import defaultdict, Counter
from tqdm import tqdm
from tree_sitter import Language, Parser
import tree_sitter_c as tsc
import numpy as np
from copy import deepcopy
import re
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
from test_glibc_fun import run
from check_git import check_and_init_repo, get_changed_files
# === 配置路径 ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LANG_SO_PATH = os.path.join(ROOT_DIR, '..', 'build', 'my-languages.so')
OUTPUT_BASE = os.path.join(ROOT_DIR, '..', 'output')
MACRO_JSON_PATH = "/home/lyk/work/code_kg_with_tree-sitter/data/glibc_data/macro_list.json"

def prepro_key(file_map):
    new_map = {}
    for key in file_map.keys():
        new_path = re.sub(r"^E:\\cpppro\\clang_kg\\", "/home/lyk/work/", key)
        new_path = new_path.replace("\\", "/")
        new_map[new_path] = file_map[key]
        
    return new_map

def save_temp(all_relations, flag):
    with open(f'E:\\cpppro\\clang_kg\\code_kg_with_tree-sitter\\output\\glibc\\temp_{flag}.json', 'w', encoding='utf-8') as f:
            json.dump(all_relations, f, indent=2, ensure_ascii=False)

def id_generator(start=1):
    while True:
        yield start
        start += 1

def get_parser():
    language = Language(tsc.language())
    parser = Parser(language)
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

    # run(MACRO_JSON_PATH)
    id_counter = id_generator()
    parser = get_parser()

    all_entities = []
    all_relations = []

    file2entity = {}
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
    flag = 0


    if not check_and_init_repo(source_dir):
        # === 阶段 1：提取所有实体 ===
        # run(source_dir, MACRO_JSON_PATH)
        # === 源码与宏信息读取 ===
        c_files = list(get_c_files(source_dir))
        macro_lookup_map = load_macro_lookup_map(MACRO_JSON_PATH)
        print("✅ 读取宏展开信息完成，共包含文件数：", len(macro_lookup_map))
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
            file2entity[source_path] = functions + structs + variables + params + fields
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
        del file_trees
        """
        with open('E:\\cpppro\\clang_kg\\code_kg_with_tree-sitter\\output\\glibc\\temp.json', 'w', encoding='utf-8') as f:
            json.dump(all_relations, f, indent=2, ensure_ascii=False)
        all_relations.clear()

        with open('E:\\cpppro\\clang_kg\\code_kg_with_tree-sitter\\output\\glibc\\temp.json', 'r', encoding='utf-8') as f:
            all_relations = json.load(f)
        """
        # === 阶段 4：静态关系（包含/成员） ===
        for source_path in tqdm(c_files, desc="🔗 阶段 4：静态关系（包含/成员）"):
            if len(all_relations) >= 50000000:
                save_temp(all_relations, flag)
                all_relations.clear()
                flag += 1

            file_id = file_id_map.get(source_path)
            contain_list = file2entity.get(source_path)
            if file_id is None or contain_list is None:
                continue
            rels = build_file_level_contains(file_id, contain_list)
            all_relations.extend(rels)

        # HAS_MEMBER
        rels = extract_has_member_relations(field_entities, struct_id_map)
        all_relations.extend(rels)

        # HAS_PARAMETER
        rels = extract_has_parameter_relations(param_entities, function_id_map)
        all_relations.extend(rels)

        # HAS_VARIABLE
        rels = extract_has_variable_relations(variable_entities, function_id_map)
        all_relations.extend(rels)

        # === 阶段 6：基于函数的内部语义关系 ===
        for source_path in tqdm(c_files, desc="🔗 阶段 6:提取 RETURNS / TYPE_OF"):
            with open(source_path, 'rb') as f:
                code_bytes = f.read()
            tree = parser.parse(code_bytes)
            root = tree.root_node
            print(source_path)
            if len(all_relations) >= 50000000:
                save_temp(all_relations, flag)
                all_relations.clear()
                flag += 1

            # RETURNS
            rels = extract_returns_relations(
                root,
                code_bytes,
                function_id_map,
                {**variable_id_map, **param_id_map},
                field_id_map
            )
            all_relations.extend(rels)
            print(f"len of rela: {len(all_relations)}")
            if len(all_relations) >= 50000000:
                save_temp(all_relations, flag)
                all_relations.clear()
                flag += 1

            # TYPE_OF
            rels = extract_typeof_relations(
                root,
                code_bytes,
                variable_entities + param_entities,
                field_entities,
                struct_id_map
            )
            all_relations.extend(rels)
            del tree, root, code_bytes
            import gc

            gc.collect()
            print(f"len of rela: {len(all_relations)}")

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
        import pickle
        data_to_save = {
            'function_id_map': function_id_map,
            'variable_id_map': variable_id_map,
            'param_id_map': param_id_map,
            'struct_id_map': struct_id_map,
            'field_id_map': field_id_map,
            'variable_scope_map': variable_scope_map,
            'file_id_map': file_id_map
        }
        pickle.dump(data_to_save, open(output_dir + '/name2id.pkl', 'wb'))
    else:
        changed_files = get_changed_files(source_dir)

        if changed_files:
            start_time = time.time()
            changed_files = [os.path.join(source_dir, value) for value in changed_files]
            with open(entity_path, 'r') as f:
                all_entities = json.load(f)
            import pickle
            id2entity = pickle.load(open(output_dir + '/name2id.pkl', 'rb'))
            function_id_map = id2entity['function_id_map']
            variable_id_map = id2entity['variable_id_map']
            param_id_map = id2entity['param_id_map']
            struct_id_map = id2entity['struct_id_map']
            field_id_map = id2entity['field_id_map']
            variable_scope_map = id2entity['variable_scope_map']
            file_id_map = id2entity['file_id_map']
            file_id_map = prepro_key(file_id_map)
            full_contain = {}
            id2end = {}
            for entity in all_entities:
                id2end[entity['id']] = entity
                if entity['type'] == 'FILE':
                    full_contain[entity['name']] = {
                        'FIELD': [],
                        'FUNCTION': [],
                        'STRUCT': [],
                        'VARIABLE': [],
                        'ALL': [entity['id']]
                    }
                else:
                    entype = entity['type']
                    sofile = entity['source_file']
                    file_id = file_id_map.get(sofile)
                    if sofile not in full_contain.keys():
                        full_contain[sofile] = {
                            'FIELD': [],
                            'FUNCTION': [],
                            'STRUCT': [],
                            'VARIABLE': [],
                            'ALL': [file_id]
                        }
                    full_contain[sofile][entype].append(entity['id'])
                    full_contain[sofile]['ALL'].append(entity['id'])
            with open(relation_path, 'r') as f:
                all_relations = json.load(f)

            id_start = int(all_entities[-1]['id']) + 1
            id_counter = id_generator(start=id_start)


            str2map = {
                'function_id_map': function_id_map,
                'variable_id_map': variable_id_map,
                'param_id_map': param_id_map,
                'struct_id_map': struct_id_map,
                'field_id_map': field_id_map,
                'variable_scope_map': variable_scope_map,
                'file_id_map': file_id_map
            }
            
            old_call = {}
            old_called = {}
            old_assign = {}
            old_assigned = {}
            copy_relation = deepcopy(all_relations)
            for rela in copy_relation:
                if rela['type'] == 'CALLS':
                    for key in changed_files:
                        if full_contain.get(key) and rela['head'] in full_contain[key]['ALL']:
                            if key not in old_call.keys():
                                old_call[key] = [rela]
                            else:
                                old_call[key].append(rela)
                        elif full_contain.get(key) and rela['head'] not in full_contain[key]['ALL'] and rela['tail'] in full_contain[key]['ALL']:
                            if key not in old_called.keys():
                                old_called[key] = [rela]
                            else:
                                old_called[key].append(rela)
                elif rela['type'] == 'ASSIGNED_TO':
                    for key in changed_files:
                        if full_contain.get(key) and rela['head'] in full_contain[key]['ALL']:
                            if key not in old_assign.keys():
                                old_assign[key] = [rela]
                            else:
                                old_assign[key].append(rela)
                        elif full_contain.get(key) and rela['head'] not in full_contain[key]['ALL'] and rela['tail'] in full_contain[key]['ALL']:
                            if key not in old_assigned.keys():
                                old_assigned[key] = [rela]
                            else:
                                old_assigned[key].append(rela)
                elif rela['type'] == 'CONTAINS':
                    if id2end[rela['head']]['name'] in changed_files:
                        all_relations.remove(rela)
                else:
                    if id2end[rela['head']]['source_file'] in changed_files:
                        all_relations.remove(rela)
            # === 阶段 1：提取所有实体 ===
            run(changed_files, MACRO_JSON_PATH)
            # === 源码与宏信息读取 ===
            macro_lookup_map = load_macro_lookup_map(MACRO_JSON_PATH)
            print("✅ 读取宏展开信息完成，共包含文件数：", len(macro_lookup_map))
            for source_path in tqdm(changed_files, desc="🔍 阶段 1：提取实体"):
                # 文件删除
                if not os.path.exists(source_path):
                    delete_en = full_contain[source_path]['ALL']
                    for en_id in delete_en:
                        en = id2end[en_id]
                        if en['type'] in ['FUNCTION', 'STRUCT']:
                            mapkey = en['type'].lower() + '_id_map'
                            en_name = id2end[en_id]['name']
                            del str2map[mapkey][en_name]
                            if en_name in variable_scope_map.keys():
                                del variable_scope_map[en_name]
                        elif en['type'] == 'VARIABLE':
                            mapkey = en['type'].lower() + '_id_map'
                            en_name = id2end[en_id]['name']
                            en_scope = id2end[en_id]['scope']
                            if variable_scope_map.get(en_scope) and en_id in variable_scope_map.get(en_scope):
                                variable_scope_map[en_scope].remove(en_id)
                            if str2map[mapkey].get((en_name, en_scope)):
                                del str2map[mapkey][(en_name, en_scope)]
                        elif en['type'] == 'FIELD':
                            mapkey = en['type'].lower() + '_id_map'
                            en_name = id2end[en_id]['name']
                            if str2map[mapkey].get(en_name):
                                str2map[mapkey][en_name].remove(en_id)
                        
                        del id2end[en_id]
                    del file_id_map[source_path]
                    copy_relation = deepcopy(all_relations)
                    for rela in copy_relation:
                        if rela['head'] in delete_en or rela['tail'] in delete_en:
                            all_relations.remove(rela)
                    continue
                # 文件增加修改
                with open(source_path, 'rb') as f:
                    code_bytes = f.read()
                tree = parser.parse(code_bytes)
                root = tree.root_node
                file_trees.append((source_path, root, code_bytes))
                file_contain = full_contain.get(source_path)
                if not file_contain:
                    file_entities, file_id = extract_file_entity(source_path, id_counter)
                    file_id_map[source_path] = file_id
                    all_entities.extend(file_entities)
                    id2end[file_id] = file_entities[0]

                    functions, f_map = extract_function_entities(root, code_bytes, id_counter)
                    for e in functions: e["source_file"] = source_path
                    function_entities.extend(functions)
                    function_id_map.update(f_map)
                    for e in functions:
                        id2end[e['id']] = e

                    structs, s_map = extract_struct_entities(root, code_bytes, id_counter)
                    for e in structs: e["source_file"] = source_path
                    struct_entities.extend(structs)
                    struct_id_map.update(s_map)
                    for e in structs:
                        id2end[e['id']] = e

                    variables, v_map, scope_map = extract_variable_entities(root, code_bytes, id_counter)
                    for e in variables: e["source_file"] = source_path
                    variable_entities.extend(variables)
                    variable_id_map.update(v_map)
                    variable_scope_map.update(scope_map)
                    for e in variables:
                        id2end[e['id']] = e

                    params, p_map = extract_function_parameters(root, code_bytes, id_counter, f_map)
                    for e in params: e["source_file"] = source_path
                    param_entities.extend(params)
                    param_id_map.update(p_map)
                    for e in params:
                        id2end[e['id']] = e

                    fields, f_map2 = extract_field_entities(root, code_bytes, id_counter, s_map)
                    for e in fields: e["source_file"] = source_path
                    field_entities.extend(fields)
                    for name, ids in f_map2.items():
                        field_id_map.setdefault(name, []).extend(ids)
                    for e in fields:
                        id2end[e['id']] = e
                    continue

                file_entities, file_id = extract_file_entity(source_path, id_counter)
                if source_path not in file_id_map.keys():
                    file_id_map[source_path] = file_id
                    id2end[file_id] = file_entities[0]
                    all_entities.extend(file_entities)
                # 删除增加修改
                del_id = []
                functions, f_map = extract_function_entities(root, code_bytes, id_counter)
                for e in functions: e["source_file"] = source_path
                func_names = [name for name in f_map.keys()]
                full_func_names = ''
                # 删
                if func_names:
                    full_func_names = [(enid, id2end[enid]['name']) for enid in file_contain['FUNCTION'] if id2end.get(enid)]
                    for en_tuple in full_func_names:
                        enid, enname = en_tuple
                        if enname not in func_names:
                            del_id.append(enid)
                            del function_id_map[enname]
                            del id2end[enid]
                            file_contain['FUNCTION'].remove(enid)
                            file_contain['ALL'].remove(enid)
                # 增
                keep_list = [1 for i in range(len(functions))]
                old_func_id = file_contain['FUNCTION']
                old_func_name = [en_tuple[1] for en_tuple in full_func_names]
                for func in functions:
                    if func['name'] in old_func_name:
                        en_id = old_func_id[old_func_name.index(func['name'])]
                        id2end[en_id]['start_line'] = func['start_line']
                        id2end[en_id]['end_line'] = func['end_line']
                        keep_list[functions.index(func)] = 0
                        del f_map[func['name']]
                    else:
                        id2end[func['id']] = func
                new_functions = [functions[i] for i in range(len(keep_list)) if keep_list[i]]
                function_entities.extend(new_functions)
                function_id_map.update(f_map)

                structs, s_map = extract_struct_entities(root, code_bytes, id_counter)
                for e in structs: e["source_file"] = source_path
                struct_names = [name for name in s_map.keys()]
                full_struct_names = ''
                # 删
                if struct_names:
                    full_struct_names = [(enid, id2end[enid]['name']) for enid in file_contain['STRUCT'] if id2end.get(enid)]
                    for en_tuple in full_struct_names:
                        enid, enname = en_tuple
                        if enname not in struct_names:
                            del_id.append(enid)
                            del struct_id_map[enname]
                            del id2end[enid]
                            file_contain['STRUCT'].remove(enid)
                            file_contain['ALL'].remove(enid)
                # 增
                keep_list = [1 for i in range(len(structs))]
                old_struct_id = file_contain['STRUCT']
                old_struct_name = [id2end[oldid]['name'] for oldid in old_struct_id]
                for struct in structs:
                    if struct['name'] in old_struct_name:
                        en_id = old_struct_id[old_struct_name.index(struct['name'])]
                        id2end[en_id]['scope'] = struct['scope']
                        keep_list[structs.index(struct)] = 0
                        del s_map[(struct['name'], struct['scope'])]
                    else:
                        id2end[struct['id']] = struct
                new_structs = [structs[i] for i in range(len(keep_list)) if keep_list[i]]
                struct_entities.extend(new_structs)
                struct_id_map.update(s_map)

                variables, v_map, scope_map = extract_variable_entities(root, code_bytes, id_counter)
                for e in variables: e["source_file"] = source_path
                vari_name_scope = [name_scope for name_scope in v_map.keys()]
                vari_names = [name_scope[0] for name_scope in v_map.keys()]
                full_vari_names = ''
                # 删
                if vari_names:
                    full_vari_names = [(enid, id2end[enid]['name']) for enid in file_contain['VARIABLE'] if id2end.get(enid) and not id2end.get(enid).get('role')]
                    for en_tuple in full_vari_names:
                        enid, enname = en_tuple
                        indices = np.where(np.array(vari_names) == enname)[0]
                        if not len(indices):
                            del_id.append(enid)
                            del variable_id_map[(enid, id2end[enid]['scope'])]
                            variable_scope_map[id2end[enid]['scope']].remove(enid)
                            del id2end[enid]
                            file_contain['VARIABLE'].remove(enid)
                            file_contain['ALL'].remove(enid)
                            continue
                        temp = 0
                        for candi in indices:
                            if id2end[enid]['scope'] == vari_name_scope[candi][1]:
                                temp = 1
                                break
                        if not temp:
                            del_id.append(enid)
                            del variable_id_map[(enid, id2end[enid]['scope'])]
                            variable_scope_map[id2end[enid]['scope']].remove(enid)
                            del id2end[enid]
                            file_contain['VARIABLE'].remove(enid)
                            file_contain['ALL'].remove(enid)
                # 增
                keep_list = [1 for i in range(len(variables))]
                old_vari_id = file_contain['VARIABLE']
                old_vari_name = [id2end[oldid]['name'] for oldid in old_vari_id]
                for vari in variables:
                    if vari['name'] in old_vari_name:
                        en_id = old_vari_id[old_vari_name.index(vari['name'])]
                        if id2end[en_id]['scope'] == vari['scope']:
                            id2end[en_id]['start_line'] = vari['start_line']
                            id2end[en_id]['end_line'] = vari['end_line']
                            keep_list[variables.index(vari)] = 0
                            del v_map[(vari['name'], vari['scope'])]
                            scope_map[vari['scope']].remove(vari['id'])
                        else:
                            id2end[vari['id']] = vari
                    else:
                        id2end[vari['id']] = vari
                new_variables = [variables[i] for i in range(len(keep_list)) if keep_list[i]]
                variable_entities.extend(new_variables)
                variable_id_map.update(v_map)
                variable_scope_map.update(scope_map)

                params, p_map = extract_function_parameters(root, code_bytes, id_counter, f_map)
                for e in params: e["source_file"] = source_path
                param_name_scope = [name_scope for name_scope in p_map.keys()]
                param_names = [name_scope[0] for name_scope in p_map.keys()]
                full_param_names = ''
                # 删
                if param_names:
                    full_param_names = [(enid, id2end[enid]['name']) for enid in file_contain['VARIABLE'] if id2end.get(enid) and id2end[enid].get('role')]
                    for en_tuple in full_param_names:
                        enid, enname = en_tuple
                        indices = np.where(np.array(param_names) == enname)[0]
                        if not len(indices):
                            del_id.append(enid)
                            del param_id_map[(enid, id2end[enid]['scope'])]
                            del id2end[enid]
                            file_contain['VARIABLE'].remove(enid)
                            file_contain['ALL'].remove(enid)
                            continue
                        temp = 0
                        for candi in indices:
                            if id2end[enid]['scope'] == param_name_scope[candi][1]:
                                temp = 1
                                break
                        if not temp:
                            del_id.append(enid)
                            del param_id_map[(enid, id2end[enid]['scope'])]
                            del id2end[enid]
                            file_contain['VARIABLE'].remove(enid)
                            file_contain['ALL'].remove(enid)
                # 增
                keep_list = [1 for i in range(len(params))]
                old_par_id = file_contain['VARIABLE']
                old_par_name = [id2end[oldid]['name'] for oldid in old_par_id]
                for param in params:
                    if param['name'] in old_par_name:
                        en_id = old_par_id[old_par_name.index(param['name'])] 
                        if id2end[en_id]['scope'] == param['scope']:
                            id2end[en_id]['start_line'] = param['start_line']
                            id2end[en_id]['end_line'] = param['end_line']
                            keep_list[params.index(param)] = 0
                            del p_map[(param['name'], param['scope'])]
                        else:
                            id2end[param['id']] = param
                    else:
                        id2end[param['id']] = param
                new_params = [params[i] for i in range(len(keep_list)) if keep_list[i]]
                param_entities.extend(new_params)
                param_id_map.update(p_map)

                fields, f_map2 = extract_field_entities(root, code_bytes, id_counter, s_map)
                for e in fields: e["source_file"] = source_path
                field_names = [name for name in f_map2.keys()]
                full_field_names = ''
                # 删
                if field_names:
                    full_field_names = [(enid, id2end[enid]['name']) for enid in file_contain['FIELD'] if id2end.get(enid)]
                    for en_tuple in full_field_names:
                        enid, enname = en_tuple
                        if enname not in field_names:
                            del_id.append(enid)
                            if enid in field_id_map[enname]:
                                field_id_map[enname].remove(enid)
                            del id2end[enid]
                            file_contain['FIELD'].remove(enid)
                            file_contain['ALL'].remove(enid)
                        else:
                            field_ids = f_map2[enname]
                            temp = 0
                            for fi_id in field_ids:
                                if id2end[fi_id]['scope'] == id2end[enid]['scope']:
                                    temp = 1
                                    break
                            if not temp:
                                del_id.append(enid)
                                if enid in field_id_map[enname]:
                                    field_id_map[enname].remove(enid)
                                del id2end[enid]
                                file_contain['FIELD'].remove(enid)
                                file_contain['ALL'].remove(enid)
                # 增
                keep_list = [1 for i in range(len(fields))]
                old_field_id = file_contain['FIELD']
                old_field_name = [id2end[oldid]['name'] for oldid in old_field_id]
                for field in fields:
                    if field['name'] in old_field_name:
                        en_id = old_field_id[old_field_name.index(field['name'])]
                        if id2end[en_id]['scope'] == field['scope']:
                            id2end[en_id]['start_line'] = field['start_line']
                            id2end[en_id]['end_line'] = field['end_line']
                            keep_list[fields.index(field)] = 0
                            f_map2[field['name']].remove(field['id'])
                        else:
                            id2end[field['id']] = field
                    else:
                        id2end[field['id']] = field
                new_fields = [fields[i] for i in range(len(keep_list)) if keep_list[i]]
                field_entities.extend(new_fields)
                for name, ids in f_map2.items():
                    field_id_map.setdefault(name, []).extend(ids)
                file2entity[source_path] = functions + structs + variables + params + fields

            # === 阶段 2：提取 CALLS 关系 ===
            """
            for source_path in changed_files:
                copy_call = deepcopy(old_call)
                for call in copy_call[source_path]:
                    # 删
                    if call['head'] not in id2end.keys() or call['tail'] not in id2end.keys():
                        all_relations.remove(call)
                        old_call.remove(call)
                        continue
                    if call['head'] in id2end.keys() and call['tail'] in full_contain[source_path]['ALL']:
                        old_called.append(call)
            """
            for source_path, root, code_bytes in tqdm(file_trees, desc="🔗 阶段 2：提取 CALLS"):
                if not os.path.exists(source_path):
                    continue
                if old_call:
                    for call in old_call.get(source_path):
                        all_relations.remove(call)
                if old_called:
                    for call in old_called.get(source_path):
                        if call['tail'] not in id2end.keys():
                            all_relations.remove(call)
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
                if not os.path.exists(source_path):
                    continue
                if old_assign:
                    for call in old_assign.get(source_path):
                        all_relations.remove(call)
                if old_assigned:
                    for call in old_assigned.get(source_path):
                        if call['tail'] not in id2end.keys():
                            all_relations.remove(call)
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
            del file_trees
            """
            with open('E:\\cpppro\\clang_kg\\code_kg_with_tree-sitter\\output\\glibc\\temp.json', 'w', encoding='utf-8') as f:
                json.dump(all_relations, f, indent=2, ensure_ascii=False)
            all_relations.clear()

            with open('E:\\cpppro\\clang_kg\\code_kg_with_tree-sitter\\output\\glibc\\temp.json', 'r', encoding='utf-8') as f:
                all_relations = json.load(f)
            """
            # === 阶段 4：静态关系（包含/成员） ===
            for source_path in tqdm(changed_files, desc="🔗 阶段 4：静态关系（包含/成员）"):
                if not os.path.exists(source_path):
                    continue
                if len(all_relations) >= 50000000:
                    save_temp(all_relations, flag)
                    all_relations.clear()
                    flag += 1

                file_id = file_id_map.get(source_path)
                contain_list = file2entity.get(source_path)
                if file_id is None or contain_list is None:
                    continue
                rels = build_file_level_contains(file_id, function_id_map, struct_id_map, variable_scope_map)
                all_relations.extend(rels)

            # HAS_MEMBER
            rels = extract_has_member_relations(field_entities, struct_id_map)
            all_relations.extend(rels)

            # HAS_PARAMETER
            rels = extract_has_parameter_relations(param_entities, function_id_map)
            all_relations.extend(rels)

            # HAS_VARIABLE
            rels = extract_has_variable_relations(variable_entities, function_id_map)
            all_relations.extend(rels)

            # === 阶段 6：基于函数的内部语义关系 ===
            for source_path in tqdm(changed_files, desc="🔗 阶段 6:提取 RETURNS / TYPE_OF"):
                if not os.path.exists(source_path):
                    continue
                with open(source_path, 'rb') as f:
                    code_bytes = f.read()
                tree = parser.parse(code_bytes)
                root = tree.root_node
                print(source_path)
                if len(all_relations) >= 50000000:
                    save_temp(all_relations, flag)
                    all_relations.clear()
                    flag += 1

                # RETURNS
                rels = extract_returns_relations(
                    root,
                    code_bytes,
                    function_id_map,
                    {**variable_id_map, **param_id_map},
                    field_id_map
                )
                all_relations.extend(rels)
                print(f"len of rela: {len(all_relations)}")
                if len(all_relations) >= 50000000:
                    save_temp(all_relations, flag)
                    all_relations.clear()
                    flag += 1

                # TYPE_OF
                rels = extract_typeof_relations(
                    root,
                    code_bytes,
                    variable_entities + param_entities,
                    field_entities,
                    struct_id_map
                )
                all_relations.extend(rels)
                del tree, root, code_bytes
                import gc

                gc.collect()
            
            new_entity = [id2end[key] for key in id2end.keys()]
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"代码执行耗时: {elapsed_time:.4f} 秒")
            # === 输出 JSON ===
            with open(entity_path, 'w') as f:
                json.dump(new_entity, f, indent=2)
            with open(relation_path, 'w') as f:
                json.dump(all_relations, f, indent=2)

            print(f"\n✅ 提取完成：实体 {len(new_entity)} 个，关系 {len(all_relations)} 条。")
            relation_types = Counter([r['type'] for r in all_relations])
            print("\n📊 关系类型统计：")
            for k, v in relation_types.items():
                print(f"  - {k}: {v}")
            import pickle
            data_to_save = {
                'function_id_map': function_id_map,
                'variable_id_map': variable_id_map,
                'param_id_map': param_id_map,
                'struct_id_map': struct_id_map,
                'field_id_map': field_id_map,
                'variable_scope_map': variable_scope_map,
                'file_id_map': file_id_map
            }
            pickle.dump(data_to_save, open(output_dir + '/name2id.pkl', 'wb'))
        else:
            print(f'代码库并无改动,代码关系图谱不变')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default='/home/lyk/work/glibc', help="C 源码目录路径")
    parser.add_argument("--output", type=str, default='/home/lyk/work/code_kg_with_tree-sitter/output/glibc', help="输出目录路径")
    args = parser.parse_args()

    tracemalloc.start()
    start_time = time.time()
    extract_all(args.source, args.output)
    current, peak = tracemalloc.get_traced_memory()
    end_time = time.time()
    print(f"\n⏱️ 总耗时：{end_time - start_time:.2f} 秒")
    print(f"🧠 当前内存：{current / 1024 / 1024:.2f} MB；峰值：{peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()
