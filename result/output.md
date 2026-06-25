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

最近一次本地验证结果：

```text
pytest tests -q
20 passed

python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
sample_llm_wiki/output/group-1-answer.md
```
