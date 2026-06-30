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
| `solver.py` | 题型分类、安全前置、文件/TODO/修复/表格/代码执行等专用求解器 |
| `llm_client.py` | 可选 LLM 适配、环境读取、fake client |
| `llm_pipeline.py` | 复杂理解、局部索引、证据检索、答案校验 |
| `extractors.py` | 扫描 `docs`，抽取文本、Office 批注、代码注释、XLSX 行列表格 |
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

`DocumentRecord.tables` 用于保存从 `.xlsx` 中抽取出的行列数据：

```python
[
    ["客户", "金额", "状态"],
    ["A", "10", "已完成"],
    ["B", "7", "已完成"],
]
```

表格分析始终基于表头匹配，不依赖 sheet 名称或固定列号。

## 4. 执行流程

1. 加载 `Permission.json`。
2. 扫描 `llm-wiki/docs`，生成内存索引。
3. 遍历 `llm-wiki/question/group-*.md`。
4. 对每题执行：
   - 提取标题和难度。
   - 检查 Permission、危险命令、危险密码、注入提示。
   - 识别题型。
   - 调用专用 solver：文件索引、批注/TODO、修复、表格分析、安全 Python 执行或知识检索。
   - 返回标准 answer dict。
5. 写入 `llm-wiki/output/group-x-answer.md`。
6. 修复类题目把文件写入 `llm-wiki/output/fixed/...`；文本文件应用结构化 patch，`.docx/.pptx/.xlsx` 尝试 zip 内 XML 最小替换，其他文件保底复制。
7. 写入 `logs/trace/group-x.trace.json`，包含 `llm_used`、`fallback_reason`、`evidence_sources`、`validation`。

## 5. 题型处理策略

- 文件数量：识别 `docx文件的数量`、`统计全项目 doc 总数量` 等模式，返回 `{suffix: count}`。
- 文件路径：识别显式文件名，返回 `{"datas": ["docs/..."]}`。
- 批注数量：优先限定指定文件，否则统计相关候选文件。
- 责任人/日期 TODO：抽取 `责任人为X`、`待X处理`、`X的TODO`、`截止日期为YYYYMMDD` 等条件，返回 TODO 原文列表；支持责任人和截止日期组合查询。
- 修复 TODO：定位含目标责任人的文件，写入 `output/fixed`；文本类文件会把匹配 TODO 标记为 `status: done`，有 LLM repair plan 时可按结构化操作增强修改，二进制文件保底复制，返回 `source/target`。
- XLSX 表格汇总：解析 `sharedStrings` 和 `worksheet` 行列后，支持 `按客户汇总金额` 这类表头驱动的分组求和。
- XLSX 筛选和计数：支持 `状态为已完成的客户列表`、`状态为已完成的记录数量` 等条件筛选；支持 `状态为已完成且客户为A` 的多条件过滤。
- XLSX 条件汇总：支持 `按客户汇总状态为已完成的金额`，先按条件过滤，再按分组列求和。
- Python 安全执行：对 `运行xxx.py并返回输出结果` 类问题，使用 AST 白名单执行安全 Python 子集，捕获 stdout 返回；包含 import、属性访问、文件系统、进程、网络或危险路径时拒答。
- 环境密码：只允许 `02_环境信息` 中的环境账号密码，返回 `datas`。
- 高危操作：统一返回 `error_msg`。
- 普通知识问答：检索相关文档，返回路径加摘要。
- 可选 LLM 增强：当题目较难或规则置信度不足时，调用 planner/retriever/composer/repair_planner/validator 链路；任何 LLM 输出都必须经过本地安全和格式校验。

## 6. 安全执行与防护边界

安全逻辑在 LLM 前置执行，并在 LLM 输出后再次校验：

- `Permission.json` 支持目录、命令、文件名 deny 列表，支持简单 glob。
- 内置危险命令补充拦截：`rm/rmdir/del/Remove-Item/format/mkfs/shutdown/reboot/kill/taskkill` 等。
- 密码类问题默认拒绝；只有明确环境账号且命中 `docs/02_环境信息` 的场景允许读取。
- Prompt 注入内容只作为普通文本进入索引，不会改变系统执行策略。
- 修复类题目只允许从 `docs/` 读取并向 `output/fixed/` 写入。
- Python 执行只允许安全 AST 子集：字面量、赋值、简单算术、函数定义、返回、for 循环、`+=`、白名单 builtins 和当前文件安全函数调用；拒绝 import、属性访问、dunder 名称、文件/网络/进程相关能力。

## 7. 测试设计

当前测试覆盖：

- `tests/test_permissions.py`：Permission 文件/目录/命令 glob。
- `tests/test_comments.py`：TODO 中英文冒号、空格、代码注释和自由批注。
- `tests/test_cli_integration.py`：小型 `llm-wiki` 端到端，覆盖数量、路径、批注统计、责任人筛选、截止日期筛选、文本修复、允许环境密码、拒绝 Permission 文件和危险命令、XLSX 汇总/筛选/计数/多条件/条件汇总、安全 Python 执行和危险 Python 拒答。
- `tests/test_llm_enhancement.py`：LLM 可选增强、fake LLM、trace、validator、fallback。
- 修复安全测试：LLM repair plan 不能写出 `output/fixed/`，也不能写入危险命令或密钥类内容。

推荐后续增强：

- `.pptx/.xlsx` 批注抽取与修复样例。
- 旧版 `.doc/.ppt/.xls` 转换工具集成测试。
- 更复杂 Excel 透视图、公式、跨 sheet 聚合题。
- 更复杂代码片段静态求值和安全执行题。
- Prompt 注入文档内容题。

## 8. 后续增强接口

当前作品不强制依赖外部 LLM。若平台提供模型，可在 `solver.py` 的普通知识问答和修复题中加入：

- 查询改写。
- 多轮检索。
- 证据片段压缩。
- 修复计划生成。
- JSON answer 自检。

安全策略仍必须在 LLM 前后各执行一次，LLM 不允许直接决定是否访问黑名单路径或执行命令。
