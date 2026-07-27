"""评估数据模型 — 测试集 + 评估运行记录"""
from tortoise import fields
from tortoise.models import Model


class EvalSample(Model):
    """评估样本 — 测试集中的每条问题 + 标准答案"""
    id = fields.CharField(max_length=50, pk=True, description="样本ID，如 qa_001")
    question = fields.TextField(description="测试问题")
    ground_truth = fields.TextField(description="标准答案（ground truth）")
    category = fields.CharField(max_length=50, null=True, description="法律类别")
    difficulty = fields.CharField(max_length=20, null=True, description="难度等级")
    relevant_law_ids = fields.JSONField(null=True, description="相关法条ID列表")
    relevant_case_ids = fields.JSONField(null=True, description="相关案例ID列表")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "eval_samples"

    def to_dict(self):
        return {
            "id": self.id,
            "question": self.question,
            "ground_truth": self.ground_truth,
            "category": self.category,
            "difficulty": self.difficulty,
            "relevant_law_ids": self.relevant_law_ids,
            "relevant_case_ids": self.relevant_case_ids,
        }


class EvalRun(Model):
    """评估运行记录 — 每次跑评估生成一条"""
    id = fields.UUIDField(pk=True)
    run_name = fields.CharField(max_length=200, description="评估名称，如 'baseline_v1'")
    total_samples = fields.IntField(default=0, description="样本总数")
    avg_faithfulness = fields.FloatField(null=True, description="平均忠实度")
    avg_answer_relevancy = fields.FloatField(null=True, description="平均答案相关性")
    avg_answer_correctness = fields.FloatField(null=True, description="平均答案正确性")
    avg_context_relevancy = fields.FloatField(null=True, description="平均上下文相关性")
    config = fields.JSONField(null=True, description="评估配置（模型、top_k等）")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "eval_runs"

    def to_dict(self):
        return {
            "id": str(self.id),
            "run_name": self.run_name,
            "total_samples": self.total_samples,
            "avg_faithfulness": self.avg_faithfulness,
            "avg_answer_relevancy": self.avg_answer_relevancy,
            "avg_answer_correctness": self.avg_answer_correctness,
            "avg_context_relevancy": self.avg_context_relevancy,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EvalResult(Model):
    """评估结果 — 每条样本的详细得分"""
    id = fields.UUIDField(pk=True)
    run = fields.ForeignKeyField("models.EvalRun", related_name="results", description="所属评估运行")
    sample = fields.ForeignKeyField("models.EvalSample", related_name="results", description="所属评估样本")
    retrieved_contexts = fields.JSONField(null=True, description="检索到的上下文（标题列表）")
    generated_answer = fields.TextField(null=True, description="LLM 生成的答案")
    faithfulness = fields.FloatField(null=True, description="忠实度 0-1")
    answer_relevancy = fields.FloatField(null=True, description="答案相关性 0-1")
    answer_correctness = fields.FloatField(null=True, description="答案正确性 0-1")
    context_relevancy = fields.FloatField(null=True, description="上下文相关性 0-1")
    judge_reasoning = fields.JSONField(null=True, description="LLM Judge 的评分理由")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "eval_results"

    def to_dict(self):
        return {
            "id": str(self.id),
            "run_id": str(self.run_id),
            "sample_id": str(self.sample_id),
            "retrieved_contexts": self.retrieved_contexts,
            "generated_answer": self.generated_answer,
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "answer_correctness": self.answer_correctness,
            "context_relevancy": self.context_relevancy,
            "judge_reasoning": self.judge_reasoning,
        }
