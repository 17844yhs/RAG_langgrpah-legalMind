"""RAG 评估脚本 — 支持自定义 LLM Judge 和 RAGAS 两种模式

流程：读取评估样本 → 检索上下文 → LLM 生成答案 → 打分 → 结果入库 + JSON 报告

用法：
  cd backend && uv run scripts/evaluate.py [--run_name baseline_v1] [--limit 10]
  cd backend && uv run scripts/evaluate.py --ragas [--limit 5]
"""
import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 限制本地模型（bge/reranker torch）线程数，避免并发检索时线程超订导致 CPU 空转
# 必须在任何 app/torch 导入前设置
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

# ── Judge 评分 Prompt ──

JUDGE_PROMPT = """你是一个法律问答质量评估专家。请对以下 RAG 系统的回答进行四维度评分。

## 评估维度
1. **faithfulness**（忠实度）：生成的答案是否完全基于提供的参考资料，有没有编造信息？
2. **answer_relevancy**（答案相关性）：生成的答案是否回答了用户的问题？
3. **answer_correctness**（答案正确性）：生成的答案与标准答案在语义上是否一致？
4. **context_relevancy**（上下文相关性）：提供的参考资料是否与用户问题相关？

## 评分标准
每个维度 0-1 分：
- 0.0 = 完全不满足
- 0.3 = 部分满足，有明显不足
- 0.5 = 基本满足，有一些问题
- 0.7 = 较好满足，有小瑕疵
- 1.0 = 完全满足

## 输入数据
**用户问题**：{question}

**标准答案（ground truth）**：{ground_truth}

**参考资料（检索到的上下文）**：
{contexts}

**系统生成的答案**：{generated_answer}

## 输出格式（只输出 JSON，不要其他内容）
{{"faithfulness": <0-1>, "answer_relevancy": <0-1>, "answer_correctness": <0-1>, "context_relevancy": <0-1>, "reasoning": {{"faithfulness": "<一句话理由>", "answer_relevancy": "<一句话理由>", "answer_correctness": "<一句话理由>", "context_relevancy": "<一句话理由>"}}}}"""

# ── 答案生成 Prompt ──

ANSWER_PROMPT = """你是一个法律咨询助手。请根据以下参考资料回答用户的法律问题。
如果参考资料中没有相关信息，请如实说明。回答要准确、专业、有条理。

## 参考资料
{contexts}

## 用户问题
{question}

请直接回答问题："""


_retrieval_agent = None

async def retrieve_contexts(query: str, top_k: int = 5) -> List[Dict]:
    """使用 RetrievalAgent 检索相关文档（HybridRetriever + Reranker）"""
    global _retrieval_agent
    if _retrieval_agent is None:
        from app.agents.retrieval_agent import RetrievalAgent
        _retrieval_agent = RetrievalAgent()
    results = await _retrieval_agent.retrieve(query=query, top_k=top_k)
    return results

async def generate_answer(question: str, contexts: List[Dict]) -> str:
    """根据检索到的上下文生成答案"""
    from app.llm.model_client import get_llm
    llm = get_llm()

    context_text = "\n\n".join(
        f"【{i+1}】{c.get('title', '未知')}\n{c.get('content', c.get('summary', ''))}"
        for i, c in enumerate(contexts)
    )
    prompt = ANSWER_PROMPT.format(contexts=context_text, question=question)
    response = await llm.ainvoke(prompt)
    return response.content


async def judge_scores(
    question: str, ground_truth: str, contexts: List[Dict], generated_answer: str
) -> Dict[str, Any]:
    """LLM Judge 四维度打分"""
    from app.llm.model_client import get_llm
    llm = get_llm()

    context_text = "\n\n".join(
        f"【{i+1}】{c.get('title', '未知')}\n{c.get('content', c.get('summary', ''))[:500]}"
        for i, c in enumerate(contexts)
    )

    prompt = JUDGE_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        contexts=context_text,
        generated_answer=generated_answer,
    )

    response = await llm.ainvoke(prompt)

    # 解析 JSON
    import re
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response.content, re.DOTALL)
    text = json_match.group(0) if json_match else response.content

    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        scores = {
            "faithfulness": 0.0, "answer_relevancy": 0.0,
            "answer_correctness": 0.0, "context_relevancy": 0.0,
            "reasoning": {"error": f"JSON 解析失败: {response.content[:200]}"},
        }

    return scores


async def run_evaluation(run_name: str, limit: int = 0):
    """执行完整评估流程"""
    from tortoise import Tortoise
    from app.models.eval_dataset import EvalSample, EvalRun, EvalResult

    # 连接数据库
    db_url = "postgres://legal_user:legal_pass@localhost:5432/legal_db"
    await Tortoise.init(
        db_url=db_url,
        modules={
            "models": [
                "app.models.case", "app.models.law", "app.models.eval_dataset",
            ]
        },
        _enable_global_fallback=True,
        use_tz=False,
    )
    await Tortoise.generate_schemas(safe=True)

    # 加载评估样本
    samples = await EvalSample.all()
    if limit > 0:
        samples = samples[:limit]
    print(f"  加载了 {len(samples)} 条评估样本")

    # 创建评估运行记录
    eval_run = await EvalRun.create(
        run_name=run_name,
        total_samples=len(samples),
        config={"top_k": 5, "judge_model": "deepseek-v4-flash"},
    )

    # 逐条评估
    results = []
    scores_sum = {"faithfulness": 0, "answer_relevancy": 0, "answer_correctness": 0, "context_relevancy": 0}

    for i, sample in enumerate(samples):
        print(f"\n[{i+1}/{len(samples)}] {sample.question[:40]}...")

        # 1. 检索
        contexts = await retrieve_contexts(sample.question, top_k=5)
        context_titles = [c.get("title", "未知") for c in contexts]
        print(f"   检索到 {len(contexts)} 条上下文")

        # 2. 生成答案
        answer = await generate_answer(sample.question, contexts)
        print(f"   生成答案：{answer[:60]}...")

        # 3. Judge 打分
        scores = await judge_scores(sample.question, sample.ground_truth, contexts, answer)
        print(f"   得分：F={scores.get('faithfulness', 0):.1f} AR={scores.get('answer_relevancy', 0):.1f} "
              f"AC={scores.get('answer_correctness', 0):.1f} CR={scores.get('context_relevancy', 0):.1f}")

        # 4. 存入数据库
        eval_result = await EvalResult.create(
            run=eval_run,
            sample=sample,
            retrieved_contexts=context_titles,
            generated_answer=answer,
            faithfulness=scores.get("faithfulness", 0),
            answer_relevancy=scores.get("answer_relevancy", 0),
            answer_correctness=scores.get("answer_correctness", 0),
            context_relevancy=scores.get("context_relevancy", 0),
            judge_reasoning=scores.get("reasoning"),
        )

        # 累加分数
        for key in scores_sum:
            scores_sum[key] += scores.get(key, 0)

        results.append({
            "sample_id": sample.id,
            "question": sample.question,
            "ground_truth": sample.ground_truth,
            "generated_answer": answer,
            "retrieved_contexts": context_titles,
            "scores": {k: scores.get(k, 0) for k in scores_sum},
            "reasoning": scores.get("reasoning", {}),
        })

    # ── 汇总 ──
    n = len(samples)
    averages = {k: round(v / n, 4) if n > 0 else 0 for k, v in scores_sum.items()}

    # 更新 EvalRun 汇总分数
    eval_run.avg_faithfulness = averages["faithfulness"]
    eval_run.avg_answer_relevancy = averages["answer_relevancy"]
    eval_run.avg_answer_correctness = averages["answer_correctness"]
    eval_run.avg_context_relevancy = averages["context_relevancy"]
    await eval_run.save()

    # ── 输出报告 ──
    report = {
        "run_id": str(eval_run.id),
        "run_name": run_name,
        "total_samples": n,
        "created_at": datetime.now().isoformat(),
        "averages": averages,
        "results": results,
    }

    report_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    report_path = os.path.join(report_dir, "eval_results.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"评估完成：{run_name}")
    print(f"样本数：{n}")
    print(f"平均忠实度：      {averages['faithfulness']:.4f}")
    print(f"平均答案相关性：  {averages['answer_relevancy']:.4f}")
    print(f"平均答案正确性：  {averages['answer_correctness']:.4f}")
    print(f"平均上下文相关性：{averages['context_relevancy']:.4f}")
    print(f"报告已保存：{report_path}")
    print(f"评估记录已存入数据库 (eval_runs id={eval_run.id})")

    await Tortoise.close_connections()
    return report


async def _collect_ragas_data(run_name: str, limit: int = 0):
    """RAGAS 阶段一（异步）：检索 + 生成答案，收集评估数据"""
    from tortoise import Tortoise
    from app.models.eval_dataset import EvalSample
    from app.llm.model_client import get_llm

    # 连接数据库
    db_url = "postgres://legal_user:legal_pass@localhost:5432/legal_db"
    await Tortoise.init(
        db_url=db_url,
        modules={
            "models": [
                "app.models.case", "app.models.law", "app.models.eval_dataset",
            ]
        },
        _enable_global_fallback=True,
        use_tz=False,
    )
    await Tortoise.generate_schemas(safe=True)

    # 加载评估样本
    samples = await EvalSample.all()
    if limit > 0:
        samples = samples[:limit]
    print(f"  加载了 {len(samples)} 条评估样本")

    # ── 第一阶段：收集数据（检索 + 生成答案，并发加速）──
    questions = []
    answers = []
    ground_truths = []
    contexts_list = []
    detail_results = []
    gen_sem = asyncio.Semaphore(5)  # 并发上限：检索走本地模型，LLM 内部还有信号量兜底

    async def _prepare(idx: int, sample):
        async with gen_sem:
            contexts = await retrieve_contexts(sample.question, top_k=5)
            answer = await generate_answer(sample.question, contexts)
        context_texts = [
            f"{c.get('title', '')}\n{c.get('content', c.get('summary', ''))}"
            for c in contexts
        ]
        context_titles = [c.get("title", "未知") for c in contexts]
        print(f"[{idx+1}/{len(samples)}] {sample.question[:40]}... 完成（{len(contexts)} 条上下文，答案 {len(answer)} 字）")
        return sample, contexts, answer, context_texts, context_titles

    tasks = [_prepare(i, s) for i, s in enumerate(samples)]
    prepared = await asyncio.gather(*tasks)

    for sample, contexts, answer, context_texts, context_titles in prepared:
        questions.append(sample.question)
        answers.append(answer)
        ground_truths.append([sample.ground_truth])  # RAGAS 要求 list of list
        contexts_list.append(context_texts)

        detail_results.append({
            "sample_id": sample.id,
            "question": sample.question,
            "ground_truth": sample.ground_truth,
            "generated_answer": answer,
            "retrieved_contexts": context_titles,
        })

    await Tortoise.close_connections()
    return {
        "sample_count": len(samples),
        "questions": questions,
        "answers": answers,
        "ground_truths": ground_truths,
        "contexts_list": contexts_list,
        "detail_results": detail_results,
    }


def run_ragas_evaluation(run_name: str, limit: int = 0):
    """使用 RAGAS 框架评估 RAG 管线

    两阶段架构（修复 executor 死锁）：
      阶段一 asyncio.run() 异步收集数据；阶段二在主线程【同步】跑 ragas_evaluate，
      让 ragas 独占事件循环。旧版把 ragas 丢进 executor 线程，其内部
      nest_asyncio 与外层事件循环互锁，进程会永久挂起（CPU 烧完后闲置）。
    """
    from app.llm.model_client import get_llm

    data = asyncio.run(_collect_ragas_data(run_name, limit))

    # RAGAS 0.4.x 兼容补丁 — ChatVertexAI 在新版 langchain_community 中已移除
    import importlib
    import sys as _sys
    import types as _types
    _mod_path = "langchain_community.chat_models.vertexai"
    if _mod_path not in _sys.modules:
        try:
            importlib.import_module(_mod_path)
        except (ImportError, ModuleNotFoundError):
            _stub = _types.ModuleType(_mod_path)
            _stub.ChatVertexAI = type("ChatVertexAI", (), {})
            _sys.modules[_mod_path] = _stub

    from datasets import Dataset
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )

    dataset = Dataset.from_dict({
        "question": data["questions"],
        "answer": data["answers"],
        "reference": [gt[0] for gt in data["ground_truths"]],  # RAGAS 0.4.x 列名
        "contexts": data["contexts_list"],
    })
    detail_results = data["detail_results"]
    sample_count = data["sample_count"]

    print(f"\n{'='*50}")
    print("  正在运行 RAGAS 评估...")

    # 使用项目的 LLM 作为 RAGAS 评估模型
    # 不能直接用 get_llm()：① RunnableWithFallbacks 禁止 setattr temperature
    #    → ragas 每样本抛 ValueError → NaN；② DeepSeek 不支持 n>1 参数
    #    → faithfulness/context_precision 请求 n=3 时 400 BadRequestError → NaN
    # 解决：直接构造 _RagasCompatibleDeepSeek 实例（解包 fallback + n>1 兼容）
    from app.llm.model_client import _ThrottledDeepSeek
    from app.config import settings
    from langchain_core.outputs import ChatResult
    from ragas.llms import LangchainLLMWrapper

    class _RagasCompatibleDeepSeek(_ThrottledDeepSeek):
        """RAGAS 兼容版：DeepSeek 不支持 n>1，此子类拆 n>1 为 n 次 n=1 调用后合并"""

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            n = self.n  # RAGAS 直接设 model 属性而非 kwargs
            if n <= 1:
                return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self.n = 1  # 临时降为 1，避免 API 400
            try:
                gens = []
                for _ in range(n):
                    r = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
                    gens.extend(r.generations)
                return ChatResult(generations=gens, llm_output={})
            finally:
                self.n = n  # 恢复原值

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            n = self.n
            if n <= 1:
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self.n = 1
            try:
                gens = []
                for _ in range(n):
                    r = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
                    gens.extend(r.generations)
                return ChatResult(generations=gens, llm_output={})
            finally:
                self.n = n

    raw_llm = _RagasCompatibleDeepSeek(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        extra_body={"thinking": {"type": "disabled"}},
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
    ragas_llm = LangchainLLMWrapper(raw_llm)
    # 包装 Embeddings（用项目的 bge-small-zh，避免依赖 OpenAI）
    try:
        from app.rag.embeddings import get_embeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        ragas_emb = LangchainEmbeddingsWrapper(get_embeddings())
    except Exception:
        ragas_emb = None
    # RunConfig：解析失败/超时自动重试，进一步压低 NaN 率
    from ragas.run_config import RunConfig
    kwargs = dict(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=ragas_llm,
        run_config=RunConfig(timeout=300, max_retries=3, max_workers=2),
    )
    if ragas_emb:
        kwargs["embeddings"] = ragas_emb
    result = ragas_evaluate(**kwargs)

    # ── 输出结果 ──
    df = result.to_pandas() if hasattr(result, 'to_pandas') else None

    if df is not None:
        avg = df.mean(numeric_only=True)
        # NaN 透明化：每列统计打分失败的行数（LLM 解析失败/超时且重试后仍失败）
        metric_cols = [c for c in ("faithfulness", "answer_relevancy", "context_precision", "context_recall") if c in df.columns]
        nan_counts = {c: int(df[c].isna().sum()) for c in metric_cols}
        print(f"\n{'='*50}")
        print(f"RAGAS 评估完成：{run_name}")
        print(f"样本数：{sample_count}")
        for col in avg.index:
            nan_note = f"（NaN {nan_counts[col]} 行）" if col in nan_counts and nan_counts[col] else ""
            print(f"  {col}: {avg[col]:.4f} {nan_note}")

        # 保存详细结果
        report_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        report_path = os.path.join(report_dir, "ragas_results.json")
        report_data = {
            "run_name": run_name,
            "total_samples": sample_count,
            "created_at": datetime.now().isoformat(),
            "averages": {col: round(float(avg[col]), 4) for col in avg.index},
            "nan_counts": nan_counts,
            "valid_samples": {col: int(df[col].notna().sum()) for col in metric_cols},
            "per_sample": df.to_dict(orient="records"),
            "details": detail_results,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n报告已保存：{report_path}")
    else:
        # 回退：手动打印 result
        print(f"\nRAGAS 结果：{result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG 评估脚本")
    parser.add_argument("--run_name", default=f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}", help="评估运行名称")
    parser.add_argument("--limit", type=int, default=0, help="限制评估样本数（0=全部）")
    parser.add_argument("--ragas", action="store_true", help="使用 RAGAS 评估框架（替代自定义 LLM Judge）")
    args = parser.parse_args()

    if args.ragas:
        print("🔍 开始 RAGAS 评估...")
        print(f"   运行名称：{args.run_name}")
        print(f"   样本限制：{args.limit or '全部'}")
        run_ragas_evaluation(args.run_name, args.limit)
    else:
        print("🔍 开始 RAG 评估...")
        print(f"   运行名称：{args.run_name}")
        print(f"   样本限制：{args.limit or '全部'}")
        asyncio.run(run_evaluation(args.run_name, args.limit))
    print("\n✅ 评估完成")
