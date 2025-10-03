
import re
def glibc_alias(s):
    s = s.replace("\n", ' ').replace('\t', ' ')
    pattern = r'\b(?P<type>strong_alias|weak_alias)\s*\(\s*(?P<src>[^,()]+?)\s*,\s*(?P<dst>[^()]+?)\s*\)'
    matches = []
    for m in re.finditer(pattern, s, flags=re.MULTILINE):
        matches.append({
            "type": m.group("type").split('_')[0],
            "src": m.group("src").strip(),
            "dst": m.group("dst").strip(),
        })
    return matches


def linux_alias(text):
    # 先定位函数/符号声明 + 随后的 __attribute__((...)) 整块
    # 使用 DOTALL 以允许换行，MULTILINE 以正确处理多行文件
    text = text.replace("\n", ' ').replace('\t', ' ')
    pattern = re.compile(
        r'\b(?P<src>[A-Za-z_]\w*)'                  # 函数/符号名（src）
        r'\s*\([^;{)]*\)\s*'                        # 括号内参数（简单匹配，不深入解析参数）
        r'__attribute__\s*\(\(\s*(?P<attr>.*?)\)\)\s*;', # attribute 的整个内容，直到分号
        re.DOTALL | re.MULTILINE
    )
    results = []
    for m in pattern.finditer(text):
        src = m.group('src').strip()
        attr = m.group('attr').strip()

        # 在 attribute 内容里寻找 alias("...") 或 alias('...')
        a = re.search(r'alias\s*\(\s*["\'](?P<dst>[A-Za-z_]\w*)["\']\s*\)', attr)
        if not a:
            continue  # 没有 alias(...) 的情况忽略

        dst = a.group('dst')

        # 判断是否包含 weak 标志（不区分顺序，只要在 attribute 内容中出现 weak 即视为弱别名）
        kind = 'weak' if re.search(r'\bweak\b', attr) else 'strong'

        results.append({"type": kind, "src": src, "dst": dst})

    return results

template = {
    'glibc': glibc_alias,
    'linux': linux_alias
}
def extract_alias_relations(
    root,
    code_bytes,
    contain_list,
    abs_path
):
    def get_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
    
    relations = []
    extract_func = None
    for pl in template.keys():
        if pl in abs_path:
            extract_func = template.get(pl)
            break
    if not extract_func:
        return []
    
    con_dir = {entity['name']: entity['id'] for entity in contain_list if entity['type'] == 'FUNCTION'}
    for child in root.children:
        child_text = get_text(child)
        alias_list = extract_func(child_text)
        
        for apair in alias_list:
            kind = apair['type']
            src_name = apair['src']
            dst_name = apair['dst']

            src_id = con_dir.get(src_name)
            dst_id = con_dir.get(dst_name)

            if src_id and dst_id:
                rela = {
                    'head': src_id,
                    'tail': dst_id,
                    'type': 'ALIAS',
                    'kind': kind
                }
                relations.append(rela)
    return relations
