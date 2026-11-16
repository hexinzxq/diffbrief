# 迭代记录

每天五个窗口（08:00 / 12:30 / 13:30 / 18:30 / 21:30）一条，改了什么 / 为什么 / 验证结果。

### #0 scaffold：一个只读自己 diff 的本地小工具

- **改了什么**：`diff.py` 把 `git diff` 的文本解析成 文件 / hunk / 行（带新旧行号，`-z` 之外的换行路径不在这一版）；`rules.py` 六条规则（`secret-literal` fail、`debug-statement`、`large-deletion`、`tests-missing` warn、`todo-added`、`lockfile-churn` note）；`report.py` 一份 JSON 同时喂 CLI 与页面；`cli.py` 两个入口（表格 / `--json` 与 `--serve`）；`server.py` stdlib 的 `/api/report` + 单页；25 个测试；CI 3.10/3.12。
- **为什么**：`alibaba/open-code-review` 是企业级的 Go 服务 + LLM agent + 多语言规则库，跑起来要 key、要服务、要上下文。这台机器上真正会发生的事是「我一口气让 agent 改了 12 个文件，push 之前想有人替我看一眼」——不需要模型，只需要几条又笨又吵的规则和一张能扫完的清单。所以这里零依赖、离线、只看你还没推上去的那几个 commit。
- **验证**：26 个测试全过；在真实仓库上跑 `diffbrief --staged` 能抓到 `API_KEY = "…"`（打码后显示）与 `console.log`；页面过了一遍 skillforge 的 `sloplint`（`clean: 0 tells, 0 failures`）。
- **补**：README 写了 `PYTHONPATH=src python -m diffbrief`，但包里没有 `__main__.py`，真跑会报 `No module named diffbrief.__main__`——补上并加了一条子进程用例（`python -m diffbrief --help` 必须 exit 0）。

### #1 `--staged` 读的是暂存区，报告的却是「against HEAD」

- **改了什么**：`--staged` 时把报告里的 `base` 标成 `the index`（CLI 与 `/api/report` 一致），不再借 `resolve_base()` 返回的 upstream/HEAD 名字。新增用例：暂存一条改动后 `--staged` 必须写 `against the index`、不能写 `against HEAD`，`--json` 的 `base` 也是 `the index`。
- **为什么**：真跑出来的——`diffbrief --staged` 的输出末尾写着「1 file(s), 3 changed line(s) against HEAD」，可它读的是索引；`base` 字段同样撒谎。这种标签错了不报错，只会让人以为「我明明只暂存了一个文件，怎么 HEAD 也变了」。工具可以不知道答案，但不能把答案写错。
- **验证**：27 个测试全过；把这一行还原成 `resolve_base(...)` 单跑新用例立刻失败（0.15s），改回来才过；真仓库上现在写 `against the index`。

### #2 `--exclude GLOB`：不该看的文件，要跳得掉，也要说跳了

- **改了什么**：`--exclude GLOB`（可重复，`fnmatch` 匹配 git 打印的路径）；`diff.read_diff()` 与 `server.make_handler()` 都接受 `exclude`，`--serve` 也生效；被跳过的数量进 JSON 的 `excluded`，终端总结行写 `(N file(s) skipped by --exclude)`——**跳过必须说出来**，不能静默少几个文件。新增用例：带 `vendor/lib.py` 的密钥改动，不排除 exit 1，`--exclude 'vendor/*'` exit 0 且 JSON `excluded == 1`、`files == 0`。
- **为什么**：真跑出来的——把 20 个第三方 skill 导进 `skillforge/vendor/` 的那一刻，`diffbrief --base f33cd59~1` 报 `2 fail, 2 warn, 4 note`，全部落在 vendored 的 `evals.json` 里（`TODO` 示例、`console.log` 片段），这个仓库的主人一行都改不了。看板如果在这种地方吵，用户第三次就会加 `2>/dev/null`。
- **验证**：28 个测试全过；同一段真实历史加 `--exclude 'vendor/*'` 后 `26 file(s), 3629 changed line(s) — 0 fail, 0 warn, 0 note (77 file(s) skipped by --exclude)`；README 用法与待办同步改写。

### #3 TODO 是注释里的标记，不是数据里出现的那个词

- **改了什么**：`todo-added` 从「行里出现 `TODO/FIXME/XXX`」收窄成「**注释形式**的标记」——`TODO_IN_COMMENT` 认 `#`、`//`、`/*`、`*`、`<!--`、`--`、`;`、`%` 开头，或标记直接在行首，或文档里的列表项 `- TODO:`。新增三条用例（数据字符串里的 TODO 不算；四种语言的注释标注都还算；原来的 note 行为不变）。
- **为什么**：真跑出来的——`dsh-daily-lab --base HEAD~6` 报了两条 `todo-added`，两条都在 `state/*.json` 里，命中的是工具自己的 angle 描述文字「抓 TODO / FIXME 这类标记」。那不是新塞进来的待办，是数据里引用了这个词；规则看的是词，人看的是意图。
- **验证**：30 个测试全过；把条件还原成 `TODO_MARK.search(text)` 后新用例立刻失败、改回来才过；同一段真实历史从 `0 fail, 0 warn, 2 note` 变成 `clean — nothing worth flagging`；README 规则表同步改写。

### #4 `--install-hook`，以及它顺手露出的一个「钩子根本拦不住」的洞

- **改了什么**：`--install-hook` 写 `.git/hooks/pre-push`（`hook.py`，`hooks_dir()` 走 `git rev-parse --git-path hooks`）；钩子内容能在 `diffbrief` 不在 PATH 时只打一行提示、不拦 push；已经有别人写的 `pre-push` 时抛 `GitError` 拒绝覆盖；重复安装只报「already there」。四条用例，其中一条真起 `git push` 到裸仓库、用假 `diffbrief` 验证钩子确实能拦下。
- **为什么**：工具的口号是「push 之前看一眼」，可没有任何东西逼你看一眼；钩子是把这个口号接上线的最小零件。
- **顺手抓到的真洞**：在演示钩子时，一个从来没 `-u` 推过的分支（只有 `git push origin main`）**钩子放行了一个带 `ghp_…` token 的提交**——`resolve_base()` 没 upstream 就退回 `HEAD`，而 `HEAD` 跟自己永远没差，于是报告「no changes against HEAD — nothing to read」。`resolve_base()` 改成三级：显式 `--base` → `@{upstream}` → 存在同名远程跟踪分支时用 `origin/<branch>` → 最后才 `HEAD`。这才是「你即将推出去的东西」。
- **验证**：35 个测试全过；新用例（无 upstream + 裸远端 + 新提交里的密钥）在没有 fallback 时必须失败——实测还原后 0.29 秒失败；真仓库里装钩子后推一个 `PASSWORD = "…"` 的提交，钩子输出 `1 file(s), 1 changed line(s) against origin/main — 1 fail`，push 被拒，远端 ref 没动。

### #5 调试语句只在会运行的文件里才算「留下的调试输出」

- **改了什么**：`debug-statement` 加一层 `EXECUTABLE` 门（py/js/ts/go/rs/…/sh/vue/svelte 这些能跑起来的扩展名）；`.md`、`.json` 里引用 `console.log(x)` 不再报。新增两条用例（代码里报、文档代码块里不报）。
- **为什么**：真跑出来的——`skillforge --base f33cd59~1`（那次把 20 个第三方 skill 导进 `vendor/`）报 `2 warn`，两条都在 `references/REFERENCE.md` 的代码块里，是文档在**举例**说明 `console.log` 怎么用。没人会把调试输出「留在」一个 markdown 文件里；这条规则原本是在猜文件会不会被执行，猜错了就变成噪音。
- **验证**：37 个测试全过；去掉门之后新用例立刻失败；同一段真实历史从 `2 fail, 2 warn, 0 note` 变成 `2 fail, 0 warn, 0 note`（剩下的 2 个 fail 是 vendored 文件里密钥形状的字符串，用 `--exclude 'vendor/*'` 处理）；README 规则表同步改写。

### #6 纯改名不算「改了源码没改测试」

- **改了什么**：`_tests_missing()` 的候选条件加 `file.changed()`——`git mv a.py b.py` 这种零行变更不再触发；改名同时改了内容的仍然触发。两条对应用例（纯改名不报、改名带内容改报）。
- **为什么**：真跑出来的——`git mv a.py b.py` + `chmod +x run.sh` 的暂存区，报告写着 `2 file(s), 0 changed line(s)`，下面却挂了一条 `WARN b.py — tests-missing: 1 source file(s) changed and no test did`。**一个 changed line 是 0 的 diff 却说自己改了源码**，这是自相矛盾的说法，而人看到「改了源码」会真的回去补测试。
- **验证**：41 个测试全过；把 `and file.changed()` 去掉后新用例立刻失败；同一暂存区现在输出 `0 file(s), 0 changed line(s) — 0 fail, 0 warn, 0 note`；README 规则表补一句「纯改名不算」。

### #7 钩子只看提交，不该被工作区的临时改动拦住

- **改了什么**：新增 `--committed`（`git diff <base>...HEAD`，只读提交，不读工作区与索引）；`--install-hook` 写的 `pre-push` 改成跑 `diffbrief --committed`；`--serve` 也透传该模式。新增两条用例：提交是干净的、工作区贴着一个密钥 → 默认模式 exit 1、`--committed` exit 0；钩子脚本必须带 `--committed`。
- **为什么**：真跑出来的——在一个提交本身干净的仓库里，调试时把 `API_KEY = "…"` 贴在 `a.py` 末尾还没提交，`git push` 被自己的钩子拦下了：报告写 `against origin/main — 1 fail`，可这次 push 里根本没有那一行。**「你即将推出去的东西」不含未提交的改动**，钩子拿工作区当依据就是假报警，假报警多了人就会 `--no-verify`。
- **验证**：42 个测试全过；同一仓库里重装钩子后再 push，报告变成 `1 file(s), 1 changed line(s) against origin/main — 0 fail`，push 通过；把密钥提交进去则照旧拦下（已有用例覆盖）。README 用法与钩子说明同步改写。

### #8 自己写的旧钩子要被重写，而不是「已经在那了」

- **改了什么**：`hook.install()` 返回值从 `(path, wrote: bool)` 改成 `(path, "new" | "updated" | "unchanged")`——文件里有我们自己的标记但内容和当前 `SCRIPT` 不同时重写；`cli.py` 三句话分别是 `installed …`、`rewrote … — the script changed since it was installed`、`… is already there and matches this version`。别人写的钩子照旧抛错不动。
- **为什么**：真踩到——`SCRIPT` 从上一条改动里加了 `--committed`，可我在那个测试仓库里跑 `--install-hook` 得到的是「already there」，钩子还留着 `exec diffbrief` 的旧行为；最后是手改文件才让它按新脚本跑。**脚本本身承载行为，升级时不重写等于没升级**，而「already there」听起来像「已经是最新」。
- **验证**：42 个测试（HEAD 是 40，新增 2 条：旧脚本必须被重写、再装一次必须报 `matches this version`）；真仓库里先看到 `rewrote …`、再装一次看到 `… matches this version`，钩子内容里出现了新注释 `not part of a push`。
