import os

# 环境变量控制调试输出
DEBUG_MODE = os.getenv('DEBUG_MODE', '0') == '1'

def debug_print(*args, **kwargs):
    """调试输出函数，可通过环境变量控制"""
    if DEBUG_MODE:
        print(*args, **kwargs)

def extract_has_member_relations(field_entities, struct_id_map):
    """
    构造 HAS_MEMBER 关系：
    STRUCT → FIELD
    修复版本：处理键格式匹配和多值映射问题
    
    - field_entities: 所有字段实体，包含其 scope（即所属 struct 名）
    - struct_id_map: 映射 (struct_name, scope) → id 或 [id1, id2, ...]
    """
    relations = []
    
    debug_print(f"\n[DEBUG] 开始提取 HAS_MEMBER 关系")
    debug_print(f"[DEBUG] 字段实体数量: {len(field_entities)}")
    debug_print(f"[DEBUG] struct_id_map 键数量: {len(struct_id_map)}")
    
    # 调试：显示struct_id_map的键
    debug_print("[DEBUG] struct_id_map 的键:")
    for key in list(struct_id_map.keys())[:5]:  # 只显示前5个
        debug_print(f"  {key}")
    if len(struct_id_map) > 5:
        debug_print(f"  ... 还有 {len(struct_id_map) - 5} 个")
    
    for field in field_entities:
        struct_name = field.get("scope")  # 例如: "Device"
        field_id = field["id"]
        field_name = field.get("name", "unknown")
        
        if not struct_name:
            debug_print(f"[DEBUG] 字段 {field_name} (id:{field_id}) 缺少 scope")
            continue
            
        # 🔧 修复：尝试多种键格式来匹配struct_id_map
        possible_keys = [
            struct_name,                    # 直接匹配："Device"
            (struct_name, "global"),        # 全局作用域：("Device", "global")
            (struct_name, struct_name),     # 自引用作用域：("Device", "Device")
        ]
        
        matched_struct_id = None
        matched_key = None
        
        for key in possible_keys:
            if key in struct_id_map:
                struct_id_or_list = struct_id_map[key]
                
                # 🔧 处理多值映射
                if isinstance(struct_id_or_list, list):
                    # 选择第一个，通常同名结构体在相同作用域只有一个
                    matched_struct_id = struct_id_or_list[0]
                else:
                    matched_struct_id = struct_id_or_list
                    
                matched_key = key
                break
        
        if matched_struct_id:
            relations.append({
                "head": matched_struct_id,
                "tail": field_id,
                "type": "HAS_MEMBER"
            })
            debug_print(f"[DEBUG] ✅ {struct_name}.{field_name}: struct_id:{matched_struct_id} -> field_id:{field_id} (键:{matched_key})")
        else:
            debug_print(f"[DEBUG] ❌ {struct_name}.{field_name}: 未找到结构体ID (尝试的键: {possible_keys})")
    
    debug_print(f"[DEBUG] 生成 {len(relations)} 个 HAS_MEMBER 关系")
    return relations