# 迭代记录

每天五个窗口（08:00 / 12:30 / 13:30 / 18:30 / 21:30）一条，改了什么 / 为什么 / 验证结果。

### #0 scaffold：一个只读自己 diff 的本地小工具

- **改了什么**：`diff.py` 把 `git diff` 的文本解析成 文件 / hunk / 行（带新旧行号，`-z` 之外的换行路径不在这一版）；`rules.py` 六条规则（`secret-literal` fail、`debug-statement`、`large-deletion`、`tests-missing` warn、`todo-added`、`lockfile-churn` note）；`report.py` 一份 JSON 同时喂 CLI 与页面；`cli.py` 两个入口（表格 / `--json` 与 `--serve`）；`server.py` stdlib 的 `/api/report` + 单页；25 个测试；CI 3.10/3.12。
- **为什么**：`alibaba/open-code-review` 是企业级的 Go 服务 + LLM agent + 多语言规则库，跑起来要 key、要服务、要上下文。这台机器上真正会发生的事是「我一口气让 agent 改了 12 个文件，push 之前想有人替我看一眼」——不需要模型，只需要几条又笨又吵的规则和一张能扫完的清单。所以这里零依赖、离线、只看你还没推上去的那几个 commit。
- **验证**：26 个测试全过；在真实仓库上跑 `diffbrief --staged` 能抓到 `API_KEY = "…"`（打码后显示）与 `console.log`；页面过了一遍 skillforge 的 `sloplint`（`clean: 0 tells, 0 failures`）。
- **补**：README 写了 `PYTHONPATH=src python -m diffbrief`，但包里没有 `__main__.py`，真跑会报 `No module named diffbrief.__main__`——补上并加了一条子进程用例（`python -m diffbrief --help` 必须 exit 0）。
