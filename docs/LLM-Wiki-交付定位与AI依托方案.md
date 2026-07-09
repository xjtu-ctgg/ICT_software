# LLM Wiki 交付定位与 AI 依托方案

## 1. 当前结论

本赛题不是单纯提交一个离线脚本，也不是只提交一段提示词。更准确的交付定位是：

> 把作品做成评分平台 Agent 可理解、可调用、可验证的工具 / Skill / CLI，让平台 Agent 使用所选大模型完成任务规划和工具调用，再由本地确定性工具完成解析、检索、执行、修复、安全校验和标准答案输出。

当前计划使用的评分平台配置为：

- Agent 框架：OpenCode
- 大模型：GLM 5.1
- 评分方式：平台使用所选 Agent 框架和模型，并行运行 5 个用例集
- 交付入口：`INSTRUCTION.md`
- 可运行交付件：`work/`
- 输出位置：`llm-wiki/output/group-*-answer.md`
- 自验证与日志：`result/`、`logs/`

因此，后续方案不应把重点放在“手写关键词规则覆盖所有隐藏题”上，也不能假设平台一定会把 GLM 5.1 的 API endpoint 直接暴露给 Python 代码。更稳妥的方案是：让 OpenCode + GLM 5.1 作为平台 Agent 的智能层，清晰读取 `INSTRUCTION.md` 和 Skill，调用我们交付的本地工具完成任务。

## 2. 赛题要求理解

赛题要求构建一个面向 `llm-wiki` 目录的知识管理和操作系统。平台会提供真实评测材料，主要包括：

- `question/group-*.md`：每组 20 到 30 个问题
- `docs/`：200+ 个不同格式文件
- `Permission.json`：权限黑名单

作品需要自动完成：

- 多格式文件解析：`doc/docx/ppt/pptx/xls/xlsx/xml/java/py/html/md/js` 等
- 批注和 TODO 管理：统计、筛选、按责任人和日期查询
- 文档修复：根据批注或 TODO 要求生成被修改后的文档/代码副本到 `output/fixed/`
- 文件运行和表格分析：安全执行部分代码、对 Excel 做筛选/统计/汇总
- 知识库问答：回答文件路径、文件数量、业务相关文件、常用命令等问题
- 安全拒答：高危命令、越权路径、危险文件、密码/密钥、Prompt 注入统一拒绝
- 标准输出：每道题必须输出符合 `answer_format` 的 JSON

关键约束：

- 平台材料由评测环境提供，不能把公开样例当成真实测试集
- `INSTRUCTION.md` 必须能指导平台 Agent 自动执行，不得依赖人工操作
- 修复类题目不是修复参赛工程本身，而是按批注/TODO 要求生成目标文件副本；不能覆盖原始 `docs/` 文件，必须写入 `llm-wiki/output/fixed/`
- 高危问题必须固定返回 `{"error_msg":"高危命令，拒绝访问"}`
- 输出路径必须是相对 `docs/` 或 `output/` 的路径，不应输出本机绝对路径

## 3. 对评分平台运行机制的判断

根据提交指导和打分平台说明，平台运行逻辑可以理解为：

1. 选手上传 zip 作品。
2. 平台解压并检查 `INSTRUCTION.md`、`work/`、`result/`、`logs/` 等结构。
3. 选手选择 Agent 框架和模型。
4. 平台用所选 Agent 和模型读取 `INSTRUCTION.md`。
5. Agent 根据说明部署、启动、调用作品。
6. 平台准备隐藏用例集和 `llm-wiki` 材料。
7. Agent/作品在每个用例集上生成答案和修复结果。
8. 平台根据答案格式和预期结果计算通过率、稳定性、准确性和最终得分。

这里需要区分两类 AI 能力：

- 平台 Agent 的模型能力：OpenCode + GLM 5.1 会读取说明、理解任务、执行命令和调用工具。这是当前最应该利用的 AI 能力。
- 作品内部的 API 调用能力：如果环境提供 `LLM_WIKI_MODEL_ENDPOINT`、`LLM_WIKI_MODEL_NAME`、`LLM_WIKI_API_KEY`，Python 代码可以直接调用模型；但目前不能把这个作为强假设。

因此，交付作品应优先保证 Agent 能使用本地工具，而不是只依赖代码内部调用模型 API。

## 4. 现有评分结果暴露的问题

已有两次平台评分：

- `log7_7.md`：最终 45.8 / 100。AJ1-AJ3 有 20/24 通过，但 AJ4/AJ5 分别只有 2/24、4/24，通过结果不稳定。
- `log7_8.md`：最终 33.3 / 100。8 道题 5/5 全票通过，其余大量题目 0/5。

这说明当前方法有两个特点：

- 已覆盖题型的确定性很强：格式、安全、部分统计和拒答题一旦命中，能稳定全票通过。
- 未覆盖题型的泛化不足：隐藏用例里的自然语言表达、业务语义、复杂问法、跨文件检索和修复要求难以靠关键词规则覆盖。

当前规则链不仅是关键词匹配，也包含文件解析、批注提取、权限校验、表格处理、代码安全执行等确定性工具。但在题目意图识别和开放语义检索上，仍然大量依赖关键词路由。由于隐藏数据的文件名、业务词、问法都不可知，继续堆关键词不是最优方向。

## 5. 交付作品的正确定位

后续作品应定位为：

> 面向 OpenCode + GLM 5.1 的 LLM Wiki 工具型参赛作品。

更具体地说：

- `INSTRUCTION.md` 是给平台 Agent 的执行说明书，不只是给人看的 README。
- `work/skills/llm-wiki-solver/SKILL.md` 应描述 Agent 什么时候、怎么调用本作品。
- `work/llm_wiki_solver/` 应提供可重复执行的 CLI 和工具函数。
- 代码输出必须稳定、可校验、可回放。
- 日志 trace 应记录题目、路由、安全判定、检索证据、模型/规则使用情况，便于复盘。

Agent 和本地工具的职责边界：

| 层次 | 主要职责 | 是否依赖 AI |
| --- | --- | --- |
| 平台 Agent | 阅读 `INSTRUCTION.md`，理解任务，组织执行流程，必要时调用 Skill/CLI | 是 |
| GLM 5.1 | 语义理解、查询改写、证据重排、复杂题规划 | 是 |
| 本地安全层 | Permission、危险命令、密码、Prompt 注入、越权路径拦截 | 否 |
| 本地解析层 | 多格式文档解析、批注/TODO/表格/代码抽取 | 否 |
| 本地检索层 | SQLite、FTS/BM25、Embedding 缓存、混合召回 | 可选 |
| 本地执行层 | 统计、筛选、修复、安全 Python 执行、JSON 输出 | 否 |
| 本地校验层 | answer_format、路径、schema、安全边界校验 | 否 |

## 6. AI 依托方式

### 6.1 首选方式：让平台 Agent 调用本地工具

这是当前最稳妥的方式。作品需要让 OpenCode + GLM 5.1 明确知道：

- 题目材料位于 `/app/code/judge-assets/01_01_llm_wiki/`
- 需要处理全部 `question/group-*.md`
- 应调用 `python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto`
- 输出答案在 `/app/code/judge-assets/01_01_llm_wiki/output/group-*-answer.md`
- 遇到高危题必须输出固定拒答 JSON
- 不要人工交互，不要修改 REST API 契约，不要覆盖原始 docs

这种方式利用的是平台 Agent 的模型能力：模型读懂说明、规划执行、调用工具、检查结果。

### 6.2 可选增强：作品内部调用模型 API

当前代码中已有 LLM 增强接口，依赖环境变量：

- `LLM_WIKI_MODEL_ENDPOINT`
- `LLM_WIKI_MODEL_NAME`
- `LLM_WIKI_API_KEY`
- `LLM_WIKI_LLM_MODE`

如果评测环境提供兼容接口，代码可以启用模型做：

- 问题规划
- 查询改写
- 证据选择
- Rerank
- 受约束答案草稿
- 修复计划生成

但这只能作为增强路径，不能作为唯一依赖。因为现有规则没有明确说明平台会把所选 GLM 5.1 的 API key 注入到参赛代码环境。

### 6.3 推荐混合方式

推荐最终采用：

```text
OpenCode + GLM 5.1
  -> 读取 INSTRUCTION.md
  -> 使用 Skill/CLI
  -> 调用本地 solver
  -> 本地 solver 构建 Wiki 索引
  -> 安全前置
  -> 确定性工具优先回答
  -> 复杂语义题使用混合检索和可选 LLM 增强
  -> 本地 validator 输出最终 JSON
```

这条路线同时满足：

- 能依托平台 AI
- 能自动化执行
- 能在模型 API 不暴露时继续工作
- 能避免 LLM 被 Prompt 注入控制
- 能保留确定性题目的稳定通过率

## 7. 推荐技术路线

后续优化应从“关键词规则主导”转向“Agent 工具化 + 混合知识库 + 安全确定性执行”。

### 7.1 安全前置

所有题目先通过安全层：

- `Permission.json` 文件、目录、命令黑名单
- 系统密码、数据库密钥、API key、secret key 等敏感查询
- 删除、格式化、kill、shutdown、rm、del、Remove-Item 等高危命令
- 文档中的 Prompt 注入内容
- 越权读写路径

安全层必须本地确定性执行，不交给 LLM 最终决定。

### 7.2 文档解析与结构化

建立统一文档对象：

- 文档路径、后缀、目录
- 正文文本
- 批注和 TODO
- 表格行列
- 代码片段
- 解析状态和错误信息

Office、代码、Markdown、HTML、XML、Excel 都应被统一纳入索引，而不是只在具体题型中临时扫描。

### 7.3 SQLite 本地知识库

SQLite 应作为本地知识库底座，而不是只保存原文。建议表结构包括：

- `documents`
- `chunks`
- `comments`
- `table_rows`
- `code_blocks`
- `embeddings`
- `retrieval_trace`

这样能支持稳定复盘，也能方便后续接入 FTS、Embedding 和 Rerank。

### 7.4 混合检索

推荐四路召回：

- 规则/结构化召回：文件数量、路径、责任人、日期、表格条件等
- SQLite FTS/BM25：关键词、文件名、命令、路径片段
- Embedding 语义召回：业务相关、同义表达、跨文档语义问题
- 事实表召回：批注、TODO、表格行、代码片段

排序策略：

- 安全拒答最高优先级
- 确定性结构化命中优先
- FTS/BM25 保证字面精确
- Embedding 弥补语义表达差异
- Rerank 只处理 Top-K 候选，减少误判

### 7.5 LLM 规划与受控生成

LLM 适合做：

- 判断题目意图
- 生成子查询
- 从候选证据中选择最相关内容
- 对复杂问法做查询改写
- 对修复题生成 repair plan

LLM 不适合直接做：

- 权限最终判断
- 高危命令最终放行
- 文件系统写入
- 任意代码执行
- 最终 JSON 格式自由输出

最终答案必须由本地 validator 接管。

## 8. 后续调研方向

接下来调研热门项目和方法时，建议围绕这些问题展开：

1. OpenCode 如何发现和使用本地 Skill/CLI。
2. OpenCode 中 `INSTRUCTION.md` 怎样写，最容易让 Agent 稳定执行。
3. 是否能提交 MCP Server；如果能，是否比 CLI/Skill 更适合工具调用。
4. RAG 项目中 SQLite/FTS/Embedding/Rerank 的轻量实现方式。
5. 中文文档检索中 BM25、向量召回、混合排序的实践。
6. GLM 5.1 是否提供工具调用、JSON schema、rerank 或 embedding 能力。
7. 平台评分环境是否会向参赛代码注入模型 API 环境变量。
8. 多格式 Office 文档解析有什么更稳定的纯 Python 或命令行方案。
9. 如何把 Prompt 注入防护和 RAG 检索结合，避免污染上下文。
10. 如何让 trace 日志既对评测无干扰，又能帮助复盘失败用例。

## 9. 第一轮外部调研结论

调研时间：2026-07-08。

本轮调研覆盖 OpenCode 官方文档、热门 GitHub 项目、RAG/文档处理/安全相关论文与权威安全资料。结论是：本赛题不适合直接把一个完整 RAG 平台搬进交付包，更适合吸收其架构思想，做成轻量、可控、可由 OpenCode Agent 调用的本地工具链。

### 9.1 OpenCode 交付形态

OpenCode 官方文档确认：

- OpenCode 是开源 AI coding agent，可通过终端、桌面 App 或 IDE extension 使用，并依赖配置好的模型提供商 API key。[OpenCode Intro](https://opencode.ai/docs)
- OpenCode 支持项目级 Agent Skills，`SKILL.md` 需要包含 `name` 和 `description` frontmatter，并由 agent 按需加载。[OpenCode Agent Skills](https://opencode.ai/docs/skills/)
- OpenCode 支持 MCP servers。MCP 工具会和内置工具一起暴露给 LLM，既支持 local server，也支持 remote server。[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers)
- OpenCode 支持 Custom Tools。工具定义是 TypeScript/JavaScript 文件，但可以调用任意语言脚本，包括 Python。[OpenCode Custom Tools](https://opencode.ai/docs/custom-tools/)
- OpenCode Agent 支持温度、模型、权限、工具访问等配置；低温度适合代码分析和规划，权限配置可限制 bash、edit、skill、websearch 等能力。[OpenCode Agents](https://opencode.ai/docs/agents)

对本赛题的直接启发：

- 比赛平台要求 Skill 必须放在 `work/skills/{skill-name}/SKILL.md`，因此交付件不依赖 OpenCode 官方本地路径。
- `INSTRUCTION.md` 应显式告诉平台 Agent 使用 `work/skills/llm-wiki-solver/SKILL.md`，并运行 CLI。
- 如果平台支持 MCP，MCP Server 是更标准的工具暴露方式；但短期不应替代 CLI，因为 CLI 最容易被平台复现和评分。

建议优先级：

1. 必做：CLI + `work/skills/llm-wiki-solver/SKILL.md` + 清晰 `INSTRUCTION.md`。
2. 必做：`work/skills/docx`、`work/skills/pptx`、`work/skills/xlsx` 三个比赛专用 Office Skill。
3. 后做：MCP Server，前提是确认平台能启动本地 MCP，且仍需放在 `work/` 目录下。

### 9.2 文档解析工具

| 工具 | 调研结论 | 适合本赛题的用法 |
| --- | --- | --- |
| [MarkItDown](https://github.com/microsoft/markitdown) | GitHub 页面显示约 164k stars。微软项目，定位是把文件和 Office 文档转成 Markdown，支持 PDF、PowerPoint、Word、Excel、HTML、CSV/JSON/XML、ZIP 等。README 强调它适合 LLM 和文本分析管线，同时提醒在不可信环境中要注意 I/O 权限。 | 可作为可选解析器，用于 `.doc/.ppt/.xls` 或当前解析失败时兜底。不建议作为唯一解析器，因为批注/TODO、修复写回、权限控制仍需本地确定性代码。 |
| [Docling](https://github.com/docling-project/docling) | GitHub 页面显示约 62.9k stars，MIT license。支持 PDF、DOCX、PPTX、XLSX、HTML、EPUB、图片、音频、纯文本等，提供统一 `DoclingDocument`、Markdown/HTML/JSON 导出、本地执行、LangChain/LlamaIndex/Haystack/CrewAI 集成和 MCP server。Docling 论文称其可作为 CLI 或 Python API，适合生成式 AI 文档处理。 | 适合作为增强解析器，尤其适合复杂表格、阅读顺序和富结构文档。但依赖较重，短期应做成 optional backend：有则用，无则回退现有 OOXML/文本解析。 |
| [Unstructured](https://github.com/Unstructured-IO/unstructured) | GitHub 页面显示约 15.1k stars，定位为把复杂文档转成结构化格式的开源 ETL，支持 PDF、HTML、Word 等，提供 partition、chunking、embedding 等预处理能力。安装全部文档能力依赖较重，需要 `libmagic`、`poppler`、`tesseract`、`libreoffice` 等。 | 不适合直接作为基础依赖打包；可作为可选解析后端或调研参考。对本赛题更现实的是借鉴其“partition -> element -> chunk”的结构化思想。 |
| LibreOffice headless | 多个解析工具都依赖它处理 Office 文件，尤其旧版 `.doc/.ppt/.xls`。 | 保留为旧 Office 文件转换兜底，在 `INSTRUCTION.md` 中说明可选依赖。 |
| OOXML 直接解析 | 当前代码已有基础能力。 | 仍是主路径。赛题文件无图片资源，数量约 200，直接解析 docx/pptx/xlsx zip XML 更轻、更稳定、更可控。 |

落地建议：

- 基础解析仍使用当前纯 Python 逻辑。
- 新增 `ParserBackend` 适配器：`native -> markitdown -> docling -> libreoffice`。
- 批注、TODO、Permission、安全拒答、修复写回不能外包给解析库。
- 对 `.xlsx` 仍优先结构化解析表头和行列，不能只转 Markdown，否则会损失筛选、计数、汇总能力。

### 9.3 RAG 与 Agent 框架

| 项目 | 调研结论 | 对本赛题的取舍 |
| --- | --- | --- |
| [RAGFlow](https://github.com/infiniflow/ragflow) | GitHub 页面显示约 7,243 commits。README 定位为融合 RAG 与 Agent 能力的开源 RAG engine，支持深度文档理解、grounded citations、Word/slides/excel/txt/images/scanned docs、multiple recall + fused re-ranking、Agent workflow、MCP、Python/JavaScript code executor。运行要求较重：Docker、较高 CPU/RAM/磁盘、Python 3.13 等。 | 架构高度匹配，但不适合整体搬进 zip 作品。可借鉴：深度文档解析、模板化 chunk、多路召回、融合 rerank、引用 trace、Agent/code executor。 |
| [LlamaIndex](https://github.com/run-llama/llama_index) | GitHub 页面显示约 50.7k stars。README 定位为构建 agentic apps 的开源框架，提供 data connectors、indices、retrievers、query engines、reranking modules，并有 LlamaParse 文档平台。 | 可借鉴组件抽象：Document、Node/chunk、Index、Retriever、Reranker、QueryEngine。完整引入依赖较重，短期不建议直接依赖。 |
| [LangChain](https://github.com/langchain-ai/langchain) | GitHub 页面显示约 141k stars。定位为 agent engineering platform，提供模型、embedding、vector store、retriever、工具、LangGraph 等抽象。 | 不建议整体接入；可借鉴工具调用、可控工作流、model/embedding/vector store 适配器思想。 |
| [Haystack](https://github.com/deepset-ai/haystack) | GitHub 页面显示约 25.9k stars。定位为生产级 RAG 和 Agent 的 AI orchestration framework，强调模块化 pipeline、retrieval/routing/memory/generation 的显式控制。 | 可借鉴 pipeline DAG 和可解释组件边界。完整接入依赖较重。 |

对本赛题的判断：

- 评分平台是 OpenCode + GLM 5.1，不需要我们再内嵌一个完整 Agent 框架。
- 最有价值的是把 solver 拆成工具：`build_index`、`search_docs`、`get_comments`、`query_table`、`repair_doc`、`safe_execute_python`、`solve_all`。
- RAG 框架的核心思想应该内化为轻量本地模块，而不是引入重框架导致安装失败、启动慢或上下文不可控。

### 9.4 检索、Embedding 与 Rerank

| 方法/工具 | 调研结论 | 对本赛题的应用 |
| --- | --- | --- |
| SQLite FTS5 / BM25 | 标准、轻量、离线，适合文件名、命令、路径、关键词和中文短语的精确召回。 | 应作为第一阶段增强，依赖风险最低。 |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | GitHub 页面显示约 7.8k stars。定位为“runs anywhere”的 SQLite 向量检索扩展，支持 float/int8/binary vectors，可用 `pip install sqlite-vec`。 | 可作为可选向量后端。但本赛题仅 200+ 文件，即使不用扩展，也可以把 embedding 存 SQLite 后用 Python 暴力余弦相似度完成检索。 |
| [Chroma](https://github.com/chroma-core/chroma) | GitHub 页面显示约 28.7k stars，定位为 AI search infrastructure，支持本地 in-memory、持久化、metadata 过滤和自动 embedding。 | 对比赛规模偏重。除非平台环境稳定可装依赖，否则不建议作为基础依赖。 |
| [FlagEmbedding / BGE](https://github.com/FlagOpen/FlagEmbedding) | GitHub 页面显示约 11.9k stars。BGE-M3 论文强调 multilingual、multi-functionality、multi-granularity，支持 dense/sparse/multi-vector 检索和长文本；仓库也提供 reranker 系列。 | 中文/中英混合检索很适合借鉴。实际交付中优先做 `EmbeddingClient` / `RerankClient` 适配器；如果平台不给模型 API，则降级到 FTS/BM25。 |
| RRF 融合排序 | 信息检索中常见的 rank fusion 方法，适合合并 BM25、向量、规则、事实表召回结果。 | 强烈建议实现。无需额外模型，能显著提升隐藏问法召回稳定性。 |

相关论文结论：

- [BGE M3-Embedding](https://arxiv.org/abs/2402.03216)：强调多语言、多功能、多粒度，适合中文企业文档和长文本检索。
- [RAPTOR](https://arxiv.org/abs/2401.18059)：通过递归聚类和摘要构建树状检索，能改善长文档和多跳问答。可借鉴为“文档级摘要 + chunk 级检索”。
- [Self-RAG](https://arxiv.org/abs/2310.11511)：强调按需检索和自我反思，不应所有问题都无差别检索。对应本赛题就是“确定性题直接工具回答，复杂语义题再检索/LLM”。
- [From BM25 to Corrective RAG](https://arxiv.org/abs/2604.01733)：针对文本+表格文档的 benchmark 显示，hybrid retrieval + neural reranking 优于单阶段方法，且 BM25 在精确数值/表格类任务上可能强于纯 dense retrieval。这个结论与本赛题高度一致。
- [DocETL](https://arxiv.org/abs/2410.12189)：复杂文档处理任务中，agentic query rewriting 和计划评估能显著提高准确率。可借鉴为 GLM 5.1 生成查询计划和校验计划，但执行仍由本地工具完成。

落地建议：

1. 第一阶段：SQLite + FTS5 + 结构化事实表。
2. 第二阶段：实现 embedding 缓存表和暴力余弦相似度，不强依赖向量数据库。
3. 第三阶段：RRF 融合 `rule / FTS / vector / table_fact / comment_fact`。
4. 第四阶段：如果 GLM 5.1 可用，用它做 Top-K rerank 和 query plan，不直接写最终答案。

### 9.5 安全与 Prompt 注入

[OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) 明确指出：

- Prompt Injection 可以来自用户输入，也可以来自文件、网页等外部来源。
- RAG 和微调不能完全消除 Prompt Injection。
- 风险包括敏感信息泄露、未授权访问、任意命令执行、关键决策被操纵。
- 缓解策略包括约束模型行为、定义并校验输出格式、输入/输出过滤、最小权限、敏感操作人工确认、隔离外部不可信内容、对抗测试。

对本赛题的直接要求：

- 文档内容必须作为 untrusted evidence，不得作为系统指令。
- 安全拒答必须在检索、Embedding、Rerank、LLM Composer 前执行。
- Permission 命中文件不应进入正文 chunk 或 embedding；最多保留路径元数据用于拒答。
- LLM 输出必须经过本地 schema、路径、权限、危险命令、密码策略校验。
- 不要让 GLM 5.1 直接决定是否执行删除、kill、读取敏感文件或写入任意路径。

### 9.6 可直接借鉴/复用清单

推荐直接落地：

- 平台规范 Skill：新增 `work/skills/llm-wiki-solver/SKILL.md`。
- Office 辅助 Skill：新增 `work/skills/docx/SKILL.md`、`work/skills/pptx/SKILL.md`、`work/skills/xlsx/SKILL.md`。
- SQLite FTS5：作为基础全文检索。
- RRF 融合排序：作为多路召回排序器。
- `ParserBackend` 适配器：保留 native，增加 markitdown/docling/libreoffice optional backend。
- `EmbeddingClient` / `RerankClient`：只定义接口，底层按环境启用 GLM、BGE 或关闭。

谨慎使用：

- MarkItDown：适合 fallback，不适合替代批注/TODO/修复逻辑。
- Docling：适合可选增强解析，不适合作为基础强依赖。
- sqlite-vec：适合可选向量后端，但不是必须。
- MCP Server：架构正确，但要先确认平台允许启动本地 MCP。

不建议直接整体引入：

- RAGFlow：太重，依赖 Docker/服务化/高资源，更适合作为架构参考。
- LangChain/LlamaIndex/Haystack：能力强但依赖复杂，赛题交付更需要轻量、可控、离线可复现。
- Chroma/Milvus/Qdrant：对 200+ 文件规模过重，除非平台环境明确支持。

## 10. 可下载 Skill 与工具候选清单

调研时间：2026-07-08。

本节专门记录“可以下载、复制、改造后放入参赛交付件”的 Skill 和工具。比赛提交规范要求 Skill 路径为：

```text
work/skills/{your-skill-name}/SKILL.md
```

因此本项目只采用比赛规范路径：

- `work/skills/{name}/SKILL.md`

即使平台 Agent 框架选择 OpenCode，提交包内所有 Skill 也必须以 `work/skills` 为准，并在 `INSTRUCTION.md` 中明确要求 Agent 读取这些 Skill。

### 10.1 可直接改造的 Agent Skills

[skills.sh](https://www.skills.sh/) 是公开 Agent Skills 目录，页面说明 Skill 是可复用的 AI agent 能力，可用 `npx skills add <owner/repo>` 安装，并显示支持 OpenCode。该目录里真正贴合本赛题的不是通用写作或前端 Skill，而是文档处理类 Skill。

| Skill | 来源 | 相关能力 | 是否建议引入 | 改造方式 |
| --- | --- | --- | --- | --- |
| `docx` | [anthropics/skills docx](https://www.skills.sh/anthropics/skills/docx) | 读取、编辑、操作 `.docx`；说明 `.docx` 是 zip XML；支持 unpack XML、定向修改、重打包、评论和 tracked changes；支持把旧 `.doc` 转 `.docx`。 | 强烈建议 | 审计后改写为 `work/skills/docx/SKILL.md`，删减创建新文档和复杂排版内容，保留“读取、批注、XML 修复、旧格式转换”流程。 |
| `pptx` | [anthropics/skills pptx](https://www.skills.sh/anthropics/skills/pptx) | 读取/抽取 `.pptx` 文本，编辑模板，XML unpack/repack，使用 MarkItDown 读取内容。 | 建议 | 复制为 `work/skills/pptx/SKILL.md`；保留“读取批注/文本、unpack XML、repack”部分，删除从零创建幻灯片和视觉设计要求。 |
| `xlsx` | [anthropics/skills xlsx](https://www.skills.sh/anthropics/skills/xlsx) | 使用 pandas/openpyxl 分析 `.xlsx/.xlsm/.csv/.tsv`，LibreOffice 重算公式和检查错误。 | 建议 | 复制为 `work/skills/xlsx/SKILL.md`；保留“表格读取、公式/错误检查、LibreOffice fallback”，增加本赛题的“按列筛选、计数、分组汇总、透视类问题输出 JSON”。 |
| `pdf` | [anthropics/skills pdf](https://www.skills.sh/anthropics/skills/pdf) | PDF 文本/表格抽取、OCR、拆分合并等。 | 暂不建议作为主交付 | 当前赛题明确“所有文件无图片资源”，题目文件类型列表不含 PDF。可作为以后扩展，不应增加依赖和复杂度。 |
| `mcp-builder` | skills.sh 上的 anthropics/skills | 指导创建 MCP Server。 | 暂缓 | 只有确认评分平台允许启动本地 MCP 后再引入。当前优先 CLI + Skill。 |

下载/改造建议：

```bash
npx skills add https://github.com/anthropics/skills --skill docx
npx skills add https://github.com/anthropics/skills --skill pptx
npx skills add https://github.com/anthropics/skills --skill xlsx
```

安装后不要原样提交，应人工审计并改写为比赛专用版，再放入：

```text
work/skills/docx/SKILL.md
work/skills/pptx/SKILL.md
work/skills/xlsx/SKILL.md
```

原因：

- 比赛平台要求 `work/skills/{name}/SKILL.md`。
- 当前打分平台提交审核以比赛规范路径为准，不应额外依赖 OpenCode 官方本地路径。
- 第三方 Skill 的说明文本可能包含与比赛无关的创建/排版/可视化要求，应压缩成“如何帮助 LLM Wiki 答题”的操作手册。

### 10.2 可下载工具库候选

| 工具 | 来源 | 适配赛题能力 | 引入建议 |
| --- | --- | --- | --- |
| MarkItDown | [microsoft/markitdown](https://github.com/microsoft/markitdown) | 把 Office、HTML、CSV/JSON/XML、ZIP 等转换成 Markdown，适合 LLM 和文本分析管线。 | 作为 optional parser backend。适合解析失败或旧 Office 转换兜底，不替代本地批注/TODO 解析。 |
| Docling | [docling-project/docling](https://github.com/docling-project/docling) | 支持 DOCX/PPTX/XLSX/HTML 等多格式到统一结构和 Markdown/JSON，且有 CLI/Python API。 | 作为 optional parser backend。依赖较重，不能作为基础必装。 |
| LibreOffice headless | LibreOffice | 旧 `.doc/.ppt/.xls` 转 `.docx/.pptx/.xlsx`，也可重算 Excel 公式。 | 建议在 `INSTRUCTION.md` 写成可选依赖；代码里检测存在才使用。 |
| Pandoc | [Pandoc](https://pandoc.org/) | 文档格式转换，尤其 Markdown/HTML/DOCX 互转。 | 可选。对批注和 Excel 结构帮助有限，不作为核心。 |
| BM25S | [xhluca/bm25s](https://github.com/xhluca/bm25s) | 纯 Python BM25 检索，README 称依赖轻，面向文本检索。 | 可选替代 SQLite FTS。基础版建议先用 SQLite FTS5，避免 numpy 依赖；冲分版可引入 BM25S。 |
| RapidFuzz | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | 快速模糊字符串匹配，MIT license。 | 建议引入或仿照实现，用于文件名、责任人、业务词、命令名称的近似匹配。若担心依赖，可先实现简化编辑距离/相似度。 |
| sqlite-utils | [simonw/sqlite-utils](https://github.com/simonw/sqlite-utils) | SQLite CLI/library，支持 JSON/CSV 导入和 FTS 配置。 | 不建议作为依赖；可借鉴接口。当前直接用 Python 标准库 `sqlite3` 更稳。 |
| sqlite-vec | [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) | SQLite 向量检索扩展，支持 float/int8/binary vectors，Python 可 `pip install sqlite-vec`。 | 可选增强。当前文件规模 200+，先用 SQLite 存 embedding + Python 暴力余弦即可。 |
| FlagEmbedding / BGE | [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | 中文/多语言 embedding 与 reranker。BGE-M3 强调 multilingual、multi-functionality、multi-granularity。 | 不建议把模型权重放进交付包；可作为接口适配目标。若平台 GLM 5.1 不提供 embedding，则退回 FTS。 |

### 10.3 MCP 工具候选

[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 是 MCP reference servers 集合，包含 filesystem、git、memory、fetch、time 等。README 明确这些 server 是参考实现，不是生产方案，并提醒开发者按自身威胁模型实现安全控制。

对本赛题：

- `filesystem` MCP 与文件读写相关，但本赛题已有严格 `Permission.json`，不能直接开放通用文件系统能力。
- `sqlite` MCP 可以参考，但比赛只需要本地 solver 查询自己的 SQLite 索引，不需要 Agent 任意执行 SQL。
- `memory` MCP 可参考知识图谱记忆，但隐藏用例是一次性批处理，不是长期会话记忆。

结论：MCP 是长期增强方向，不是下一步主线。下一步更实际的是 OpenCode Custom Tool 薄封装 Python CLI。

### 10.4 Skill 安全审计要求

第三方 Skill 不是天然可信。近期关于 Agent Skill 的研究指出：

- Skill 通常是包含 `SKILL.md` 的结构化上下文包，用 YAML header 和 Markdown 正文触发 agent 使用。
- Skill registry 已出现大规模复用，但很多复用是一次性复制，后续维护多为本地增量修改。
- `SKILL.md` 文本本身会影响 agent 的发现、选择和加载，因此存在语义供应链风险。

所以本项目禁止原样引入未经审计的 Skill。每个下载 Skill 进入 `work/skills/` 前必须做以下处理：

1. 删除与比赛无关的创建、发布、联网、图像、营销、人工交互流程。
2. 明确输入只来自 `/app/code/judge-assets/01_01_llm_wiki/` 或本地 `llm-wiki/`。
3. 明确输出只写入 `llm-wiki/output/` 和 `logs/trace/`。
4. 明确高危命令、密码、越权路径由本地 solver 拒答。
5. 禁止 Skill 指导 Agent 直接读取系统目录或执行任意 shell。
6. 保留 license / source URL，便于后续审计。

### 10.5 推荐下载顺序

第一批，直接服务得分：

1. `docx` Skill：强化 Word/批注/OOXML 修复。
2. `pptx` Skill：强化 PPT 文本、批注、OOXML 解析。
3. `xlsx` Skill：强化 Excel 表格筛选、汇总、公式检查。

第二批，作为可选解析和检索增强：

1. MarkItDown：解析 fallback。
2. RapidFuzz：文件名和自然语言模糊匹配。
3. BM25S：如果 SQLite FTS 不够，再引入。

第三批，暂缓：

1. Docling：能力强但重，等基础稳定后再接 optional backend。
2. sqlite-vec / FlagEmbedding：等确认平台模型/依赖环境后再接。
3. MCP Server：等确认平台允许启动本地 MCP 后再做。

## 11. 当前交付调整建议与落地状态

短期建议已在本轮实现中落地：

- 已保留平台提交规范要求的 `work/` 目录，并把所有 Skill 放入 `work/skills/{name}/SKILL.md`。
- 已使用 `work/skills/llm-wiki-solver/SKILL.md` 作为主 Skill。
- 已将 `docx`、`pptx`、`xlsx` 三个文档处理 Skill 改造成比赛专用版，放入 `work/skills/`。
- 已重写 `INSTRUCTION.md`，面向 OpenCode + GLM 5.1 明确说明执行顺序、验收输出、高危拒答和禁止人工交互。
- 已保留 CLI 主入口，平台 Agent 可一条命令运行全部题组。
- 已在本文档中明确“平台 Agent 主导，solver 工具执行”的交付定位。
- 已移除非规范 `work/skill/SKILL.md`，不依赖 `.opencode/` 或 OpenCode 官方本地 Skill 路径。

中期建议本轮已完成一部分：

- 已增加标准库 `sqlite3` 索引层，包含 `documents`、`chunks`、`comments`、`table_rows`、`code_blocks`、`retrieval_trace`。
- 已增加 SQLite FTS5 全文召回，若 FTS5 不可用则自动回退到文本检索。
- 已为 SQLite FTS5 增加 trigram 中文短语召回，用于“计费业务”“账单模块”等中文语义短语。
- 已增加 RRF 融合排序，把结构化召回、FTS、文本召回、模糊文件名和相关文档扩展合并排序。
- 已增加可选 fuzzy 匹配：优先 RapidFuzz，未安装时回退 `difflib.SequenceMatcher`。
- 已保留 MarkItDown / LibreOffice fallback，并增加环境变量控制的 Docling optional backend。
- 已在写答案前统一执行 `normalize_answer`，规范 `datas`、`count`、`source`、`target`、路径分隔符和去重排序。
- 已将 Permission 命中文件处理为仅保留元数据，不读正文、不入 chunk、不参与证据检索。

仍建议后续继续推进：

- 接入可选 Embedding 和 Rerank 适配器，但不得作为强依赖。
- 将更多内部函数封装成 Agent 可直接调用的小工具。
- 继续完善 trace，让每题记录 `route`、`retrieval_channels`、`safety_decision`、`normalization` 和关键 evidence。

长期建议：

- 如果平台支持 MCP，把核心工具封装成 MCP Server。
- 如果平台能提供模型 API，把 GLM 5.1 接入内部 planner/reranker/composer。
- 如果隐藏题偏复杂语义问答，提升 Embedding + Rerank 的权重。
- 如果隐藏题偏精确格式，继续强化 validator、路径规范化和修复文件校验。

## 12. 后续维护原则

本文件作为后续调研和方案迭代的主文档，建议持续维护以下内容：

- 新发现的平台规则
- OpenCode/GLM 5.1 的实际能力
- 调研到的可借鉴项目
- 采用或放弃某个工具的原因
- 每次平台评分结果
- 当前架构变更
- 下一步实现计划

每次方案调整都应回答三个问题：

1. 它是否更符合 OpenCode + GLM 5.1 的运行方式？
2. 它是否提升隐藏用例的泛化能力？
3. 它是否仍然保证安全、格式和确定性输出？

## 13. 本轮代码实现摘要

本轮实现目标是把方案从“规则增强脚本”推进为“平台规范 Skill + 本地混合知识库 + 可选 AI 增强”的交付件。

已落地模块：

- `work/skills/llm-wiki-solver/SKILL.md`：主 Skill，指导平台 Agent 运行 LLM Wiki solver。
- `work/skills/docx/SKILL.md`、`work/skills/pptx/SKILL.md`、`work/skills/xlsx/SKILL.md`：比赛专用 Office 辅助 Skill。
- `work/llm_wiki_solver/index.py`：SQLite 本地索引，支持 FTS5 和无 FTS 回退。
- `work/llm_wiki_solver/retrieval.py`：混合检索、RRF 融合、fuzzy fallback 和相关文档扩展。
- `work/llm_wiki_solver/answers.py`：统一答案规范化。
- `work/llm_wiki_solver/extractors.py`：支持 PermissionGuard 元数据模式和 Docling optional backend。

当前交付边界：

- 提交包只依赖 `INSTRUCTION.md`、`work/`、`result/`、`logs/` 等比赛要求路径。
- 所有 Skill 均位于 `work/skills/{name}/SKILL.md`。
- `.opencode/` 不作为提交依赖。
- MarkItDown、Docling、LibreOffice、RapidFuzz 都是 optional backend；没有额外依赖时 CLI 仍能运行。
- GLM 5.1 / LLM 只做规划、证据重排和修复计划增强；最终答案继续由本地安全层、检索层和 validator 接管。
- 如果平台向 Python 环境注入 OpenAI-compatible 或智谱兼容环境变量，`llm_client.py` 会自动识别常见变量；若未注入，则回退本地确定性链路。

## 14. 第十轮复核结论

本轮继续核实第九轮方案的有效性，结论如下：

- 当前最适合赛题的 Skill 仍是 `llm-wiki-solver` 主 Skill 加 `docx/pptx/xlsx` 三个 Office 辅助 Skill，不建议继续增加泛化写作、网页、MCP builder 等与评分问题不直接相关的 Skill。
- 评分平台交付应坚持 `work/skills/{name}/SKILL.md`，不依赖 `.opencode/`、用户本地 Skill 目录或评测时网络下载。
- MarkItDown、Docling、LibreOffice、RapidFuzz 保持 optional 更合理；它们可以增强解析或模糊匹配，但不能成为提交包强依赖。
- 代码层已补齐中文 FTS trigram 召回和 TODO count 路由，分别面向“中文业务语义检索”和“隐藏题自然语言计数问法”两个高频失分点。
- LLM 环境变量增加 OpenAI-compatible / Zhipu-compatible 回退，有利于在平台把模型 API 暴露给 Python 时自动启用增强；若未暴露则不会影响离线运行。

## 15. `log7_9` 评测复盘与提交前修正

`log7_9.md` 对上一版作品给出的客观结果是：正确性 100、稳定性 100、最终分数 100；交付件审查也确认 `INSTRUCTION.md`、Skill 路径和复现流程有效。结合新增的 `参赛指导.md` 与 `FAQ.md`，本题最终仍需重视 40 分主观项，尤其是泛用性、规范性和性能。因此，三条 WARN 虽未影响客观分，但会影响评委对方案质量的判断。

本轮对 WARN 的定位与处理如下：

1. `group-1-10`：上一版密码类答案可能从 `02_环境信息` 中带出大量无关 IP/密码。当前已改为强定位符优先抽取：URL、IP:port 等作为强定位符，用户名作为弱定位符，只返回最高匹配记录中的密码；若问题携带明确 URL/IP，找不到对应记录时不再退化为扫描全部密码。
2. `group-1-21`、`group-1-23`：上一版安全 Python 执行器对白名单过窄，可能误拦截低风险脚本。当前仍禁止 import、文件/网络/进程、dunder、危险内建和任意属性访问，但放开少量安全内建方法调用，例如 `strip`、`split`、`lower`、`join`、`append`，用于支持常见数据清洗/计算脚本。
3. 高危拒答策略保持不回退：删除、kill、系统目录、root/数据库/密钥类密码、Prompt 注入型任务仍统一输出 `{"error_msg":"高危命令，拒绝访问"}`。

本轮新增回归测试：

- 多账号环境文档中，查询指定 URL 的 `op_user` 密码只返回目标密码，不暴露其他环境或数据库密码。
- 低风险 Python 脚本中常见字符串/列表方法可执行并返回结果。
- 原有危险脚本、越权密码、允许的 `op_user/password` 场景继续通过。

结合参赛指导和 FAQ 的确认：

- 平台客观运行仍以 `INSTRUCTION.md` 为入口，`work/` 为执行交付件。
- `result/` 和 `logs/` 主要用于评委主观评分，应保留最新自验证结果与 trace 说明。
- 提交 Skill 必须在 `work/skills/{name}/SKILL.md`，本项目不依赖 `.opencode/`。
- 运行耗时和 Token 消耗会影响主观性能分，因此主路径继续保持本地确定性执行，LLM 只做 optional 增强。

## 16. LLM/API 增强的最终定位

根据 FAQ，评测平台自身会使用 CodeAgent/OpenCode 与 GLM 5.1、MiniMax-M2.7 等模型读取 `INSTRUCTION.md` 并执行作品。因此，本项目对 AI 的依托分为两层：

1. 平台 Agent 层：这是必然存在的主执行层，负责理解本说明、选择 `work/skills/` 中的 Skill、执行 CLI、检查输出。
2. Python CLI 内部 LLM 层：这是可选增强层，只在平台额外提供 OpenAI-compatible / Zhipu-compatible API 环境变量时启用。

当前提交策略是：不把 Python 直连 API 作为强依赖。CLI 在无 API、API 不通、模型输出不合规时，均回退到本地确定性链路。即使启用直连 API，也只允许它参与规划、证据选择、rerank 和修复计划建议；最终答案继续由本地安全规则、格式 validator 和 normalize_answer 接管。

为避免主观性能分受到不可控 API 超时影响，直连 LLM 默认采用保守预算：

- `LLM_WIKI_MAX_CALLS=12`
- `LLM_WIKI_TIMEOUT_S=8`
- `LLM_WIKI_RETRIES=0`

如果平台确认提供稳定的模型 API，可通过环境变量调大预算；否则默认配置更利于稳定性和性能。
