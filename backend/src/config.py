"""
应用配置 — 通过环境变量加载，绝不硬编码密钥。

LLM 提供商通过 LLM_PROVIDER 选择：auto | contract | minimax | openai
- auto: 按 contract → minimax → openai 顺序取第一个有效 key
- contract: 通用 OpenAI 兼容端点（通义千问、DeepSeek、智谱、本地 vLLM 等）
- minimax: MiniMax 官方
- openai: OpenAI 官方
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    return val if val not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    return int(val) if val not in (None, "") else default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    return float(val) if val not in (None, "") else default


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val in (None, ""):
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _is_real_key(key: str) -> bool:
    """API key 非空且不是 'your_xxx_here' 等占位符。"""
    return bool(key) and not key.startswith("your_")


class Settings:
    def __init__(self) -> None:
        # ── LLM 提供商选择 ──────────────────────────────────
        self.LLM_PROVIDER: str = _env("LLM_PROVIDER", "auto").lower()

        # contract: 通用 OpenAI 兼容端点（千问、DeepSeek、智谱…）
        self.CONTRACT_LLM_API_KEY: str = _env("CONTRACT_LLM_API_KEY", "")
        self.CONTRACT_LLM_BASE_URL: str = _env(
            "CONTRACT_LLM_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.CONTRACT_LLM_MODEL: str = _env("CONTRACT_LLM_MODEL", "qwen-max")

        # MiniMax
        self.MINIMAX_API_KEY: str = _env("MINIMAX_API_KEY", "")
        self.MINIMAX_API_BASE: str = _env("MINIMAX_API_BASE", "https://api.minimax.chat/v1")
        self.MINIMAX_MODEL: str = _env("MINIMAX_MODEL", "MiniMax-M2.7")

        # OpenAI 官方
        self.OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
        self.OPENAI_API_BASE: str = _env("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-4o-mini")

        # LLM-as-judge 评估器用的模型（默认与生产 LLM 区分以避免「自评偏差」）
        self.LLM_JUDGE_MODEL: str = _env("LLM_JUDGE_MODEL", "gpt-4o-mini")

        # 向后兼容：旧 LLM_MODEL 若设置则覆盖所有 provider 的默认 model
        legacy_model = _env("LLM_MODEL", "")
        if legacy_model:
            if not _env("MINIMAX_MODEL", ""):
                self.MINIMAX_MODEL = legacy_model
            if not _env("OPENAI_MODEL", ""):
                self.OPENAI_MODEL = legacy_model
            if not _env("CONTRACT_LLM_MODEL", ""):
                self.CONTRACT_LLM_MODEL = legacy_model

        # ── LLM 调用参数 ────────────────────────────────────
        self.LLM_TIMEOUT: int = _env_int("LLM_TIMEOUT", 60)
        self.LLM_MAX_RETRIES: int = _env_int("LLM_MAX_RETRIES", 2)
        self.LLM_TEMPERATURE: float = _env_float("LLM_TEMPERATURE", 0.1)
        self.LLM_MAX_TOKENS: int = _env_int("LLM_MAX_TOKENS", 4096)
        # 长文分块：单块最大字符数（超长合同按章节分块提取后合并，避免截断丢条款）
        self.LLM_CHUNK_CHARS: int = _env_int("LLM_CHUNK_CHARS", 12000)
        # 内容层「修复重试」：LLM 输出 JSON 不合法/不符 schema 时的自我纠正重试次数
        self.LLM_REPAIR_RETRIES: int = _env_int("LLM_REPAIR_RETRIES", 1)
        # 是否请求 OpenAI 兼容端点的 JSON mode（qwen/openai 支持；不支持的端点请关闭）
        self.LLM_JSON_MODE: bool = _env_bool("LLM_JSON_MODE", False)
        self.CIRCUIT_BREAKER_THRESHOLD: int = _env_int("CIRCUIT_BREAKER_THRESHOLD", 3)
        self.CIRCUIT_RECOVERY_TIMEOUT: int = _env_int("CIRCUIT_RECOVERY_TIMEOUT", 60)

        # ── 应用基础配置 ────────────────────────────────────
        self.APP_HOST: str = _env("APP_HOST", "0.0.0.0")
        self.APP_PORT: int = _env_int("APP_PORT", 8000)
        self.LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
        self.LOG_FORMAT: str = _env("LOG_FORMAT", "text")

        # ── 向量数据库（Milvus standalone 服务：docker compose --profile milvus up -d）──
        self.MILVUS_URI: str = _env("MILVUS_URI", "http://localhost:19530")
        self.MILVUS_TOKEN: str = _env("MILVUS_TOKEN", "")  # user:password 或云服务 API-Key；自建默认为空
        self.MILVUS_COLLECTION: str = _env("MILVUS_COLLECTION", "regulations")
        self.EMBEDDING_MODEL: str = _env("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")
        # 嵌入来源：local=sentence-transformers 本地推理（文本不出机）；api=OpenAI 兼容 /embeddings（默认硅基流动）
        self.EMBEDDING_SOURCE: str = _env("EMBEDDING_SOURCE", "local").lower()
        self.SILICONFLOW_API_KEY: str = _env("SILICONFLOW_API_KEY", "")
        self.EMBEDDING_BASE_URL: str = _env("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")

        # ── 数据库 ──────────────────────────────────────────
        self.DATABASE_URL: str = _env(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5433/contract_review",
        )
        # 启动时若 users 表为空则加载 data/seed.sql（Docker 本地开发使用）
        self.SEED_ON_STARTUP: bool = _env_bool("SEED_ON_STARTUP", False)
        self.DATABASE_URL_SYNC: str = _env(
            "DATABASE_URL_SYNC",
            "postgresql://postgres:postgres@localhost:5433/contract_review",
        )
        self.DB_POOL_SIZE: int = _env_int("DB_POOL_SIZE", 10)
        self.DB_MAX_OVERFLOW: int = _env_int("DB_MAX_OVERFLOW", 20)

        # ── JWT 认证 ────────────────────────────────────────
        self.JWT_DEFAULT_SECRET = "dev-secret-change-in-production"
        self.JWT_SECRET_KEY: str = _env("JWT_SECRET_KEY", self.JWT_DEFAULT_SECRET)
        self.JWT_ALGORITHM: str = _env("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_MINUTES: int = _env_int("JWT_EXPIRE_MINUTES", 60)

        # 鉴权总开关：默认开启。仅当显式设置 AUTH_DISABLED=true 时关闭（本地纯前端联调）。
        # 注意：不再用「密钥等于默认值」来隐式关闭鉴权——那是一个安全后门。
        self.AUTH_DISABLED: bool = _env_bool("AUTH_DISABLED", False)
        # 是否允许无数据库时用内置 admin/admin123 登录（默认关闭，仅本地开发可开）
        self.DEV_MEMORY_LOGIN: bool = _env_bool("DEV_MEMORY_LOGIN", False)

        # ── 邮件（注册验证码 SMTP）──────────────────────────
        # 未配置完整（HOST/USER/PASSWORD 缺任一）时注册发码端点返回 503，其余功能不受影响。
        # QQ 邮箱示例：SMTP_HOST=smtp.qq.com SMTP_PORT=465，PASSWORD 填"授权码"而非登录密码
        self.SMTP_HOST: str = _env("SMTP_HOST", "")
        self.SMTP_PORT: int = _env_int("SMTP_PORT", 465)
        self.SMTP_USER: str = _env("SMTP_USER", "")
        self.SMTP_PASSWORD: str = _env("SMTP_PASSWORD", "")
        # 发件人地址，留空则等同 SMTP_USER（部分服务商要求二者一致）
        self.SMTP_FROM: str = _env("SMTP_FROM", "")

        # ── 异步任务后端 ────────────────────────────────────
        # inprocess: asyncio.create_task（单进程，重启即丢，仅开发/单机）
        # celery: 走 Celery + Redis，任务持久、可重试、可续跑（生产推荐）
        self.TASK_BACKEND: str = _env("TASK_BACKEND", "inprocess").lower()

        # ── LangGraph checkpoint 后端（人机协同 interrupt/resume）──
        # redis: 跨进程/多副本持久（生产推荐）；sqlite: 单机持久；memory: 仅单进程（开发）
        self.CHECKPOINT_BACKEND: str = _env("CHECKPOINT_BACKEND", "memory").lower()
        self.REDIS_URL: str = _env("REDIS_URL", "redis://localhost:6379/2")
        self.CHECKPOINT_SQLITE_PATH: str = _env(
            "CHECKPOINT_SQLITE_PATH",
            str(Path(__file__).parent.parent / "data" / "checkpoints.sqlite"),
        )

        # ── RAG 检索增强 ────────────────────────────────────
        # 开启后主流水线会加载 Milvus 向量索引为 Agent 注入相似历史条款上下文
        self.RAG_ENABLED: bool = _env_bool("RAG_ENABLED", False)

        # ── 知识库（法规条例向量入库）──────────────────────
        _data_root = Path(__file__).parent.parent / "data"
        self.KNOWLEDGE_DIR: Path = _data_root / "knowledge_docs"  # 上传原件副本
        self.KNOWLEDGE_REGISTRY_PATH: Path = _data_root / "knowledge_docs.json"  # 文档注册表
        self.KNOWLEDGE_MAX_CHUNKS_PER_DOC: int = _env_int("KNOWLEDGE_MAX_CHUNKS_PER_DOC", 400)

        # ── Celery / Redis ─────────────────────────────────
        self.CELERY_BROKER_URL: str = _env("CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.CELERY_RESULT_BACKEND: str = _env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
        self.CELERY_TASK_TIME_LIMIT: int = _env_int("CELERY_TASK_TIME_LIMIT", 300)
        self.CELERY_TASK_SOFT_TIME_LIMIT: int = _env_int("CELERY_TASK_SOFT_TIME_LIMIT", 240)

        # ── 安全 ────────────────────────────────────────────
        self.CORS_ORIGINS: str = _env("CORS_ORIGINS", "*")
        self.RATE_LIMIT_PER_MINUTE: int = _env_int("RATE_LIMIT_PER_MINUTE", 60)
        self.MAX_UPLOAD_SIZE_MB: int = _env_int("MAX_UPLOAD_SIZE_MB", 20)

        # ── OpenTelemetry ──────────────────────────────────
        self.OTEL_ENABLED: bool = _env_bool("OTEL_ENABLED", False)
        self.OTEL_SERVICE_NAME: str = _env("OTEL_SERVICE_NAME", "fencun-contract")
        self.OTEL_EXPORTER_OTLP_ENDPOINT: str = _env(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )

        # ── 路径常量 ────────────────────────────────────────
        self.PROJECT_ROOT: Path = Path(__file__).parent.parent
        self.RULES_DIR: Path = self.PROJECT_ROOT / "src" / "rules" / "definitions"

    # ── 安全相关派生属性 ────────────────────────────────────

    @property
    def auth_enabled(self) -> bool:
        """是否启用鉴权。默认启用；仅当显式 AUTH_DISABLED=true 时关闭。"""
        return not self.AUTH_DISABLED

    @property
    def using_default_jwt_secret(self) -> bool:
        return self.JWT_SECRET_KEY == self.JWT_DEFAULT_SECRET

    def validate_security(self) -> list[str]:
        """返回启动时的安全问题列表（空列表表示通过）。

        生产环境（AUTH 开启）下若仍使用默认 JWT 密钥，视为致命错误。
        """
        problems: list[str] = []
        if self.auth_enabled and self.using_default_jwt_secret:
            problems.append(
                "JWT_SECRET_KEY 仍为默认值。请设置一个至少 32 字符的随机密钥："
                "python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if self.auth_enabled and len(self.JWT_SECRET_KEY) < 32:
            problems.append("JWT_SECRET_KEY 长度不足 32 字符，签名强度不够。")
        return problems


settings = Settings()


# ── LLM 客户端工厂 ──────────────────────────────────────────


_PROVIDER_SPECS = (
    ("contract", "CONTRACT_LLM_API_KEY", "CONTRACT_LLM_BASE_URL", "CONTRACT_LLM_MODEL"),
    ("minimax", "MINIMAX_API_KEY", "MINIMAX_API_BASE", "MINIMAX_MODEL"),
    ("openai", "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL"),
)


def get_llm(settings_obj: Settings | None = None):
    """根据 LLM_PROVIDER 构造 ChatOpenAI 客户端。

    - auto: 按 contract → minimax → openai 顺序选第一个有效 key
    - 指定 provider: 若该 provider 无有效 key 则抛出 ValueError
    所有 provider 都走 OpenAI 兼容接口（ChatOpenAI）。
    """
    from langchain_openai import ChatOpenAI

    s = settings_obj or settings
    provider = s.LLM_PROVIDER

    if provider == "auto":
        candidates = _PROVIDER_SPECS
    else:
        candidates = [c for c in _PROVIDER_SPECS if c[0] == provider]
        if not candidates:
            raise ValueError(
                f"未知的 LLM_PROVIDER='{provider}'，"
                "可选值：auto | contract | minimax | openai"
            )

    for name, key_attr, base_attr, model_attr in candidates:
        api_key = getattr(s, key_attr)
        if _is_real_key(api_key):
            model = getattr(s, model_attr)
            extra = {}
            if s.LLM_JSON_MODE:
                # 让兼容端点强制返回 JSON 对象（qwen/openai 支持）
                extra["model_kwargs"] = {"response_format": {"type": "json_object"}}
            if model.lower().startswith("qwen3"):
                # DashScope 的 Qwen3 系非流式调用默认走思考模式：答案全部落在
                # reasoning_content 里、content 返回空，会被误判为「LLM 返回为空」
                # 连败至熔断。显式关闭思考恢复常规应答通道（兼容模式官方参数）。
                extra.setdefault("extra_body", {})["enable_thinking"] = False
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=getattr(s, base_attr),
                temperature=s.LLM_TEMPERATURE,
                max_tokens=s.LLM_MAX_TOKENS,
                **extra,
            )
        if provider != "auto":
            raise ValueError(
                f"LLM_PROVIDER='{name}' 但未配置有效 {key_attr}（空或占位符）"
            )

    raise ValueError(
        "未配置任何有效 LLM API Key。请在 .env 中设置 "
        "CONTRACT_LLM_API_KEY / MINIMAX_API_KEY / OPENAI_API_KEY 之一，"
        "或设置 LLM_PROVIDER=contract|minimax|openai 明确选择。"
    )
