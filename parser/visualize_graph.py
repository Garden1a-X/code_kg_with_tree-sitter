import os
import json
import networkx as nx
import matplotlib.pyplot as plt

# === 路径配置 ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
entity_path = os.path.join(ROOT_DIR, '..', 'output/test', 'entity.json')
relation_path = os.path.join(ROOT_DIR, '..', 'output/test', 'relation.json')
output_path = os.path.join(ROOT_DIR, '..', 'output/test', 'graph.png')

# === 读取数据 ===
with open(entity_path, 'r') as f:
    entities = json.load(f)
with open(relation_path, 'r') as f:
    relations = json.load(f)

# === 构建图 ===
G = nx.DiGraph()
id_to_label = {}
id_to_type = {}

for ent in entities:
    eid = ent['id']
    name = ent['name']
    etype = ent['type']
    label = f"{name}\n({etype})"
    id_to_label[eid] = label
    id_to_type[eid] = etype
    G.add_node(eid, label=label, type=etype)

for rel in relations:
    G.add_edge(rel['head'], rel['tail'], type=rel['type'])

# === 可视化样式 ===

# 增加更多类型颜色
type_color = {
    "FILE": "#f7c59f",
    "FUNCTION": "#f6f930",
    "VARIABLE": "#84dcc6",
    "STRUCT": "#e07a5f",
    "FIELD": "#57a773",
    "TYPEDEF": "#6a4c93"
}

# 增加更多边类型颜色
edge_color = {
    "CONTAINS": "gray",
    "CALLS": "blue",
    "REFERENCES": "green",
    "HAS_MEMBER": "#ffb347",
    "HAS_PARAMETER": "#00bcd4",
    "HAS_VARIABLE": "#90caf9",
    "ASSIGNED_TO": "#ff1744",
    "RETURNS": "#9575cd",
    "TYPE_OF": "#00897b"
}

node_colors = [type_color.get(id_to_type[n], "#cccccc") for n in G.nodes]
edge_colors = [edge_color.get(G[u][v]['type'], "black") for u, v in G.edges]

# === 布局并绘图 ===
pos = nx.spring_layout(G, seed=42)  # 可换为 nx.kamada_kawai_layout(G)

plt.figure(figsize=(14, 12))
nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1000, edgecolors='black')
nx.draw_networkx_labels(G, pos, labels=id_to_label, font_size=7)
nx.draw_networkx_edges(G, pos, edge_color=edge_colors, arrows=True, arrowsize=15, width=1.2)

# 边标签
edge_labels = {(u, v): G[u][v]['type'] for u, v in G.edges}
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6)

plt.axis('off')
plt.tight_layout()
plt.savefig(output_path, dpi=300)

print(f"✅ 图谱已保存至: {output_path}")
