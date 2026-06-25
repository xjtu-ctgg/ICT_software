# LLM Wiki 参赛作品运行说明

## 运行环境

- Python 3.11.0 或兼容版本。
- 默认不强制依赖第三方包，使用标准库完成扫描、解析、检索、权限拦截和 JSON 输出。
- 若配置了 LLM 环境变量，作品会以 `auto` 模式启用可选 LLM 增强；未配置时完全回退到规则链。
- LLM 增强仅用于规划、检索和修复建议生成，所有输出都受 schema / function-call 约束，最终仍由本地 validator 接管。
- 若验收环境包含旧版 `.doc/.ppt/.xls`，可按平台能力额外安装 MarkItDown、LibreOffice 或 Unstructured 作为转换增强；本作品核心流程不依赖这些工具。

## 目录要求

平台解压后应形成如下结构：

```text
.
├── INSTRUCTION.md
├── work/
├── result/
├── logs/
└── llm-wiki/
    ├── docs/
    ├── question/
    ├── output/
    ├── README.md
    └── Permission.json
```

其中 `llm-wiki` 由赛题验证环境释放到 `work` 同级目录。

## 执行命令

在压缩包根目录执行：

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace
```

关闭 LLM 增强：

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group all --log-dir ./logs/trace --llm-mode off
```

如果只验证某一组问题：

```bash
python work/llm_wiki_solver/main.py --root ./llm-wiki --group group-1 --log-dir ./logs/trace
```

## 输出

- 答案文件：`llm-wiki/output/group-x-answer.md`
- 修复文件：`llm-wiki/output/fixed/...`
- 推理 trace：`logs/trace/group-x.trace.json`
- 人工交互记录：`logs/interaction.md`
- LLM 模式：`off` / `auto` / `required`
- 修复题会在 trace 中记录 `repair_plan`，并将结果写入 `llm-wiki/output/fixed/`。

答案文件严格为 JSON 数组，每个元素格式如下：

```json
{"id":"group-1-1","answer":{"datas":["docs/example.md"]}}
```

高危问题统一输出：

```json
{"error_msg":"高危命令，拒绝访问"}
```

## 自验证

本仓库内可运行：

```bash
pytest tests -q
```

也可执行随包自验证样例：

```bash
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace
```
