# LLM Wiki 工作台说明

当前仓库根目录就是唯一迭代工作台，不再维护第二套 `submission/` 或 `deliverable/` 代码。

## 日常修改位置

- 运行入口：`INSTRUCTION.md`
- 参赛代码：`work/`
- 自动化测试：`tests/`
- 本地样例：`sample_llm_wiki/`
- 自验证记录：`result/output.md`
- 运行/推理日志：`logs/`
- 赛题要求备查：`requirement/`
- 方案和历史计划：`docs/`
- 迭代状态记录：`CHANGELOG_AND_STATUS.md`

## 平台提交时打包

提交前只需要从根目录打包以下内容：

```text
INSTRUCTION.md
work/
result/
logs/
```

如平台或评审额外需要方案材料，可再附带：

```text
CHANGELOG_AND_STATUS.md
docs/
```

## 不需要提交

以下内容用于本地开发和验证，默认不打包提交：

```text
tests/
sample_llm_wiki/
requirement/
score_calculator.py
update.md
log7_7.md
log7_8.md
```

## 常用验证命令

```bash
pytest tests -q
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
```
