"""R3 ｜ rerank 阈值校准：正负两组测试集的分数分布 → 建议切点

背景：RAG_SCORE_THRESHOLD=0.05 是观察性定值（当年只看噪声 ≤0.04 就卡线），
未经正负集校准。本脚本按 R3 方案构造两组数据：

- 正对：EvalSample.question × 其 relevant_law_ids 对应法条（应得高分）
- 负对：EvalSample.question × 随机抽的非相关法条（应得低分）

跑 bge-reranker 输出两组分布（P05/P25/中位/P75）+ 正负重叠分析 + 建议阈值
（正 P05 与负 P95 之间取几何中点；若重叠则报告"该重叠区不可分"并给保守值）。

用法：cd backend && uv run python scripts/calibrate_rerank_threshold.py [--n 60]
（连 DB 读 eval_samples/laws，加载 cross-encoder，秒级~30s）
"""
import argparse
import asyncio
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


def _pct(sorted_vals: list[float], p: float) -> float:
    """分位数（最近邻法，len>=1）"""
    if not sorted_vals:
        return 0.0
    idx = min(int(p * (len(sorted_vals) - 1)), len(sorted_vals) - 1)
    return sorted_vals[idx]


def _fmt(v: float) -> str:
    return f"{v:.4f}"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=60, help="抽样样本数（正对来源）")
    args = parser.parse_args()
    rng = random.Random(42)  # 固定种子：可复现

    from tortoise import Tortoise
    from app.config import settings
    from app.db.database import TORTOISE_ORM
    from app.models.eval_dataset import EvalSample
    from app.models.law import Law
    from app.rag.reranker import Reranker

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        # ── 取正负对 ──
        samples = (await EvalSample.all()
                   .exclude(relevant_law_ids=None)
                   .limit(args.n))
        laws = await Law.all()
        laws_by_id = {law.id: law for law in laws}
        law_ids = list(laws_by_id)

        pairs_pos: list[tuple[str, str]] = []  # (query, content)
        pairs_neg: list[tuple[str, str]] = []
        for s in samples:
            rel = [i for i in (s.relevant_law_ids or []) if i in laws_by_id]
            if not rel:
                continue
            for lid in rel[:2]:  # 每题至多 2 个相关法条，防单题刷量
                pairs_pos.append((s.question, laws_by_id[lid].content))
            # 负对：随机 3 个非相关法条
            for lid in rng.sample(law_ids, min(3, len(law_ids))):
                if lid not in rel:
                    pairs_neg.append((s.question, laws_by_id[lid].content))

        if not pairs_pos or not pairs_neg:
            print("eval_samples 缺 relevant_law_ids 或 laws 表为空，先跑 import_eval_data.py")
            return
        print(f"正对 {len(pairs_pos)} 个（{len(samples)} 题样本），负对 {len(pairs_neg)} 个\n")

        # ── 跑 cross-encoder 打分 ──
        reranker = Reranker()

        async def score(pairs: list[tuple[str, str]]) -> list[float]:
            # reranker.rerank(query, documents, top_k) 按分数降序返回；
            # 这里全量保留（top_k=len），逐 doc 读 rerank_score
            out = []
            for i in range(0, len(pairs), 16):  # 小批防 OOM
                batch = pairs[i:i + 16]
                # 同一 query 的 docs 一起送：cross-encoder 是 (query, doc) 对打分
                by_q: dict[str, list[str]] = {}
                for q, c in batch:
                    by_q.setdefault(q, []).append(c)
                for q, contents in by_q.items():
                    docs = [{"content": c, "title": "", "metadata": {}} for c in contents]
                    ranked = await reranker.rerank(query=q, documents=docs, top_k=len(docs))
                    out.extend(d["rerank_score"] for d in ranked)
            return out

        pos = sorted(await score(pairs_pos))
        neg = sorted(await score(pairs_neg))

        # ── 分布报告 ──
        print("          P05     P25     中位     P75     P95     max")
        print(f"正(相关)  {_fmt(_pct(pos, .05))}  {_fmt(_pct(pos, .25))}  "
              f"{_fmt(_pct(pos, .5))}  {_fmt(_pct(pos, .75))}  "
              f"{_fmt(_pct(pos, .95))}  {_fmt(pos[-1])}")
        print(f"负(无关)  {_fmt(_pct(neg, .05))}  {_fmt(_pct(neg, .25))}  "
              f"{_fmt(_pct(neg, .5))}  {_fmt(_pct(neg, .75))}  "
              f"{_fmt(_pct(neg, .95))}  {_fmt(neg[-1])}")

        pos_p05, neg_p95 = _pct(pos, .05), _pct(neg, .95)
        cur = settings.RAG_SCORE_THRESHOLD
        print(f"\n当前阈值 {cur}；正P05={_fmt(pos_p05)}，负P95={_fmt(neg_p95)}")

        if pos_p05 > neg_p95:
            # 可分：切点取正P05与负P95的几何中点（对数尺度，贴近重尾分布）
            import math
            suggested = math.sqrt(pos_p05 * neg_p95) if pos_p05 > 0 and neg_p95 > 0 \
                else (pos_p05 + neg_p95) / 2
            print(f"两组可分：建议阈值 ≈ {_fmt(suggested)}（正P05/负P95 几何中点）")
            print(f"校验：此切点误杀正例 {sum(1 for s in pos if s < suggested)}/{len(pos)}"
                  f"，漏放负例 {sum(1 for s in neg if s >= suggested)}/{len(neg)}")
            if suggested > cur * 2:
                print(f"显著高于现值 {cur}——建议在 config.RAG_SCORE_THRESHOLD 更新后"
                      f"跑 RAGAS 全量回归（149 条）确认 Faithfulness 不降")
            else:
                print("与现值同量级——现值可保留，本报告作为校准留档")
        else:
            print("警告：正负分布重叠（该重叠区不可分）——"
                  "口语 query × 抽象条文的语义鸿沟所致，阈值只能保守（宁漏勿杀正例），"
                  "维持低阈值 + 空结果显式拒答声明（qa_agent.build_messages）兜底")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
