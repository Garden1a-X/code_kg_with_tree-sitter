# 📘 Code Knowledge Graph Extraction for C Projects

本项目旨在从 C 语言源码中自动抽取结构化的代码知识图谱（Code Knowledge Graph, CKG），用于辅助理解系统结构、隐式调用路径（如函数指针）、模块间依赖等复杂关系。适用于系统软件、嵌入式工程、大型开源项目（如 Linux / glibc）等源代码分析场景。

---

## ✅ 已支持功能

* **实体提取**：

  * 文件（FILE）
  * 函数（FUNCTION）
  * 变量（VARIABLE，支持全局变量/局部变量/函数参数，含作用域信息）
  * 结构体（STRUCT）
  * 字段（FIELD，含嵌套匿名结构体字段）

* **关系提取**：

  * 包含关系（CONTAINS）：文件/函数/结构体的成员归属
  * 函数调用（CALLS）：支持函数直接调用、函数指针调用、宏函数调用等
  * 参数归属（HAS\_PARAMETER）：函数参数归属
  * 局部变量归属（HAS\_VARIABLE）：函数内变量定义
  * 结构体成员（HAS\_MEMBER）：结构体中字段定义
  * 类型归属（TYPE\_OF）：变量/字段归属的结构体类型
  * 函数返回（RETURNS）：函数返回变量或结构体字段
  * 指针赋值（ASSIGNED\_TO）：包括函数指针赋值、结构体字段赋值、通过宏展开的隐式赋值等

* **图谱输出**：

  * 标准格式：`entity.json` 与 `relation.json`，可供后续分析使用

* **静态可视化**：

  * 使用 `networkx` + `matplotlib` 输出 `.png` 格式图像

---

## 📁 项目结构

```
code_kg/
├── build/
│   └── my-languages.so             # Tree-sitter C 动态库
├── data/
│   ├── test_case_multi_file/       # 多文件测试用例（test_1.c, test_2.c）
│   ├── glibc_data/                 # glibc 源码目录
│   └── linux_data/                 # Linux 源码目录
├── output/
│   ├── entity.json                 # 抽取结果（总）
│   ├── relation.json
│   └── <filename>/                # 针对每个文件的子文件夹输出
│       ├── entity.json
│       └── relation.json
├── parser/
│   ├── extract_entity_*.py        # 各类实体抽取脚本
│   ├── extract_relation_*.py      # 各类关系抽取脚本（包含 CALLS、ASSIGNED_TO 等）
│   ├── run_extract_all.py         # 主运行入口（支持批量处理、性能统计）
│   └── visualize_graph.py         # 可视化模块
├── tree-sitter-c/                 # Tree-sitter 语法树目录
└── README.md
```

---

## ⚙️ 安装环境

建议使用 Anaconda 环境：

```bash
pip install tree_sitter networkx matplotlib python-dateutil
```

确保已正确构建 Tree-sitter C 动态库至 `build/my-languages.so`，否则请参考 Tree-sitter 官方说明构建。

---

## 🧪 使用方法

### 1. 抽取图谱

```bash
python parser/run_extract_all.py
```

* 输入路径默认为 `data/`
* 输出将保存在 `output/` 目录下，支持：

  * 所有文件的合并输出：`output/entity.json`, `output/relation.json`
  * 每个源文件对应一个子文件夹：如 `output/test_1.c/entity.json`

## 🔍 支持的实体类型

| 类型       | 描述             |
| -------- | -------------- |
| FILE     | 源文件路径          |
| FUNCTION | 函数名，带作用域信息     |
| VARIABLE | 变量名，支持局部/全局/参数 |
| STRUCT   | 结构体名           |
| FIELD    | 结构体字段，支持嵌套匿名字段 |

---

## 🔗 支持的关系类型

| 关系类型           | 描述                                   |
| -------------- | ------------------------------------ |
| CONTAINS       | 文件→函数、结构体→字段、函数→变量等归属关系              |
| CALLS          | 函数调用关系，支持函数指针、宏调用等                   |
| HAS\_PARAMETER | 函数参数归属                               |
| HAS\_VARIABLE  | 函数内部定义的变量                            |
| HAS\_MEMBER    | STRUCT 与 FIELD 的结构体字段关系              |
| TYPE\_OF       | VARIABLE/FIELD 的类型归属结构体（支持嵌套 struct） |
| RETURNS        | 函数返回变量、字段、常量等                        |
| ASSIGNED\_TO   | 赋值关系，支持结构体字段赋值、宏函数右值展开、函数指针绑定等复杂情况   |

---

## 📌 后续可扩展方向

* ✅ ✅ 支持跨文件宏展开与函数调用路径分析；
* ✅ ✅ 支持 ops 表指针调用链解析；
* ⏳ typedef、union、enum 类型实体解析；
* ⏳ 将图谱导入 Neo4j 等图数据库进行交互式可视化；
* ⏳ 提供 HTML 报告输出及调用路径可视化；
* ⏳ 大规模代码库（如 glibc、Linux kernel）高效抽取与多线程优化。

---

如需扩展或定制，请联系开发者或提交 issue。欢迎贡献与建议！
