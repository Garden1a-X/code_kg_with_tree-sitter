import os
import re
from collections import defaultdict, deque

# 环境变量控制调试输出
DEBUG_MODE = os.getenv('DEBUG_MODE', '0') == '1'

def debug_print(*args, **kwargs):
    """调试输出函数，可通过环境变量控制"""
    if DEBUG_MODE:
        print(*args, **kwargs)

def extract_include_relations(root_node, code_bytes, file_id_map, current_file_path):
    """
    提取 INCLUDES 关系：FILE → FILE
    
    Args:
        root_node: Tree-sitter 根节点
        code_bytes: 文件字节内容
        file_id_map: 文件路径 → 文件ID 映射
        current_file_path: 当前处理的文件路径
    
    Returns:
        list: INCLUDES 关系列表
        set: 当前文件直接包含的文件路径集合
    """
    
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
    
    def resolve_include_path(include_path, current_file_dir, include_dirs=None):
        """解析 #include 路径为绝对路径"""
        if include_dirs is None:
            include_dirs = []
        
        # 相对于当前文件的路径
        if include_path.startswith('"'):
            # #include "local.h" - 相对路径
            clean_path = include_path.strip('"')
            full_path = os.path.join(current_file_dir, clean_path)
            if os.path.exists(full_path):
                return os.path.abspath(full_path)
            
            # 如果当前目录找不到，在项目包含目录中查找
            for inc_dir in include_dirs:
                full_path = os.path.join(inc_dir, clean_path)
                if os.path.exists(full_path):
                    return os.path.abspath(full_path)
        
        elif include_path.startswith('<'):
            # #include <system.h> - 系统路径，通常忽略
            return None
        
        return None
    
    include_relations = []
    direct_includes = set()
    current_file_dir = os.path.dirname(current_file_path)
    current_file_id = file_id_map.get(current_file_path)
    
    if not current_file_id:
        return include_relations, direct_includes
    
    # 自动检测项目包含目录
    project_root = current_file_path
    while project_root and project_root != '/':
        project_root = os.path.dirname(project_root)
        if any(os.path.exists(os.path.join(project_root, d)) for d in ['include', 'src', 'lib']):
            break
    
    include_dirs = []
    if project_root:
        for subdir in ['include', 'src', 'lib']:
            inc_path = os.path.join(project_root, subdir)
            if os.path.exists(inc_path):
                include_dirs.append(inc_path)
    
    def traverse(node):
        nonlocal include_relations, direct_includes
        
        if node.type == 'preproc_include':
            # 查找 #include 指令
            path_node = node.child_by_field_name('path')
            if path_node:
                include_path_text = get_text(path_node)
                resolved_path = resolve_include_path(include_path_text, current_file_dir, include_dirs)
                
                if resolved_path and resolved_path in file_id_map:
                    included_file_id = file_id_map[resolved_path]
                    include_relations.append({
                        "head": current_file_id,
                        "tail": included_file_id, 
                        "type": "INCLUDES",
                        "include_path": include_path_text
                    })
                    direct_includes.add(resolved_path)
        
        for child in node.children:
            traverse(child)
    
    traverse(root_node)
    return include_relations, direct_includes


def build_transitive_includes(all_include_relations, file_id_map):
    """
    构建传递包含关系：A includes B, B includes C => A can see C
    优化版本：使用BFS和缓存机制，大幅提升性能
    
    Args:
        all_include_relations: 所有 INCLUDES 关系
        file_id_map: 文件路径 → 文件ID 映射
    
    Returns:
        dict: 文件路径 → 可见文件路径集合
    """
    # 构建包含图
    include_graph = defaultdict(set)
    reverse_graph = defaultdict(set)  # 分离双向关系以优化性能
    id_to_path = {file_id: path for path, file_id in file_id_map.items()}
    
    # 构建正向和反向图
    for rel in all_include_relations:
        if rel["type"] == "INCLUDES":
            head_path = id_to_path.get(rel["head"])
            tail_path = id_to_path.get(rel["tail"])
            if head_path and tail_path:
                include_graph[head_path].add(tail_path)
                reverse_graph[tail_path].add(head_path)
    
    # 头文件到实现文件的映射（预计算）
    header_to_impl = {}
    for file_path in file_id_map.keys():
        if file_path.endswith('.h'):
            base_path = file_path[:-2]
            for ext in ['.c', '.cpp', '.cc']:
                impl_path = base_path + ext
                if impl_path in file_id_map:
                    header_to_impl[file_path] = impl_path
                    break
    
    # 扩展包含图：添加头文件→实现文件的关联
    extended_graph = defaultdict(set)
    for file_path, included_files in include_graph.items():
        extended_graph[file_path].update(included_files)
        # 添加头文件对应的实现文件
        for included_file in included_files:
            if included_file in header_to_impl:
                impl_file = header_to_impl[included_file]
                if impl_file != file_path:  # 避免自引用
                    extended_graph[file_path].add(impl_file)
    
    # 使用BFS计算传递闭包（带缓存）
    visibility_cache = {}
    
    def compute_transitive_closure_bfs(start_file):
        if start_file in visibility_cache:
            return visibility_cache[start_file]
        
        visible_files = {start_file}  # 文件本身可见
        queue = deque([start_file])
        visited = {start_file}
        
        while queue:
            current_file = queue.popleft()
            
            # 处理正向包含关系
            direct_includes = extended_graph.get(current_file, set())
            for included_file in direct_includes:
                if included_file not in visited:
                    visited.add(included_file)
                    visible_files.add(included_file)
                    queue.append(included_file)
            
            # 处理反向可见性（被包含文件可以看到包含文件）
            reverse_includes = reverse_graph.get(current_file, set())
            for including_file in reverse_includes:
                if including_file not in visited:
                    visited.add(including_file)
                    visible_files.add(including_file)
                    queue.append(including_file)
        
        # 缓存结果
        visibility_cache[start_file] = visible_files
        return visible_files
    
    # 为所有文件计算可见性（带进度指示）
    file_visibility = {}
    total_files = len(file_id_map)
    
    print(f"正在计算 {total_files} 个文件的传递可见性...")
    
    for i, file_path in enumerate(file_id_map.keys()):
        file_visibility[file_path] = compute_transitive_closure_bfs(file_path)
        
        # 每处理1000个文件显示一次进度
        if (i + 1) % 1000 == 0 or (i + 1) == total_files:
            progress = (i + 1) / total_files * 100
            print(f"  进度: {i + 1}/{total_files} ({progress:.1f}%)")
    
    print("✅ 传递可见性计算完成")
    return file_visibility


def extract_extern_declarations(root_node, code_bytes):
    """
    提取文件中的 extern 函数声明
    
    Returns:
        set: extern 声明的函数名集合
    """
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
    
    def find_identifier(node):
        if node is None:
            return None
        if node.type == 'identifier':
            return node
        for child in node.children:
            result = find_identifier(child)
            if result:
                return result
        return None
    
    extern_functions = set()
    
    def traverse(node):
        if node.type == 'declaration':
            # 检查是否有 extern 存储类
            has_extern = False
            for child in node.children:
                if child.type == 'storage_class_specifier' and get_text(child) == 'extern':
                    has_extern = True
                    break
            
            if has_extern:
                # 查找函数声明
                declarator_node = node.child_by_field_name('declarator')
                if declarator_node and declarator_node.type == 'function_declarator':
                    id_node = find_identifier(declarator_node)
                    if id_node:
                        func_name = get_text(id_node)
                        extern_functions.add(func_name)
        
        for child in node.children:
            traverse(child)
    
    traverse(root_node)
    return extern_functions