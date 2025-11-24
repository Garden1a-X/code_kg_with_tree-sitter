import os
import subprocess
import sys

def run_git_command(args, cwd=None):
    """运行 Git 命令并返回结果"""
    try:
        # 如果没有指定工作目录，使用当前脚本所在目录
        if cwd is None:
            cwd = os.getcwd()
            
        result = subprocess.run(
            ['git'] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # 检查是否是"not a git repository"错误
        if "not a git repository" in e.stderr:
            print('Not a Git Repository')
            return None
        if 'user.email' in args or 'user.name' in args:
            print('Git email/name has not been configured yet')
            return None
        # 输出更详细的错误信息
        print(f"Git 命令执行失败: {e}")
        print(f"命令: git {' '.join(args)}")
        print(f"错误输出: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Git 未安装，请先安装 Git")
        return None

def configure_git_user(repo_path):
    """配置Git用户信息（如果尚未配置）"""
    # 检查是否已配置用户邮箱
    user_email = run_git_command(['config', 'user.email'], cwd=repo_path)
    if not user_email:
        # 设置本地仓库的用户邮箱（可以设置为一个默认值）
        run_git_command(['config', 'user.email', '2423796276@qq.com'], cwd=repo_path)
    
    # 检查是否已配置用户名称
    user_name = run_git_command(['config', 'user.name'], cwd=repo_path)
    if not user_name:
        run_git_command(['config', 'user.name', 'lyklly'], cwd=repo_path)

def check_and_init_repo(repo_path=None):
    """检查是否为 Git 仓库，如果不是则初始化"""
    if repo_path is None:
        repo_path = os.getcwd()
    
    # 检查是否为 Git 仓库
    git_dir = run_git_command(['rev-parse', '--git-dir'], cwd=repo_path)
    if git_dir is None:
        print(f"目录 {repo_path} 不是 Git 仓库，正在初始化...")
        run_git_command(['init'], cwd=repo_path)
        
        # 配置用户信息
        configure_git_user(repo_path)
        
        # 添加所有文件
        add_output = run_git_command(['add', '.'], cwd=repo_path)
        
        # 检查是否有文件可提交
        status_output = run_git_command(['status', '--porcelain'], cwd=repo_path)
        run_git_command(['commit', '-m', '初始提交'], cwd=repo_path)
        print(f"已在 {repo_path} 初始化 Git 仓库并提交所有文件")
        return False
    return True

def get_changed_files(repo_path=None):
    """获取变更的文件列表"""
    if repo_path is None:
        repo_path = os.getcwd()
    
    # 检查是否有变更
    status_output = run_git_command(['status', '--porcelain'], cwd=repo_path)
    if not status_output:
        print("没有检测到文件变更")
        return []
    
    # 解析变更的文件列表
    changed_files = []
    for line in status_output.split('\n'):
        if line.strip():
            # 提取文件路径（处理可能的重命名等情况）
            file_path = line.split(' ')[1]
            # 处理重命名情况（例如：R  file1.txt -> file2.txt）
            if ' -> ' in file_path:
                file_path = file_path.split(' -> ')[1].strip()
            # 确保文件路径是相对于仓库根目录的
            changed_files.append(file_path)
    
    return changed_files

def init_and_get_change(repo_path=None):
    """主函数"""
    if repo_path is None:
        repo_path = os.getcwd()
    
    # 检查并初始化仓库（如果不是 Git 仓库）
    result = check_and_init_repo(repo_path)
    if not result:  # 表示刚刚初始化了仓库
        changed_files = []
    else:
        # 获取变更文件列表
        changed_files = get_changed_files(repo_path)
    
    # 输出结果供其他 Python 代码使用
    print(f"在仓库 {repo_path} 中检测到变更的文件:")
    for file in changed_files:
        print(file)
    
    return changed_files

if __name__ == "__main__":
    # 可以选择指定仓库路径，如果不指定则使用当前目录
    repo_path = None
    print(1)
    changed_files = init_and_get_change(repo_path)
    # 现在 changed_files 变量包含了所有变更的文件路径列表
    # 你可以将它传递给其他函数进行处理