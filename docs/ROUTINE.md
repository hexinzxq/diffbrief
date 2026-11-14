# 每日窗口怎么做（给未来的自己）

每次窗口（08:00 / 12:30 / 13:30 / 18:30 / 21:30）只做一件事，做完就停。当天满 5 次就只做维护。

1. `cd /Users/xin/Documents/deepseek-harness/default-workspace/diffbrief`，`git status` 应干净、`origin/main` 已推。
2. 读 `docs/ITERATIONS.md` 最后一条，知道上次做到哪、下一步是什么。
3. 从「待办」或真实输入里挑**一个**小改动：拿一个真实仓库真跑 `diffbrief`（先 staged、再 `--base`、再看页面），看哪里不对。
4. 写代码 + 写测试（`PYTHONPATH=src python3 -m unittest discover -s tests -t .` 全绿）。
5. 页面改动时顺手自扫：`python3 ../skillforge/skills/frontend-design/scripts/sloplint.py src/diffbrief/static/index.html`。
6. commit（一句话说清改了什么）→ push → `sleep 35 && gh run list --limit 1` 确认 CI 绿。
7. `docs/ITERATIONS.md` 追加一条；向用户三行汇报。

红线：不上传代码、不联网、不加运行时依赖（测试可依赖 git）、默认只绑 127.0.0.1。
