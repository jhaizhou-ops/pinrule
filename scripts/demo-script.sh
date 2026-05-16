#!/bin/bash
LANG_MODE="${LANG_MODE:-zh}"
banner() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "  $2"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 2
}

if [ "$LANG_MODE" = "en" ]; then
    export KARMA_LOCALE=en
    T1="Scene 1/4 — Inject rules at every prompt header"
    T1S="(UserPromptSubmit hook → ~490 token anchor)"
    T2="Scene 2/4 — Real-time block of sleep 30"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="Scene 3/4 — Catch short-term intent in Agent response"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="Scene 4/4 — Nudge Agent to keep pushing after silent stop"
    T4S="(Stop hook → keep-pushing-no-stop)"
    TE="That's karma in 60s — pure engineering, zero LLM."
    TES="github.com/jhaizhou-ops/karma"
    FIX_LONGTERM=/tmp/karma-demo-fixtures/short-term-talk-en.jsonl
    FIX_SILENT=/tmp/karma-demo-fixtures/silent-stop-en.jsonl
else
    export KARMA_LOCALE=zh
    T1="场景 1/4 — 每条 prompt 头部注入规则"
    T1S="(UserPromptSubmit hook → ~490 token 精简 anchor)"
    T2="场景 2/4 — sleep 30 实时拦截"
    T2S="(PreToolUse hook → non-blocking-parallel)"
    T3="场景 3/4 — Agent 回应短期话术拦截"
    T3S="(Stop hook → long-term v0.11.0 response-level)"
    T4="场景 4/4 — Agent 静默停止时推动继续"
    T4S="(Stop hook → keep-pushing-no-stop)"
    TE="这就是 karma — 纯工程, 零 LLM, 60 秒看完"
    TES="github.com/jhaizhou-ops/karma"
    FIX_LONGTERM=/tmp/karma-demo-fixtures/short-term-talk.jsonl
    FIX_SILENT=/tmp/karma-demo-fixtures/silent-stop.jsonl
fi

# Scene 1
banner "$T1" "$T1S"
echo '$ echo {prompt} | karma_user_prompt_submit.py | jq additionalContext'
sleep 1
echo
echo '{"session_id":"demo","prompt":"hi","transcript_path":"/dev/null","cwd":"/Users/jhz/karma"}' \
  | .venv/bin/python karma/hooks/user_prompt_submit.py 2>/dev/null \
  | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print(d.get('hookSpecificOutput',{}).get('additionalContext','')[:600])"
sleep 4

# Scene 2
banner "$T2" "$T2S"
echo '$ echo {tool=Bash, command=sleep 30} | karma_pre_tool_use.py'
sleep 1
echo
echo '{"session_id":"demo","tool_name":"Bash","tool_input":{"command":"sleep 30"}}' \
  | .venv/bin/python karma/hooks/pre_tool_use.py 2>/dev/null
sleep 4

# Scene 3
banner "$T3" "$T3S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Let me just hardcode this case to ship it"'
else
    echo '$ # Agent 说: "我先硬编码这个 case 让 CI 过"'
fi
sleep 1
echo '$ echo {transcript_path} | karma_stop.py'
sleep 1
echo
echo "{\"session_id\":\"demo\",\"transcript_path\":\"$FIX_LONGTERM\",\"cwd\":\"/Users/jhz/karma\"}" \
  | .venv/bin/python karma/hooks/stop.py 2>&1 | grep -v "使用旧配置" | head -6
sleep 4

# Scene 4
banner "$T4" "$T4S"
if [ "$LANG_MODE" = "en" ]; then
    echo '$ # Agent said: "Task complete."  (pure statement, no next step)'
else
    echo '$ # Agent 说: "任务已经完成了。"  (纯陈述无下一步)'
fi
sleep 1
echo '$ echo {transcript_path} | karma_stop.py'
sleep 1
echo
echo "{\"session_id\":\"demo\",\"transcript_path\":\"$FIX_SILENT\",\"cwd\":\"/Users/jhz/karma\"}" \
  | .venv/bin/python karma/hooks/stop.py 2>&1 | grep -v "使用旧配置" | head -4
sleep 4

banner "$TE" "$TES"
sleep 2
