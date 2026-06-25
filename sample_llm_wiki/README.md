# LLM Wiki 自验证样例

用于验证参赛作品的端到端流程。真实验收时，平台会释放自己的 `llm-wiki` 目录。

可用命令：

```bash
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
```
