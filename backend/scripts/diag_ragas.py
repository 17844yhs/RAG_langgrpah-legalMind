"""诊断 RAGAS faithfulness/context_precision 全 NaN 的根因

用 raise_exceptions=True 让 ragas 不再吞异常，跑 2 个样本看真实报错。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main():
    from tortoise import Tortoise

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.eval_dataset"]},
        _enable_global_fallback=True,
        use_tz=False,
    )
    from app.models.eval_dataset import EvalSample

    samples = await EvalSample.all().limit(2)
    print(f"加载 {len(samples)} 条样本")

    # 复用评估脚本的检索+生成
    from scripts.evaluate import retrieve_contexts, generate_answer

    questions, answers, refs, contexts_list = [], [], [], []
    for s in samples:
        ctx = await retrieve_contexts(s.question, top_k=5)
        ctx_texts = [f"{c.get('title','')}\n{c.get('content', c.get('summary',''))}" for c in ctx]
        ans = await generate_answer(s.question, ctx)
        questions.append(s.question)
        answers.append(ans)
        refs.append(s.ground_truth)
        contexts_list.append(ctx_texts)
        print(f"已生成: {s.question[:30]}... 答案长度 {len(ans)}")

    await Tortoise.close_connections()

    # ragas 补丁（同 evaluate.py）
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
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import faithfulness, context_precision
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    from app.llm.model_client import get_llm
    from app.rag.embeddings import get_embeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "reference": refs,
        "contexts": contexts_list,
    })

    ragas_llm = LangchainLLMWrapper(get_llm())
    ragas_emb = LangchainEmbeddingsWrapper(get_embeddings())

    print("\n=== raise_exceptions=True 诊断运行 ===")
    try:
        result = ragas_evaluate(
            dataset=dataset,
            metrics=[faithfulness, context_precision],
            llm=ragas_llm,
            embeddings=ragas_emb,
            raise_exceptions=True,
            run_config=RunConfig(timeout=120, max_retries=3, max_workers=2),
        )
        df = result.to_pandas()
        print(df[["faithfulness", "context_precision"]])
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n!!! 异常类型: {type(e).__name__}: {str(e)[:500]}")


asyncio.run(main())
