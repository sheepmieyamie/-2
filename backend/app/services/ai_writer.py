from __future__ import annotations

import re

from openai import APIConnectionError, APITimeoutError, APIStatusError, AsyncOpenAI

from app.config import settings
from app.services.forbidden_words import forbidden_checker


OUTPUT_STYLE_RULES = """输出格式要求（严格遵守）：
1. 用【区块名】划分结构；回复中禁止出现字符 # 和 *（【话题标签】区块内 #话题 除外）
2. 禁止 Markdown：不要写 ## 标题、不要写 **加粗**、不要写任何星号强调
3. 正文与方案直接呈现，像运营同事交付成品；不要写「收到」「已合规」「根据检测/报告」「修正了上一轮」等元话术
4. 不要在文末附合规说明、风险评级或检测结论；输出默认即可发布
5. 话题标签仅在【话题标签】区块使用 #话题 格式"""

SYSTEM_PROMPT_TEMPLATE = """你是一位专业的小红书运营文案策划师。

你的任务是根据对标账号的风格特征，为用户生成符合小红书平台调性的文案。

对标账号风格档案：
{style_profile}

当前产品 / 目标人群（优先围绕此创作）：
{product_context}

{strategy_context}

{reference_context}

文案生成规范：
1. 模仿对标账号/参考帖子的标题结构、语气、emoji 使用习惯和分段方式
2. 输出格式固定为：
   - 【标题】（15-25字，吸引眼球）
   - 【正文】（分段清晰，口语化，适当使用 emoji）
   - 【话题标签】（3-5个相关 #话题）
3. 内容真实可信，不做虚假承诺
4. 产品 & 目标人群见上方档案；用户每次输入的是「本篇帖子需求」，围绕该需求创作
5. 写作时内化合规要求，直接输出可发布成稿

{forbidden_words_block}

{output_style_rules}
"""

PSEUDO_ACCOUNT_RULES = """伪素人号特别规范：
- 语气像真实用户：口语化、有轻微不完美，避免「我们平台」「官方」「专业服务」等商业化表述
- 评论不要硬广、不要导流（微信/私信/二维码），用「姐妹」「真的吗」「蹲一个」等自然互动
- 素人配套帖如需发布，必须像路人自发分享，不能暴露矩阵关系
"""

ADVICE_OUTPUT_FORMAT = """【对标数据解读】
（2-4 条，引用数据：视频/图文表现、高赞共性）

【本篇定位与运营目标】
（结合第 N 篇所处阶段，本篇要达成什么）

【主帖文案】（可直接发布）
【标题】
【正文】
【话题标签】

【发布与节奏】
- 建议发布时间：
- 与上一条间隔：
- 发布后 1h / 24h 要做什么：

【评论区运营方案】
【互动策略】
（什么时候自己评、什么时候用素人号、如何引导讨论）

【主号回复话术】（2-3 条模板）
（用户常见提问时主号怎么回）

【伪素人评论】（写 4-6 条，可直接复制）
按角色区分，例如：
- 路人好奇型：
- 用过分享型：
- 提问互动型：
- 帮顶热度型：
（每条单独一行，语气各异，自然真实）

【素人配套号方案】
先判断：本篇是否需要素人配套号协同（写「需要」或「不需要」+ 一句理由）

若需要，继续输出：
【配套素人号发帖文案】
（1 篇完整文案，路人视角）
【配套号运营策略】
（何时发、间隔多久、评论区如何与主帖配合、注意别暴露矩阵）

若不需要，说明用什么方式替代（如仅靠评论区互动即可）

【避坑提醒】
（结合平台规则与伪素人暴露风险，直接给操作建议）

要求：方案具体可落地，评论和素人文案可直接复制使用，不要空泛套话。"""

ADVICE_PROMPT_TEMPLATE = """你是一位资深小红书全域运营顾问，擅长主号 + 评论区 + 素人矩阵协同打法。

根据对标账号真实数据，为用户即将发布的帖子输出完整可执行运营方案（不仅是文案）。

对标账号与发帖计划：
{strategy_context}

产品 / 目标人群：
{product_context}

{reference_context}

{forbidden_words_block}

{pseudo_rules}

{output_style_rules}

输出格式（严格遵守，缺一不可）：

{advice_output_format}
"""

CONSULT_PROMPT_TEMPLATE = """你是一位资深小红书运营顾问，正在与用户多轮对话，结合对标账号真实数据，逐步引导并完善本篇帖子的运营策略。

对标账号风格档案：
{style_profile}

对标账号与发帖计划：
{strategy_context}

产品 / 目标人群：
{product_context}

{reference_context}

{forbidden_words_block}

{output_style_rules}

你的工作方式（严格遵守）：
1. 每轮必须先引用已有对标数据：优先引用对标账号数据；若仅有参考帖子，则引用该帖标题、互动与正文特点；多个对标账号/参考帖时综合对比，说明异同与可借鉴点
2. 引导式提问：根据当前信息缺口，提出 1-3 个聚焦问题，优先确认：写什么主题、什么角度、核心卖点、目标人群；发帖第几篇为可选项，用户未提及时不要追问
3. 不要重复追问用户已经说清的内容；每轮结尾可简要归纳「目前已确认：…」
4. 策略共创：在用户回答后，给出基于对标数据的建议倾向（如「对标账号视频赞均值更高，本篇可考虑…」），邀请用户确认或调整
5. 语气：像运营同事聊天，专业但亲切，避免长篇说教

【何时输出完整方案】
- 用户明确说「出完整方案」「生成方案」「定稿」等 → 立即按下方「完整方案格式」输出，不再提问
- 用户未明确要求，但主题、角度、核心卖点已齐全 → 先问一句「信息差不多了，要不要我出完整执行方案？」；若用户确认或本轮消息含定稿意图，则输出完整方案
- 信息明显不足时 → 只引导提问，不要硬出完整方案

【引导阶段回复格式】（默认）
【对标洞察】
（1-2 条，带数据）

【策略建议】
（基于当前信息的初步方向，2-4 句）

【需要你补充】
（编号列出 1-3 个问题）

【已确认】
（列出对话中已明确的信息；首轮若无则写「暂无，等你补充」）

【完整方案格式】（仅在应出稿时使用，严格遵守）
{pseudo_rules}

{advice_output_format}
"""

FIX_USER_MESSAGE = (
    "上一版有几处用词需要换成更自然的说法。请直接输出完整新版内容，"
    "从正文第一句开始，不要解释修改过程，不要提及检测、报告、合规或修正。"
    "回复中禁止出现星号 * 和井号 #（【话题标签】区块内 #话题 除外）。\n\n"
    "需调整的用词：\n{issues}"
)

_META_PREAMBLE = re.compile(
    r"^收到[，,][^\n]*?(?:回到正题|继续推进|继续)[。.]?\s*",
    flags=re.MULTILINE,
)
_META_LINE_KEYWORDS = ("检测报告", "已合规", "修正了上一轮", "根据检测", "合规检测", "按以下报告")

_TRAILING_COMPLIANCE = re.compile(
    r"\n+(?:合规检查|风险等级|总评)[：:].*$", flags=re.DOTALL
)


def _strip_meta_opening(text: str) -> str:
    lines = text.split("\n")
    while lines:
        head = lines[0].strip()
        if not head:
            lines.pop(0)
            continue
        if (
            head.startswith("收到，")
            or (head.startswith("，") and "回到正题" in head)
            or "回到正题" in head
            or any(k in head for k in _META_LINE_KEYWORDS)
        ):
            lines.pop(0)
            continue
        break
    return "\n".join(lines)


def _strip_markdown_formatting(text: str) -> str:
    """彻底去除 Markdown 的 ** 与 ##，保留【话题标签】区块内的 #话题。"""
    in_topic_block = False
    lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("【话题标签】"):
            in_topic_block = True
            lines.append(line)
            continue
        if in_topic_block:
            if stripped.startswith("【") and stripped.endswith("】"):
                in_topic_block = False
            else:
                lines.append(line)
                continue

        header = re.match(r"^[ \t]*#{1,6}[ \t]+(.+)$", line)
        if header:
            title = header.group(1).strip()
            line = title if title.startswith("【") else f"【{title}】"
        else:
            header = re.match(r"^[ \t]*#{2,6}[ \t]*(.+)$", line)
            if header:
                title = header.group(1).strip()
                line = title if title.startswith("【") else f"【{title}】"

        line = line.replace("**", "").replace("__", "")
        line = re.sub(r"#{2,}", "", line)
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"#{2,}", "", cleaned)
    return cleaned


def _sanitize_output(text: str) -> str:
    if not text:
        return text
    cleaned = text.strip()
    cleaned = _META_PREAMBLE.sub("", cleaned)
    cleaned = _strip_meta_opening(cleaned)
    cleaned = _TRAILING_COMPLIANCE.sub("", cleaned)
    cleaned = _strip_markdown_formatting(cleaned)
    return cleaned.strip()


def sanitize_output(text: str) -> str:
    return _sanitize_output(text)


def _normalize_effort(effort: str) -> str:
    mapping = {"xhigh": "high", "x-high": "high", "minimal": "low"}
    value = mapping.get(effort.lower(), effort.lower())
    return value if value in ("low", "medium", "high") else "high"


def _extract_response_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for block in getattr(item, "content", []) or []:
                if getattr(block, "type", None) == "output_text":
                    parts.append(block.text)
    return "\n".join(parts)


class AIWriter:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=120.0,
            max_retries=1,
        )
        self.model = settings.openai_model
        self.wire_api = settings.openai_wire_api
        self.reasoning_effort = _normalize_effort(settings.openai_reasoning_effort)

    def _build_system_prompt(
        self,
        style_profile: str,
        product_context: str = "",
        strategy_context: str = "",
        reference_context: str = "",
    ) -> str:
        strategy_block = f"本篇发帖计划：\n{strategy_context}" if strategy_context else ""
        return SYSTEM_PROMPT_TEMPLATE.format(
            style_profile=style_profile or "（未选择对标账号）",
            product_context=product_context or "（未选择产品档案，根据用户当次输入理解）",
            strategy_context=strategy_block,
            reference_context=reference_context or "",
            forbidden_words_block=forbidden_checker.get_prompt_block(),
            output_style_rules=OUTPUT_STYLE_RULES,
        )

    def _fix_messages(
        self,
        messages: list[dict[str, str]],
        content: str,
        report: dict,
    ) -> list[dict[str, str]]:
        issues = forbidden_checker.format_fix_issues(report)
        return messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": FIX_USER_MESSAGE.format(issues=issues)},
        ]

    def _finalize(self, content: str) -> str:
        return _sanitize_output(content)

    def _to_response_input(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    async def _call(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> str:
        try:
            if self.wire_api == "responses":
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=system,
                    input=self._to_response_input(messages),
                    reasoning={"effort": self.reasoning_effort},
                    max_output_tokens=max_tokens,
                )
                return sanitize_output(_extract_response_text(response))

            api_messages = [{"role": "system", "content": system}, *messages]
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return sanitize_output(response.choices[0].message.content or "")
        except APITimeoutError as exc:
            raise ValueError("AI 接口响应超时，请稍后重试") from exc
        except APIConnectionError as exc:
            raise ValueError("无法连接 AI 服务，请检查 API 地址与网络") from exc
        except APIStatusError as exc:
            detail = getattr(exc, "message", None) or str(exc)
            raise ValueError(f"AI 接口错误：{detail}") from exc

    async def generate(
        self,
        messages: list[dict[str, str]],
        style_profile: str = "",
        product_context: str = "",
        strategy_context: str = "",
        reference_context: str = "",
    ) -> str:
        if not settings.openai_api_key:
            raise ValueError("未配置 OPENAI_API_KEY，请在 backend/.env 中设置")

        system = self._build_system_prompt(
            style_profile, product_context, strategy_context, reference_context
        )
        content = await self._call(system, messages)

        report = forbidden_checker.check_report(content)
        if report["issue_count"] > 0:
            fix_messages = self._fix_messages(messages, content, report)
            content = await self._call(system, fix_messages)

        return self._finalize(content)

    async def generate_advice(
        self,
        strategy_context: str,
        product_context: str = "",
        extra_requirement: str = "",
    ) -> str:
        if not settings.openai_api_key:
            raise ValueError("未配置 OPENAI_API_KEY，请在 backend/.env 中设置")

        system = ADVICE_PROMPT_TEMPLATE.format(
            strategy_context=strategy_context,
            product_context=product_context or "（未选择产品档案）",
            forbidden_words_block=forbidden_checker.get_prompt_block(),
            pseudo_rules=PSEUDO_ACCOUNT_RULES,
            advice_output_format=ADVICE_OUTPUT_FORMAT,
            output_style_rules=OUTPUT_STYLE_RULES,
        )
        user_msg = extra_requirement.strip() or (
            "请输出本篇帖子的完整运营方案，包含主帖文案、评论区互动、"
            "伪素人评论示例，并自行判断是否需要素人配套号及配套策略。"
        )
        content = await self._call(
            system,
            [{"role": "user", "content": user_msg}],
            temperature=0.75,
            max_tokens=6000,
        )

        report = forbidden_checker.check_report(content)
        if report["issue_count"] > 0:
            issues = forbidden_checker.format_fix_issues(report)
            content = await self._call(
                system,
                [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": FIX_USER_MESSAGE.format(issues=issues)},
                ],
                temperature=0.5,
                max_tokens=6000,
            )
        return self._finalize(content)

    async def generate_plan_consult(
        self,
        messages: list[dict[str, str]],
        style_profile: str = "",
        strategy_context: str = "",
        product_context: str = "",
        reference_context: str = "",
        *,
        finalize: bool = False,
    ) -> str:
        if not settings.openai_api_key:
            raise ValueError("未配置 OPENAI_API_KEY，请在 backend/.env 中设置")

        system = CONSULT_PROMPT_TEMPLATE.format(
            style_profile=style_profile or "（未选择对标账号）",
            strategy_context=strategy_context or "（未选择对标账号，暂无账号级数据）",
            product_context=product_context or "（未选择产品档案，根据对话理解）",
            reference_context=reference_context or "",
            forbidden_words_block=forbidden_checker.get_prompt_block(),
            pseudo_rules=PSEUDO_ACCOUNT_RULES,
            advice_output_format=ADVICE_OUTPUT_FORMAT,
            output_style_rules=OUTPUT_STYLE_RULES,
        )
        if finalize:
            system += (
                "\n\n【本轮指令】用户已要求输出完整方案，请立即按「完整方案格式」输出，"
                "不要再提问。"
            )

        content = await self._call(
            system,
            messages,
            temperature=0.75 if finalize else 0.8,
            max_tokens=6000 if finalize else 4096,
        )

        report = forbidden_checker.check_report(content)
        if report["issue_count"] > 0:
            fix_messages = self._fix_messages(messages, content, report)
            content = await self._call(
                system,
                fix_messages,
                temperature=0.5,
                max_tokens=6000 if finalize else 4096,
            )
        return self._finalize(content)


ai_writer = AIWriter()
