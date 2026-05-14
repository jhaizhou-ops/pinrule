"""check 函数共用工具。"""

from __future__ import annotations

import re

# code block ``` 包裹的内容（多种语言标记）
_CODE_BLOCK_RE = re.compile(r"```[\w]*\n.*?\n```", re.DOTALL)
# inline `code` 包裹
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# shell 引号字面 — git commit -m "..." / echo "..." 的内容是描述/数据不是执行意图
_SHELL_QUOTED_RE = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")
# 间接 shell / 解释器执行 — bash -c '...' / sh -c "..." / python -c '...' 等
# 引号内是真要执行的子命令 / 代码，剥引号时要保留扫
# 包括 shell 解释器 + 编程语言 -c flag（python/node/ruby/perl 等）
_INDIRECT_SHELL_RE = re.compile(
    r"\b(?:bash|sh|zsh|dash|ksh|python\d?|node|ruby|perl)\s+-c\s+(['\"])(.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
# bash -c 无引号形式：bash -c sleep30 / sh -c ls （POSIX 合法，引号可省）
# 取 -c 之后第一个 token 作为子命令
_INDIRECT_SHELL_NOQUOTE_RE = re.compile(
    r"\b(?:bash|sh|zsh|dash|ksh|python\d?|node|ruby|perl)\s+-c\s+([^\s'\"`][^\s;&|\n]*)",
    re.IGNORECASE,
)
# 反引号命令替换 `cmd` — 内容是真执行的子命令
# 排除前导反斜杠转义（\` 是字面反引号不展开）
_BACKTICK_SUBST_RE = re.compile(r"(?<!\\)`([^`\n]+?)(?<!\\)`")
# $(...) 命令替换 — 内容是真执行的子命令（不支持嵌套，足够覆盖常见场景）
# 排除前导反斜杠转义（\$( 是字面美元 + 括号，shell 不展开）
_DOLLAR_PAREN_SUBST_RE = re.compile(r"(?<!\\)\$\(([^()\n]*)\)")
# 双引号字面 — 双引号内的 $() / 反引号会被 shell 真展开执行，需要提到外层
# 单引号字面不展开（shell 字面不解析），不在这里处理
_DOUBLE_QUOTED_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
# heredoc 多行字符串 — `<<EOF ... EOF` 形式
# 支持 `<<EOF` / `<<'EOF'` / `<<"EOF"` / `<<-EOF` / `<<~EOF` 几种变体
# 允许 `<<EOF` 后到换行前有任意非换行字符（如 `> /tmp/x.sh` 重定向）
# 终结符前允许 tab/space 缩进 — `<<-` 形式 bash 会剥 tab 缩进，karma 也要识别到
_HEREDOC_RE = re.compile(
    r"<<[-~]?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n[\t ]*\1\b",
    re.DOTALL,
)
# heredoc 头部是 shell 解释器 → 内容是真要执行的 shell 命令（保留扫）
# 头部是 python / cat / grep / sed / awk 等 → 内容是数据传 stdin（剥）
_SHELL_INTERPRETER_RE = re.compile(r"^(bash|sh|zsh|dash|ksh|fish)$", re.IGNORECASE)


def _heredoc_prefix_command(prefix: str) -> str:
    """从 `<<` 之前的字串里取最近一条命令的第一个 token（命令名）。

    边界含 `(` — 处理 `$( cat <<EOF ...)` / `(cat <<EOF ...)` 子 shell 嵌套
    （v0.4.33 真根因 fix：之前不含 `(` 边界导致 `gh ... --notes "$(cat <<EOF ...)"`
    被误识 prefix=gh 不是 cat → heredoc 内容被错误处理）。
    """
    # 找命令边界 — 行首 / ; / | / && / || / 子 shell `(` / 子 shell `$(`
    boundary_pos = max(
        prefix.rfind("\n"),
        prefix.rfind(";"),
        prefix.rfind("|"),
        prefix.rfind("&"),
        prefix.rfind("("),  # v0.4.33 加：子 shell 嵌套 `$(cmd <<EOF)` / `(cmd <<EOF)`
    )
    line = prefix[boundary_pos + 1:] if boundary_pos >= 0 else prefix
    tokens = line.strip().split()
    return tokens[0] if tokens else ""


def strip_shell_quoted_literals(cmd: str) -> str:
    """剥 shell 命令里的引号字面 + 部分 heredoc 内容，保留命令骨架。

    特殊处理：
    - `bash -c '...'` / `python -c '...'` 等 -c flag 后引号是真执行代码，
      剥时保留内容（用 placeholder 防被后续 _SHELL_QUOTED_RE 内部引号字面误剥）。
    - heredoc 区分头部：
        * `bash <<EOF ... EOF` / `sh <<EOF ... EOF` → 内容是 shell 命令保留扫
        * `python <<EOF ... EOF` / `cat <<EOF ... EOF` → 内容是数据剥掉

    跨 non_blocking + 关键词层共用，统一描述上下文剥离逻辑。
    """
    # Step 1：先剥 heredoc 内容（早于 hoist / indirect 处理）— v0.4.33 真根因 fix。
    # 之前顺序错：indirect 先抽 → heredoc 内的反引号 / $() 字面被先抽到 placeholder
    # → heredoc 剥时 placeholder 已不在内容里 → 最终替回保留扫漏 markdown 字面。
    # 真触发：`gh release create --notes "$(cat <<'EOF' ...`cat ~/.claude/karma/...`
    # ... EOF)"` 里 markdown 反引号包的路径字面被错当 shell substitution 保留扫。
    # 修：heredoc 先剥（按 prefix 命令决定 python/cat 剥 / bash 保留），让 heredoc
    # 内一切字面跟 heredoc 一起处理。
    def _maybe_strip_heredoc(m: re.Match) -> str:
        head_cmd = _heredoc_prefix_command(cmd[:m.start()])
        if _SHELL_INTERPRETER_RE.match(head_cmd):
            # bash/sh 等 heredoc — 内容是真 shell 命令，保留当真命令扫
            return " " + m.group(2) + " "
        # python/cat 等头部，heredoc 内容是数据 — 剥掉
        return ""

    cmd = _HEREDOC_RE.sub(_maybe_strip_heredoc, cmd)

    # Step 2：双引号内 substitution「提升」到外层（shell 双引号真行为是展开
    # $() 和反引号执行）。如果不先提升，后续 _SHELL_QUOTED_RE 会把整个 "..."
    # 连同 substitution 一起剥造成漏报。实测漏报：'echo "result: $(sleep 30)"'
    # 整段被吞 → non_blocking 漏报 sleep。单引号字面 shell 不展开不处理。
    hoisted_subst: list[str] = []

    def _hoist_subst_in_double_quoted(m: re.Match) -> str:
        body = m.group(0)[1:-1]  # 去掉两端双引号
        def _grab(sub_m: re.Match) -> str:
            hoisted_subst.append(sub_m.group(1))
            return ""
        body = _BACKTICK_SUBST_RE.sub(_grab, body)
        body = _DOLLAR_PAREN_SUBST_RE.sub(_grab, body)
        return '"' + body + '"'

    cmd = _DOUBLE_QUOTED_RE.sub(_hoist_subst_in_double_quoted, cmd)
    if hoisted_subst:
        cmd = cmd + " ; " + " ; ".join(hoisted_subst)

    # Step 3：抽 indirect shell 内容到 placeholder（防内部引号被 _SHELL_QUOTED_RE 误剥）
    # 三种形态：bash -c '...' / bash -c sleep30 / `cmd` / $(cmd)
    indirect_contents: list[str] = []

    def _capture_indirect_quoted(m: re.Match) -> str:
        indirect_contents.append(m.group(2))
        return f"\x00INDIRECT_{len(indirect_contents) - 1}\x00"

    def _capture_indirect_simple(m: re.Match) -> str:
        indirect_contents.append(m.group(1))
        return f"\x00INDIRECT_{len(indirect_contents) - 1}\x00"

    cmd = _INDIRECT_SHELL_RE.sub(_capture_indirect_quoted, cmd)
    cmd = _INDIRECT_SHELL_NOQUOTE_RE.sub(_capture_indirect_simple, cmd)
    cmd = _BACKTICK_SUBST_RE.sub(_capture_indirect_simple, cmd)
    cmd = _DOLLAR_PAREN_SUBST_RE.sub(_capture_indirect_simple, cmd)

    cmd = _SHELL_QUOTED_RE.sub("", cmd)
    # 替回 indirect 内容（含内部所有字面）
    for i, content in enumerate(indirect_contents):
        cmd = cmd.replace(f"\x00INDIRECT_{i}\x00", " " + content + " ")
    return cmd


def extract_tool_text(tool_name: str, tool_input: dict) -> str:
    """从 tool_input 提取要扫违反的关键文本。

    不同 tool 不同字段：
    - Bash: command
    - Write: content
    - Edit: new_string (只看 Agent 加的，不看已有 old_string)
    - 其他: JSON dump
    """
    if not tool_input:
        return ""
    if tool_name == "Bash":
        return str(tool_input.get("command", "") or "")
    if tool_name == "Write":
        return str(tool_input.get("content", "") or "")
    if tool_name == "Edit":
        return str(tool_input.get("new_string", "") or "")
    if tool_name == "NotebookEdit":
        return str(tool_input.get("new_source", "") or "")
    try:
        import json
        return json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(tool_input)


def strip_code_blocks(text: str) -> str:
    """剔除 markdown ``` 包裹的 code block 和 `inline` code。

    用于 chinese_plain 类检查 — 自然语言部分才算 jargon 对话。
    """
    no_block = _CODE_BLOCK_RE.sub("", text)
    no_inline = _INLINE_CODE_RE.sub("", no_block)
    return no_inline


# 代码注释 / docstring 提取 — 关键词层扫 Write/Edit 自然语言部分
# 跨语言通用 — # 行注释 (Python/Shell/Ruby) / // 行注释 (C/JS/Go/Rust) /
# -- 行注释 (SQL/Lua/Haskell) / """ ''' docstring (Python) / /* */ 块注释 (C/JS)
_LINE_COMMENT_PY = re.compile(r"#[^\n]*")
_LINE_COMMENT_C = re.compile(r"//[^\n]*")
_LINE_COMMENT_SQL = re.compile(r"(?:^|\s)--[^\n]*")  # 前缀空白避免 `x--` 自减误判
_DOCSTRING_DOUBLE = re.compile(r'"""([\s\S]*?)"""')
_DOCSTRING_SINGLE = re.compile(r"'''([\s\S]*?)'''")
_BLOCK_COMMENT = re.compile(r"/\*([\s\S]*?)\*/")


def extract_natural_language(content: str, file_path: str = "") -> str:
    """从代码 content 抽出注释行 + docstring/block 注释内容（自然语言部分）。

    关键词层扫 Write/Edit 时只看这部分 — 代码主体（变量赋值、函数调用等）
    里出现字面词几乎全是描述/数据假阳，注释里写违反字眼才是真意图表达。

    跨语言通用，返回拼接的自然语言文本。
    """
    parts: list[str] = []
    for m in _LINE_COMMENT_PY.finditer(content):
        parts.append(m.group()[1:].strip())
    for m in _LINE_COMMENT_C.finditer(content):
        parts.append(m.group()[2:].strip())
    for m in _LINE_COMMENT_SQL.finditer(content):
        # group 含可能的前缀空白 + --
        text = m.group().lstrip()[2:].strip()
        parts.append(text)
    for m in _DOCSTRING_DOUBLE.finditer(content):
        parts.append(m.group(1).strip())
    for m in _DOCSTRING_SINGLE.finditer(content):
        parts.append(m.group(1).strip())
    for m in _BLOCK_COMMENT.finditer(content):
        parts.append(m.group(1).strip())
    return "\n".join(p for p in parts if p)


def chinese_char_count(text: str) -> int:
    return sum(1 for c in text if "一" <= c <= "鿿")


def total_visible_char_count(text: str) -> int:
    return sum(1 for c in text if not c.isspace())
