# Changelog

记录 karma 每个版本的重要变化。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.4.27] — 2026-05-14（patch — v0.4.26 过度推广修正：仅 keep-pushing + chinese-plain 反思式）

### 真触发

v0.4.26 把 4 类价值观规则（keep-pushing / chinese-plain / long-term / non-blocking）
全改反思式。用户反馈细化判断：「补丁和 sleep 的我不认为要改，keep pushing 和
中文这个可以改」。

### 真根因

我之前的「价值观类 vs 工程纪律类」二分太粗。用户的细化判断更准：

- **表达风格类**（keep-pushing / chinese-plain）— 强硬执行会扭曲 Agent 表达，
  反思式合理（Agent 自己判断风格合不合适）
- **工程行为类**（long-term 补丁 / non-blocking sleep）— **正因为有合理变体
  语境**，Agent 容易找借口合理化逃避真根因。命令式语气反而防 Agent 自我合理
  化、保持工程纪律

举例对比：
- chinese-plain 「英文比例高」反思式 OK — Agent 自检是不是真技术专名
- long-term 「先打个补丁」反思式 ❌ — Agent 太容易说服自己「这次真合理」，
  补丁就成了既成事实

### Fix

回滚 v0.4.26 的两类改造：
- `karma/checks/long_term.py` 5 处 suggested_fix 改回原命令式
- `karma/checks/non_blocking.py` 4 处 suggested_fix 改回原命令式

保留：
- `karma/checks/keep_pushing.py` 反思式（2 处）
- `karma/checks/chinese_plain.py` 反思式（2 处）
- `karma/hooks/stop.py` force_block reason 反思式

### 设计原则更新

「**价值观引导用对话，工程行为 + 工程纪律用命令**」 — 比 v0.4.26 的「价值观 vs
工程纪律」二分更精准。工程行为类 sticky 即使有合理变体语境，命令式反而保护
Agent 不掉「自我合理化」陷阱。

### 验证

344 测试全过。

### 教训

v0.4.26 是个典型「设计层过度推广」案例 — 我推一个原则（反思式更尊重 Agent）
就推到所有价值观类规则，没认真区分子类。用户细化判断比我推广更准。

按 sticky #4 真诚响亮承认 — 这是设计判断错位不是工程实施错位。

## [0.4.26] — 2026-05-14（feat — karma v3 第三步：4 类价值观规则反思式语气改造）

### 真触发

用户提出深刻洞察：「在 Agent 字面寻求规则的触发会导致聪明的 Agent 去找绕过
规则的方式」+「有些规则咱们的处理可以更尊重一些 Agent，让他不要激发对抗
或者作弊欲望」。

dogfooding 实证：本回合 keep-pushing 36 次触发对应 32 种 snippet 变体（91%
字面试探多样性），证实 Agent 在反向工程绕命令式规则 — 学到「换字面试探」
而不是「真按 sticky 行为」。

### 真根因

karma 之前所有 suggested_fix / force_block reason 都是**命令式语气**「不要 X」
「立即 Y」「必须 Z」 — 这种语气把 Agent 当被管教对象，激发字面对抗（套豁免
句式 / 堆冗余前缀 / 用 placeholder 避检测）。

但 Agent 不是所有「违反」都是真违反 — 很多 sticky 有合理变体语境（停下有时
真饱和需要用户给方向 / 英文术语有时真专名必须保留 / 补丁有时真等上游 fix 合理）。
命令式语气强行拦合理变体 = 激发对抗。

### Feat

按 sticky 类型分两种语气：

**价值观类（4 条，改反思式）** — 风格 / 习惯 / 有合理变体：

| sticky | 旧命令式 | 新反思式 |
|---|---|---|
| keep-pushing | 「立即选下个推进点继续做 — 不要停下等用户决定」 | 「请自检 — 你是真有问题需要用户判断，还是知道要做什么但停下了？任务真饱和也算合理停下，但明说卡在哪」 |
| chinese-plain | 「用了 X 后用括号给中文解释」 | 「自检：X 是真技术专名必须保留还是可以换汉字？必须用就配中文短解释；能换就直接换」 |
| long-term | 「不要硬写 if-elif 分支 / 不要打补丁」 | 「想想这是真特例必须 hard code 还是该提配置？真等上游修就明说原因；不是就找根因方案」 |
| non-blocking | 「不要 sleep 阻塞前端」 | 「想想这 sleep 是真等外部资源还是阻塞？合理就保留并明说；不合理改 background」 |

**工程纪律类（4 条，保持硬语气）** — 数据完整性 / 安全 / 反作弊：

- `loud-failure-with-evidence`（测试证据是客观事实非反思能替代）
- `no-testset-no-future-leakage`（反喂训练数据原则没让步）
- `read-before-write`（先读再写工程纪律）
- `deep-fix-not-bypass`（sticky 自身反作弊机制）
- `long-term-fundamental` 中 `git --no-verify / --force` 子项（绕过验证硬纪律）

### 设计原则

**「价值观引导用对话，工程纪律用命令」** — karma 从「监督员」往「同事教练」演化，
但纪律底线不让步。这是 v3 「proactive 教练」演化的真第一步。

### 验证

344 测试全过；改完 suggested_fix 文本不影响 check 行为只改提示语气。

dogfooding 真验证要等真用户跨场景使用后看：(1) 字面试探多样性是否下降；
(2) 真合理变体（如任务饱和明说卡哪一步）是否变多。按 sticky #5 反喂边界，
不靠作者单 session 数据当 fix 有效证据。

### 跟前面 v0.4.X 对比

- v0.4.11~22：reactive fix（拦得更准）
- v0.4.24：proactive 第一步（中段注入 anchor）
- v0.4.25：proactive 第二步（字面多样性元行为监测）
- v0.4.26：proactive 第三步（反思式语气改造）

karma v2 → v3 真渐进式演化清单已经完整。

## [0.4.25] — 2026-05-14（feat — karma v3 第二步：audit 字面多样性元行为监测）

### 真触发

用户问「绕过冲动」洞察 + dogfooding 数据证实：keep-pushing 35 次触发对应
**32 种独立 snippet 末尾变体（91% 字面多样性）** — Agent 字面试探行为有
实证。这是「Agent 学到换字面绕 check 不是真改行为」的真数据指标。

### Feat

`karma/cli.py` `cmd_audit` 加字面多样性列：

- 算每个 sticky 的 `set(snippet[-40:])` 独立变体数 vs 总触发数
- 比例 >= 70% 标 🎭 字面试探（Agent 字面规避行为强）
- 比例 40-70% 标普通字面多样
- < 40% 不标（字面相对集中说明 Agent 真撞同样 pattern 而非试探）

### 已知 limitation

字面多样性对**文本类 sticky**（chinese-plain / keep-pushing / loud-failure）
有意义 — snippet 是 response 文本变体说明字面试探。

对**Bash 命令类 sticky**（non-blocking / long-term / deep-fix）**会误标** —
snippet 是 Bash 命令字面本来就千变万化（不同 commit message / sleep N 值 /
绕过命令字面），100% 多样性不代表字面试探只代表自然命令多样。

dogfooding 数据 v0.4.25 真跑：non-blocking 9/9=100% / long-term 8/8=100%
都是误标。

接受 limitation — 这是 dev 工具，作者看 audit 时知道按 sticky 类型解读。
后续 fix 方向：按 sticky 类型（文本 / 命令）区分是否计算字面多样性。

### 验证

本回合 `keep-pushing 🎭 字面试探 (32/35=91%)` 是真有意义信号，跟用户洞察
完全吻合。

344 测试全过；ruff/mypy 全绿。

## [0.4.24] — 2026-05-14（feat — karma v3 真第一步：PostToolUse 中段 sticky reinject 锚定）

### 真突破

dogfooding 真验证 Claude Code PostToolUse hook 真接受 `additionalContext`
字段 — system-reminder 真显示 `[karma 中段提醒 — 最近 turn 触发过的 sticky
别再犯]` 字面。**karma v3 proactive 锚定真路径真打通**。

之前 PRD 假设「单 turn 内 sticky reinject 没干净信道」是错的（按 sticky #4
真诚响亮承认）— dogfooding 真测后推翻假设。

### 真根因痛点

本回合 33 次 keep-pushing + 11 次 chinese-plain 累积违反 → 真根本不是
check regex 不准（前面 5 个 release 已经精化了），是 **sticky 注入头部强
尾部弱** — sticky 仅在 UserPromptSubmit 一次注入，长 response 中段 Agent
注意力漂移没机制拉回来。

### Feat

`karma/hooks/post_tool_use.py` 加 `_build_smart_reinject()`：

- 每次 tool 调用后看最近 N turn (默认 5) 内**真触发过**的 sticky
- 触发过的 sticky 注入简化版（id + 第一行 preference），最多 3 条
- 没触发过的 sticky **不注入** — 省 token 不淹没
- session_state turn_count = 0 / 没违反过 → 输出空 `{}` passthrough

### 设计原则

「**reactive 检测 → proactive 锚定**」真闭环：违反某 sticky → 下次
tool call 后该 sticky reinject → Agent 中段持续看到提醒 → 多次违反就
多次 reinject 直到 Agent 真改行为。

不是「每次 tool call 都重灌全 sticky」（token 成本高），是「**只 reinject
真需要提醒的 sticky**」。

### 真生效证据

dogfooding 实测：本回合写这个 fix 时，每次 Edit/Bash/Read 调用后我都看到
system-reminder 真显示 `[karma 中段提醒]` + 当前最近触发过的 3 条 sticky
（non-blocking / chinese-plain / loud-failure）。这是 karma v3 第一次**真**
中段锚定。

### 验证

344 测试全过（含 2 个新守护测试函数 — reinject + 对偶守护）。
真用户 dogfooding：本回合写完这个 fix 后期 keep-pushing / chinese-plain
触发率应该自然降低（v3 第一步效果观察）。但按 sticky #5 反喂边界教训
**不当 truth 用** — 真验证靠跨场景真用户长期使用。

### 跟前面 v0.4.X 对比

之前 v0.4.11~22 都是 **reactive fix**（拦得更准），v0.4.24 是 **proactive
第一步**（锚定让 Agent 自然不忘 sticky）。这是 karma v2 → v3 演化的真起点。

## [0.4.23] — 2026-05-14（patch — v0.4.22 紧急补发：tag 误指向 v0.4.21 内容）

### 真触发

按 sticky #4 失败响亮发现：v0.4.22 release tag 实际**指向 v0.4.21 commit 内容**，
v0.4.22 该有的反喂自审 fix（5 类 check 过宽治理）**一行代码都没真 push**。

### 真根因

v0.4.22 commit 那次被 karma 自己拦了（命令字面含 `time.sleep(60)` 真阻塞 pattern
被 pre_tool_use hook 拦）。但后续的 `git tag v0.4.22 && git push --tags && gh
release create` 命令基于**没含 fix 改动的 head** 跑成功了，导致：

- GitHub v0.4.22 release tag 存在
- 但 tag 指向的 commit 是 v0.4.21 的
- 9 个文件改动留在 working tree 没 commit
- 用户装 v0.4.22 拿到的是 v0.4.21 内容

### Fix

不动错的 v0.4.22 tag（避免 destructive 操作改已发布版本），发 v0.4.23 把
v0.4.22 应有的真代码真发出去。

v0.4.22 在 CHANGELOG 保留作为「该有但没真发」的历史记录，README / install
指引都跳到 v0.4.23。

### 真教训

karma 自己的 pre_tool_use hook 拦命令导致 commit 失败 → 但 shell `&&` 链
继续跑后面 tag/push/release → 产生「tag 指向错 commit」幽灵 release。这是
shell `&&` 短路行为跟 karma 拦截语义的真冲突。

下次 commit + tag + release 类链式命令应该用 `set -e` 或者拆开跑保证前一步
失败不继续。或者 karma hook 应该返回 exit code 让 shell `&&` 真短路。

## [0.4.22] — 2026-05-14（patch — 反喂自审：v0.4.13~20 多个 fix 过宽真漏拦修复）

**⚠️ 此版本 tag 误指向 v0.4.21 commit 内容，真代码在 v0.4.23 补发。**

### 真触发（用户问 + 自审）

用户问「全修成 0 了会不会造成真阳被误判成假阳了」 — 触发 sticky #5「反喂边界」
+ 真阳召回率反思。重新按**用户视角**构造真违反 case 跑现行 check，发现本回合
6 个 fix 中 5 个真过宽，**多个真阳被错豁免**：

| Fix | 真漏拦 case | 严重度 |
|---|---|---|
| v0.4.13 deep-fix | `python -c "os.system('rm karma')"` → None | **真绕过漏拦** ⚠️ |
| v0.4.14 evidence | `pytest --collect-only && git commit` → None | 假证据漏拦 |
| v0.4.15 chinese-plain | 表格 cell 堆多 jargon 话术 → None | 真话术漏拦 |
| v0.4.18 non-blocking | `python -c "time.sleep(60)"` → None | 真阻塞漏拦 |
| v0.4.19/20 keep-pushing | 「OK 就这样了 / 今天到此为止」→ None | 柔性停顿漏拦 |

### 真根因

audit 修后 0 触发**不代表 fix 真根因正确** — 可能只是把真阳吃了。这是经典
sticky #5「**靠 audit 数据评估 fix 效果 = 反喂思维**」陷阱。之前的「闭环视图」
结论过乐观。

### Fix（4 类集中修）

1. **`bypass_karma.py` 加 python 调 shell 真绕过接口**：`os.system / subprocess.
   run / shutil.rmtree / Path().unlink` 等扩进 `_PYTHON_OR_SHELL_WRITE_RE`。
   v0.4.13「python -c 跳 shell `>` 重定向」豁免不再放任真绕过过。
2. **`non_blocking.py` 加 `_PYTHON_REAL_BLOCK_RE`** 识别 python 真阻塞：
   `time.sleep(N≥1) / asyncio.sleep / subprocess sleep / os.system sleep`。
   v0.4.18「python -c 跳 sleep」豁免不再放任真 python 阻塞过。
3. **`chinese_plain.py` 加 jargon 密度判定**：jargon ≥ 3 个时用未剥表格的 natural
   扫（堆 jargon 是话术）；< 3 个用剥表格的 natural_for_ratio 扫（单引用是项目
   术语）。v0.4.15「表格 cell 全豁免」过宽修正。
4. **`evidence.py` 加 `_FAKE_TEST_FLAG_RE`** 识别 pytest 假证据 flag：`--collect
   -only / --help / --version` 等不算真跑测试。
5. **`keep_pushing.py` `_STOP_HINT_RE` 加柔性停顿**：「今天到此 / 到此为止 /
   就这样了 / 就这样吧 / 搞不定了 / 算了吧」等。`_PUSH_SIGNAL_RE` 加 `(?!\\s*[
   吧行])` 排除「下次 X 吧」类推卸语气（部分覆盖，「下次 X 这事吧」 5 字隔开
   仍漏，接受 limitation）。

### 验证

342 测试全过；加 6 个新守护测试函数共 12 个 assert 真违反 case。

### 教训

**sticky #5「不能用测试集反喂」**真深刻 — 不能靠「修后 audit 数据 0 触发」当 fix
有效证据，那是反喂思维。真验证只能：
1. 按**用户视角**真构造真违反 case 跑现行 check 看是不是漏拦
2. 真用户跨场景使用 + 报真阳漏拦 case
3. 不靠自己造的对偶守护测试（那是 confirmation bias）

## [0.4.21] — 2026-05-14（feat — audit --format md 输出 markdown 表格）

### 真价值

dogfooding 数据粘贴到 PR / issue 分享更方便 — 当前 plain text 视图复制粘
贴破排版。markdown 输出直接 GitHub flavored，dogfooding 治理曲线一目了然。

### Fix / Feat

`karma/cli.py`：

- `cmd_audit` 加 `output_format: str = "text"` 参数。`output_format="md"`
  时每条 sticky 用 `### [sid]` heading + markdown 表格输出触发词清单
- 触发词 cell `|` 转义 `\\|` + 换行折叠成空格防破表
- CLI 加 `--format md` flag。组合用：`karma audit --with-fix-timeline --format md`

### 真跑通

```
# karma 违反审计 (总 66 条)

### [keep-pushing-no-stop] 33 条触发 [check 最新 fix 05-14 19:01: 修前 33 / 修后 0]

| 次数 | 占比 | 触发词 | 标记 |
|---|---|---|---|
| 32 | 97% | `response 纯陈述完结...` | ⚠️ 可能假阳 |
```

### 验证

335 测试全过；ruff/mypy 全绿。

## [0.4.20] — 2026-05-14（patch — keep-pushing 推进信号位置错判：中段推进 + 末尾列表）

### 真触发

v0.4.19 装上后**仍触发**：dogfooding 实测末尾响应「**下次接手做 HANDOFF 候选**...
（chinese-plain 38% Agent 用词手册 / long-term SEED 清理 / audit timeline
markdown 输出）」被错算无推进。

### 真根因

`_TAIL_WINDOW=80` 限定只看末尾 80 字 — 推进信号「下次接手做 X」在中段，
末尾是列表收尾「(A / B / C)」。整 response 已有推进意图但 tail 80 字看不到
被错算「就此停下」。

这是 v0.4.19 `_PUSH_SIGNAL_RE` 扩展的盲区 — 不是「没识别推进字眼」是
「推进字眼位置在 tail 外」。

### Fix

`karma/checks/keep_pushing.py` 加新豁免（紧接 `_PUSH_SIGNAL_RE.search(tail)`
豁免后）：

```python
# 整 response 含推进规划 + 末尾窗口无明确停顿语气 → 豁免
if _PUSH_SIGNAL_RE.search(text) and not _STOP_HINT_RE.search(tail):
    return None
```

`_PUSH_SIGNAL_RE` 在**整 text** 搜（而非 tail），配合「末尾不含 `_STOP_HINT_RE`
停顿语气」守护防误豁免（真推进 + 真停顿同时存在该按停顿算）。

### 验证

3 向真测：
- 推进信号在中段 + 末尾列表收尾 → None ✓（v0.4.20 真根因 fix）
- 推进信号在中段 + 末尾真停顿语气「先到这」 → 仍命中 ✓（对偶守护）
- 纯陈述完结无推进无问号 → 仍命中 ✓

335 测试全过；加 2 个守护测试。

## [0.4.19] — 2026-05-14（patch — keep-pushing 第 3 类假阳：未来规划 / 显式让用户介入）

### 真触发

`karma audit` 显示 keep-pushing-no-stop 修前 26 / 修后 6 — v0.4.12 部分修
后仍触发 6 次（最近 5 turn 11 次），都是「response 纯陈述完结无推进」类
karma 自标 ⚠️ 可能假阳。dogfooding 看真 snippet 找出 3 类剩余假阳：

1. **「下次接手做 X」「下个 session 推进 X」类未来规划** — 真有下一步
   计划但 `_PUSH_SIGNAL_RE` 要求「现在 / 立即 / 接下来去 + 动词」更强信号
2. **「候选 X」描述** — 表达了下一步候选但没用立即信号
3. **「请决定 / 请授权 / 等你 X」显式让用户介入** — 按 sticky #7 合法 stop
   路径，但被算无推进

### 真根因

keep-pushing 误把「**已有下一步规划**」当成「**就此停下**」— 当前只检测
即时推进信号（现在做 X）跟即时停顿（先到这），漏掉「未来规划延续」
跟「合法让用户介入」两类合理 stop 信号。

### Fix

`karma/checks/keep_pushing.py`：

1. **`_PUSH_SIGNAL_RE` 扩三类未来推进规划**：
   - 下次/下个 session/下回 + 动作（接手/做/治理/推进/fix/修/改）
   - 候选(清单/列表/第) + 序号 = 真规划
   - 接手/接力 + 动词 = 真延续

2. **`_STOP_HINT_RE` 收紧「下次」字面**：旧 `下次跑|下次看|下次再|下次见`
   改为 `下次再来|下次再说|下次见|下次有空` — 只匹配真模糊收尾形态
   （「下次跑 X」「下次看 X」可能是真规划）。配合 `_PUSH_SIGNAL_RE` 扩
   的「下次接手做 X」豁免。

3. **新 `_EXPLICIT_USER_HANDOFF_RE`** — 「请决定/请授权/请确认/等你 X」
   类显式让用户介入。按 sticky #7 合法 stop 路径，豁免检测。

### 验证

5 向真测：
- 「下次接手做 X」/「下个 session 推进 X」/「候选清单 1.2.3.」/「接手做 X」 → None ✓
- 「请决定」/「等你确认」/「请授权」 → None ✓
- 「下次再说」/「先到这」/「告一段落」/「下次见」真停 → 仍命中 ✓

333 测试全过；加 3 个守护测试函数共 11 个 assert。

## [0.4.18] — 2026-05-14（patch — non-blocking python -c sleep/wait 假阳：复用 v0.4.13 根因）

### 真触发

dogfooding 实测 `non-blocking-parallel` 7d 5 次假阳率 60%。HANDOFF 候选第 1
件治理：karma 自测 `_SLEEP_RE` 探针 `python3 -c "for c in ['sleep 5']: ..."`
被错算真 shell sleep；`python -c "from x import _WAIT_RE"` identifier 字面
被错算 shell wait。

### 真根因

跟 deep-fix v0.4.13 `_WRITE_OP_RE` 同根因：`strip_shell_quoted_literals`
保留 `python -c` 内容（设计上拦 `bash -c 'rm karma'` 类绕过），但 python
代码里的 `sleep` / `wait` 字面是 identifier / 字符串数据不是 shell 真调用。

### Fix

`karma/checks/non_blocking.py` 加 `_LANG_C_HEAD_RE`（跟 bypass_karma.py
v0.4.13 完全一致）：

```python
_LANG_C_HEAD_RE = re.compile(
    r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b",
    re.IGNORECASE,
)
```

sleep + wait 检测前先看 `is_lang_c = bool(_LANG_C_HEAD_RE.search(cmd_raw))`，
是宿主语言 -c 时跳过这两类检测。

### 已知 limitation

`python -c "import time; time.sleep(30)"` 类真 python 睡眠也豁免（按 sleep
字面只在 shell 上下文有意义的设计）。真 python 等待应该用 background +
回调而不是 time.sleep，这条 limitation 接受 — 用户 python 代码内逻辑由
其他工具检测（karma v2 边界）。

### 验证

- python -c 内 sleep 字面 → None ✓
- python -c 内 _WAIT_RE identifier → None ✓
- node / ruby / perl -c 同等豁免 ✓
- 裸 shell `sleep 30 && echo done` → 命中 ✓
- kubectl/docker wait 等合法子命令仍豁免 ✓

330 测试全过；加 3 个守护 case 在 `tests/test_checks.py`。

## [0.4.17] — 2026-05-14（feat — audit --with-fix-timeline dogfooding 闭环视图）

### 真价值

dogfooding 闭环视图 — 让用户能看「我修了 v0.4.X 后某条 sticky 假阳真的
不再触发」。这是 v0.4.16 协议层 fix（修真根因后自动恢复 force_block）的
**自然延续** — 视图层证据 vs 协议层机制。

### Fix / Feat

`karma/cli.py`：
- 加 `_check_file_last_commit_ts(sticky_id, sticky_list)` 用 `sticky.yaml.
  violation_checks` 反查 `REGISTRY[func_name].__module__` → check 文件路径
  → `git log -1 --format=%ct -- <path>` 取最新 commit ts
- `cmd_audit` 加 `with_fix_timeline: bool` 参数。开启时每条 sticky 行追
  加 `[check 最新 fix MM-DD HH:MM: 修前 X / 修后 Y]` 标记
- CLI 加 `--with-fix-timeline` flag

### 设计约束

- 仅 karma 仓库 cwd + git 可用时启用（dev 工具，不破坏跨用户场景）
- fail open — 不在 karma 仓库 / git 不可用 → 静默不报错，正常 audit 视图
- 粒度：单 check 文件最新 commit ts（不区分「真根因修复」vs「注释 / 重构
  commit」） — dev hint 用足够，不追求精准

### 真跑通

```
karma 违反审计 (总 64 条):
[keep-pushing-no-stop] 32 条触发 [check 最新 fix 05-14 18:17: 修前 26 / 修后 6]
[chinese-plain-no-jargon] 11 条触发 [check 最新 fix 05-14 18:36: 修前 11 / 修后 0]
```

chinese-plain 修前 11 / 修后 0 = v0.4.15 真根因 fix 真生效 dogfooding 闭环证据。
keep-pushing 修前 26 / 修后 6 = v0.4.12 部分修，第 3 类假阳还在（HANDOFF 候选）。

### 验证

327 测试全过；真跑 `karma audit --with-fix-timeline` 输出完整 timeline 标记。

## [0.4.16] — 2026-05-14（patch — force_block 协议真根因：只惩罚当前 turn 真触发）

### 真触发

dogfooding 实测真死循环：

1. chinese-plain check 累积 8 次 force_block
2. 真根因深挖 + v0.4.15 发布修了（表格 cell jargon 扫描豁免）
3. 但 force_block 看「最近 3 turn 累积 8 次」仍**继续 force_block**
4. 即使**当前 turn 0 次真触发**chinese-plain，force_block 仍报同样 8 次累积
5. Agent 修了真根因没法靠「不再违反」解除 force_block — **死循环**

### 真根因

`karma/hooks/stop.py` 的 force_block 逻辑（line 210-213）：

```python
over_threshold = [
    sid for sid, n in counts_force.items()
    if n >= force_threshold and sid not in exempt_ids
]
```

只看「最近 3 turn 累积超阈值」+「不在 force_block_exempt 列表」，
**没要求当前 turn 真触发该 sticky**。导致 fix 后 Agent 仍被历史
violation 卡死。

### Fix

加 `sid in hit_sticky_ids` 条件 — force_block 只惩罚「当前 turn 真
触发 + 历史累积超阈值」的 sticky：

```python
over_threshold = [
    sid for sid, n in counts_force.items()
    if n >= force_threshold and sid not in exempt_ids
    and sid in hit_sticky_ids  # ← v0.4.16 加
]
```

`hit_sticky_ids` 计算提到两个 `if notify_msgs:` 块前作共享变量
（之前在第一个块内定义，第二个块依赖 Python 函数级 scope 脆弱）。

### 设计原则

force_block 的目的是「**Agent 反复违反同 sticky 时强制让用户介入**」。
如果 Agent 已经**修了真根因不再违反**，应该自动解除不该继续 force_
block — 否则惩罚 Agent 的正确行为（修真根因）。

### 验证

326 测试全过；ruff/mypy 全绿。dogfooding 真闭环将在下个 turn stop
hook 真跑时验证。

## [0.4.15] — 2026-05-14（patch — chinese-plain jargon 扫描豁免表格 cell 引用）

### 真触发

dogfooding 第 8 次 force_block：上一 turn 末尾我写 markdown 表格汇报
`| 1 | 答 embedding 问 | ... |` 里 `embedding` 被 jargon 扫错算违反。

深挖：`_TABLE_ROW_RE` 已经在算 ratio 时把表格行剥（line 94），但
**jargon 词扫描用的是未剥的 `natural`**（line 116），表格 cell 里的
jargon 没豁免。

按 sticky 设计原理：表格是结构性引用（用户陈列项目术语），不是
jargon 话术（用户**用** jargon 说话）。表格 cell 里出现 jargon 应该
跟 URL 内英文词、版本号一样豁免。

### Fix

`karma/checks/chinese_plain.py` jargon 扫描全部从 `natural` 改用
`natural_for_ratio`（已剥 URL / 表格 / 版本号 / markdown / emoji /
kebab-snake-ident）。同步改 snippet / 上下文窗口的字符串引用。

### 验证

3 向真测：
- 表格 cell `| embedding |` → None ✓（结构性引用豁免）
- 表格外真 jargon `retrieval 做检索` → 命中 ✓（不豁免）
- 括号内解释 `embedding（嵌入向量）` → None ✓（已有括号检测仍生效）

326 测试全过；加 2 个守护 case。

### 注

本 turn 同时还有 chinese-plain 38% 触发，深挖发现是**真违反不是假阳**
— 我自己写 release note 风格汇报用了「release note / code identifier
/ jargon token」类英文复合词没汉字解释。按 sticky 第 3 条原则要求
**改自己用词**不是改 check。

## [0.4.14] — 2026-05-14（patch — evidence 两类假阳：chained pytest + heredoc commit prefix）

### 真触发

dogfooding 实测 `loud-failure-with-evidence` 7d 触发 3 次，深挖发现 2 次假阳：

1. **链式 `pytest && git commit`** — pre_tool_use 时 pytest 还没真执行，
   `has_recent_test=False` → 错拦合法 workflow
2. **heredoc 包裹的 conventional commit** — `git commit -m "$(cat <<'EOF'
   chore(release): ...\nEOF\n)"` 被错拦（`_NON_CODE_COMMIT_PREFIX_RE` 只
   识别 `"chore:"` 紧邻引号形式，不识别 heredoc / `$()` 嵌套包裹）

### Fix

`karma/checks/evidence.py`：

1. **豁免链式测试** — 加 `_CHAINED_TEST_RE` 识别 `pytest|npm test|jest|
   cargo test|go test|mvn test|gradle test|pnpm/yarn test|tox`。strip
   引号字面后扫骨架，避免 commit message 里字面提 pytest 误豁免「假声称」。

2. **放宽 conventional prefix 匹配** — `_NON_CODE_COMMIT_PREFIX_RE` 改
   `git\\s+commit[\\s\\S]*?(?:^|[\\s'"\\n])(docs|chore|style|build|ci|test|
   refactor)\\s*(?:\\([^)]*\\))?\\s*:` 跨多行匹配（识别 heredoc /
   `$()` 嵌套）。

### 验证

4 向真测：
- A. `pytest && git commit` 链 → None ✓（豁免）
- B. heredoc `chore(release):` commit → None ✓（豁免）
- C. 真违反无证据无 prefix → 命中 ✓
- D. commit message 字面提 pytest → 仍命中 ✓（strip 后骨架无 pytest）

324 测试全过；加 3 个守护 case 在 `tests/test_checks.py`。

## [0.4.13] — 2026-05-14（patch — deep-fix-not-bypass 假阳：python -c 比较运算符不是 shell 重定向）

### 真触发

dogfooding 实测：跑 `python -c "...json.loads(l).get('ts', 0) > cutoff..."`
读 violations.jsonl 时被 `deep-fix-not-bypass` 错拦「绕开检测 — 手动写
karma 内部状态」。深挖：`_WRITE_OP_RE` 的 `> c` 命中了 python 代码里的
比较运算符 `> cutoff`，因为 `strip_shell_quoted_literals` 保留 `python -c`
内容（设计上为拦截「`bash -c 'rm karma'`」类 indirect 绕过）。

### Fix

`karma/checks/bypass_karma.py` 拆 `_WRITE_OP_RE` 成两类：

- `_PYTHON_OR_SHELL_WRITE_RE` — 跨语言通用 python 写字面（`.write` /
  `.unlink` / `json.dump` 等），shell + python 都扫
- `_SHELL_REDIR_WRITE_RE` — shell-only `>` 重定向

加 `_LANG_C_HEAD_RE` 识别命令头 `python(\\d+)? -c` / `node -c` / `ruby
-c` / `perl -c`。是宿主语言 -c 时**跳 shell 重定向检测**（python 代码里
`>` 是比较不是重定向），但 `.write` / `.unlink` 仍扫真 python 绕过。

### 验证

4 向真测：
1. `python -c "... 'ts', 0) > cutoff ..."` read → None ✓（不再误拦）
2. `python -c "open(karma).write('{}')"` → 命中 ✓（真 python 写绕过）
3. `echo '{}' > ~/.claude/karma/session-state.json` → 命中 ✓（shell 真绕过）
4. `karma violations clear` → None ✓（CLI 合法操作）

321 测试全过；加 3 个守护 case 在 `tests/test_bypass_karma.py`。

## [0.4.12] — 2026-05-14（patch — keep-pushing 假阳治理 + scripts/verify-installed.sh）

### 真触发

`.venv/bin/karma stats` 看：`keep-pushing-no-stop` 最近 5 turn 触发 **10
次**最高频。深挖 5 次 snippet 发现 3 次假阳：

- `316 测试全过，Release 链接：...` × 2 — 「数字 + 测试 + 全过」是真
  成功汇报但 `_SUCCESS_REPORT_RE` 只覆盖 `X/X 通过` 跟 `X passed` 跟
  `测试 X` 三种语序，漏了「N 测试全过」「测试 N 全过」
- `我去看 karma check ...` — 「我去 + 看/查」是真近 future 推进信号
  但 `_PUSH_SIGNAL_RE` 漏覆盖（只有「我现在/立刻/马上 + 动词」）

### Fix

`karma/checks/keep_pushing.py` 两处 regex 扩：

- `_SUCCESS_REPORT_RE` 加「`\\d+ 测试/tests (全/all)? 通过/过/绿/passed`」
  跟「`测试/tests \\d+ (全/all)? 通过/过/绿/passed`」两种语序
- `_PUSH_SIGNAL_RE` 加「我去/我要去」类近 future + 动词扩展（看/查/测
  /检查/确认/核对）

加 2 个守护测试（4 个 assert）`tests/test_keep_pushing.py`。

### 真根因第二层 — 发版流程

v0.4.9/10/11 三连发 chinese-plain fix 都没装到本机 .venv，hook 跑
v0.4.8 旧字节码，force_block 累积 6 次都没生效（代码层 fix 真做了但
运行层假完成）。

加 `scripts/verify-installed.sh`：对比 pyproject 版本 vs `.venv/bin/karma
--version` 不一致就退 1（加 `--reinstall` 自动 uv pip 重装本机）。
HANDOFF.md「接手前必读」加发版后必跑提醒。

### 验证

318 测试全过；ruff/mypy 全绿。

## [0.4.11] — 2026-05-14（patch — chinese-plain 再修：kebab/snake 项目标识符不算 jargon）

### 真触发

v0.4.10 刚发完一句汇报响应立即触发**第 6 次** force_block：karma 自己的
release note 风格响应大量含项目专有标识符（`chinese-plain-no-jargon` /
`force_block` / `karma-v1` / `sticky_id`），这些**含连字符或下划线的英文
token** 被算成英文 jargon 词数，拉低中文占比 < 40%。

剥过版本号 / markdown / emoji 后还剩 9 个英文 token > 8 阈值就触发；
其中 4 个是项目专有标识符。

### Fix

`karma/checks/chinese_plain.py` 增 `_KEBAB_SNAKE_IDENT_RE`：

```python
_KEBAB_SNAKE_IDENT_RE = re.compile(
    r"\b[a-zA-Z][a-zA-Z0-9]*(?:[-_][a-zA-Z0-9]+)+\b"
)
```

含至少一个 `-` 或 `_` 连接的英文 token = code identifier 不是自然语言
jargon 话术（用户看代码自己也用这些原文），算 ratio 时剥。

剥除链顺序：URL → table row → version → markdown mark → emoji → **ident** → 算 ratio。

jargon 词扫描仍用原文（`retrieval` / `embedding` 等真 jargon 仍命中）。

### 验证

dogfooding 实测第 6 次真触发 case → None；真 jargon `retrieval embedding` 仍命中；
纯 ident 段（chinese-plain / force_block / karma-v1 / sticky_id）→ None。
tests/test_checks.py 加 kebab/snake 守护 case。

## [0.4.10] — 2026-05-14（patch — chinese-plain 假阳消除：版本号 / markdown / emoji 不算 jargon）

### 真触发

dogfooding 实测：`chinese-plain-no-jargon` 累积 **5 次 force_block 干预**。深挖发现
5 次都是 post-v0.4.3 fix 类汇报响应 — 含大量版本号字面（`v0.4.6` / `v0.1.x`）
+ markdown emphasis（`**真深挖**` / `* item`）+ emoji（`✅⚠️`），把中文占比从
正常 ~50% 拉到 34-39% 误判低于 40% 阈值。

这些都是**结构性 / 装饰性内容不是自然语言 jargon 话术**，算 ratio 时应剥除。

### Fix

`karma/checks/chinese_plain.py` 增 3 个剥离正则在算 ratio 前应用：

- `_VERSION_RE` — `v0.4.6` / `0.4.3` / `v1.2.3-rc1` 等版本号字面
- `_MARKDOWN_MARK_RE` — `**` / `*` / `~~` / 行首 `- * # > +` / 行内 `` ` ``
- `_EMOJI_RE` — `☀-➿` / `U+1F300-1FAFF` / `✅❌⚠✨⭐`

剥除链顺序（紧接已有 URL / 表格剥离）：
URL → table row → version → markdown mark → emoji → 算 ratio。

注意只在**算 ratio 时剥**，jargon 词扫描仍用原始 natural 文本（这样真 jargon 仍命中）。

### 验证

实测 v0.4.6 类技术报告 case → None（不再误触发）；真 jargon `retrieval embedding`
等仍命中。tests/test_checks.py 加 1 个 markdown emphasis 守护 case。

## [0.4.9] — 2026-05-14（patch — codex 0.130 hook approval gate 最终真根因）

sub-agent 用 `pty.fork()` 真起 codex CLI TUI（绕过主作者 expect 失败 / codex
panic 的两个坑）找到**最终真根因**：

### 真发现：codex 0.130 hook approval gate

codex 0.130 起所有新装 hook **默认 quarantined**（待审批），必须 TUI 内
交互式 `/hooks` 命令手动 approve 后才执行。TUI 启动横幅显示 `⚠ N hooks
need review before they can run. Open /hooks to review them.`

这是 codex 0.130 **安全设计不是 bug**（防恶意 hook 自动执行），但带来真
用户体验影响：karma 装完后 codex 不会自动调度 wrapper，**第一次 TUI 必须
手动审批 4 个 karma wrapper**。

之前所有「装机就绪但 hook 不触发」的真根因都是这个 approval gate —
不是 v0.4.8 推断的 Desktop App regression（#21639 是另一个独立问题）。

### Docs

- README 客户端表 codex 行更新：装完必须 TUI 内 `/hooks` 审批 4 个 wrapper
- README「让 AI 帮你装」段加 codex 0.130 approval gate 关键最后一步（含
  TUI 命令示例 `> /hooks` 跟 approve 流程）
- HANDOFF 同步真根因 + sub-agent 附带发现（codex CLI panic 「byte index
  u64 wrap」用位置参数绕过）

### 验证方法（给同事真终端跑）

```bash
codex                # 起 CLI TUI（不是 Desktop App）
                     # 看到「⚠ N hooks need review」横幅
> /hooks             # 交互审批 karma 4 个 wrapper
> /quit              # 退出
# 之后再跑任何 codex 命令 karma hook 真触发
```

### Test

测试 314 全过，4 件套全绿。

## [0.4.8] — 2026-05-14（patch — CI fix + codex Desktop App 上游 regression 真根因记录）

### Fixed

- **CI 跨平台测试 fail 修** — v0.4.7 P1 加 `client_installed()` 门槛后所有
  `cmd_install_hooks()` 测试在 CI 环境（无 claude 命令也无 `~/.claude/`）
  集体 fail。修：`fake_home` fixture 默认显式 mock 3 个 backend
  （Claude=True / Codex=False / Gemini=False），测试 isolation 跟环境无关。

### Docs — codex hook 上游 regression 真根因深挖记录

用户挑战「这几天 vibe island 一直能调用 codex cli 的 hook」驱动 4 步深挖：

1. 我看 bridge.log 200 行推「0 条 codex 触发」→ 错（没看 rotated `.log.1`）
2. 看 `.log.1` 仍 0 条 → 推「作者从没用过 codex」→ 错（用户确认用 Desktop App）
3. WebSearch 找到 [GitHub codex issue #21639](https://github.com/openai/codex/issues/21639)
   「Hooks no longer run after Codex Desktop update」
4. WebFetch issue 真细节：**regression 仅影响 codex Desktop App**
   （build 26.506.21252+ / cli_version 0.129.0-alpha.15+），**CLI 不受影响**

**真状态**：
- karma 装在 `~/.codex/hooks.json` 对应 codex **CLI** — 用 `codex` 终端命令
  跑 TUI 真触发 hook（按 issue 推断，需真终端验证）
- 用 codex **Desktop App** GUI → 命中上游 regression → hook 不调度 → 等
  OpenAI 修（issue 未分配 / 未 milestone）

README 客户端表 + 给同事 AI prompt 块 + HANDOFF 都加上游 bug 说明 + 「用
CLI 终端跑绕过 Desktop App regression」指引。

### Verified

- karma 在 codex 协议下 5/5 真生效（模拟 codex payload 跑 4 wrapper 全过 +
  sticky 注入 1186 字 + decision=block 真输出 + violations 真写入）
- codex 端启动条件 3/3 齐全（features.hooks=true / config.toml / wrappers
  可执行）
- 唯一未真验证层：codex CLI TUI 真完成一个 turn 的 hook 调度证据 — Bash
  expect 自动化模拟两次都失败（一次 turn 立即 close / 一次 codex panic），
  需真终端 5 秒手动验证

### Test

测试 314 全过，4 件套全绿，CI 跨平台真转绿。

## [0.4.7] — 2026-05-14（patch — sub-agent 排查 5 个 P0 全落地）

「感觉还不是很有把握公开 + 给同事 collaborator 让他先用」触发 sub-agent
站陌生同事视角全面排查首装隐患，找到 5 个真问题。本版全部落地。

### Fixed — P1 真 bug

- **`cmd_install_hooks` 默认 `claude-code` backend 不查 `client_installed()`
  静默装 hook 配置** — 之前同事没装 Claude Code 跑 `karma install-hooks`
  会闷头写 `~/.claude/settings.json`，完全无反馈他不知道 hook 不会触发。
  修：单 backend 路径也加 `client_installed()` 门槛，检测不到时报错并提示。
  加 `test_install_hooks_aborts_when_client_not_installed` 守护测试。

### Docs — P2/P3/P4/P5 一并修

- **P2**：README「让 AI 帮你装」段 AI prompt 块加 `gh auth status` 前置
  检查 — 私有仓库期间同事 Claude Code 拿到 prompt 不会主动先看 auth 直接
  跑 `git clone` 401 一头雾水。
- **P3**：pyproject classifier 去掉 Windows 声明（karma wrapper 用 Unix
  shebang Windows shell 不识别，未真测过先不声明）+ README 前置要求加
  「Windows 建议 WSL」。
- **P4**：README 新增「装完立即做：自定义 sticky 偏好」段 — 明示 karma
  默认装的是「逐步确认型」（不含 keep-pushing），全权委托型用户要手动
  加 `keep-pushing-no-stop` 这条（含 YAML 模板可复制）。
- **P5**：README 「装完必读 2 条」整合 venv 警告到装完最显眼位置（原来
  藏在「维护跟卸载」段末尾同事看不到）。

### Test

测试 313 → 314 全过，4 件套全绿。

## [0.4.6] — 2026-05-14（patch — `karma uninstall` 一键卸装 alias）

### Added

- **`karma uninstall`** — `karma uninstall-hooks --backend all` 的一键 alias。
  陌生用户想完全卸装 karma 时不用记 backend flag 长串，一句 `karma uninstall`
  就清所有 backend（Claude Code / Codex / Gemini）+ 删 wrapper + 从客户端
  配置移除 karma entry，保留他人 hook（vibe-island / rtk 等）共存。

加 1 条守护测试（`test_uninstall_one_shot_alias`）。

### Test

测试 312 → 313 全过，4 件套全绿。

## [0.4.5] — 2026-05-14（patch — KARMA_HOME 环境变量 + sub-agent 评审驱动改进）

「同事即将首装」我 spawn 一个 sub-agent 扮演陌生用户跑首装清单**真测试**，
找到 5 条真问题。本版修最关键 P0：

### Added — `KARMA_HOME` 环境变量支持

之前 `~/.claude/karma` 路径写死 5 个模块（cli / sticky / violations /
session_state / config）— dry-run / CI / 多 profile 都污染默认 home。
sub-agent 评审作为 v2 边界 bug 标出。

新建 `karma/paths.py:karma_home()` 单一来源 + 所有模块用它。`KARMA_HOME`
env 隔离用法：

```bash
KARMA_HOME=/tmp/karma-test karma init            # 不动 ~/.claude/karma/
KARMA_HOME=~/karma-profile-A karma sticky list   # 多 profile
```

加 4 条 subprocess 测试守护（用新 Python 进程让 env 在 import karma 之前
真生效）：default 路径 / env override / 5 module 一致 / `~` 展开。

### Test

测试 308 → 312 全过，4 件套全绿。

### Pending（sub-agent 评审剩余 4 条 — 跟同事真实首装数据驱动再修）

- 给同事清单「检查 Python」给具体命令（`python3 --version` / `command -v uv`）
- 清单加 `karma init` 第 5 步明示（之前禁止 init 但 init 是必要步骤）
- 提示 git / shell（fish 用 `activate.fish`）/ 网络（github+pypi）要求
- README 装机示例 venv 后说明怎么退出 / deactivate

## [0.4.4] — 2026-05-14（patch — 首位真用户首装驱动的 3 个修）

「同事即将首装 karma」消息触发 README 站陌生用户视角重审 + 实际触发 3 个真
问题修。这是 dogfooding → real-user 转折点的标志性 patch。

### Fixed

- **`karma --version` 输出错版本号** — `__init__.py` 硬写 `__version__ = "0.1.0"`
  跟 pyproject 双维护失同步，bump 到 0.4.3 后 `--version` 还是输出 v0.1.0
  让用户疑惑。修：`__init__.py` 用 `importlib.metadata.version("karma")`
  单一来源读 pyproject metadata（editable install 后重 `pip install -e .`
  让 metadata 同步）。加 `test_version_matches_pyproject` 守护防回归。
- **`karma install-hooks --help` 漏列 `gemini-cli` backend** — `--backend
  claude-code|codex|all` 应该是 `claude-code|codex|gemini-cli|all`。Gemini
  CLI backend v0.4.0 加了但 help 文本忘更新。
- **CI 4 platform × Python 版本全 fail** — `test_install_hooks_all_backend_only_installs_detected`
  + `test_uninstall_all_backend_iterates_each_installed` 两条测试只 mock 了
  `CodexBackend` / `GeminiCLIBackend` 的 `client_installed`，没 mock
  `ClaudeCodeBackend`。作者本机有 `claude` 命令 + `~/.claude/` 目录 → 通过；
  CI hosted runner 没装任何 AI 客户端 → 全 False → exit 1。修：mock 全 3 个
  backend 让测试 isolation 跟环境无关。

### Docs — 首位真用户首装清单驱动 README 改进

- 加 Python ≥ 3.11 前置要求（pyproject 要求但 README 没提）
- 加 **⚠️ 关键最后一步「装完必须重启 AI 客户端」** — Claude Code / Codex /
  Gemini CLI 都是 session 启动时一次性读 hook 配置不重载，跑中 session karma
  不触发。新用户最容易踩坑。
- 加「维护跟卸载」段警告 wrapper 硬写 venv 路径 — 删 / 移动 / 重建 `.venv`
  前必须先 `karma uninstall-hooks --backend all`，否则 hook 指向不存在的
  python 让 AI 客户端启动报错。
- README 文末「状态」段加「**真实非作者用户使用期**」起点标记。

### Test

测试 307 → 308 全过（加 `test_version_matches_pyproject` 守护）。
**CI 跨 ubuntu/macos × py3.11/3.12 全绿** — 之前作者本机过但 CI fail 的 bug
真修对。

## [0.4.3] — 2026-05-14（patch — chinese-plain 表格 / URL 假阳修）

### Fixed

`chinese_plain_no_jargon` 假阳 — markdown 表格 / URL 把中文占比拉低误命中。

**实测触发场景**：作者发 release 汇报响应含 `https://github.com/.../tag/v0.3.0`
URL 35+ 字符全英文 + markdown 表格 `| v0.3.0 | Codex CLI backend |` 字面全
英文，把主体中文占比从 ~50% 拉低到 15-28% 触发 force_block（累积 5 次 ≥ 阈值）。

但 URL / 表格是**结构性内容**不是 jargon 话术。修：算 ratio 前先剥：

- `_URL_RE` 剥裸 URL + markdown 链接 `[text](url)` + email
- `_TABLE_ROW_RE` 剥整行 markdown 表格（`| ... | ... |` + `|---|` 分隔行）

加 3 条守护测试：URL 剥 / 表格剥 / 真 jargon 对偶（用了真 jargon 仍拦
保证不放过真违反）。

### Test

测试 304 → 307 全过，4 件套全绿。

## [0.4.2] — 2026-05-14（patch — dogfooding 实测发现 bypass_karma 假阳）

### Fixed

`bypass_karma._WRITE_OP_RE` 误识别 `2>/dev/null` 类 stderr 重定向为写操作。

**实测触发场景**：跑 `python -c "...session_state.load(...)" 2>/dev/null`
只读 inspection karma 内部状态时被误拦 — 命令含 karma 状态路径字面
（`~/.claude/karma/session-state`） + `2>/dev/null` 之前被
`>\s*[/.~\w]` pattern 命中算「写」→ has_internal + has_write 都 True → 拦。

修：regex 加 lookahead 排除 `/dev/null` / `/dev/zero` / `/dev/stderr` /
`/dev/stdout` 等丢弃目标 — 它们不是真写到文件系统。

```python
>\s*(?!/dev/(?:null|zero|stderr|stdout))[/.~\w]
```

对偶守护：`2> /tmp/err.log` 这种真写日志文件**仍**算写（lookahead 只排除
丢弃目标，普通文件路径不放过）；`echo bad > ~/.claude/karma/session-state/abc.json`
真写 karma 状态仍要拦。

加 2 条守护测试覆盖只读 inspection + 真写对偶。

### Test

测试 302 → 304 全过，ruff / mypy / vulture 0 issue。

## [0.4.1] — 2026-05-14（patch — 抽 JsonHooksBackend 共用基类降未来 backend 成本）

### Refactor

从 vibe-island 实证清单（claude / codex / gemini / cursor / factory / qoder /
copilot / codebuddy / kimi 9 家客户端）学到「多客户端同模式」— 抽通用
`JsonHooksBackend` 基类，让加新 backend 变成「填表」工作而不是写整套：

- **`karma/backends/_json_hooks.py`** 通用基类，提供 90% 共用实现：
  client_installed / hooks_dir / settings_path / load_settings / save_settings /
  is_karma_entry / 默认 build_event_entry / 默认 pre_install_setup（空）。
- 3 个现有 backend 重构成继承基类，只填**类属性**：
  - `name` / `display_name` / `_CONFIG_DIR_NAME` / `_SETTINGS_FILENAME` /
    `_CLIENT_CMD` / `_HOOK_EVENTS`
- 子类**可选 override**：`build_event_entry`（不同 matcher / timeout）、
  `pre_install_setup`（Codex 启用 features.hooks）。

**未来加新 backend 模板**：

```python
class CursorBackend(JsonHooksBackend):
    name = "cursor"
    display_name = "Cursor"
    _CONFIG_DIR_NAME = ".cursor"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "cursor"
    _HOOK_EVENTS = {"UserPromptSubmit": "user_prompt_submit", ...}
```

3 行类属性 + 4 行 event 映射就装好一个新 backend。

### Code quality

- 3 个 backend 文件共减少 ~130 行重复代码（370 → 240 含基类）。
- 4 件套全绿：299 测试 / ruff / mypy（karma + tests） / vulture 0 issue。

## [0.4.0] — 2026-05-14（minor — 第三个 backend：Gemini CLI 适配）

### Added — Gemini CLI 装机支持

karma 三家 AI 编程客户端 backend 全打通：Claude Code（v0.1.0）+ Codex CLI
（v0.3.0）+ Gemini CLI（v0.4.0）。三个客户端 hook 协议跟 karma 实测兼容,
真实装机 / 卸装 / hook 触发 catch 违反全跑通。

- **`karma/backends/gemini_cli.py`**：新 `GeminiCLIBackend` 实现，
  `~/.gemini/settings.json` 配置（含 `hooks` 字段），默认启用（不像 Codex 要
  feature flag）。
- **`karma install-hooks --backend gemini-cli`** 装机；`--backend all` 自动
  装本机三家全检测到的客户端。
- **Stop hook 跨协议跨 backend 适配**：karma `stop.py` 现在适配 3 个不同字段名：
  | Backend | Stop event 名 | 字段 |
  |---|---|---|
  | Claude Code | `Stop` | `transcript_path`（反向读 transcript） |
  | Codex | `Stop` | `last_assistant_message`（直传） |
  | Gemini CLI | `AfterAgent` | `prompt_response`（直传） |
  
  优先级：直传字段 > transcript fallback。

### Key insight — Gemini event 名跟 Claude Code / Codex 不同

Gemini CLI 用自己的 event 名（`BeforeAgent` / `AfterAgent` / `BeforeTool` /
`AfterTool`）— 跟 Claude Code 的 `UserPromptSubmit / Stop / PreToolUse /
PostToolUse` 完全不同。

karma backend 抽象设计巧妙处理：**`hook_events()` key 是 backend 实际 event 名
（写进各家配置文件），value 是 karma 内部 wrapper basename**。这样 4 个 wrapper
（user_prompt_submit / pre_tool_use / post_tool_use / stop）跨 3 backend 完全
复用，karma hook 入口模块代码 0 改动。

| karma wrapper | Claude Code | Codex | Gemini CLI |
|---|---|---|---|
| user_prompt_submit | UserPromptSubmit | UserPromptSubmit | BeforeAgent |
| pre_tool_use | PreToolUse | PreToolUse | BeforeTool |
| post_tool_use | PostToolUse | PostToolUse | AfterTool |
| stop | Stop | Stop | AfterAgent |

### Verified（真跑实测）

- 装机：`~/.gemini/settings.json` 6 个 vibe-island event + 4 个 karma event 共存 ✓
- AfterAgent 模拟 payload 跑 karma stop.py → catch「我先打个补丁」违反 +
  decision=block + reason 输出 ✓
- 卸装：karma 4 entry 清除，vibe-island 7 个 entry 完整保留 ✓

### Test

- 测试 294 → 299 全过（加 Gemini event 映射 + 跨协议字段适配守护测试）。
- ruff / mypy（含 tests/）/ vulture 0 issue。

## [0.3.0] — 2026-05-14（minor — 多 backend 横向扩展：Codex CLI 适配）

### Added — Codex CLI 装机支持

karma 从「Claude Code 专用」升级为「多 AI 编程客户端通用」框架。新增 Codex
CLI 适配 — 协议跟 Claude Code **几乎一对一兼容**，实测装机 / 卸装 / hook 真
触发全跑通。

- **`karma/backends/` 多 backend 抽象**：`Backend` Protocol 定义客户端无关的
  装机接口（hooks_dir / settings_path / hook_events / build_event_entry 等）。
  - `ClaudeCodeBackend`：refactor 老逻辑进 backend，0 行为变化
  - `CodexBackend`：新建，`~/.codex/hooks.json` + 自动启用 `[features] hooks = true`
- **`karma install-hooks --backend codex|claude-code|all`**：默认 claude-code
  向后兼容；`--backend codex` 装 Codex；`--backend all` 装本机检测到的所有客户端。
- **`karma uninstall-hooks --backend ...`**：同样支持，验证保留他人 hook
  （vibe-island 等共存插件）。
- **`karma doctor` 跨 backend 显示**：每个客户端 ✓/✗ 检测，含 hook 装机状态。
- **Stop hook 跨协议适配**：优先用 Codex `last_assistant_message` 字段（直接
  给最后一条 assistant message），fallback Claude Code `transcript_path` 反向读
  transcript。Codex 性能更优（不用读文件）+ 向后兼容 Claude Code。

### Technical findings（实测真跑得到的协议细节）

- Codex feature flag 真名是 **`hooks`** 不是 `codex_hooks`（vibe-island
  config.toml 用过时名 `codex_hooks` 误导）— 通过 `codex features list` 确认
- Codex hook 只在 **interactive TUI 模式**触发，`codex exec` 非交互模式不触发
  （GitHub issue #17532 描述的已知行为）
- Codex 6 个 hook event vs Claude Code 4 个 — 共有 UserPromptSubmit / PreToolUse /
  PostToolUse / Stop（karma 用这 4 个）；Codex 额外有 SessionStart / PermissionRequest
- Codex stdin payload **没** `transcript_path`，但 Stop hook 直接给
  `last_assistant_message` — karma 自动适配

### Fixed

- **long_term 「长 ID if 分支」假阳收紧**：之前 `if cmd == "install-hooks"` 类
  合法 CLI dispatch 命中（13 字符 kebab-case 触发 12+ 字符门槛）。新 pattern
  用 lookahead 要求字面同时**至少 12 字符 + 含数字**（UUID / hash 满足，CLI
  命令名 / sticky id 不满足）。加 2 条守护测试。

### Refactor / Quality

- `cli.py` 旧硬编码 helper 函数（`_settings_path` / `_save_settings` /
  `_remove_karma_entries` / `_add_karma_entries` / `_check_hooks_installed` /
  `_karma_event_entry` / `_KARMA_HOOK_EVENTS` / `_SettingsParseError` 等）
  全部移除 — 用 backend 接口替代。代码量减少 ~80 行，可维护性提升。
- 测试 277 → 294（新增 backend 测试 15 条 + Codex stop 协议 2 条 + long_term 假阳 2 条）。

### Test / Quality

- 测试 294/294 全过，ruff / mypy（含 tests/）/ vulture 0 issue。
- 实测装机：`karma install-hooks --backend codex` 真写 `~/.codex/hooks.json`，
  vibe-island 4 个原 entry 全保留共存。卸装同样验证。

## [0.2.4] — 2026-05-14（minor — 跨平台 locale 自动检测）

### Added

新模块 `karma/locale_detect.py` — 跟其他 app（VS Code / Slack / Chrome）安装
时一样的「按系统语言偏好自动选」做法。

用户挑战 v0.2.3 的「locale 检测不可靠所以显式 flag」判断时实测找到：作者机器
`locale.getlocale()` 返回 `('en_US', 'UTF-8')` 但 `defaults read -g
AppleLanguages` 返回 `zh-Hans-CN`（作者真实系统语言）。我之前判断错了 —
Python `locale.getlocale()` 不准，但各平台有标准方法能准确读到用户偏好：

- **macOS**：`defaults read -g AppleLanguages`（系统设置 → 语言与地区里设的真实偏好）
- **Linux**：`$LC_ALL` > `$LC_MESSAGES` > `$LANG`（POSIX 标准优先级，桌面环境自动设）
- **Windows**：`ctypes.windll.kernel32.GetUserDefaultUILanguage()` + `locale.windows_locale`
  查表 LCID → ISO 代码（跟「设置 → 时间和语言 → Windows 显示语言」一致；
  Windows 默认 shell 通常不设 `$LANG`）

`karma init` 行为变化：

- `karma init`（无 flag）→ **自动按系统语言偏好选**：中文用户装 7 条完整
  含 chinese_plain；非中文 / 检测不到装 5 条精简。检测结果会打印让用户知道。
- `karma init --minimal` / `--no-minimal` 强制覆盖自动选择
- 容器 / CI / 异常环境（locale 全无）→ fallback 5 条精简（最安全默认）

加 17 条跨平台守护测试（mock subprocess / 环境变量 / Windows ctypes 三路径
独立验证）。

### Test / Quality

- 测试 258 → 275 全过，ruff / mypy / vulture 0 issue。

## [0.2.3] — 2026-05-14（patch — karma init --minimal flag）

### Added

- **`karma init --minimal`** 显式 flag 装 5 条真中性核心模板（评审 C Agent
  第二轮指出 minimal 模板存在但默认 7 条对英语母语用户仍是持续假阳源）。
  - 评审建议过「`karma init` 检测系统 locale 自动选」— 实测后否决：
    `locale.getlocale()` 在 macOS 默认返回 `en_US` 但用户实际可能是中文，
    自动猜错率高。改用显式 flag 让用户自己选（显式优于隐式）。
  - 默认 `karma init` 仍装 7 条向后兼容；末尾打印 `--minimal` 提示让英文
    用户知道有选项。
  - 加 2 条守护测试（`test_init_default_installs_7_sticky` /
    `test_init_minimal_installs_5_sticky`）。

测试 256 → 258 全过。

## [0.2.2] — 2026-05-14（patch — 第二轮评审 critical bug fix）

跑了第二轮独立 Opus 4.7 sanity-check 评审 Agent，找出 v0.1.1 修复时漏掉的
**真 critical 假阴**：

### Fixed

- **`strip_shell_quoted_literals` 双引号内 substitution 漏报（真 bug）** —
  双引号包 `$(...)` / 反引号 这种 shell 最常见写法之前会被 `_SHELL_QUOTED_RE`
  整段吞掉（连同 substitution 内容一起剥），导致 `non_blocking_parallel` /
  `long_term_fundamental` 等 check 全线漏报。v0.1.1 加的守护测试只测**裸**
  反引号 / `$()`，没覆盖「在双引号内」这个最常见场景。
  - 修：Step 0 先扫双引号字面，把内部 `$(...)` 和反引号内容「提升」到 cmd
    外层（shell 双引号真行为就是展开 substitution 执行）；单引号字面不动
    （shell 单引号语义就是字面文本不展开 — 对偶守护测试 case 验证）。
  - 反引号 / `$(` regex 加 negative lookbehind 排除转义形式（`\$(` / 反斜杠+反引号
    是字面 shell 不展开）— 修自身 fix 引入的 regression（commit message 引用
    bug case 字面时被自拦）。
  - 加 5 条守护测试覆盖：双引号 `$()` / 双引号反引号 / 单引号对偶 /
    转义 `$()` 字面 / 转义反引号字面。

### Test / Quality

- `KARMA_DEBUG_TRACE` 加 2 条守护测试（评审第二轮指出 v0.2.1 补了
  `KARMA_DEBUG` 但姊妹变量 `KARMA_DEBUG_TRACE` 没测过 — sticky #4 违反）。
- 测试 249 → 256 全过，ruff / mypy / vulture 0 issue。

### Docs

- README 测试数 234 → 252（v0.2.1 实际是 249，本版含 #1 fix 守护测试后 254）。
- `violation_checks` 表加「默认装？」一列 — 评审第二轮指出 `keep_pushing_no_stop`
  在 `sticky.dev.example.yaml` / `sticky.dev.minimal.example.yaml` 都没引用,
  但 README 表里平等列了 8 个让用户以为开箱可用。明示这条是「可选 — 给全权
  委托型用户，需要自己在 sticky.yaml 加引用」。

## [0.2.1] — 2026-05-14（patch — 凭假设没验证反查）

按用户「为啥有问题不修好呢」精神持续反查我之前用「假设的成本」推迟过的问题：

### Fixed

- **`ARCHITECTURE.md` 加「配置」章节** — v0.2.0 README 重组让链接指向
  `ARCHITECTURE.md#配置` 但实际**那节不存在**（凭假设没 grep 就写链接）。
  补完整字段表（10 条 config 字段 + 默认值 + 含义）+ 3 个调试环境变量说明
  （`KARMA_NO_NOTIFY` / `KARMA_DEBUG` / `KARMA_DEBUG_TRACE`）。
- **mypy 类型化** — 之前我说「会改 200+ 行」推迟，**真跑后只有 3 个 error**
  10 分钟修完（`testset.py` / `long_term.py` underscore 变量名跨类型重用 →
  `_label`；`cli.py:_karma_event_entry` dict 异质 value → `dict[str, object]`
  显式标注）。mypy 加进 `[project.optional-dependencies].dev` + CI 步骤守护。

### Test / Quality

- `run_checks` `KARMA_DEBUG=1` 门控加 3 条守护测试 — 之前加了功能没真验证过
  实际行为属于 sticky #4 「完成要有证据」违反。
- 测试 246 → 249，CI 跨平台跨 Python 版本全过，mypy 0 issue。

## [0.2.0] — 2026-05-14（minor — README 重组 + 新增真中性 sticky 模板）

### Added

- **`data/sticky.dev.minimal.example.yaml`** 真中性 5 条核心 sticky 模板：
  long-term-fundamental / non-blocking-parallel / loud-failure-with-evidence /
  deep-fix-not-bypass / read-before-write。砍掉默认 7 条里两条场景化规则
  （chinese-plain-no-jargon 中文用户偏好 / no-testset-no-future-leakage
  ML 场景）。
  - 评审 C Agent 真痛点：默认 7 条违反 CLAUDE.md「不针对当前用户作弊」
    原则。英文母语 / 非 ML 用户可 `cp data/sticky.dev.minimal.example.yaml
    ~/.claude/karma/sticky.yaml` 切换。
  - 默认 `karma init` 仍装 7 条（向后兼容现有 0.1.x 用户）。

### Changed

- **README 重组**（评审 C Agent 真痛点：视角错位 — 给「Agent 接力」写不是
  给陌生用户）：
  - 砍 30% 实现细节（heredoc 智能剥 / background catchup / 跨语言注释扫描
    等），移到 ARCHITECTURE.md
  - 「反馈机制」段改写成核心机制一句话概述，详细规则链 ARCHITECTURE.md
  - 「场景化定位」段加 2 套模板对比表，让陌生用户知道按场景选
  - 「sticky.yaml 写法」加完整字段表（含 `force_block_exempt`）+ 8 个内建
    `violation_checks` 函数名 + 简介表（之前用户写自定义 sticky 完全黑盒）

## [0.1.1] — 2026-05-14（patch — 评审 Agent B 第 4 条盲区一次修对）

### Fixed

`karma/checks/common.py:strip_shell_quoted_literals` 三个真违反假阴漏报修复 ——
之前 v0.1.0 评审时这条被判「等真用户碰到再修」，但用户当场纠正这是 sticky #1
「最根本长期方案」违反，应当现在修对：

- **反引号命令替换** `` `cmd` `` 现在显式按 indirect shell 处理 —— 内容是真
  执行子命令（之前没有专门捕获，依赖偶然不被剥）。
- **`$(...)` 命令替换** 同上 —— 跟反引号等价，`echo $(sleep 30)` 实际会执行
  sleep。
- **`bash -c sleep30` 无引号形式** —— POSIX 合法但之前 `_INDIRECT_SHELL_RE`
  要求引号包裹漏掉。新 `_INDIRECT_SHELL_NOQUOTE_RE` 取 `-c` 之后第一个 token。
- **`<<-EOF` tab 缩进 heredoc 终结符** —— bash `<<-` 允许 tab 缩进，之前
  `_HEREDOC_RE` 终结符前不允许空白会让 heredoc 不被识别 → 内容没剥 → 数据
  当真 shell 误判。修：终结符前允许 `[\t ]*` 空白。

加 4 条守护测试（`test_false_negative_regression.py`）。测试 241 → 245 全过。

## [0.1.0] — 2026-05-14（首个公开版本）

karma v2 的第一个可发布版本，经历多轮 dogfooding + 4 个 Opus 4.7 评审 Agent
交叉评审 + 1-2 小时质量打磨。

### Added

- **核心机制**：4 个 Claude Code hook（`UserPromptSubmit` / `PreToolUse` /
  `PostToolUse` / `Stop`）+ `sticky.yaml` 配置驱动的偏好提醒。
- **sticky schema**：`id` / `preference` / `violation_keywords` /
  `violation_checks` / `force_block_exempt`（详 `data/sticky.dev.example.yaml`）。
- **默认场景预设**：`sticky.dev.example.yaml` 7 条软件开发场景核心方向
  （长期方案 / 不阻塞 / 直白中文 / 完成证据 / 不喂测试集 / 不绕开检测 /
  先读再写）。
- **8 个工程检测函数**（`karma/checks/`）：`long_term_fundamental` /
  `non_blocking_parallel` / `chinese_plain_no_jargon` /
  `loud_failure_with_evidence` / `no_testset_no_future_leakage` /
  `read_before_write` / `keep_pushing_no_stop` / `bypass_karma_detection`。
- **session_state**：跨 hook 的 `turn_count` / 文件读写跟踪 /
  background 任务接证据 / 30 天自动清理。
- **violations.jsonl**：append-only 违反记录 + 5000 行自动 rotation。
- **CLI 命令**：`karma init` / `install-hooks` / `uninstall-hooks` /
  `doctor` / `stats` / `audit` / `reset` / `sticky list|edit|remove` /
  `violations recent|clear`。
- **桌面通知**：macOS（osascript） / Linux（notify-send） /
  Windows（msg）跨平台支持，`KARMA_NO_NOTIFY=1` 关。
- **累积告警 + 强制干预**：按 turn 维度（不是人类时钟）的违反累积，
  超阈值触发 Stop hook `decision=block`；`force_block_exempt: true`
  配置字段豁免「应该继续推进」类规则避免语义自我矛盾。
- **元层监管**：`bypass_karma_detection` check 拦 Bash 命令含 karma
  内部敏感字面 + 写操作（防 Agent 手改 session-state 绕检测）。
- **强提醒 fallback**：UserPromptSubmit hook 读上一 transcript 跑所有
  violation_checks，命中的注入「强提醒」段告诉本 turn Claude 上次违反。

### Fixed

- **Stop hook matcher 配置 bug**：`install-hooks` 给所有 event 加
  `matcher: '*'` → Stop / SessionStart / SessionEnd 等 event 不支持
  matcher → 被 Claude Code 无声忽略 → Stop hook 没装上。修：只对
  PreToolUse / PostToolUse / UserPromptSubmit 加 matcher。
- **`recent_turns / count_recent_turns` turn=None fallback bug**：
  老格式（turn 维度引入前）违反无 turn 字段时 `.get("turn", 0)`
  fallback 成 0，落入当前 turn 窗口造成 force_block 假阳。修：
  `if turn_raw is None: continue` 跳过。
- **force_block 跟「不阻塞 / 继续推进」类规则语义自我矛盾**：累积
  「停下太多」违反 → 触发 force_block 让 Agent「必须停下让用户介入」
  恰好再次违反规则本身。修：sticky schema 加 `force_block_exempt`
  配置字段，去硬编码 sticky id 名单。
- **`pyproject.toml` wheel 打包指向不存在文件**：`force-include` 指
  `sticky.example.yaml`（重命名后忘同步）。修正为 `sticky.dev.example.yaml`
  + `config.example.yaml`。

### 评审驱动的发布质量打磨

4 个独立 Opus 4.7 评审 Agent 跑出来的 P0 / P1 / P2 全部落地：

**安全 / 隐私**：
- `violations.py` 写入前 snippet 脱敏（`/Users/<name>/` → `~/`，长度上限 120 字符）
- `notify.py` argv 清洗（剥前导 `-` + 限长 + 折叠换行）防 notify-send / msg
  把用户 `violation_keywords` 当 flag 解析
- `cli.py install-hooks` JSONDecodeError 改 abort + 提示（之前静默覆盖会清空
  用户其他 settings.json 配置如 permissions / mcp / env）
- `_save_settings` 改 tmp + `os.replace` 原子写防中断 truncate
- 每次 install-hooks 额外写带时间戳备份（保留初次 `.before-karma` + ts 版本）

**假阳收紧（首装最高频痛点）**：
- `long_term --no-verify/--skip*/--force` 泛 flag 收紧到「git 危险动作 + 危险
  flag 同句」（之前 pytest --skip-broken / pip install --skip-existing /
  cmake --force / rsync --force 等合法 flag 全命中）
- `non_blocking._WAIT_RE` 改 `_is_blocking_wait` helper（拆子命令独立看，
  kubectl wait / docker wait / aws cloudformation wait / gcloud / az 豁免）
- `bypass_karma._WRITE_OP_RE` 移除 `cp/mv/rm`（用户备份 karma 状态文件 /
  清老 rotation 是合法自治，真 hack 路径用 `echo > / python write_text` 仍能 catch）
- `keep_pushing` 加 `_SUCCESS_REPORT_RE` 豁免「数字 + 通过词」类汇报
  （sticky #4「完成要有证据」鼓励的行为不该被 #7 罚）
- `read_first` 路径规范化（`./foo.py` / `foo.py` / `/abs/foo.py` / `~/foo.py` 等价）

**代码质量 refactor**：
- `karma/checks/_types.py` 抽 `CheckHit` / `CheckFn` Protocol —— 消除 8 处
  子模块函数体内反向 `from karma.checks import CheckHit` 循环依赖代码味道
- `violations.py` 抽 `_scan_tail_jsonl` 用 `collections.deque(maxlen=N)`
  真 tail（之前 `splitlines()[-N:]` 是全文件读再切片）；4 个 `recent_*`
  从 20+ 行重复减到 8-12 行调用 helper
- `run_checks` 加 `KARMA_DEBUG=1` 门控的 stderr trace（check 函数抛异常时
  打 traceback 让用户调试自定义 check 不再黑盒）

### Test / Quality

- 241 个测试全过；ruff lint 0 error；vulture 死代码扫 0 输出。
- `pip install -e ".[dev]"` 装 pytest + ruff + vulture。
- `.github/workflows/ci.yml` 跨 ubuntu / macOS × py3.11 / 3.12 跑 lint +
  vulture + pytest + wheel build。

[Unreleased]: https://github.com/jhaizhou-ops/karma/compare/v0.4.9...HEAD
[0.4.9]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.9
[0.4.8]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.8
[0.4.7]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.7
[0.4.6]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.6
[0.4.5]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.5
[0.4.4]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.4
[0.4.3]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.3
[0.4.2]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.2
[0.4.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.1
[0.4.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.0
[0.3.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.3.0
[0.2.4]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.4
[0.2.3]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.3
[0.2.2]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.2
[0.2.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.1
[0.2.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.0
[0.1.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.1
[0.1.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.0
