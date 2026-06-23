from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings

# 素人账号专项：伪素人暴露 / 商业化语气
PSEUDO_AMATEUR_RISKS = [
    ("我们平台", "素人身份暴露，建议删除"),
    ("欢迎入驻", "素人身份暴露，建议删除"),
    ("官方账号", "素人身份暴露，建议删除"),
    ("完美体验", "语气过于商业化，建议改为「体验还不错」"),
    ("专业服务", "语气过于商业化，建议改为「挺用心的」"),
    ("一站式解决", "语气过于商业化，建议删除"),
]

PRICE_PATTERN = re.compile(r"\d+\s*元")

GENERATION_COMPLIANCE_BLOCK = """写作时注意（内化执行，不要在回复中提及）：
- 规避引流、绝对化、虚假承诺、医疗功效等高风险表述
- 限流词改用自然说法（如入手、多少米、评论区见）
- 素人视角避免「我们平台」「官方」等商业化用语
- 输出即定稿，默认可直接发布；不要声明合规、检测或修正过程"""


class ContentChecker:
    """三层内容检测，规则来自 xhs-content-check skill。"""

    def __init__(self) -> None:
        self.words_path = Path(settings.forbidden_words_path)
        self.limit_words_path = Path(settings.forbidden_words_path).parent / "limit_words.json"
        self.skill_path = (
            Path(settings.forbidden_words_path).parents[1]
            / ".cursor"
            / "skills"
            / "xhs-content-check"
            / "SKILL.md"
        )
        self.forbidden_words: list[str] = []
        self.limit_words: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self.forbidden_words = self._load_forbidden_words()
        self.limit_words = self._load_limit_words()

    def _load_forbidden_words(self) -> list[str]:
        if not self.words_path.exists():
            return []
        words: list[str] = []
        for line in self.words_path.read_text(encoding="utf-8").splitlines():
            word = line.strip()
            if word and not word.startswith("#"):
                words.append(word)
        return sorted(set(words), key=len, reverse=True)

    def _load_limit_words(self) -> dict[str, str]:
        if not self.limit_words_path.exists():
            return {}
        return json.loads(self.limit_words_path.read_text(encoding="utf-8"))

    def _find_word(self, text: str, word: str) -> bool:
        if word.lower() in text.lower():
            return True
        pattern = ".*?".join(re.escape(ch) for ch in word)
        return bool(re.search(pattern, text, flags=re.IGNORECASE))

    def _layer1_check(self, text: str) -> list[dict]:
        hits = []
        for word in self.forbidden_words:
            if self._find_word(text, word):
                hits.append({
                    "word": word,
                    "layer": "forbidden",
                    "risk": "high",
                    "suggestion": "必须删除或彻底改写",
                })
        return hits

    def _layer2_check(self, text: str) -> list[dict]:
        hits = []
        for word, replacement in sorted(self.limit_words.items(), key=lambda x: len(x[0]), reverse=True):
            if self._find_word(text, word):
                hits.append({
                    "word": word,
                    "layer": "limit",
                    "risk": "medium",
                    "suggestion": replacement if replacement else "建议直接删除",
                    "replacement": replacement,
                })
        return hits

    def _layer3_check(self, text: str) -> list[dict]:
        hits = []
        for phrase, suggestion in PSEUDO_AMATEUR_RISKS:
            if phrase in text:
                hits.append({
                    "word": phrase,
                    "layer": "amateur",
                    "risk": "medium",
                    "suggestion": suggestion,
                })

        if PRICE_PATTERN.search(text):
            hits.append({
                "word": PRICE_PATTERN.search(text).group(),  # type: ignore
                "layer": "amateur",
                "risk": "medium",
                "suggestion": "具体金额改为「几十块」「很划算」",
            })

        if "扫码" in text and ("加我" in text or "微信" in text):
            hits.append({
                "word": "扫码+加我",
                "layer": "amateur",
                "risk": "high",
                "suggestion": "改为「评论区见」",
            })

        return hits

    def check(self, text: str) -> list[dict]:
        """兼容旧接口：返回所有命中词。"""
        report = self.check_report(text)
        return report["all_hits"]

    def check_report(self, text: str) -> dict:
        layer1 = self._layer1_check(text)
        layer2 = self._layer2_check(text)
        layer3 = self._layer3_check(text)

        all_hits = layer1 + layer2 + layer3
        total_issues = len(all_hits)

        if layer1 or any(h["risk"] == "high" for h in layer3):
            risk_level = "高危"
            compliance = "fail"
            publishable = False
        elif layer2 or layer3:
            risk_level = "需调整"
            compliance = "warning"
            publishable = False
        else:
            risk_level = "可发布"
            compliance = "pass"
            publishable = True

        fixed = self.auto_fix(text)

        return {
            "risk_level": risk_level,
            "compliance": compliance,
            "publishable": publishable,
            "issue_count": total_issues,
            "layer1_forbidden": layer1,
            "layer2_limit": layer2,
            "layer3_amateur": layer3,
            "all_hits": all_hits,
            "fixed_text": fixed if fixed != text else None,
        }

    def auto_fix(self, text: str) -> str:
        result = text
        for word, replacement in sorted(self.limit_words.items(), key=lambda x: len(x[0]), reverse=True):
            if replacement:
                result = re.sub(re.escape(word), replacement, result, flags=re.IGNORECASE)
            else:
                result = re.sub(re.escape(word), "", result, flags=re.IGNORECASE)
        for word in self.forbidden_words:
            if self._find_word(result, word):
                result = re.sub(re.escape(word), "【已删】", result, flags=re.IGNORECASE)
        return result.strip()

    def get_prompt_block(self) -> str:
        return GENERATION_COMPLIANCE_BLOCK

    def format_fix_issues(self, report: dict) -> str:
        lines = []
        for h in report.get("all_hits", []):
            rep = h.get("replacement") or h.get("suggestion", "删除或改写")
            lines.append(f"- 「{h['word']}」→ {rep}")
        return "\n".join(lines)

    def format_report_text(self, report: dict) -> str:
        lines = []

        if report["layer1_forbidden"]:
            lines.append("## 🔴 高危（必须修改）")
            for h in report["layer1_forbidden"]:
                lines.append(f"- 「{h['word']}」→ {h['suggestion']}")

        if report["layer2_limit"]:
            lines.append("\n## 🟡 中风险（建议修改）")
            for h in report["layer2_limit"]:
                rep = h.get("replacement") or "删除"
                lines.append(f"- 「{h['word']}」→ 建议替换为「{rep}」")

        if report["layer3_amateur"]:
            lines.append("\n## 🔵 素人账号专项")
            for h in report["layer3_amateur"]:
                lines.append(f"- 「{h['word']}」→ {h['suggestion']}")

        lines.append(f"\n## ✅ 总评\n- 风险等级：{report['risk_level']}\n- 需修改处：{report['issue_count']} 处")

        if report.get("fixed_text"):
            lines.append(f"\n## 📝 修改后版本\n{report['fixed_text']}")

        return "\n".join(lines)


forbidden_checker = ContentChecker()
