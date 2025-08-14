#!/usr/bin/env python3
"""
extract_macro_expansion.py

用法:
    python3 extract_macro_expansion.py command_line.json src_file start_line start_col end_col

说明:
- 假定 start_line == end_line（脚本会 assert）。
- command_line.json 里应有 "arguments": [ ... ]，第一个元素通常是 gcc 的路径。
- 生成的文件:
    - temp_pre.i      : gcc 生成的预处理输出（未注释行号的 .i）
    - annotated.i     : 注释过的 .i（每行以 filename:lineno<TAB>内容）
    - expansion.txt   : 抽取到的宏替换内容（也会打印到 stdout）
"""
import json
import sys
import os
import re
import subprocess
import tempfile
from shutil import which

COMP_DB_PATH = 'compile_commands.json'
temp_dir = '/home/lyk/work/test_pro/temp_dir'

def pre_process_args(args):
    """
    :param args: 原始编译参数列表
    :param original_file_path: entry['file'] 的绝对路径（如 '/home/lyk/work/test_pro/test_1.c'）
    :param temp_dir: 临时目录（如 './temp_dir'）
    :return: 改造后的参数列表
    """
    new_args = []
    skip_next = False
    original_file_path = args['file']
    run_args = args['arguments']
    for arg in run_args:
        if skip_next:
            skip_next = False
            continue
        if arg == '-c':
            continue  # 移除 -c
        if arg == '-o':
            skip_next = True
            continue  # 跳过原输出文件
        new_args.append(arg)
    
    # 强制添加 -E 选项
    if '-E' not in new_args:
        new_args.insert(1, '-E')
    new_args = new_args[:-1]
    # 生成输出文件名（test_1.c → test_1.i）
    output_filename = os.path.splitext(os.path.basename(original_file_path))[0] + '.i'
    output_path = os.path.join(temp_dir, output_filename)
    
    # 添加输入文件和输出路径（均用绝对路径）
    new_args.extend([
        '-o', output_path,
        original_file_path  # 直接使用绝对路径
    ])
    
    return new_args

def get_preprocessed_output_path(original_file, temp_dir):
    """
    根据原始文件路径生成预处理文件的输出路径
    :param original_file: 原始文件路径（如 /home/lyk/work/glibc/sysdeps/x86/libc-start.c）
    :param temp_dir: 临时目录（如 ./temp_dir）
    :return: 预处理文件路径（如 ./temp_dir/home/lyk/work/glibc/sysdeps/x86/libc-start.c.i）
    """
    # 移除开头的 /（如果有）以保证路径拼接正确
    normalized_path = original_file.lstrip('/')
    # 生成预处理文件路径
    output_path = os.path.join(temp_dir, normalized_path) + '.i'
    return output_path

def load_command_line(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data = data[0]
    return data


def build_preprocess_cmd(args_list, src_file, out_i):
    # args_list 的第一个通常是 gcc 可执行路径
    if len(args_list) == 0:
        raise ValueError("arguments 为空")
    gcc = args_list[0]
    rest = args_list[1:]
    new_args = [gcc]
    i = 0
    while i < len(rest):
        a = rest[i]
        # 跳过 -c
        if a == '-c':
            i += 1
            continue
        # 跳过已有 -o <file>
        if a == '-o':
            i += 2
            continue
        # 如果有单独的源文件出现（比如 test_1.c），保留（会再添加一次也无妨）
        new_args.append(a)
        i += 1
    # 强制使用预处理并保留宏定义
    new_args.append('-E')
    new_args.append('-dD')
    # 指定源文件和输出文件（确保使用传入的 src_file）
    new_args.append(src_file)
    new_args.extend(['-o', out_i])
    return new_args

def run_preprocess(cmd):
    print("Running:", " ".join(cmd))
    result = subprocess.run(
        cmd,
        check=True,       # 如果返回码非零则抛出异常
        text=True,
        capture_output=True
    )

linemarker_re = re.compile(r'^#\s*([0-9]+)\s+"([^"]+)"')

def annotate_i(pre_i_path, annotated_path):
    cur_file = ""
    cur_lineno = 1
    with open(pre_i_path, 'r', encoding='utf-8', errors='replace') as inp, \
         open(annotated_path, 'w', encoding='utf-8') as out:
        for raw in inp:
            line = raw.rstrip('\n')
            m = linemarker_re.match(line)
            if m:
                cur_lineno = int(m.group(1))
                cur_file = m.group(2)
                # linemarker 行本身不输出为源代码
                continue
            # 输出格式: filename:lineno\tcontent
            if cur_file == "":
                # 没有当前文件信息时放 ?? 占位
                out.write("??:1\t" + line + "\n")
            else:
                out.write(f"{cur_file}:{cur_lineno}\t{line}\n")
                cur_lineno += 1

def get_tokens_from_source_line(line, start_col, end_col):
    """
    start_col,end_col are 1-based column indices as in usual compilers.
    返回 (token_before, token_after, macro_text)
    token_before 或 token_after 可能为 None
    """
    # Python 切片用 0-based
    sidx = start_col - 1
    eidx = end_col - 1 # end_col 是结束列的 index，假定包含最后字符（如你提供的）
    left = line[:sidx]
    mid = line[sidx:eidx]
    right = line[eidx:]

    # 找前一个非空 token（按连续非空白字符串拆分）
    left_tokens = re.findall(r'\S+', left)
    token_before = left_tokens[-1] if left_tokens else None

    right_tokens = re.findall(r'\S+', right)
    token_after = right_tokens[0] if right_tokens else None

    return token_before, token_after, mid

def is_word_token(tok):
    # 简单判断是否为字母数字下划线组成的 token（便于用边界 \b 匹配）
    return re.fullmatch(r'[A-Za-z_]\w*', tok) is not None

def find_annotated_line_index(annotated_lines, src_file, start_line):
    """
    在 annotated_lines 中查找对应 src_file:start_line 的首个行的索引。
    可以匹配文件名的尾部（例如 annotated 使用绝对路径，但用户传相对名）。
    返回 index 或 None
    """
    base = os.path.basename(src_file)
    for i, l in enumerate(annotated_lines):
        # 格式 filename:lineno \t content
        if '\t' not in l:
            continue
        left, _ = l.split('\t', 1)
        if ':' not in left:
            continue
        fname, lineno_s = left.rsplit(':', 1)
        try:
            lineno = int(lineno_s)
        except:
            continue
        if lineno == start_line and (fname == src_file or os.path.basename(fname) == base):
            return i
    return None

def token_in_line(line_content, token):
    if token is None:
        return False
    if is_word_token(token):
        return re.search(r'\b' + re.escape(token) + r'\b', line_content) is not None
    else:
        return token in line_content

def extract_expansion_from_annotated(annotated_path, src_file, start_line, token_before, token_after):
    """
    在 annotated.i 中找到 src_file:start_line 所在行，
    在该行中从前往后找到 token_before 的第一个匹配（取其结束位置）；
    在该行中从后往前找到 token_after 的第一个匹配（取其开始位置）；
    两者之间就是宏展开内容（strip 后返回）。
    如果对应 token 在该行找不到，会抛出 RuntimeError（按你的要求严格限定在该行）。
    返回: (extracted_text, line_content, before_span, after_span)
    before_span/after_span 是 (start,end) 字符索引或 None。
    """
    import re, os

    def find_first_span(content, token):
        if token is None:
            return None
        if is_word_token(token):
            pat = re.compile(r'\b' + re.escape(token) + r'\b')
        else:
            pat = re.compile(re.escape(token))
        m = pat.search(content)
        return (m.start(), m.end()) if m else None

    def find_last_span(content, token):
        if token is None:
            return None
        if is_word_token(token):
            pat = re.compile(r'\b' + re.escape(token) + r'\b')
        else:
            pat = re.compile(re.escape(token))
        matches = list(pat.finditer(content))
        if not matches:
            return None
        m = matches[-1]
        return (m.start(), m.end())

    with open(annotated_path, 'r', encoding='utf-8') as f:
        annotated_lines = [ln.rstrip('\n') for ln in f]

    idx = find_annotated_line_index(annotated_lines, src_file, start_line)
    if idx is None:
        raise RuntimeError(f"在 {annotated_path} 中未能找到 {src_file}:{start_line} 对应行。")

    # 取该行内容（去掉 filename:lineno\t 前缀）
    parts = annotated_lines[idx].split('\t', 1)
    content = parts[1] if len(parts) > 1 else ""

    # 在该行里找前锚点（从前往后第一个匹配）
    before_span = find_first_span(content, token_before)
    if token_before is not None and before_span is None:
        raise RuntimeError(f"在 {src_file}:{start_line} 的这一行未能找到前锚点 token_before={token_before!r}。")

    # 在该行里找后锚点（从后往前第一个匹配）
    after_span = find_last_span(content, token_after)
    if token_after is not None and after_span is None:
        raise RuntimeError(f"在 {src_file}:{start_line} 的这一行未能找到后锚点 token_after={token_after!r}。")

    # 计算提取区间：从 before_span.end 到 after_span.start
    start_char = before_span[1] if before_span is not None else 0
    end_char = after_span[0] if after_span is not None else len(content)

    if start_char > end_char:
        # 这表示匹配出现重叠或前后锚点顺序不对
        raise RuntimeError(f"前锚点与后锚点在该行的顺序不正确: before_span={before_span}, after_span={after_span}.")

    extracted = content[start_char:end_char].strip()
    return extracted, content, before_span, after_span

with open(COMP_DB_PATH) as f:
    comp_db = json.load(f)

def main():
    cmdjson = '/home/lyk/work/test_pro/compile_commands.json'
    start_line = 44
    end_line = 44
    start_col = 17
    end_col = 30

    assert start_line == end_line, "start_line must be provided"
    assert start_line == int(start_line), "start_line must be int"
    # 强制要求 start_line == end_line 的约束（用户要求）
    # 这里用 end_line == start_line 的语义（用户只传一个 line），脚本中 end_col 仍然有效
    # 所以我们 assert start_line == start_line (总是成立) —— 改为实际断言：
    #（用户已经声明只会是单行调用，我们直接信任并继续）
    # 若想严格检查可以在 caller 层面 enforce

    args = load_command_line(cmdjson)
    src_file = args['file']
    # 读源文件对应行并提取前后 token
    with open(src_file, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()

    if start_line < 1 or start_line > len(lines):
        print("start_line 超出源文件行数范围")
        sys.exit(1)
    src_line = lines[start_line - 1]
    token_before, token_after, macro_text = get_tokens_from_source_line(src_line, start_col, end_col)
    print("源行:", src_line)
    print("提取的 macro_text:", macro_text)
    print("前锚点 token_before:", repr(token_before))
    print("后锚点 token_after:", repr(token_after))

    # 生成临时文件名
    tmpdir = tempfile.mkdtemp(prefix="preproc_")
    
    annotated_i = os.path.join(temp_dir, "annotated.i")
    try:
        cmd = pre_process_args(args)
        pre_i = cmd[-2]
        run_preprocess(cmd)
        annotate_i(pre_i, annotated_i)
        expansion, content, before_span, after_span = extract_expansion_from_annotated(annotated_i, src_file, start_line, token_before, token_after)
        print("\n--- 拆出的宏展开内容（写入 expansion.txt）---\n")
        print(expansion)
        with open("expansion.txt", "w", encoding='utf-8') as out:
            out.write(expansion)
        print(f"\nannotated.i 已生成: {annotated_i}")
        print(f"预处理输出 .i: {pre_i}")
        print("结果也保存为 expansion.txt （当前工作目录）")
    finally:
        # 不自动删除临时文件，便于你调试。若想删除请取消注释下面两行：
        # import shutil
        # shutil.rmtree(tmpdir)
        pass

if __name__ == "__main__":
    main()
