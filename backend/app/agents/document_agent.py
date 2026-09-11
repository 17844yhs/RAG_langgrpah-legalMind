"""
法律文书生成 Agent

生成起诉状、答辩状、合同等法律文书。
prompt 统一在 _build_chain 一处构造，generate / astream_generate 共用。
"""
from typing import Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.llm.model_client import get_llm
from app.llm.prompts import (
    DOCUMENT_TEMPLATES,
    DOCUMENT_SYSTEM_PROMPT,
    DOCUMENT_USER_PROMPT,
    DOCUMENT_TEMPLATE_INSTRUCTION,
    DOCUMENT_FALLBACK_INSTRUCTION,
)


class DocumentAgent:
    """法律文书生成 Agent"""

    DOCUMENT_TYPES = {
        "起诉状": "civil_complaint",
        "答辩状": "defense_statement",
        "合同": "contract",
        "律师函": "lawyer_letter",
        "上诉状": "appeal_statement",
    }

    def __init__(self):
        self.llm = get_llm()

    def _build_chain(self, document_type: str, params: Dict, query: str,
                     references: List[Dict] | None = None):
        """构造 prompt | llm 链。

        generate 与 astream_generate 共用此方法，prompt（system 文案 +
        _build_user_prompt）只在此一处维护，避免散落在多处。
        """
        template_key = self.DOCUMENT_TYPES.get(document_type, "civil_complaint")
        template = DOCUMENT_TEMPLATES.get(template_key, "")

        prompt = ChatPromptTemplate.from_messages([
            ("system", DOCUMENT_SYSTEM_PROMPT),
            ("human", self._build_user_prompt(document_type, params, query, references, template)),
        ])

        return prompt | self.llm

    async def generate(self, document_type: str, params: Dict, query: str,
                       references: List[Dict] | None = None) -> Dict:
        """非流式生成法律文书，返回完整文本。"""
        chain = self._build_chain(document_type, params, query, references) | StrOutputParser()
        content = await chain.ainvoke({})

        return {
            "content": content,
            "document_type": document_type,
            "references": references or [],
        }

    async def astream_generate(self, document_type: str, params: Dict, query: str,
                               references: List[Dict] | None = None):
        """流式生成法律文书：逐 chunk 产出 AIMessageChunk（打字机效果）。"""
        chain = self._build_chain(document_type, params, query, references)

        async for chunk in chain.astream({}):
            yield chunk

    def _build_user_prompt(self, document_type: str, params: Dict, query: str,
                           references: List[Dict] | None, template: str = "") -> str:
        """组装用户 Prompt：文案骨架在 prompts.py，参数块在此按需填充"""
        params_block = "".join(f"\n- {k}:{v}" for k, v in params.items())
        references_block = (
            f"\n\n参考案例：\n{self._format_references(references)}" if references else ""
        )
        if template:
            # 有模板骨架：让 LLM 严格照此结构填空，保证格式齐整
            template_block = "\n\n" + DOCUMENT_TEMPLATE_INSTRUCTION.format(template=template.strip())
        else:
            # 无模板：退回兜底句，避免未配模板的类型报错
            template_block = "\n\n" + DOCUMENT_FALLBACK_INSTRUCTION.format(document_type=document_type)

        return DOCUMENT_USER_PROMPT.format(
            document_type=document_type,
            query=query,
            params_block=params_block,
            references_block=references_block,
            template_block=template_block,
        )

    def _format_references(self, references: List[Dict]) -> str:
        """格式化参考案例"""
        if not references:
            return "暂无参考案例。"
        formatted = []
        for ref in references[:2]:
            formatted.append(
                f"- {ref.get('title', '未知')} ({ref.get('case_number', '未知')})"
            )
        return "\n".join(formatted)
