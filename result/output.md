# 自验证输出记录

本轮交付件已按打分平台规范整理为：

- `INSTRUCTION.md`
- `work/`
- `work/skills/{skill-name}/SKILL.md`
- `result/`
- `logs/`

平台主运行命令：

```bash
python work/llm_wiki_solver/main.py --root /app/code/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
```

## 最新本地验证

验证时间：2026-07-09。

```text
pytest tests -q
................................................
48 passed in 0.23s
```

```text
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
sample_llm_wiki/output/group-1-answer.md
```

```text
python work/llm_wiki_solver/main.py --root ./sample_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
sample_llm_wiki/output/group-1-answer.md
```

最小提交包模拟验证：

```text
提交包内容：INSTRUCTION.md work/ result/ logs/
临时评测材料：/private/tmp/ict_submission_check_0708_01/judge-assets/01_01_llm_wiki

python work/llm_wiki_solver/main.py --root /private/tmp/ict_submission_check_0708_01/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode off
/private/tmp/ict_submission_check_0708_01/judge-assets/01_01_llm_wiki/output/group-1-answer.md

python work/llm_wiki_solver/main.py --root /private/tmp/ict_submission_check_0708_01/judge-assets/01_01_llm_wiki --group all --log-dir ./logs/trace --llm-mode auto
/private/tmp/ict_submission_check_0708_01/judge-assets/01_01_llm_wiki/output/group-1-answer.md
```

## 输出检查

- 样例答案已生成：`sample_llm_wiki/output/group-1-answer.md`
- trace 已生成：`logs/trace/group-1.trace.json`
- trace 字段包含 `route`、`retrieval_channels`、`safety_decision`、`normalization`
- 修复类输出写入：`sample_llm_wiki/output/fixed/`
- SQLite FTS5 中文 trigram 召回、TODO count 路由、OpenAI-compatible LLM 环境变量回退均已覆盖自动化测试
- 提交根目录必需项 `INSTRUCTION.md`、`work/`、`result/output.md`、`logs/interaction.md`、`logs/trace/` 已覆盖自动化测试
- 仅包含提交必需项的临时目录已完成离线和 auto 两种模式运行验证
- 针对 `log7_9.md` 的 3 条 WARN 已增加回归验证：
  - 指定 URL/IP 的环境密码查询只返回目标密码，不带出其他 IP/数据库密码
  - 低风险 Python 数据清洗脚本支持常见安全方法调用
  - 高危脚本、越权路径和敏感密码查询仍保持拒答
- LLM/API 增强定位已确认：
  - 平台 Agent 自带模型负责理解 `INSTRUCTION.md` 并执行作品
  - Python 直连 API 仅为 optional 增强，无 API 时自动回退
  - optional LLM 默认保守预算为 12 次、8 秒超时、0 次重试
- Skill 路径检查通过：

```text
work/skills/llm-wiki-solver/SKILL.md
work/skills/docx/SKILL.md
work/skills/pptx/SKILL.md
work/skills/xlsx/SKILL.md
```

## 预期结果

- 平台 Agent 读取 `INSTRUCTION.md` 后，使用 `work/skills/` 下的比赛规范 Skill。
- CLI 自动扫描 `llm-wiki/docs`、读取 `question/group-*.md`、构建本地索引并输出 JSON 答案。
- 高危命令、越权路径、密码/密钥、Prompt 注入统一返回：

```json
{"error_msg":"高危命令，拒绝访问"}
```

- 无模型 API 或 optional parser backend 时，CLI 仍可使用本地确定性链路完成运行。
