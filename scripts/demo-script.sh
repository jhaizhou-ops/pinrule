#!/bin/bash
LANG_MODE="${LANG_MODE:-zh}"
banner() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "  $2"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 1.5
}

PY=.venv/bin/python

if [ "$LANG_MODE" = "en" ]; then
    export PINRULE_LOCALE=en
    export PINRULE_HOME="${PINRULE_HOME:-/tmp/pinrule-demo-en-home}"
    T1="Scene 1/5 — Inject full rule baseline at session start"
    T1S="(SessionStart hook → full sticky baseline ~435 chars)"
    T2="Scene 2/5 — Real-time block of sleep 30"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="Scene 3/5 — Catch short-term intent in Agent response"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="Scene 4/5 — Nudge Agent to keep pushing after silent stop"
    T4S="(Stop hook → keep-pushing-no-stop)"
    T5="Scene 5/5 — Mid-conversation full reinject at decay threshold"
    T5S="(PostToolUse hook → byte_seq hits Opus 60K → full baseline)"
    TE="That's pinrule — pure engineering, zero LLM."
    TES="github.com/jhaizhou-ops/pinrule"
    FIX_LONGTERM=/tmp/pinrule-demo-fixtures/short-term-talk-en.jsonl
    FIX_SILENT=/tmp/pinrule-demo-fixtures/silent-stop-en.jsonl
else
    export PINRULE_LOCALE=zh
    export PINRULE_HOME="${PINRULE_HOME:-/tmp/pinrule-demo-zh-home}"
    T1="场景 1/5 — session 起手注入完整规则 baseline"
    T1S="(SessionStart hook → 全量 sticky baseline ~435 字符)"
    T2="场景 2/5 — sleep 30 实时拦截"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="场景 3/5 — Agent 回应短期话术拦截"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="场景 4/5 — Agent 静默停止时推动继续"
    T4S="(Stop hook → keep-pushing-no-stop)"
    T5="场景 5/5 — 长 context 累积到拐点中段补一次完整规则"
    T5S="(PostToolUse hook → byte_seq 达 Opus 60K 自动 reinject)"
    TE="这就是 pinrule — 纯工程, 零 LLM"
    TES="github.com/jhaizhou-ops/pinrule"
    FIX_LONGTERM=/tmp/pinrule-demo-fixtures/short-term-talk.jsonl
    FIX_SILENT=/tmp/pinrule-demo-fixtures/silent-stop.jsonl
fi

# Setup: 1) rules fixture → PINRULE_HOME, 2) transcript fixtures → /tmp/pinrule-demo-fixtures/
# (历史 bug: /tmp/pinrule-demo-fixtures/ 不存在 → scene 3/4 stop.py 读不到 transcript → 0 输出.
# 历史 bug: scene 5 无 rules.yaml → smart_reinject 早 return.)
mkdir -p "$PINRULE_HOME/session-state"
RULES_FIX="scripts/demo-fixtures/rules-$LANG_MODE.yaml"
[ -f "$RULES_FIX" ] && cp "$RULES_FIX" "$PINRULE_HOME/rules.yaml"
mkdir -p /tmp/pinrule-demo-fixtures
cp scripts/demo-fixtures/*.jsonl /tmp/pinrule-demo-fixtures/ 2>/dev/null

# Scene 1: session 起手注入完整 baseline (SessionStart hook).
# Note: user_prompt_submit hook v0.13.0+ 输出"精简 anchor" 只列累积违反过的 rule
# (新 session 0 违反 → anchor 空). session_start hook 起手注入**全量** baseline 是
# 给 Agent 看到完整 sticky list 的真触发点 — 这正是 demo 该展示的初印象.
banner "$T1" "$T1S"
echo '$ echo {session start} | pinrule_session_start.py'
sleep 0.8
echo '{"session_id":"sc1","source":"startup","cwd":"/Users/jhz/pinrule"}' \
  | $PY pinrule/hooks/session_start.py 2>/dev/null \
  | $PY -c "import json,sys; d=json.load(sys.stdin); ac=d.get('hookSpecificOutput',{}).get('additionalContext',''); print(ac[:500])"
sleep 0.8

# Scene 2: sleep 30 拦 (PreToolUse) — 解析 JSON 显示真换行 reason
banner "$T2" "$T2S"
echo '$ echo {tool=Bash, command=sleep 30} | pinrule_pre_tool_use.py'
sleep 0.8
echo '{"session_id":"sc2","tool_name":"Bash","tool_input":{"command":"sleep 30"}}' \
  | $PY pinrule/hooks/pre_tool_use.py 2>/dev/null \
  | $PY -c "
import json, sys, textwrap
d=json.load(sys.stdin)
out = d.get('hookSpecificOutput',{})
print(f\"  permissionDecision: {out.get('permissionDecision','')}\")
print()
# 按 76 col wrap 长 reason 行 — terminal 80col auto-wrap 在中文里换行不优雅
for raw in out.get('permissionDecisionReason','').split('\\n')[:4]:
    for w in textwrap.wrap(raw, width=72) or ['']:
        print(f'  {w}')
"
sleep 0.8

# Scene 3: long-term response-level 拦
banner "$T3" "$T3S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Let me just hardcode this case to ship it"'
else
    echo '$ # Agent 说: "我先硬编码这个 case 让 CI 过"'
fi
sleep 0.8
echo '$ pinrule_stop.py reads transcript, scans response'
sleep 0.8
echo "{\"session_id\":\"sc3\",\"transcript_path\":\"$FIX_LONGTERM\",\"cwd\":\"/Users/jhz/pinrule\"}" \
  | $PY pinrule/hooks/stop.py 2>&1 1>/dev/null | head -2
sleep 0.8

# Scene 4: keep-pushing nudge
banner "$T4" "$T4S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Task complete."  (pure statement, no next step)'
else
    echo '$ # Agent 说: "任务已经完成了。"  (纯陈述无下一步)'
fi
sleep 0.8
echo '$ pinrule_stop.py reads transcript, scans response'
sleep 0.8
echo "{\"session_id\":\"sc4\",\"transcript_path\":\"$FIX_SILENT\",\"cwd\":\"/Users/jhz/pinrule\"}" \
  | $PY pinrule/hooks/stop.py 2>&1 1>/dev/null | head -2
sleep 0.8

# Scene 5: PostToolUse 中段 reinject
banner "$T5" "$T5S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # session state: tool_byte_seq=62000 (past Opus 60K threshold)'
else
    echo '$ # session state: tool_byte_seq=62000 (已过 Opus 60K 衰减拐点)'
fi
sleep 0.8
SESSDIR="$PINRULE_HOME/session-state"
mkdir -p "$SESSDIR"
echo '{"session_id":"sc5","read_files":[],"edit_files":[],"recent_bash":[],"last_test_pass_ts":0.0,"last_edit_ts":0.0,"pending_bg_tasks":[],"turn_count":50,"stop_block_count":0,"tool_byte_seq":62000,"last_reinject_byte_seq":0,"model":"claude-opus-4","pending_subagent_models":[]}' > "$SESSDIR/sc5.json"
echo '$ echo {tool=Read} | pinrule_post_tool_use.py'
sleep 0.8
echo '{"session_id":"sc5","tool_name":"Read","tool_input":{"file_path":"/tmp/foo.py"},"tool_response":{"content":"x"}}' \
  | $PY pinrule/hooks/post_tool_use.py 2>/dev/null \
  | $PY -c "import json,sys; d=json.load(sys.stdin); ac=d.get('hookSpecificOutput',{}).get('additionalContext',''); print(ac[:450] + ('...' if len(ac) > 450 else ''))"
rm -f "$SESSDIR/sc5.json" "$SESSDIR/sc5.json.lock"
sleep 0.8

# Ending banner 真留 3 秒看清结束语
banner "$TE" "$TES"
sleep 3
