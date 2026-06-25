# LLM Wiki 代码流程与实现计划

## 1. 交付目录

```text
.
├── INSTRUCTION.md
├── docs/
│   ├── LLM-Wiki-赛题分析与技术方案.md
│   └── LLM-Wiki-代码流程与实现计划.md
├── work/
│   ├── llm_wiki_solver/
│   │   ├── main.py
│   │   ├── solver.py
│   │   ├── extractors.py
│   │   ├── comments.py
│   │   ├── permissions.py
│   │   ├── search.py
│   │   └── models.py
│   └── skill/
│       └── SKILL.md
├── result/
│   └── output.md
└── logs/
    ├── interaction.md
    └── trace/
```

运行时 `llm-wiki` 与 `work` 同级：

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace
```

可选增强模式：

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace --llm-mode auto
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace --llm-mode off
```

## 2. 模块职责

| 模块 | 职责 |
| --- | --- |
| `main.py` | CLI 参数解析、遍历 question group、写 answer 文件 |
| `solver.py` | 题型分类、安全前置、各类题专用求解器 |
| `llm_client.py` | 可选 LLM 适配、环境读取、fake client |
| `llm_pipeline.py` | 复杂理解、局部索引、证据检索、答案校验 |
| `extractors.py` | 扫描 `docs`，抽取文本、Office 批注、代码注释 |
| `comments.py` | 结构化 TODO 和自由批注解析 |
| `permissions.py` | Permission.json 与默认危险动作拦截 |
| `search.py` | 文件名抽取、路径匹配、轻量文本检索 |
| `models.py` | `DocumentRecord`、`CommentRecord`、`Question`、`Answer` |

## 3. 核心数据结构

```python
DocumentRecord(
    path=Path,
    rel_path="docs/05_需求设计/产品规则详解.docx",
    suffix="docx",
    folder="05_需求设计",
    text="...",
    tables=[],
    comments=[CommentRecord(...)],
    todos=[CommentRecord(...)],
    metadata={},
)
```

`CommentRecord.text` 使用统一格式：

```text
todo: 补充产品报价字段, to: 李四,end_date: 20251231
```

自由批注保留原文，`kind="free"`。

## 4. 执行流程

1. 加载 `Permission.json`。
2. 扫描 `llm-wiki/docs`，生成内存索引。
3. 遍历 `llm-wiki/question/group-*.md`。
4. 对每题执行：
   - 提取标题和难度。
   - 检查 Permission、危险命令、危险密码、注入提示。
   - 识别题型。
   - 调用专用 solver。
   - 返回标准 answer dict。
5. 写入 `llm-wiki/output/group-x-answer.md`。
6. 修复类题目把文件写入 `llm-wiki/output/fixed/...`；文本文件应用结构化 patch，`.docx/.pptx/.xlsx` 尝试 zip 内 XML 最小替换，其他文件保底复制。
7. 写入 `logs/trace/group-x.trace.json`，包含 `llm_used`、`fallback_reason`、`evidence_sources`、`validation`。

## 5. 题型处理策略

- 文件数量：识别 `docx文件的数量`、`统计全项目 doc 总数量` 等模式，返回 `{suffix: count}`。
- 文件路径：识别显式文件名，返回 `{"datas": ["docs/..."]}`。
- 批注数量：优先限定指定文件，否则统计相关候选文件。
- 责任人 TODO：抽取 `责任人为X`、`待X处理`、`X的TODO`，返回 TODO 原文列表。
- 修复 TODO：定位含目标责任人的文件，写入 `output/fixed`；有 LLM repair plan 时按结构化操作修改，模型不可用时保底复制，返回 `source/target`。
- 环境密码：只允许 `02_环境信息` 中的环境账号密码，返回 `datas`。
- 高危操作：统一返回 `error_msg`。
- 普通知识问答：检索相关文档，返回路径加摘要。
- 可选 LLM 增强：当题目较难或规则置信度不足时，调用 planner/retriever/composer/validator 链路。
- 可选 LLM 增强：当题目较难或规则置信度不足时，调用 planner/retriever/composer/repair_planner/validator 链路。

## 6. 测试设计

当前测试覆盖：

- `tests/test_permissions.py`：Permission 文件/目录/命令 glob。
- `tests/test_comments.py`：TODO 中英文冒号、空格、代码注释和自由批注。
- `tests/test_cli_integration.py`：小型 `llm-wiki` 端到端，覆盖数量、路径、批注统计、责任人筛选、修复、允许环境密码、拒绝 Permission 文件和危险命令。
- `tests/test_llm_enhancement.py`：LLM 可选增强、fake LLM、trace、validator、fallback。
- 修复安全测试：LLM repair plan 不能写出 `output/fixed/`，也不能写入危险命令或密钥类内容。

推荐后续增强：

- `.pptx/.xlsx` 批注抽取与修复样例。
- 旧版 `.doc/.ppt/.xls` 转换工具集成测试。
- Excel 透视图/聚合题。
- 代码片段安全执行题。
- Prompt 注入文档内容题。

## 7. 后续增强接口

第一版不强制依赖外部 LLM。若平台提供模型，可在 `solver.py` 的普通知识问答和修复题中加入：

- 查询改写。
- 多轮检索。
- 证据片段压缩。
- 修复计划生成。
- JSON answer 自检。

安全策略仍必须在 LLM 前后各执行一次，LLM 不允许直接决定是否访问黑名单路径或执行命令。
