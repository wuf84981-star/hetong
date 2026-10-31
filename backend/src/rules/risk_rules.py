"""风险规则数据（单一事实来源，无重依赖）。

抽出为纯数据模块的原因：
- 风险识别 Agent 与 eval 评测脚本共用同一套规则，避免两处维护漂移；
- 本模块不导入 langgraph/langchain/pydantic，因此 eval 可在不装重依赖的环境跑「规则模式」。

risk_level 用字符串（"high"/"medium"/"low"），Agent 侧再映射为 RiskLevel 枚举。
keywords 支持正则（含正则元字符时按正则匹配），由 rules.keyword_matcher 统一处理。
"""

from __future__ import annotations

RISK_RULE_DEFS: list[dict] = [
    {
        "name": "unlimited_liability",
        "keywords": ["无限责任", "不限于", "承担全部", "无上限", "不设限", "承担.*全部.*责任"],
        "risk_level": "high",
        "description": "条款包含无限责任相关表述",
    },
    {
        "name": "unilateral_termination",
        "keywords": ["单方解除", "单方终止", "有权随时", "任意解除"],
        "risk_level": "high",
        "description": "条款包含单方解除权",
    },
    {
        "name": "unfair_penalty",
        "keywords": ["违约金不低于", "双倍赔偿", "三倍赔偿", "全额赔偿"],
        "risk_level": "medium",
        "description": "违约金条款可能不合理",
    },
    {
        "name": "auto_renewal",
        "keywords": ["自动续约", "自动续期", "默认续签"],
        "risk_level": "medium",
        "description": "包含自动续约条款",
    },
    {
        "name": "vague_terms",
        "keywords": ["酌情处理", "另行协商", "视情况而定", "合理范围"],
        "risk_level": "low",
        "description": "条款表述模糊，存在歧义风险",
    },
    {
        "name": "exclusive_jurisdiction",
        "keywords": ["仅由.*法院管辖", "排他性管辖", "只能向.*提起"],
        "risk_level": "medium",
        "description": "管辖权条款可能对一方不利",
    },
]
