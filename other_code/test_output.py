import json

path = "/data/xuao/code_kg/output/glibc/relation.json"
with open(path, "r") as f:
    data = json.load(f)

result = list(set([rel["tail"] for rel in data if rel.get("head") == "122244" and rel.get("type") == "CALLS"]))

print("TAIL IDs:", result)
