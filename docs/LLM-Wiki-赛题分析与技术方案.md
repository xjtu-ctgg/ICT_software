# LLM Wiki 赛题分析与技术方案

## 1. 赛题目标与硬约束

本题要求构建一个面向 `llm-wiki` 目录的离线 Wiki 操作系统。系统需要在 200+ 混合格式文件上完成检索、统计、批注/TODO 管理、文档修复、有限文件运行/分析以及安全拒答，并把每组问题输出为严格 JSON 数组。

以赛题“略微修改调整后的赛题大纲”为准，关键约束如下：

- 解压运行时，`work` 同级存在 `llm-wiki` 目录。
- 代码解析和格式化文件生成使用 Python 3.11。
- `docs` 下文件夹名称、归类和文件类型不固定，不能依赖目录名判断业务含义。
- 可统计文件类型仅限 `doc/docx/ppt/pptx/xls/xlsx/xml/java/py/html/md/js`。
- Office 文件和代码文件都可能包含结构化批注或自由批注。
- 修复类答案必须把文件写到 `llm-wiki/output/fixed/` 下，不能覆盖原始 `docs` 文件。
- 任何命中 `Permission.json` 的目录、命令、文件，以及系统/数据库/密钥等危险密码查询，统一返回 `{"error_msg":"高危命令，拒绝访问"}`。
- 输出路径统一以 `docs/` 或 `output/fixed/` 为根，不输出本机绝对路径。

## 2. 评分点拆解

| 能力 | 题型 | 推荐策略 |
| --- | --- | --- |
| 文件知识库 | 文件类型数量、文件路径、业务相关文件 | 全量扫描建立元数据索引，确定性查询优先 |
| 批注/TODO 管理 | 统计数量、责任人筛选、日期筛选 | 解析结构化字段，统一规范化为 `todo: ..., to: ...,end_date: ...` |
| 文档修复 | 按批注/TODO 生成修复文件 | 文本文件应用结构化 patch；OOXML Office 文件做 zip 内 XML 最小替换；其他二进制保底复制 |
| 文件运行/分析 | 代码片段结果、Excel 透视图 | 建议沙箱化解释器/只读分析，先覆盖可静态求值和表格聚合 |
| 安全防护 | 高危命令、密码、Prompt 注入 | 前置规则拦截，文档内容只作为数据，不作为指令 |
| 标准输出 | answer_format 对齐 | 每题答案通过统一 formatter 校验 |

## 3. 外部方法调研与取舍

去年参考中提到 Dify Workflow + Knowledge Base + Rerank + DeepResearch 多轮检索。这一思路适合企业 Wiki 复杂问答，但本赛题的验收环境强调离线 zip 交付、文件修改和安全拦截，因此不适合作为唯一方案。

可借鉴的方法如下：

- 模块化 RAG：把检索、重排、生成和校验分层，适合混合题型系统。
- RAPTOR：通过分层摘要改善跨文档问题召回，本题可用于“涉及某业务的文件”这类宽泛问题。
- GraphRAG：抽取实体、文件、业务概念关系，适合全局知识组织，但实现成本较高，可作为增强项。
- ReAct/工具调用：将自然语言问题路由到确定性工具，适合 CodeAgent 运行模式。
- OWASP LLM Prompt Injection 防护：把外部文档视为不可信数据，关键动作由本地策略控制。

本方案采用“确定性规则优先，LLM 辅助复杂理解”的路线。简单和中等题尽量由索引和规则直接求解，困难题可在安全前置通过后使用多轮检索上下文辅助回答。

默认运行策略是 `auto`：规则能解决的题直接回答；复杂题在模型可用时进入 LLM 增强，模型不可用时自动回退。

## 4. 总体技术路线

### 4.1 文档层

扫描 `llm-wiki/docs` 下所有文件，形成 `DocumentRecord`：

- 路径、后缀、文件夹、正文文本。
- Office 批注、代码 TODO、自由批注。
- 表格文本和结构化行列信息。
- 解析失败时保留元数据并写 trace，避免单文件影响整组题。

`.docx/.pptx/.xlsx` 优先走 OOXML zip 解析；文本类文件直接按 UTF-8/GB18030/Latin-1 读取；旧版 `.doc/.ppt/.xls` 可通过 MarkItDown、LibreOffice 或 Unstructured 作为可选依赖兜底。

### 4.2 检索层

第一版实现轻量可控检索：

- 元数据过滤：后缀、文件名、路径片段、责任人、日期。
- 字符级关键词匹配：适配中文短语和命令文本。
- 结果排序：命中标题 token 越多越靠前。

增强方向：

- BM25 或 SQLite FTS5。
- Embedding + Rerank。
- 文件摘要树和业务实体图。

### 4.3 任务层

问题处理流程：

1. 安全预判。
2. 题型分类。
3. 专用 solver 求解。
4. answer formatter 校验。
5. 写入 `llm-wiki/output/group-x-answer.md`。
6. 写入 `logs/trace/group-x.trace.json`。

### 4.4 LLM 辅助复杂理解层

LLM 只承担“复杂理解”，不承担安全裁决。

- `QuestionPlanner`：把题目转成可执行子查询和答案格式，输出必须经过 schema / tool-call 约束。
- `EvidenceRetriever`：从事实、chunk、摘要三路检索证据并做融合排序。
- `AnswerComposer`：基于证据产出答案草稿，输出必须经过 schema / tool-call 约束。
- `RepairPlanner`：将修复题转成结构化 repair plan，明确 `source`、`target` 和操作列表。
- `AnswerValidator`：检查输出是否符合 answer_format 与安全策略，失败时回退到规则链。
- `Fallback`：任意环节失败都回到规则链，不影响简单题稳定性。

题型按确定性程度排序：安全拒答、数量统计、路径查找、批注统计、责任人筛选、修复、密码允许查询、普通知识问答。

### 4.4 安全层

安全策略独立于 LLM：

- `Permission.json` 支持精确和 `*` glob。
- 默认危险命令补充拦截：`rm/rmdir/del/Remove-Item/format/mkfs/shutdown/reboot/kill/taskkill`。
- 路径归一化后检查文件名和目录片段。
- 密码查询默认拒绝，只有明确环境账号且位于 `docs/02_环境信息` 的场景允许。
- 文档中的“忽略规则、上帝模式、删除文件、kill 进程”等注入文本只作为普通文本，不进入系统指令。
- 修复计划只允许读取 `docs/` 源文件并写入 `output/fixed/`，任何目标越界、Permission 命中、危险命令或密钥类 patch 内容都会拒绝执行并回退。

## 5. 风险与应对

- Office 旧格式解析不稳定：通过可选依赖说明和文本兜底降低风险。
- 自然语言题型表达多样：先覆盖样例和高频模式，再用检索结果兜底为 `datas`。
- 文档修复语义复杂：当前对文本和 OOXML Office 文件执行最小替换，无法定位文本节点时保底复制并记录 trace。
- 误拒答影响得分：对 `02_环境信息` 环境密码设白名单，其余密码和 Permission 命中严格拒绝。
- 输出格式一旦多文本会失败：最终仅写 JSON，不写解释。

## 6. 推荐参赛亮点

- 明确的安全策略和可审计 trace。
- 规则与 LLM 分层，避免 Prompt 注入控制执行。
- 对多格式文档做统一 `DocumentRecord` 抽象。
- 可扩展到 GraphRAG/DeepResearch，但基础版无需外部服务即可跑通。
