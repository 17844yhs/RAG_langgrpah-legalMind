"""一次性诊断：Chroma 切片构成细分（type / case_type 分布）。用完可删。"""
from collections import Counter
from pathlib import Path

import chromadb

CHROMA_PATH = Path(__file__).resolve().parent.parent / "data" / "chroma"

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
col = client.get_collection("legal_cases")
data = col.get(include=["metadatas"])
metas = data["metadatas"]

print(f"总切片数: {len(metas)}")
print("\n按 type 分布:")
for k, v in Counter(m.get("type", "?") for m in metas).most_common():
    print(f"  {k}: {v}")

print("\n按 case_type 分布:")
for k, v in Counter(m.get("case_type", "-") for m in metas).most_common():
    print(f"  {k}: {v}")

# 案例切片里不重复的案例数
case_ids = {m.get("id") for m in metas if m.get("type") == "case"}
print(f"\n案例切片对应的不重复案例数: {len(case_ids)}")
