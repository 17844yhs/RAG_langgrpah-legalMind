"""一次性诊断：案例 chunk 的 case_type 真实取值分布（层级 Agent 团队领域枚举的依据）"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from collections import Counter


def main():
    from app.rag.vector_store import get_vector_store
    vs = get_vector_store()
    col = vs._collection
    data = col.get(include=["metadatas"])
    case_metas = [m for m in data["metadatas"] if m.get("type") == "case"]
    print(f"案例 chunk 总数: {len(case_metas)}")
    dist = Counter((m.get("case_type") or "(空)") for m in case_metas)
    for k, v in dist.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
