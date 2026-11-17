# diffbrief

推之前，先看一份你自己 diff 的体检单。

它读 `git diff` 的输出——默认是**还没推上去的那几个 commit**（没有上游时退回 `HEAD`）——然后用几条又笨又吵的规则挑出「人会停下来想两秒」的行：疑似密钥、调试残留、大块删除、改了代码没改测试、lockfile 抖动、新塞进来的 TODO。结果能打在终端，也能开一个本地页面看。

```
$ diffbrief
FAIL  config.py:12
      secret-literal: a key-shaped literal is being added
      APIC…******
WARN  src/app.py
      tests-missing: 3 source file(s) changed and no test did

4 file(s), 61 changed line(s) against @{upstream} — 1 fail, 1 warn, 0 note
```

## 和 [alibaba/open-code-review](https://github.com/alibaba/open-code-review) 的关系

它是企业级的：Go 服务 + 确定性流水线 + LLM agent + 多语言规则库 + 行级评论，能接 OpenAI / Anthropic，在阿里巴巴的规模上跑过。这些都对，但那是「团队审查流水线」。

diffbrief 只做一件更小的事：

- **只读你自己的、还没推的 diff**，不做 harness、不做仓库级上下文、不发 PR 评论；
- **不联网、不需要 key、不上传代码**——规则就是正则和计数，跑在本地；
- **零运行时依赖**（Python 标准库），`pip install -e .` 之后立刻能用，也能 `python -m diffbrief`；
- **退出码是契约**：`0` 干净或没东西可看，`1` 有 fail，`2` git 报错。挂进 pre-push 钩子不用再解析输出。

如果你要的是一个懂语言的审查 agent，用它；如果你要的是「push 前 3 秒内被提醒一句」，用这个。

## 规则（v0.1）

| 规则 | 级别 | 触发条件 |
|---|---|---|
| `secret-literal` | fail | 新增行里出现 `api_key/secret/token/password … = "…"`，或 `ghp_/gho_/sk-/AKIA…`、私钥头。证据打码；模板占位值（`CHANGE_ME`、`your-…-here`、`${API_KEY}`、`<token>`、`dummy`、`redacted`）不算 |
| `debug-statement` | warn | **可执行文件**的新增行里有 `console.log(`、`debugger`、`pdb.set_trace()`、`breakpoint()`、`binding.pry`、`dbg!(`（文档里举例不算） |
| `large-deletion` | warn | 单个文件删 ≥30 行且加 ≤5 行（lockfile 除外） |
| `tests-missing` | warn | 改了源码（py/js/ts/go/rs/java/rb/kt/swift/php）却没有任何测试文件跟着改；纯改名（一行没动）不算 |
| `todo-added` | note | 新增行里以注释形式出现 `TODO` / `FIXME` / `XXX`（`#`、`//`、`<!--`、行首、列表项；字符串里的这个词不算） |
| `lockfile-churn` | note | `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml` / `poetry.lock` / `Cargo.lock` / `uv.lock` / `go.sum` 等改动 ≥200 行 |

路径按磁盘原样输出（git 的 `core.quotePath` 会被关掉），中文/带空格的文件名可以直接拿去 grep。

规则会误报——这是设计上的取舍：它宁可吵，也不假装自己懂语义。请把它当「有人在你耳边念一遍」，不是「审查结论」。

## 用法

```bash
pip install -e .            # 或者不装，PYTHONPATH=src python -m diffbrief
diffbrief                   # 未推送的 commit（上游 → origin/<branch> → origin/HEAD，都没有才 HEAD）
diffbrief --staged          # 只看暂存区
diffbrief --base origin/main
diffbrief --json            # 给脚本/钩子
diffbrief --exclude 'vendor/*' --exclude '*.min.js'   # 跳过不该看的文件（可重复）
diffbrief --committed       # 只看提交，不看工作区（pre-push 该用这个）
diffbrief --install-hook    # 写一个 pre-push：有 fail 就拦下这次 push（自己的旧脚本会被重写）
diffbrief --serve           # 本地页面（默认 127.0.0.1:8765，5 秒轮询）
```

`--exclude` 跳过的文件不会被静默丢掉：总结行会写 `(N file(s) skipped by --exclude)`，JSON 里有 `excluded`。

装钩子之后，`.git/hooks/pre-push` 跑的是 `diffbrief --committed`——只读**这次要推出去的提交**，你调试时临时贴在文件里还没提交的密钥不会被算成「要推的东西」；钩子里 `diffbrief` 不在 PATH 时只打一行提示、不拦 push（工具坏了不该堵住你的工作）。已经有别人写的 `pre-push` 时拒绝覆盖。

刚推出去的新分支还没有上游，也没有 `origin/<branch>`：这时候比的是 `origin/HEAD`（远端默认分支）——「这条新分支带出去的所有提交」，而不是空。

退出码：`0` 干净 / `1` 有 fail / `2` git 或端口出错。

## JSON

```json
{
  "root": "/path/to/repo",
  "base": "@{upstream}",
  "files": 4,
  "changed_lines": 61,
  "findings": [
    {"path": "config.py", "line": 12, "severity": "fail",
     "rule": "secret-literal", "message": "a key-shaped literal is being added",
     "evidence": "APIC…******"}
  ],
  "totals": {"fail": 1, "warn": 1, "note": 0}
}
```

## 待办

- `--exclude` 目前只匹配 git 打印的路径字面（glob），不展开目录语法；缩进的忽略规则（`.diffbriefignore`）还没做；
- 二进制与超大文件的提示（现在直接跳过）；
- 钩子只认 `pre-push`，不支持 `pre-commit` / `commit-msg`；
- 更多语言的行级规则（注释掉的代码块、`except: pass` 之类）。

## 许可

MIT。
