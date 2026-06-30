# 自验证输出记录

当前作品已包含自动化测试和本地样例运行入口。

推荐验证命令：

```bash
pytest tests -q
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
```

预期结果：

- `tests` 全部通过。
- `sample_llm_wiki/output/group-1-answer.md` 生成 JSON 数组答案。
- `logs/trace/group-1.trace.json` 生成推理摘要。
- 修复类样例会在 `sample_llm_wiki/output/fixed/` 中生成标记完成后的文件。
- 自动化测试覆盖 TODO 日期筛选、文本修复、XLSX 汇总/筛选/计数、多条件筛选/条件汇总、简单 Python 安全执行、函数/循环 Python 执行和危险 Python 拒答。

最近一次本地验证结果：

```text
pytest tests -q
26 passed

python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
sample_llm_wiki/output/group-1-answer.md
```
