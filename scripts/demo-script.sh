#!/bin/bash
LANG_MODE="${LANG_MODE:-zh}"
banner() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "  $2"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 1
}

PY=.venv/bin/python

if [ "$LANG_MODE" = "en" ]; then
    export KARMA_LOCALE=en
    export KARMA_HOME="${KARMA_HOME:-/tmp/karma-demo-en-home}"
    T1="Scene 1/5 — Inject rules at every prompt header"
    T1S="(UserPromptSubmit hook → ~490 token anchor)"
    T2="Scene 2/5 — Real-time block of sleep 30"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="Scene 3/5 — Catch short-term intent in Agent response"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="Scene 4/5 — Nudge Agent to keep pushing after silent stop"
    T4S="(Stop hook → keep-pushing-no-stop)"
    T5="Scene 5/5 — Mid-conversation full reinject at decay threshold"
    T5S="(PostToolUse hook → byte_seq hits Opus 60K → full baseline)"
    TE="That's karma — pure engineering, zero LLM."
    TES="github.com/jhaizhou-ops/karma"
    FIX_LONGTERM=/tmp/karma-demo-fixtures/short-term-talk-en.jsonl
    FIX_SILENT=/tmp/karma-demo-fixtures/silent-stop-en.jsonl
else
    export KARMA_LOCALE=zh
    export KARMA_HOME="${KARMA_HOME:-/tmp/karma-demo-zh-home}"
    T1="场景 1/5 — 每条 prompt 头部注入规则"
    T1S="(UserPromptSubmit hook → ~490 token 精简 anchor)"
    T2="场景 2/5 — sleep 30 实时拦截"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="场景 3/5 — Agent 回应短期话术拦截"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="场景 4/5 — Agent 静默停止时推动继续"
    T4S="(Stop hook → keep-pushing-no-stop)"
    T5="场景 5/5 — 长 context 累积到拐点中段补一次完整规则"
    T5S="(PostToolUse hook → byte_seq 达 Opus 60K 自动 reinject)"
    TE="这就是 karma — 纯工程, 零 LLM"
    TES="github.com/jhaizhou-ops/karma"
    FIX_LONGTERM=/tmp/karma-demo-fixtures/short-term-talk.jsonl
    FIX_SILENT=/tmp/karma-demo-fixtures/silent-stop.jsonl
fi

# Scene 1: 头部注入 (UserPromptSubmit)
banner "$T1" "$T1S"
echo '$ echo {prompt} | karma_user_prompt_submit.py'
sleep 1
echo '{"session_id":"sc1","prompt":"hi","transcript_path":"/dev/null","cwd":"/Users/jhz/karma"}' \
  | $PY karma/hooks/user_prompt_submit.py 2>/dev/null \
  | $PY -c "import json,sys; d=json.load(sys.stdin); print(d.get('hookSpecificOutput',{}).get('additionalContext','')[:550])"
sleep 1

# Scene 2: sleep 30 拦 (PreToolUse) — 解析 JSON 显示真换行 reason
banner "$T2" "$T2S"
echo '$ echo {tool=Bash, command=sleep 30} | karma_pre_tool_use.py'
sleep 1
echo '{"session_id":"sc2","tool_name":"Bash","tool_input":{"command":"sleep 30"}}' \
  | $PY karma/hooks/pre_tool_use.py 2>/dev/null \
  | $PY -c "
import json,sys
d=json.load(sys.stdin)
out = d.get('hookSpecificOutput',{})
print(f\"  permissionDecision: {out.get('permissionDecision','')}\")
print()
for line in out.get('permissionDecisionReason','').split('\\n')[:5]:
    print(f\"  {line}\")
"
sleep 1

# Scene 3: long-term response-level 拦
banner "$T3" "$T3S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Let me just hardcode this case to ship it"'
else
    echo '$ # Agent 说: "我先硬编码这个 case 让 CI 过"'
fi
sleep 1
echo '$ karma_stop.py reads transcript, scans response'
sleep 1
echo "{\"session_id\":\"sc3\",\"transcript_path\":\"$FIX_LONGTERM\",\"cwd\":\"/Users/jhz/karma\"}" \
  | $PY karma/hooks/stop.py 2>&1 1>/dev/null | head -2
sleep 1

# Scene 4: keep-pushing nudge
banner "$T4" "$T4S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Task complete."  (pure statement, no next step)'
else
    echo '$ # Agent 说: "任务已经完成了。"  (纯陈述无下一步)'
fi
sleep 1
echo '$ karma_stop.py reads transcript, scans response'
sleep 1
echo "{\"session_id\":\"sc4\",\"transcript_path\":\"$FIX_SILENT\",\"cwd\":\"/Users/jhz/karma\"}" \
  | $PY karma/hooks/stop.py 2>&1 1>/dev/null | head -2
sleep 1

# Scene 5: PostToolUse 中段 reinject
banner "$T5" "$T5S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # session state: tool_byte_seq=62000 (past Opus 60K threshold)'
else
    echo '$ # session state: tool_byte_seq=62000 (已过 Opus 60K 衰减拐点)'
fi
sleep 1
SESSDIR="$KARMA_HOME/session-state"
mkdir -p "$SESSDIR"
echo '{"session_id":"sc5","read_files":[],"edit_files":[],"recent_bash":[],"last_test_pass_ts":0.0,"last_edit_ts":0.0,"pending_bg_tasks":[],"turn_count":50,"stop_block_count":0,"tool_byte_seq":62000,"last_reinject_byte_seq":0,"model":"claude-opus-4","pending_subagent_models":[]}' > "$SESSDIR/sc5.json"
echo '$ echo {tool=Read} | karma_post_tool_use.py'
sleep 1
echo '{"session_id":"sc5","tool_name":"Read","tool_input":{"file_path":"/tmp/foo.py"},"tool_response":{"content":"x"}}' \
  | $PY karma/hooks/post_tool_use.py 2>/dev/null \
  | $PY -c "import json,sys; d=json.load(sys.stdin); ac=d.get('hookSpecificOutput',{}).get('additionalContext',''); print(ac[:450] + ('...' if len(ac) > 450 else ''))"
rm -f "$SESSDIR/sc5.json" "$SESSDIR/sc5.json.lock"
sleep 1

banner "$TE" "$TES"
sleep 1
