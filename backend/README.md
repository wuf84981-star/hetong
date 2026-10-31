# 分寸合同 · Python 后端

基于 LangGraph 的多 Agent 智能合同审查系统后端：FastAPI + Pydantic v2 + SQLAlchemy 2 (async)，规则引擎与大模型双引擎判定，interrupt/resume 人工把关闭环，RAG 法规知识库（Milvus 向量检索）。

产品全景与部署入口见 [上级 README](../README.md)。

## 技术栈

- **LangGraph** — Agent 有向图编排，checkpointer 支持 memory / sqlite / redis
- **FastAPI + Pydantic v2** — 异步 Web 框架与强类型 schema（LLM 输出治理的地基）
- **多 LLM 提供商** — OpenAI 兼容接口统一接入：通义千问 / DeepSeek / 智谱 / MiniMax / OpenAI / 本地 vLLM，`LLM_PROVIDER=auto` 自动择优
- **RAG** — 嵌入本地 sentence-transformers 或远程 /embeddings；向量库 Milvus standalone（pymilvus 直连，compose profile 一键起）
- **持久化** — PostgreSQL (SQLAlchemy async) 或纯内存双模式；启动自动执行 migrations

## 项目结构

```
backend/
├── src/
│   ├── agents/                    # 四个 Agent（条款拆解/风险识别/合规检查/修订建议）
│   │   ├── clause_extraction.py   # Agent 1: 解析 + 分块 + LLM 结构化提取，失败回退规则切分
│   │   ├── risk_identification.py # Agent 2: 规则预筛 ∥ LLM 语义，双引擎就严合并、分歧标注
│   │   ├── compliance_check.py    # Agent 3: 合规规则 + 必备条款清单核查 + LLM 分析
│   │   ├── suggestion.py          # Agent 4: 高/中风险条款改稿 + difflib 对照
│   │   ├── structured.py          # 结构化调用：校验失败把错误喂回模型自我纠正（重试 1 次）
│   │   ├── prompt_guard.py        # 不可信内容 <untrusted_content> 源-汇隔离
│   │   └── rag_utils.py           # 检索参考记账（透出前 2 条、snippet 200 字）
│   ├── pipeline/
│   │   ├── graph.py               # LangGraph 编排 + 并行分析节点 + 分步进度回调
│   │   ├── state.py               # ContractReviewState（含 current_step / step_log / progress）
│   │   └── checkpointer.py        # 断点续跑三后端工厂
│   ├── api/
│   │   ├── main.py                # 入口（lifespan：迁移 + 种子 + 索引重建钩子）
│   │   ├── routers/               # 12 个路由模块 / 52 端点（auth review rules templates
│   │   │                          #   regulations knowledge diff negotiation bad_cases
│   │   │                          #   diagnostics metrics health）
│   │   ├── schemas/               # Pydantic 请求/响应模型
│   │   ├── auth/                  # JWT + RBAC 三角色（require_role 依赖工厂）
│   │   ├── middleware.py          # 中间件
│   │   ├── rate_limit.py          # 60 次/分钟/IP 滑动窗口
│   │   ├── upload_guard.py        # 白名单 + 魔数 + 20MB
│   │   └── exceptions.py          # 统一异常处理
│   ├── services/                  # review_service / knowledge_service / storage /
│   │                              #   report(Word/PDF/红线) / bad case / LLM Judge /
│   │                              #   mail_service(SMTP) / verification_service(验证码)
│   ├── db/                        # SQLAlchemy async 模型 + CRUD
│   ├── rules/                     # 规则引擎 + definitions/*.yaml（热加载）
│   ├── nlp/legal_nlp.py           # 法律 NLP 工具
│   ├── parsers/document_parser.py # PDF/DOCX/TXT 解析
│   ├── vector/
│   │   ├── milvus_store.py        # Milvus 向量库（软删标记 + 行内模型名防线 + replace_all 整库重建 + 状态探针）
│   │   ├── rag.py                 # 检索器：过采 top_k×3 → 过滤软删 → 截 top_k
│   │   └── embeddings.py          # 嵌入工厂：local（sentence-transformers）/ api（OpenAI 兼容）
│   ├── worker/                    # Celery 异步任务（TASK_BACKEND=celery 时）
│   ├── config.py                  # 全部配置项（pydantic-settings，读 .env）
│   ├── cache.py / resilience.py / tracing.py / logging_config.py
│   └── ...
├── tests/                         # 42 个测试文件 / 321 用例（unit + API 集成 + Milvus 真机）
├── eval/                          # 离线评测三件套：run_eval / metrics / LLM Judge
├── migrations/                    # 启动时自动执行的 SQL 迁移（幂等 IF NOT EXISTS）
├── data/seed.sql                  # 默认账号种子（admin/admin123）
├── scripts/                       # build_index.py（直写 Milvus 集合）等
├── requirements.txt / .env.example
├── Dockerfile / Dockerfile.dev
└── （compose 编排文件在仓库根：docker-compose.yml + docker-compose.dev.yml）
```

## 快速开始（Docker，推荐）

compose 编排在仓库根目录，服务与 profile 实况：

| 服务 | profile | 说明 |
| --- | --- | --- |
| `postgres` `redis` `python-backend` | 默认起 | 主链路三件：8000 端口 |
| `celery-worker` | `worker` | TASK_BACKEND=celery 时启用 |
| `frontend` | `frontend` | Vite dev 服务器，5173 |
| `etcd` `minio` `milvus` | `milvus` | Milvus standalone，19530 只绑 127.0.0.1 |

```bash
# 在仓库根目录
cp backend/.env.example backend/.env    # 填 LLM Key
docker compose up -d --build            # 主链路
docker compose logs -f python-backend
```

启动成功后访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health
- 默认账号：`admin / admin123`（首次启动自动注入）

开发态热重载：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

常用命令：

```bash
docker compose ps                        # 查看容器状态
docker compose restart python-backend    # 重启后端
docker compose down                      # 停止并删除容器（数据卷保留）
docker compose --profile milvus stop     # 停 Milvus 三件套（命名卷数据保留）
docker compose down -v                   # ⚠️ 清除全部数据卷（含 Milvus 向量库）
docker compose exec postgres psql -U postgres -d contract_review   # 进入 psql
```

LLM Key 经 `backend/.env` 传入：`LLM_PROVIDER=auto` 自动检测 `CONTRACT_LLM_API_KEY` / `MINIMAX_API_KEY` / `OPENAI_API_KEY` 中已配置者；任何 OpenAI 兼容端点（千问/DeepSeek/智谱/vLLM）填 `CONTRACT_LLM_BASE_URL` + `CONTRACT_LLM_MODEL` 即可。

## 快速开始（本地）

```bash
# Python 3.12+；虚拟环境推荐 uv（pip 亦可）
cd backend
uv venv .venv && uv pip install -r requirements.txt
cp .env.example .env                      # 编辑填入 API Key
.venv/Scripts/python.exe -m uvicorn src.api.main:app --port 8000 --reload   # Windows
# Linux/macOS: .venv/bin/uvicorn src.api.main:app --port 8000 --reload
```

内存模式（`DATABASE_URL` 留空）即可跑通全部功能，卷宗驻留进程内；生产配 PostgreSQL DSN，迁移与种子在启动时自动执行。

## API 示例

登录取到 Token 后，其余接口带 `Authorization: Bearer <token>`。

### 注册（邮箱验证码自助开户）

```bash
# 1) 发验证码（60 秒冷却 / 邮箱已注册 409 / SMTP 未配 503）
curl -X POST http://localhost:8000/api/v1/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"email":"someone@example.com"}'

# 2) 带码注册：自助通道恒为 reviewer + 独立租户；
#    库内无任何账号时首注册免码直落 admin；已登录 admin 带 token 可免码建任意角色
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","email":"someone@example.com","password":"secret123","code":"123456"}'
```

SMTP 在 `.env` 配 `SMTP_HOST/PORT/USER/PASSWORD/FROM` 五键（QQ 邮箱：465 端口 + 授权码）。

### 登录

`username` 字段支持用户名或注册邮箱（大小写不敏感）。

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### 合同审查

```bash
# 同步模式（等待流水线完成）
curl -X POST 'http://localhost:8000/api/v1/review?mode=sync' \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"review_body":{"text":"甲方：…\n第一条 付款：逾期须支付无限违约金。","with_human_review":false}}'

# 异步模式：立即返回 review_id，前端 1s 轮询进度
curl -X POST 'http://localhost:8000/api/v1/review?mode=async' \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{ "review_body": { "text": "...", "with_human_review": false } }'
curl http://localhost:8000/api/v1/review/{review_id} -H "Authorization: Bearer $TOKEN"
```

完整端点见 Swagger：<http://localhost:8000/docs>（12 模块 52 端点，覆盖认证 / 审查 / 规则 / 模板 / 法规 / 知识库 / 协商 / 质量运维）。

## 核心概念

### 共享状态

所有 Agent 通过 `ContractReviewState`（Pydantic 模型）共享数据，分步进度字段供前端轮询：

```python
class ContractReviewState(BaseModel):
    review_id: str
    status: ReviewStatus
    raw_text: str                      # 或 raw_text_path（sidecar 文件化，防 checkpoint 膨胀）
    clauses: list[Clause]
    risk_findings: list[RiskFinding]   # source: rule / llm / conflict
    compliance_findings: list[ComplianceFinding]
    suggestions: list[Suggestion]
    needs_human_review: bool
    rag_refs: list[RagRef]             # 检索参考随批注持久化，结论可审计

    current_step: str = ""             # 分步进度
    step_log: list[StepEvent] = []
    progress: float = 0.0              # 0.0 – 1.0
```

### 编排图与条件路由

```python
graph = StateGraph(ContractReviewState)
graph.add_node("clause_extraction", clause_agent)
graph.add_node("parallel_analysis", parallel_risk_and_compliance)  # 深拷贝两份 state，asyncio.gather
graph.add_node("suggestion", suggestion_agent)
graph.add_node("human_review", feedback_node)                      # 条件路由 + interrupt_before
# 整体 HIGH 或存在 conflict → 停在 human_review 前等人；否则直达 complete
```

thread_id 用 review_id；恢复 = `aupdate_state` 注入 human_feedback + `ainvoke(None)`。跨进程恢复的前提是 checkpointer 用共享后端（`CHECKPOINT_BACKEND=redis|sqlite`），memory 后端会打警告并如实退化为一次性执行。

## RAG 向量库（Milvus）

`src/vector/milvus_store.py` 封装 Milvus 集合（AUTOINDEX + 内积度量），是知识库/RAG 的唯一向量后端；检索器 `rag.py` 过采过滤软删块。

| 语义项 | 实现 |
| --- | --- |
| 索引形态 | standalone 集合：id（主键自增）/ vector / doc_id / deleted / emb_model / text / meta |
| 删除语义 | 软删：行置 deleted=True（delete+insert 换主键），物理向量不回收 |
| 检索过滤 | 检索侧过采 top_k×3 后滤软删（`rag.py`） |
| 建库模型名 | 行内 `emb_model` 字段 |
| 换模型防线 | 不一致拒绝追加；启动钩子用原文重嵌入——先全量预嵌入、全成功才 drop+分批插入（all-or-nothing） |
| 依赖 | `pymilvus>=2.5,<3` + 起服务（`docker compose --profile milvus up -d`） |

运维要点：

- **单后端收敛史**：项目曾以工厂实现 FAISS/Milvus 双后端同一契约，真机全部转 Milvus 运行后彻底删除 FAISS——对齐两套语义、维护两套测试的成本超过剩余价值，配置键 `VECTOR_DB_TYPE` / `FAISS_INDEX_PATH` 一并退役；
- **容量上限**：单字段 64KB（VARCHAR），超长条文块在 `_ingest` 被拒并映射 400；
- **一致性窗口**：Milvus 写入可见与软删标记传播有延迟，真机集成测试以轮询等待（`test_milvus_integration.py`）；
- **降级不炸**：服务不可达时状态探针把错误放进 `reason`（提示启动命令），启动重建钩子返回 `unreachable` 仅告警——绝不阻塞应用启动；
- 换嵌入模型后重启，自动重建集合，无需重新上传。

## 测试

```bash
# 回归（离线环境必带 HF_HUB_OFFLINE=1，防测试触碰网络下载）
HF_HUB_OFFLINE=1 .venv/Scripts/python.exe -m pytest tests/ -q      # 321 用例

# Milvus 真机集成：需先 docker compose --profile milvus up -d，未起服务自动 skip
.venv/Scripts/python.exe -m pytest tests/test_milvus_integration.py -q
```

套件构成：auth（JWT/RBAC/邮箱注册）、db/e2e、rules/services、report、rag/knowledge（服务层 + API）、Milvus 真机集成、bad case 质量线。知识库单测/接口测试用假 MilvusStore 与假探针隔离网络和嵌入栈——**Milvus 起没起都不影响全量单测全绿**（真机用例在服务缺席时自动跳过）。

## 常见问题

### Q: 如何添加新的 Agent？

1. `src/agents/` 新建，实现 `__call__`；
2. `pipeline/state.py` 加输出字段；
3. `pipeline/graph.py` 注册节点与边。

### Q: 如何添加新的规则？

编辑 `src/rules/definitions/risk_rules.yaml`（热加载），或经 `/api/v1/rules` 动态 CRUD。YAML DSL 支持 and/or 条件组合、9 种算子；`rules/risk_rules.py` 是流水线用的纯数据模块（零重依赖，与 eval/ 共用以单一事实来源）。

### Q: 如何切换大模型？

`.env` 改 `LLM_PROVIDER` 或 `CONTRACT_LLM_*`（任何 OpenAI 兼容端点均可）。向量库不再是切换项：Milvus 为唯一后端，`docker compose --profile milvus up -d` 起服务即用。

### Q: 生产部署为什么强制 `--workers 1`？

异步模式的分步进度靠 `asyncio.create_task` 后台运行，多进程会丢后台任务。横向扩展在容器层做，或 `TASK_BACKEND=celery`（`--profile worker`）分担负载。

### Q: 邮箱注册收不到验证码？

依次查：SMTP 五键是否齐（缺任一发码 503）→ 发码返回体 detail（冷却 429 / 已注册 409）→ QQ/163 须用**授权码**而非登录密码、465 端口。库内无账号时首注册免码，可先用 admin 进门。

## 相关文档

- [项目首页](../README.md)（部署入口、配置表、隐私边界）
- [使用说明](../docs/使用说明.md)（使用者操作手册）
- [面试讲解稿](../docs/项目介绍-面试讲解稿.md)（架构决策与实测数字）
