"""模型护栏（UPGRADE_PLAN 14.1 Pre/Post Model Hooks 等价落地）

LangGraph 1.0 的 pre_model_hook/post_model_hook 只挂在 create_react_agent 上，
本项目图是手搓 StateGraph，等价落法：
- Pre Hook  = 图入口 input_guardrail 节点（set_entry_point），命中风险输入即短路
  到 final_output，0 次 LLM 调用
- Post Hook = quality_gate 内的确定性输出校验，先于 LLM 自评执行（违规不花评审调用，
  重试额度用尽则替换为兜底话术，绝不放行泄漏内容）

设计原则：**规则宁少勿滥、高精度低召回**——护栏误杀正常法律咨询（如"正当防卫
怎么认定"含"杀人"字样）比漏放更伤系统可信度；模式只收明确越界表达。内容真实性
由质量门控（忠实性一票否决）负责，这里只兜"内容安全"。
"""
import re

# ── Pre Hook：输入护栏 ──

# 自伤/自杀风险：拒绝 + 危机干预导向
_SELF_HARM = re.compile(
    r"自杀|自残|自伤|轻生|割腕|结束自己的生命|怎么(才能)?死"
)
# 违法行为实施方法请求（制造/获取类动词 + 危害对象；方法/教程类后缀降低误杀）
_ILLEGAL = re.compile(
    r"(制造|制作|合成|配制|提炼)(炸药|爆炸物|炸弹|毒物|毒药|毒品|冰毒|枪支|弹药)"
    r"|(毒品|冰毒|炸药|爆炸物|枪支|弹药)(制造|制作|合成|提炼|生产)(方法|教程|技术|流程)?"
    r"|杀人(方法|教程|技巧|怎么杀)|投毒(方法|教程)|洗钱(方法|教程|操作)"
)

REFUSAL_SELF_HARM = (
    "听到你正在经历这些，我很担心你。这不只是法律问题，请优先照顾自己的安全："
    "可拨打全国心理援助热线 12356（24 小时）。"
    "如果是人身安全或权益受损问题，建议尽快报警或联系专业律师，我也可以继续帮你分析具体的法律问题。"
)
REFUSAL_ILLEGAL = (
    "抱歉，我无法提供涉及违法犯罪行为的实施方法。"
    "如果你遇到的是相关法律问题（如被害维权、涉案辩护），欢迎换个角度描述，我会尽力从法律层面帮你分析。"
)


def check_input_guardrail(query: str) -> str | None:
    """输入护栏：命中返回拒绝话术（Pre Hook 短路用），放行返回 None"""
    if not query:
        return None
    if _SELF_HARM.search(query):
        return REFUSAL_SELF_HARM
    if _ILLEGAL.search(query):
        return REFUSAL_ILLEGAL
    return None


# ── Post Hook：输出护栏 ──

# 内部信息泄漏标记：chat 模板特殊 token、系统提示词标记、角色指令标记
_OUTPUT_LEAK = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|<\|User\|>|<\|Assistant\|>"
    r"|\[SYSTEM\]|system\s*prompt[:：]|###\s*Instruction[:：]",
    re.IGNORECASE,
)

OUTPUT_FALLBACK = "抱歉，本次回答未通过输出安全校验，已停止展示。请换个表述重新提问。"


def find_output_violation(text: str) -> str | None:
    """输出护栏：返回违规描述（供重试反馈），通过返回 None；空回复也算违规"""
    if not text or not text.strip():
        return "回答为空"
    if _OUTPUT_LEAK.search(text):
        return "回答疑似泄漏内部指令/模板标记"
    return None
