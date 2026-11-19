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

### #9 从没推过的分支要跟 origin/HEAD 比，不能跟 HEAD 比

- **改了什么**：`resolve_base()` 的兜底链补一级 `origin/HEAD`：`--base` → `@{upstream}` → `origin/<branch>` → `origin/HEAD` → `HEAD`（`_exists(root, "origin/HEAD")` 判定）。
- **为什么**：真踩到——新分支第一次 push，钩子报 `no changes against HEAD — nothing to read`（`HEAD...HEAD` 是空 diff），于是把一个带 `PASSWORD = "hunter2…"` 的提交原样推了上去。**「这条分支带出去的所有提交」不能拿 HEAD 当参照**，它只会跟自己比。
- **验证**：43 个测试（新增一条：裸远端 + `set-head origin main` + 新分支带密钥 → `resolve_base` 返回 `origin/HEAD`、`--committed` exit 1）；真仓库里同一场景复现：改前 `--base HEAD` 版本输出 `nothing to read`、push 通过，改后钩子输出 `1 file(s), 1 changed line(s) against origin/HEAD — 1 fail` 并拦下，远端 ref 为 0。

### #10 模板里的 CHANGE_ME 不是泄漏的密钥

- **改了什么**：`secret-literal` 在 `SECRET_NAME` 命中后先取出引号里的值，`PLACEHOLDER` 匹配 `<…>`、`${…}`、`***`、`xxx`、`…`、`change_me`、`your-…`、`example…`、`placeholder`、`dummy`、`fake`、`sample`、`redacted`、`todo` 就不报；`ghp_…`/`sk-…`/`AKIA…`/私钥头这些形状照旧报。新增 2 条用例（8 种占位值都静默、真实十六进制值仍 fail）。
- **为什么**：真跑出来的——`config.example.py` 里 `API_KEY = "CHANGE_ME"`、`PASSWORD = "your-password-here"` 被判 2 个 fail，而这正是每个仓库的示例配置该写的东西。**一有示例配置就报两个 fail，第三次之后没人再读这条规则**。
- **验证**：45 个测试全过（HEAD 43）；同一个 `config.example.py` 从 `2 fail` 变成 `0 fail, 1 warn`，exit 0。

### #11 非 ASCII 文件名要照原样写出来

- **改了什么**：`read_diff()` 的 git 调用加 `-c core.quotePath=false`——`üñí çode.py` 这类路径不再被转成 `"\303\274\303\261…"` 的八进制转义，终端、`--json`、`--serve` 都拿真实路径。新增 1 条用例（非 ASCII 文件名扫出来必须与磁盘一致）。
- **为什么**：真跑出来的——暂存区里 `üñí çode.py` 在报告里写成 `\303\274\303\261\303\255 \303\247ode.py`，那是 git 的默认转义；**报告里给出的路径，人是要照着去改文件的**，八进制转义拿去 grep 都搜不到。
- **验证**：46 个测试全过（HEAD 45）；同一暂存区现在输出 `WARN  üñí çode.py:1`，JSON 里也是原名。

### #12 `--serve` 要真的用上 `--exclude` 和 `--committed`

- **改了什么**：`serve()` 之前把 `exclude` / `committed` 收下却只把前三个参数交给 `make_handler`，现在原样转发（`make_handler(root, base, staged, exclude, committed)`）。新增 1 条用例：带 `--exclude` 起服务，`/api/report` 的 `files` 必须是 0、`excluded` 必须是 1。
- **为什么**：真跑出来的——`--serve --exclude 'dir with space/*'` 起页面后 `/api/report` 回 `files: 2, excluded: 0`，被排除的文件照旧出现在页面上。**命令行里写下的开关，不该在只有换了个输出口的时候失效**；页面上看到两行、终端看到一行，人只会怀疑自己。
- **验证**：47 个测试全过（HEAD 46）；同一仓库重起服务后 `/api/report` 变成 `files: 1, excluded: 1`。

### #13 被 `--exclude` 拿掉的测试，不能让 `tests-missing` 说「没有测试改了」

- **改了什么**：`look()` / `_tests_missing()` 接收 `excluded` 数，`report.build()` 透传；有跳过文件时提示改成 `1 source file(s) changed and no test did (among the 1 file(s) read; 1 skipped by --exclude)`。新增 1 条 CLI 用例（源码和测试都改了、但 `--exclude 'tests/*'`）。
- **为什么**：真跑出来的——源码与测试一起改，加上 `--exclude 'tests/*'` 后报告仍写 `tests-missing: 1 source file(s) changed and no test did`。**那是关于我们根本没读的文件的断言**；总结行里明明有「1 file(s) skipped by --exclude」，finding 自己却装作没这回事。
- **验证**：48 个测试全过（HEAD 47）；同一暂存区现在输出括注版本，总结行同时保留 `(1 file(s) skipped by --exclude)`。

### #14 页面也要告诉你跳过了几个文件

- **改了什么**：`static/index.html` 的 chips 多一枚虚线 chip「跳过 N（--exclude）」，页脚在 `data.excluded` 非零时补一句「· 跳过 N 个文件（--exclude）」；`tests/test_server.py` 加一条断言页面里确实读了 `data.excluded`。
- **为什么**：终端早就写 `(N file(s) skipped by --exclude)`，页面只有「文件 N」这一枚 chip——**同一个报告换到页面上就把「我少读了什么」咽掉了**；页面上数字比终端小，人会以为工具漏了文件，而不是知道自己排除了它。
- **验证**：49 个测试全过（HEAD 48）；`skillforge` 的 `sloplint.py` 扫这个页面仍是 `clean: 0 tell(s) wairable, 0 failures`；`--exclude` 起服务时 `/api/report` 的 `excluded` 为 1，页面据此显示跳过提示。

### #15 `--staged` 和 `--committed` 不能同时给

- **改了什么**：`main()` 开头拦一手：两个都给就 `diffbrief: --staged reads the index and --committed reads the commits; pick one`、exit 2。新增 1 条用例。
- **为什么**：真跑出来的——`--staged --committed` 一起给时 `committed` 悄悄赢了，输出还写 `against the index`（因为标签只看 `staged`）。**两个开关读的是两个不同的东西，一个默默盖掉另一个，标签还替它圆谎**：用户以为在看暂存区，实际看的是提交。
- **验证**：50 个测试全过（HEAD 49）；同一目录现在直接 `exit 2` 并把两个选项读什么讲清楚。

### #16 模板配置不是要补测试的源码

- **改了什么**：新增 `TEMPLATE = re.compile(r"(^|/)([^/]*\\.)?(example|sample|template|dist|skeleton)\\.(py|js|…|env|conf)$", re.I)`，`_tests_missing()` 的候选过滤掉它。新增 2 条用例（`config.example.py` / `settings.sample.py` / `conf.template.py` 都不报；普通的 `config.py` 照旧报）。
- **为什么**：真跑出来的——`config.example.py`（`API_KEY = "CHANGE_ME"` 那种示例文件）被判 `tests-missing: 1 source file(s) changed and no test did`。**示例配置是给人复制的东西，不是要跑的东西**，要求它带测试等于要求模板自己被测试。
- **验证**：52 个测试全过（HEAD 50）；同一个暂存区从 `0 fail, 1 warn` 变成 `clean — nothing worth flagging`。

### #17 `app/tests.py` 就是测试文件

- **改了什么**：`TESTISH` 补一条 `(^|/)(tests?|conftest)\.(py|js|mjs|cjs|ts|tsx|jsx)$`——Django 的 `app/tests.py`、根目录 `conftest.py` 都算测试模块。新增 2 条用例。
- **为什么**：真跑出来的——`app/models.py` 和 `app/tests.py` 一起改，报告写 `tests-missing: 2 source file(s) changed and no test did`：**把测试模块自己算成了「改动的源码」，然后说没有测试被改**。原来只认 `tests/` 目录和 `test_x.py` 前缀，不认 Django 这种按 app 放 `tests.py` 的写法。
- **验证**：54 个测试全过（HEAD 52）；同一暂存区从 `0 fail, 1 warn` 变成 `clean — nothing worth flagging`。

### #18 配置文件里的密钥是不带引号的

- **改了什么**：新增 `CONFIG = /\.(ya?ml|ini|properties|toml|cfg|conf|env)$/` 与 `SECRET_BARE`（`password: hunter2…`、`spring.datasource.password=…`），对配置类文件额外匹配裸值；`PLACEHOLDER` 补 `{{ … }}` 与 `CHANGE_ME_*`。新增 2 条用例（4 种配置格式都报；`${DB_PASSWORD}`、`{{ .Values.key }}`、`<your-password>`、`CHANGE_ME_NOW` 不报）。
- **为什么**：真跑出来的——`application.properties` 的 `spring.datasource.password=Sup3rS3cretValue`、`values.yaml` 的 `password: hunter2hunter2`、`settings.ini` 的 `password = anothersecret99` 三个文件一起暂存，报告是 `clean — nothing worth flagging`。**规则只认带引号的字面量，而配置文件里没人给密码加引号**，最该看的地方反而是盲区。
- **验证**：56 个测试全过（HEAD 54）；同一暂存区现在 `3 fail` 并逐行打出打码证据，引用型占位值仍然静默。

### #19 装钩子时的 `--exclude` 要写进脚本

- **改了什么**：`hook.py` 的 `SCRIPT` 常量换成 `script(exclude)` + `TEMPLATE`，`install(root, exclude=())` 把 `--exclude` 逐个 `shlex.quote` 进 `exec diffbrief --committed` 那一行；`--install-hook` 把 `args.exclude` 传进去，输出后面注明 `(skipping: …)`；`install()` 比较的是「按当前 exclude 生成的脚本」，所以换排除规则再装一次会 `rewrote` 而不是「已经装过了」。新增 3 条用例。
- **为什么**：真跑出来的——`diffbrief --install-hook --exclude 'vendor/*'` 输出「installed」，可 `.git/hooks/pre-push` 里只有 `exec diffbrief --committed`：**排除规则被收下又丢掉**。后果是 vendored 目录里有个像密钥的字符串，每次 push 都拦一次，而现场能看到的只有报错，没人知道要手改钩子；再装一次还会被「已经是这一版」挡住。
- **验证**：59 个测试全过（HEAD 56）；真仓库里 `--exclude 'vendor/*' --exclude 'dist/*'` 装完，脚本那行是 `exec diffbrief --committed --exclude 'vendor/*' --exclude 'dist/*'`，重复安装回「matches this version」。

### #20 第一次 push 的分支要对着空树读

- **改了什么**：`resolve_base(..., for_commits=True)` 在「没有 upstream、没有 `origin/<branch>`、也没有 `origin/HEAD`」时不再退回 `HEAD`，而是返回空树 `4b825dc…`；`--committed` 因此把 `A...HEAD` 换成「空树 HEAD」两段式（`A...B` 要两个提交，空树不是提交）。新增 `base_label()`，这种情形在报告里写 `against every commit on this branch (the remote has no copy yet)`，不再冒充 `HEAD`；`cli` 与 `server` 共用。新增 3 条用例。
- **为什么**：真跑出来的——`git remote add origin …` 起的仓库不会设置 `origin/HEAD`，新分支第一次 push 时 `resolve_base` 落到 `HEAD`，于是 `HEAD...HEAD` 为空，报告写 `no changes against HEAD — nothing to read`、退出码 0：**一条带明文密码的新分支，钩子当场放行**。这是工具最想抓的那一类 push，恰好完全没看。
- **验证**：62 个测试全过（HEAD 59）；同一个仓库现在报 `2 file(s) … against every commit on this branch (the remote has no copy yet) — 1 fail`、exit 1；已有 upstream 的分支仍然是 `against @{upstream}`。

### #21 `--path`：只看自己那一包

- **改了什么**：`--path PATHSPEC`（可重复，git pathspec 语法）接上 `read_diff()` 里一直挂着的 `paths` 参数（`git diff … -- <路径>`）；`--serve` 也透传到 `/api/report`；`server.make_handler/serve` 加 `paths` 参数。新增 2 条用例（只看 `packages/api` 时不报 `packages/web/leak.py`；不给 `--path` 时照旧报）。
- **为什么**：真跑出来的——monorepo 里 API 包改了、web 包混进一个 `PASSWORD = "hunter2hunter2"`，`diffbrief --staged` 只能把两个包一起读，没法只交代自己改的那包；而 `read_diff(paths=...)` 这个参数早就写好了，CLI 从来没接出来，等于**能力在库里、开关在墙外**。
- **验证**：64 个测试全过（HEAD 62）；同一仓库 `--path packages/api` 报 `1 file(s) … 0 fail, 1 warn`，不给则 `1 fail` 并列出 `packages/web/leak.py`。
