<div align="center">
<h3 align="center">分寸合同 · Fencun Contract</h3>
<p align="center">
跑在你自己机器上的多 Agent 合同审查幕僚：拆条款、挑风险、查合规、给改法，最后拍板的永远是人——合同、法规、卷宗，全在你自己的盘里。
<br />
<a href="#快速开始"><strong>本地跑起来 »</strong></a>
<br />
</p>
<details style="margin-top: 24px;" open>
<summary>目录</summary>
<ol>
<li><a href="#项目简介">项目简介：解决什么痛点</a></li>
<li><a href="#核心亮点">✨ 核心亮点</a></li>
<li><a href="#技术栈">🛠️ 技术栈</a></li>
<li><a href="#快速开始">🚀 快速启动</a></li>
<li><a href="#目录结构">📁 项目目录说明</a></li>
<li><a href="#使用示例">📖 使用示例与接口说明</a></li>
<li><a href="#后续规划">📋 后续规划</a></li>
<li><a href="#参与贡献">参与贡献 / 许可证 / 联系 / 致谢</a></li>
</ol>
</details>
</div>




---

## 项目简介

<a id="项目简介"></a>

**痛点**——把合同交给 AI 看的人普遍卡死在五件事上：

| 痛点 | 现状 | 分寸合同的答案 |
|---|---|---|
| 合同三五页，看完心里没底 | 人工通读会漏条款；丢给通用大模型，答案飘忽没章法 | 四位「幕僚」流水线接手：**条款拆解 →（风险识别 ∥ 合规检查）→ 修订建议**，批注逐条落到条款上，分步进度实时可追 |
| AI 引法条不靠谱 | 大模型凭「记忆」背条文编号，背错了也理直气壮 | 知识库 RAG：法规上传即自动按「第X条」切块建向量索引，批注附**「检索参考」**（条文原文＋出处＋相似度）——从「背出来的依据」变「翻出来的依据」 |
| 怕漏判风险 | 单模型说了算，没有反证机制 | **双引擎判定**：YAML 规则库（关键词/正则，热加载）与大模型各出一手，分歧按**就严**采信并写明理由 |
| 怕 AI 替自己做主 | 一键「通过/驳回」盖章 = 没人对结果负责 | **人在回路**定夺门：逐条认同/存疑投票，三态定夺（同意/驳回/部分同意），人不点头流程不合卷；反馈回流教训库与错判档案 |
| 敏感合同不敢出门 | 多数 SaaS 审查工具强制传云端 | 本地优先：无数据库也能跑（内存模式）、无 API Key 也能审（纯规则降级、文本不出机）、向量库端口只绑 127.0.0.1；配置大模型时透明告知文本发往哪家服务商 |

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## ✨ 核心亮点

<a id="核心亮点"></a>

1. **LangGraph 四幕僚流水线 + 定夺关节点**（`backend/src/pipeline/graph.py` / `checkpointer.py`）
   条款拆解（`clause_extraction`）→ 风险识别（`risk_identification`）∥ 合规检查（`compliance_check`）并行 → 修订建议（`suggestion`），有向图编排、分步进度前端轮询实时跟踪。审查立场可选**买方/卖方/中立**——幕僚按你的立场衡量利害。定夺门走 `interrupt/resume`，checkpoint 支持 memory/sqlite/redis 三档，进程重启断点能续。
2. **双引擎判定，分歧就严**（`backend/src/rules/engine.py` + `definitions/risk_rules.yaml`）
   规则引擎 10 条 YAML 规则（无限责任/单方解除/违约金超标/格式条款无效等，severity 分 critical/warning/info）+ 6 组 Agent 关键词 + 4 条内置合规速查（如《民法典》第497条格式条款无效）；改 YAML 即热加载不重启。LLM 完全不可用时自动降级**纯规则模式**，合同文本一个字节不出机器。
3. **RAG 知识库：翻出来的依据**（`backend/src/vector/milvus_store.py` / `rag.py` / `embeddings.py`）
   admin 在「知识库」页上传 PDF/DOCX/TXT（≤20MB）或粘贴条文，自动按「第X条」切块（单文档 ≤400 块）、嵌入入 **Milvus standalone**（AUTOINDEX + 内积度量，软删除只置标记），审查批注透出「检索参考 · N 条」。**换嵌入模型重启自动用留存原文重建索引**，无需重新上传；嵌入源二选一：本地 sentence-transformers（文本不出机）或 OpenAI 兼容 /embeddings（默认硅基流动 `BAAI/bge-m3`）。
4. **产出流转：批注本、红线稿、协商追踪**（`backend/src/services/report_service.py` 等）
   PDF 审查报告、Word **修订红线稿**（删句标红、增句标青）、任意两版 diff 对照、多轮协商条款级追踪、一次最多 10 份批量审查；历史卷宗台账按租户隔离可回看。
5. **韧性防线内建**（`backend/src/resilience.py` / `src/api/rate_limit.py` / `src/config.py`）
   LLM 连败 3 次熔断即走规则回退、JSON 输出不合法自我修复重试、前端对 429/5xx 退避续轮询（限流只计写请求，GET 豁免——进度轮询不再被自家闸门拦死）；Qwen3 思考模型非流式返回空文本的坑在 `get_llm` 显式关闭思考模式解决。
6. **账号与权限**（`backend/src/api/routers/auth.py`）
   JWT + admin/reviewer/viewer 三角色，卷宗按 `tenant_id` 存储层强制隔离；**邮箱验证码自助注册**（SMTP 五键配置），自助开户恒为 reviewer + 独立随机租户（防自我提权），知识库写权限收口仅 admin；用户名/邮箱双通道登录；空库首注册免验证码直落 admin——新装机器没配邮件也能先进门。
7. **质量运维闭环**（`/bad-cases` `/diagnostics` `/metrics`）
   错判档案（bad case）沉淀、诊断端点、OpenTelemetry 可选接入——审得不对有账可查，改完有回归测试兜底（42 个测试文件 321 用例，全离线假件，零真网零真烧钱）。

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 🛠️ 技术栈

<a id="技术栈"></a>

| 层 | 选型 |
|---|---|
| **前端** | React 19 · TypeScript · Vite 6 · Tailwind CSS 3 · lucide-react（15 页面 + 12 组件：落地页/工作台/审查/批注本/台账/知识库/法规/规则/模板/对比/协商/错判/设置/登录） |
| **API** | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2（async/asyncpg）· PyJWT |
| **AI 编排** | LangGraph ≥1.2（四 Agent 有向图 + checkpoint memory/sqlite/redis）· OpenAI 兼容多提供商（千问/DeepSeek/智谱/MiniMax/OpenAI/本地 vLLM） |
| **RAG** | Milvus 2.5 standalone（etcd + MinIO）· pymilvus · sentence-transformers 本地嵌入 / 硅基流动 bge-m3 |
| **数据** | PostgreSQL 16（compose 宿主映射 :5433）或**内存模式**（DATABASE_URL 留空即得，卷宗驻进程）· Redis 7 |
| **任务** | asyncio 进程内（开发默认）/ Celery worker + Redis（生产可选 profile） |
| **导出** | reportlab（PDF 报告）· python-docx（Word 红线稿）· PyPDF2 |
| **部署** | Docker Compose：默认起 postgres + redis + 后端；`worker` / `frontend` / `milvus` 三个可选 profile |
| **可观测** | OpenTelemetry · 结构化日志 · `/metrics` 看板 |

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 🚀 快速启动

<a id="快速开始"></a>

### 前置依赖

- Docker Desktop（起数据库/向量库，纯内存模式可不要）
- Python 3.12+ 与 Node 20+（本地开发模式）
- 一把**可选**的 LLM API Key：OpenAI 兼容端点任意一家（通义千问/DeepSeek/智谱/MiniMax…）——不配也能跑，自动走纯规则模式（能力打折，但文本绝对不出机）

### 方式 A：Docker 全家桶

```bash
cp backend/.env.example backend/.env     # 填入至少一把 LLM Key（可留空走纯规则）
docker compose up -d                     # postgres + redis + 后端 :8000
docker compose --profile milvus   up -d  # 可选：向量库（知识库/RAG 必需）
docker compose --profile frontend up -d  # 可选：前端 :5173
```

### 方式 B：本地开发（本仓库日常主力）

```bash
# 后端（先起 compose 的 postgres，或 DATABASE_URL 留空走内存模式）
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Linux/macOS 用 venv/bin/pip
cp .env.example .env                                                     # 配 CONTRACT_LLM_API_KEY 等
.venv/Scripts/python.exe -m uvicorn src.api.main:app --port 8000

# 前端（另开终端）
cd frontend && npm install
VITE_API_TARGET=http://127.0.0.1:8000 npm run dev      # Windows PowerShell: $env:VITE_API_TARGET=…
```

**验证活着**（跑起来后执行）：

```bash
curl http://127.0.0.1:8000/api/v1/health
# → {"status":"healthy","service":"fencun-contract","version":"1.2.0","database":"connected"}
```

浏览器开 `http://localhost:5173`：登录页切「注册」标签，邮箱验证码开户（自助注册恒为 reviewer）；库内第一个账号免验证码直落 admin。没数据库想先进门：`.env` 设 `DEV_MEMORY_LOGIN=true`，内置 `admin/admin123`（仅限本地，勿带上线）。

> **端口避让**：本机若 8000 被占（compose 的 PostgreSQL 已默认让到 :5433，就是被占过留下的坑），后端改 `--port 8001` 并同步 `VITE_API_TARGET` 即可，互不影响。
> **Windows 注意**：`uvicorn --reload` 热重载在本机不可靠（发了 Reloading 信号新进程不一定会起），改完后端代码请**整个重启进程**。

### 启用 RAG 知识库（可选）

```bash
docker compose --profile milvus up -d    # etcd + MinIO + milvus 三容器，端口只绑 127.0.0.1
```

`backend/.env` 设 `RAG_ENABLED=true`，嵌入二选一：`EMBEDDING_SOURCE=local`（本地推理，文本不出机）或 `=api` + `SILICONFLOW_API_KEY=sk-…`（默认 `BAAI/bge-m3`）。admin 登录进「知识库」页上传法规即自动切块入库。

> 📦 **《民法典》全文已备好待传**：仓库根目录 [`民法典全文/`](民法典全文/) 内 6 份 UTF-8 txt（按编切分、共 1260 条零缺号、源自全国人大网官方全文存档，机器审计验证），每份 ≤325 条，正落在单文档 400 块上限之内——逐份上传即可。
> **诚实边界**：拍照片/无文本层图片暂不能识别（未接 OCR），请用聊天工具「提取文字」后粘贴文本框；**空文档或解析不出条款时会显示「0 条款」——0 条款 ≠ 审查通过**，请换有文本层的文件再审。

### 开发模式与测试

```bash
cd backend  && .venv/Scripts/python.exe -m pytest tests/ -q   # 42 文件 321 用例，离线假件零真实外呼（最近实测：319 passed + 2 skipped / 21 分钟；Milvus 集成用例未起服务自动跳过）
cd frontend && npm run build                                  # tsc -b && vite build（最近实测：1678 模块 / 417.66 kB JS，gzip 120.48 kB，10.6s）
```

> 方式 A 的容器全家桶与方式 B 的本地链路均已备妥，其中**方式 B + compose 起 postgres 为日常实测路径**；纯 Docker 一键路径本环境未整体验收，首次使用遇到问题先看下方「故障速查」。

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### `.env` 键一览

| 键 | 干什么 | 备注 |
|---|---|---|
| `LLM_PROVIDER` | `auto`（contract→minimax→openai 取第一把有效钥匙）或指定一家 | |
| `CONTRACT_LLM_API_KEY` / `_BASE_URL` / `_MODEL` | 通用 OpenAI 兼容端点三件套 | 千问/DeepSeek/智谱/vLLM 都走这路 |
| `MINIMAX_*` / `OPENAI_*` | 另两家的钥匙与端点 | 不用可不填 |
| `DATABASE_URL` / `DATABASE_URL_SYNC` | **留空 = 内存模式**；填 DSN 切 PostgreSQL | 默认指向 compose 的 :5433 |
| `JWT_SECRET_KEY` | 生产必换 ≥32 字符随机串 | 默认值 + 鉴权开启会被**启动校验拦下** |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | 自助注册邮箱验证码 | 缺任一发码端点返回 503，其余功能不受影响（QQ 邮箱：smtp.qq.com/465/授权码） |
| `RAG_ENABLED` / `EMBEDDING_SOURCE` / `EMBEDDING_MODEL` / `SILICONFLOW_API_KEY` | RAG 开关与嵌入来源 | 换模型重启自动重建索引 |
| `MILVUS_URI` / `MILVUS_TOKEN` / `MILVUS_COLLECTION` | 向量库连接 | 单机自建默认值即可 |
| `TASK_BACKEND` | inprocess（默认）/ celery | 生产可切 Celery+Redis |
| `CHECKPOINT_BACKEND` | memory / sqlite / redis | 人机协同断点续跑 |
| `DEV_MEMORY_LOGIN` / `AUTH_DISABLED` | 本地开发后门 | 仅限本机，上线必关 |
| `RATE_LIMIT_PER_MINUTE` / `MAX_UPLOAD_SIZE_MB` | 限流（只计写请求）/ 上传上限 | 默认 60/分/IP、20MB |

> **密钥纪律**：真 `.env` 永不进 git、不进日志、不贴进任何聊天窗口；`.env.example` 只放占位符。

### 故障速查（本机真实踩过）

| 症状 | 意思 | 怎么办 |
|---|---|---|
| 注册提示「数据库不可用」 | `DATABASE_URL` 为空或连不上库 | 起 `docker compose up -d postgres`；或确认 DSN 端口是 :5433 |
| 登录 401 循环 / DSN 密码不对 | `.env` 里库口令与容器实际口令不一致 | 以 compose 的 `POSTGRES_PASSWORD` 为准对齐 `.env`，重启后端 |
| 改了后端代码没生效 | Windows 热重载不可靠 | 整进程重启 uvicorn |
| 前端弹「核阅中断」 | 旧版把进度轮询计入限流；现 GET 已豁免、前端对 429 自动退避 | 拉最新代码重启两端即可 |
| 审查秒完但 0 条款 0 风险 | 文档没有文本层（照片/空文档）或 LLM 熔断 | 看批注本错误条；照片先提字再粘贴 |
| 知识库状态卡报连接失败 | Milvus 三容器没起 | `docker compose --profile milvus up -d`，不影响其余功能 |
| LLM 返回为空、连败熔断 | Qwen3 系思考模式在非流式下把答案全塞 reasoning_content | 已在 `get_llm` 统一关闭思考（`enable_thinking=False`）；换其他思考模型注意同类参数 |

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 📁 项目目录说明

<a id="目录结构"></a>

```
intelligent-contract-review/
├── backend/                   # FastAPI + LangGraph 流水线（工程细节见 backend/README.md）
│   ├── src/agents/            #   四位幕僚 + prompt_guard（注入防线）/structured（schema 校验修复）/file_tools（长文旁路）
│   ├── src/pipeline/          #   graph.py 有向图编排 · state.py 共享状态 · checkpointer.py 断点续跑
│   ├── src/rules/             #   engine.py 规则引擎 + definitions/ YAML 规则与模板（热加载）
│   ├── src/vector/            #   embeddings 双源嵌入 · milvus_store 向量库 · rag 检索器
│   ├── src/services/          #   审查/知识库/报告/邮箱验证码/错判检测/版本对比/协商… 14 个服务
│   ├── src/api/               #   12 路由模块 · JWT/RBAC 依赖 · 限流中间件（GET 豁免）
│   ├── src/db/                #   SQLAlchemy 2 模型 · CRUD · 会话
│   ├── migrations/            #   6 个增量 SQL（启动自动执行，ADD COLUMN IF NOT EXISTS 风格）
│   ├── scripts/               #   build_index / seed_data / 错判转评测集
│   ├── tests/                 #   42 文件 321 用例（离线假件注入 LLM/向量层，零真实外呼）
│   └── .env.example           #   密钥模板（真 .env 永不进库）
├── frontend/                  # React 19 + Vite 6 SPA：src/pages 15 页 · src/components 12 件
├── docs/                      # README 导航 · 使用说明（使用者手册）· 项目介绍讲解稿
├── 民法典全文/                # 官方全文按编切好的 6 份 txt（1260 条，待上传知识库）
├── 示例合同/                  # 3 份演示合同（劳动合同/技术服务/硬件采购，故意埋雷）
├── LICENSE                    # MIT 开源许可
└── docker-compose.yml         # 默认 postgres+redis+后端；worker/frontend/milvus 可选 profile
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 📖 使用示例与接口说明

<a id="使用示例"></a>

### 一段真实审查剧本（房屋租赁合同，本机跑通）

```text
你：（登录页 → 注册 tab，邮箱收码开户 → 自动登录）
你：（工作台「审查」→ 文件上传 → 选中《房屋.docx》→ 立场选「买方」→ 上传并审查）
它：（流水线跑马灯：条款拆解 ✓ → 风险识别 ∥ 合规检查 ✓ → 修订建议 ✓ → 到定夺门停住等拍板）
    状态 awaiting_human：拆出 12 条条款，标出 5 处风险，每处附判断依据与修改建议。
你：（批注本逐条看——押金条款超法定上限被标红，「民法典第七百零三条」等援引挂在右侧依据栏）
    （知识库上传《民法典》后，同一位置的依据会从「模型记忆引用」升级为「检索参考 · N 条」：条文原文+出处+相似度）
你：（对每条投「认同/存疑」→ 三态定夺：同意/驳回/部分同意 → 定夺）
它：（合卷。台账留档，可导 PDF 报告 / Word 红线稿，改后第二版可与本版 diff。）
```

### 接口说明（共 52 端点 / 12 模块，前缀 `/api/v1`，Swagger 交互式文档见 `/docs`）

| 模块 | 端点数 | 说明 |
|---|---|---|
| 账号 auth | 4 | 发码 / 注册 / 登录（用户名或邮箱）/ me |
| 审查 review | 11 | 文本/上传/批量开审、进度、定夺、反馈、重审、PDF·Word·红线导出 |
| 台账 reviews | — | 历史卷宗列表（按租户隔离；并入 review 模块路由） |
| 规则 rules / 模板 templates | 9 + 6 | YAML 规则与审查模板管理（admin/reviewer） |
| 知识库 knowledge | 4 | 列表（admin/reviewer）· 上传/粘贴/删除（仅 admin） |
| 法规 regulations | 3 | 内置速查库（公开） |
| 协商 negotiation | 7 | 多轮协商追踪：发版、接受/驳回、状态机 |
| 对比 diff | 1 | 任意两版批注对照 |
| 质量运维 | 2 + 2 | bad-cases 错判档案 · diagnostics 诊断 |
| 系统 | 1 + 2 | health 健康检查 · metrics 看板（公开） |

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 📋 后续规划

<a id="后续规划"></a>

- [ ] 《民法典》6 份文本逐份上传知识库并验收（文件已备于 `民法典全文/`，重审合同应见「检索参考 · N 条」）
- [ ] 图片 OCR：拍照/扫描件合同直接识别（当前需先转文字）
- [ ] 「0 条款却显示无风险」的展示整改：解析不出条款时不得呈现绿色通过章
- [ ] 偶发失败的加权抽样用例修随机种子（当前单独重跑即过）
- [ ] 生产形态实跑：`TASK_BACKEND=celery` + `CHECKPOINT_BACKEND=redis` 全链路验收
- [ ] 上公网三件套：HTTPS + 域名 + 网关限流（当前定位局域网自用）

<p align="right">(<a href="#readme-top">back to top</a>)</p>


## 参与贡献 / 许可证 / 联系 / 致谢

<a id="参与贡献"></a>

- **贡献方式**：文档入口见 [docs/README.md](docs/README.md)（导航）与 [docs/使用说明.md](docs/使用说明.md)（使用者手册）；后端细节见 [backend/README.md](backend/README.md)。行为与代码不符时，以代码为准。
- **许可证**：[MIT](LICENSE)（见 LICENSE 文件）。
- **联系方式**：暂无（待补）。
- **致谢**：LangGraph / FastAPI / React / Milvus / Tailwind 社区；《中华人民共和国民法典》全文取自全国人大网官方发布文本（经联合国粮农组织法规库存档获取）；示例合同与「埋雷」条款为本项目自编。

> **免责声明**：AI 输出仅为审查辅助建议，不构成法律意见；重要合同请以执业律师意见为准。
