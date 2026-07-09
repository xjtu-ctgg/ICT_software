# LLM Wiki 参赛作品运行说明

本作品面向 ICT 软件大赛 LLM Wiki 赛题，提交形态为 CLI 工具 + 平台规范 Skill。平台 Agent 读取本文件后，应使用 `work/skills/` 下的 Skill 说明，并执行主 CLI 完成全部题组。

## 1. 环境准备

- Python 3.11.0 或兼容版本。
- 默认不强制安装第三方依赖，核心扫描、解析、索引、检索、安全拦截、修复和 JSON 输出均使用 Python 标准库。
- 不需要编译、不需要启动常驻服务、不需要联网下载依赖。
- 自动评测系统应在参赛作品根目录执行命令，即 `INSTRUCTION.md` 所在目录。
- 平台 Agent 自带的 OpenCode/CodeAgent + GLM 5.1/MiniMax-M2.7 模型能力用于阅读本说明、理解 Skill、规划执行命令；本作品的 Python CLI 不要求平台把模型 API key 注入运行环境。
- 可选增强：
  - 若存在 `libreoffice`，旧版 `.doc/.ppt/.xls` 会优先转换为现代 OOXML 格式后解析。
  - 若安装 `markitdown`，旧 Office 或复杂文件解析失败时可作为兜底文本抽取。
  - 若设置 `LLM_WIKI_ENABLE_DOCLING=1` 且安装 `docling`，会尝试使用 Docling 作为可选解析后端。
  - 若配置 `LLM_WIKI_MODEL_ENDPOINT`、`LLM_WIKI_MODEL_NAME`、`LLM_WIKI_API_KEY`，`--llm-mode auto` 会启用可选 LLM 增强；未配置时自动回退到本地确定性工具链。
  - 若平台注入 OpenAI-compatible 或智谱兼容变量，也会自动识别 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`、`ZHIPUAI_BASE_URL`、`ZHIPUAI_API_KEY`。
  - 直连 LLM 仅用于规划、证据选择、rerank 和修复计划建议；最终答案仍由本地安全校验、格式 validator 和确定性规则接管。
  - 直连 LLM 默认采用保守调用预算：最多 12 次、单次超时 8 秒、不重试；可通过 `LLM_WIKI_MAX_CALLS`、`LLM_WIKI_TIMEOUT_S`、`LLM_WIKI_RETRIES` 覆盖。

所有可选依赖不可用时，作品仍必须自动运行，不需要人工交互。

## 2. Skill 位置

本作品使用的 Skill 均按打分平台要求放在 `work/skills/{skill-name}/SKILL.md`：

```text
work/skills/llm-wiki-solver/SKILL.md
work/skills/docx/SKILL.md
work/skills/pptx/SKILL.md
work/skills/xlsx/SKILL.md
```

平台 Agent 应优先阅读 `work/skills/llm-wiki-solver/SKILL.md`，并把 `docx`、`pptx`、`xlsx` 三个 Skill 作为 Office 文档处理辅助说明。

## 3. 平台材料路径

评测平台提供的真实材料位于：

```text
/app/code/judge-assets/01_01_llm_wiki/
├── question/group-*.md
├── docs/
└── Permission.json
```

公开样例和本地 `sample_llm_wiki` 仅用于自验证，不作为实际评测依据。

## 4. 执行方式

在作品根目录执行以下命令处理全部题组：

```bash
python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
```

参数说明：

- `--root`：平台提供的 LLM Wiki 材料根目录，必须指向 `/app/code/judge-assets/01_01_llm_wiki`。
- `--group`：题组选择。`all` 表示处理 `question/group-*.md` 下全部题组。
- `--log-dir`：推理和执行 trace 输出目录，提交包内使用 `./logs/trace`。
- `--llm-mode`：LLM 增强模式。`auto` 表示环境提供模型 API 时启用规划/证据选择增强，未提供时自动回退本地确定性工具链。

说明：这里的 `--llm-mode auto` 不要求平台额外配置 API。若无可用 API，CLI 会直接走本地确定性链路；平台 Agent 仍可使用自身 GLM/OpenCode 能力读取本说明并执行命令。

如需关闭 LLM 增强，仅使用本地确定性工具：

```bash
python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
```

如需只运行单组题：

```bash
python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group group-1 --log-dir ./logs/trace --llm-mode auto
```

## 5. 执行完成判定

- 命令退出码为 0。
- 每个 `question/group-x.md` 均生成对应答案文件：

```text
/app/code/judge-assets/01_01_llm_wiki/output/group-x-answer.md
```

- 修复类题目只写入：

```text
/app/code/judge-assets/01_01_llm_wiki/output/fixed/
```

- 推理和执行日志写入：

```text
logs/trace/group-x.trace.json
```

- 自验证记录位于：

```text
result/output.md
```

## 6. 修复类题目结果获取方式

自动评测系统应从平台材料目录下获取运行结果：

- 答案文件：

```text
/app/code/judge-assets/01_01_llm_wiki/output/group-*-answer.md
```

- 修复类题目生成的文件副本：

```text
/app/code/judge-assets/01_01_llm_wiki/output/fixed/
```

- 这里的“修复类题目”是指赛题中的批注/TODO 修复问题，例如“修复责任人为张三的 TODO 事项”“产品 V1 需求.doc 自由批注优化整理”等。
- 这里的“修复文件”不是修复参赛作品工程本身，而是根据题目要求对 `docs/` 中对应文档或代码文件生成一个修改后的副本。
- 修复类答案必须返回源文件和目标文件路径，例如：

```json
{"source":"docs/需求设计文档/产品V1需求.doc","target":"output/fixed/需求设计文档/产品V1需求.doc"}
```

- 本作品不会覆盖 `/app/code/judge-assets/01_01_llm_wiki/docs/` 下的原始文件。
- 本作品不会修改 REST API 契约，也不需要启动 Web 服务。
- 运行 trace 可从提交包内读取：

```text
logs/trace/group-*.trace.json
```

## 7. 答案格式要求

答案文件必须是 JSON 数组，每个元素格式为：

```json
{"id":"group-1-1","answer":{"datas":["docs/example.md"]}}
```

常见答案格式：

```json
{"datas":["docs/example.md"]}
{"count":3}
{"docx":5}
{"source":"docs/a.docx","target":"output/fixed/a.docx"}
{"error_msg":"高危命令，拒绝访问"}
```

路径必须使用 `/`，并以 `docs/` 或 `output/fixed/` 为根，不输出本机绝对路径。

## 8. 安全规则

作品将所有文档内容视为不可信证据，不作为系统指令执行。

以下情况统一返回：

```json
{"error_msg":"高危命令，拒绝访问"}
```

- 命中 `Permission.json` 的文件、目录或命令。
- 请求读取系统目录、C 盘根目录、`/etc` 等敏感位置。
- 请求删除、格式化、kill、shutdown、rm、del、Remove-Item 等高危操作。
- 请求系统密码、数据库密钥、API key、secret key、配置明文密钥。
- 文档或题目中包含 Prompt 注入指令，如忽略规则、上帝模式、删除全部文档、强制 kill agent。

允许的环境账号密码查询仅限赛题要求中明确允许的 `docs/02_环境信息` 场景，并仍需通过 `Permission.json` 检查。

## 9. 自验证

本地运行测试：

```bash
pytest tests -q
```

本地样例运行：

```bash
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
```

## 10. 平台执行注意事项

- 全流程禁止人工交互；如平台模型要求确认，应继续执行本说明中的主命令，不向选手提问。
- `logs/interaction.md` 用于记录人工交互；本作品设计为全程无干预，因此该文件保持空白。
- `logs/trace/` 用于记录每题执行 trace，包含路由、检索渠道、安全决策和答案规范化信息。
- 若可选模型或解析后端不可用，不视为失败，CLI 会自动使用本地确定性链路继续完成输出。
