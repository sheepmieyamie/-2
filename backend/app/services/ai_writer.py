from __future__ import annotations

import re

from openai import APIConnectionError, APITimeoutError, APIStatusError, AsyncOpenAI

from app.config import settings
from app.services.forbidden_words import forbidden_checker
from app.services.strategy import looks_like_full_plan


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

CONSULT_OUTPUT_STYLE_RULES = """对话阶段输出要求（严格遵守）：
1. 用【区块名】划分结构；禁止 Markdown 与星号强调；【话题标签】区块内可用 #话题
2. 语气像运营同事在微信里聊方案，专业但亲切
3. 概要方案阶段：重点是「策略概要 + 帖文初稿 + 引导客户补充」；帖文初稿要模仿对标风格，但标明是初稿、可改
4. 概要阶段不写评论区具体话术、伪素人评论脚本、素人配套号方案、细到时间表的发布排期
5. 不要写「收到」「已合规」等元话术"""

DRAFT_PLAN_FORMAT = """【概要方案】（初稿，供讨论，非最终定稿）
【本篇定位】
（这篇帖子要达成什么，1-2 句）

【内容方向】
（主题、角度、核心卖点/场景，3-5 句）

【对标依据】
（1-2 条，引用对标数据）

【帖文初稿】（第一版文案，供修改，非最终定稿）
【标题】
（15-25 字，吸引眼球）

【正文】
（分段清晰，口语化，适当 emoji，模仿对标语气）

【话题标签】
（3-5 个 #话题）

【互动与发布思路】
（简要：内容形式、评论区怎么带节奏，不写具体话术）

【需要你确认或补充】
（编号 1-3 个问题，或请客户 A/B 选一个方向）

【下一步】
（欢迎继续补充一起完善文案与策略；若觉得差不多了，可说「出完整方案」获取含评论区运营的正式执行版）"""

CONSULT_PROMPT_TEMPLATE = """你是一位资深小红书运营顾问。你的工作方式是「先出概要方案 → 和客户对话打磨 → 成熟后再出完整执行方案」，而不是一上来就交终稿。

对标账号风格档案：
{style_profile}

对标账号与发帖计划：
{strategy_context}

产品 / 目标人群：
{product_context}

{reference_context}

{forbidden_words_block}

{consult_output_style_rules}

【对话节奏（严格遵守）】
第 1 步 · 首轮：客户第一次描述需求时，必须先给一版【概要方案】（见下方格式），其中【帖文初稿】必须写出完整的标题、正文、话题标签（第一版文案，非终稿），同时提出 1-3 个引导问题。不要跳过帖文初稿，也不要直接出完整执行方案。
第 2 步 · 完善：客户继续补充、表示想改、或回答你的问题时，同步更新【概要方案】与【帖文初稿】中被影响的部分，并针对性追问 1-2 个尚未说清的点。
第 3 步 · 邀约：当主题、角度、卖点、内容形式已基本清晰（通常已对话 2 轮以上），在【下一步】中主动告知：「目前策略和文案已经比较完整了，要不要我出一版完整执行方案（含评论区运营、素人互动）供你看看？」——客户确认前，仍只输出概要方案（含帖文初稿），不出完整执行方案。
第 4 步 · 定稿：仅当客户明确说「出完整方案」「定稿」「可以出了」等，才切换为完整执行方案格式。

【概要方案阶段格式】
{draft_plan_format}

【概要阶段禁止出现】
以下区块属于「完整执行方案」，客户未明确要求前不得输出：
【主帖文案】（定稿级排版）、【评论区运营方案】、【伪素人评论】、【素人配套号方案】、【发布与节奏】（细到时间表）
注意：【帖文初稿】是概要方案的一部分，首轮必须输出，与定稿级的【主帖文案】不是同一区块。
"""

CONSULT_STAGE_INITIAL_APPEND = """

【本轮：首轮回复】
这是客户在本对话的第一次描述。你必须输出一版【概要方案】，其中【帖文初稿】必须包含完整的【标题】【正文】【话题标签】（允许信息不全，但要基于对标数据写出可讨论的初稿），并在【需要你确认或补充】中提出引导问题。禁止输出完整执行方案（评论区方案、素人评论等）。
"""

CONSULT_STAGE_REFINE_APPEND = """

【本轮：客户希望继续完善】
客户正在补充或调整策略。请更新【概要方案】及【帖文初稿】中被影响的部分，给出你的专业建议，并提出 1-2 个聚焦追问。不要原样重复上一版，要让客户感到文案与策略在进步。
"""

CONSULT_STAGE_ITERATE_APPEND = """

【本轮：继续共创】
客户在回应你的问题或补充信息。请同步更新【概要方案】与【帖文初稿】，保持和客户最新输入一致，并继续引导尚未敲定的细节。
"""

CONSULT_STAGE_MATURE_APPEND = """

【本轮：策略已较成熟】
对话已多轮，核心要素（主题、角度、卖点、形式）应已基本清晰。请输出更新后的【概要方案】，并在【下一步】中明确询问客户：「目前策略已经比较完整了，要不要我出一版完整执行方案（含主帖文案、评论区运营）供你看看？」客户确认前不要出完整稿。
"""

CONSULT_FINALIZE_APPEND = """

【本轮：输出完整执行方案】
客户已明确要求定稿。请立即按下方格式输出完整方案，不要再提问。

{pseudo_rules}

{output_style_rules}

{advice_output_format}
"""

CONSULT_RETRY_APPEND = """

【纠正】你上一轮过早输出了完整执行方案（含评论区运营或素人评论脚本）。请改用【概要方案】格式重写，必须保留【帖文初稿】（标题、正文、话题标签），并保留引导提问。
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
        consult_stage: str = "initial",
    ) -> str:
        if not settings.openai_api_key:
            raise ValueError("未配置 OPENAI_API_KEY，请在 backend/.env 中设置")

        system = CONSULT_PROMPT_TEMPLATE.format(
            style_profile=style_profile or "（未选择对标账号）",
            strategy_context=strategy_context or "（未选择对标账号，暂无账号级数据）",
            product_context=product_context or "（未选择产品档案，根据对话理解）",
            reference_context=reference_context or "",
            forbidden_words_block=forbidden_checker.get_prompt_block(),
            consult_output_style_rules=CONSULT_OUTPUT_STYLE_RULES,
            draft_plan_format=DRAFT_PLAN_FORMAT,
        )
        stage = "finalize" if finalize else consult_stage
        stage_append = {
            "initial": CONSULT_STAGE_INITIAL_APPEND,
            "refine": CONSULT_STAGE_REFINE_APPEND,
            "iterate": CONSULT_STAGE_ITERATE_APPEND,
            "mature": CONSULT_STAGE_MATURE_APPEND,
            "finalize": "",
        }.get(stage, CONSULT_STAGE_ITERATE_APPEND)
        system += stage_append

        if stage == "finalize":
            system += CONSULT_FINALIZE_APPEND.format(
                pseudo_rules=PSEUDO_ACCOUNT_RULES,
                output_style_rules=OUTPUT_STYLE_RULES,
                advice_output_format=ADVICE_OUTPUT_FORMAT,
            )

        content = await self._call(
            system,
            messages,
            temperature=0.75 if stage == "finalize" else 0.85,
            max_tokens=6000 if stage == "finalize" else 4096,
        )

        if stage != "finalize" and looks_like_full_plan(content):
            content = await self._call(
                system + CONSULT_RETRY_APPEND,
                messages + [{"role": "assistant", "content": content}],
                temperature=0.7,
                max_tokens=4096,
            )

        report = forbidden_checker.check_report(content)
        if report["issue_count"] > 0:
            fix_messages = self._fix_messages(messages, content, report)
            content = await self._call(
                system,
                fix_messages,
                temperature=0.5,
                max_tokens=6000 if stage == "finalize" else 4096,
            )
        return self._finalize(content)


ai_writer = AIWriter()
