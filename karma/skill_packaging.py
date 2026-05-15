"""karma skill 多 backend 打包 — Markdown source → 各 backend 原生格式.

karma 仓库内 source of truth 是 `skills/karma/SKILL.md` (Markdown + YAML frontmatter).
不同 AI 编程客户端的 skill 接受格式不同:

- Claude Code: 接受 Markdown 直接装 (`~/.claude/skills/karma/SKILL.md`)
- Codex CLI: 接受 Markdown 直接装 (`~/.agents/skills/karma/SKILL.md`, 注意路径)
- Gemini CLI 「显式 slash command」: 要 TOML 格式 `~/.gemini/commands/karma.toml`,
  里面 `prompt = <triple-quoted string>` 字段是 Markdown body 内容; Gemini 用 `{{args}}` 接用户输入
- Gemini CLI 「Agent Skills auto-trigger」: 也接受 Markdown `~/.gemini/skills/karma/SKILL.md`

本模块提供:
- `parse_frontmatter(md_text)` — 拆 YAML frontmatter + body
- `markdown_to_toml(md_text)` — Markdown 转 Gemini commands TOML 格式
- `replace_arguments_token(text, target)` — `$ARGUMENTS` ↔ `{{args}}` 互转
"""

from __future__ import annotations

import re


def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """拆 Markdown 头部 YAML frontmatter (--- 包裹) + body.

    返回 (frontmatter dict, body text). 没 frontmatter 返回 ({}, md_text 原文).
    用最小手写 YAML 解析 (key: value 单行 — skill frontmatter 字段都是简单 string),
    不引入 PyYAML 依赖避免 hook 启动开销 (karma v2 极简原则).
    """
    if not md_text.startswith("---"):
        return {}, md_text

    # 找第二个 --- 分隔
    end_match = re.search(r"\n---[ \t]*\n", md_text[3:])
    if not end_match:
        return {}, md_text

    fm_raw = md_text[3 : 3 + end_match.start()].strip()
    body = md_text[3 + end_match.end():].lstrip("\n")

    fm: dict[str, str] = {}
    current_key: str | None = None
    for line in fm_raw.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^(\w[\w-]*)\s*:\s*(.*)$", line)
        if m:
            current_key = m.group(1)
            value = m.group(2).strip()
            # 剥两端引号
            if (len(value) >= 2) and (
                (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
            ):
                value = value[1:-1]
            fm[current_key] = value
        elif current_key and line.startswith((" ", "\t")):
            # 多行 value continuation — append with space
            fm[current_key] = f"{fm[current_key]} {line.strip()}"
    return fm, body


def replace_arguments_token(text: str, target_syntax: str) -> str:
    """`$ARGUMENTS` (Claude Code/Codex) ↔ `{{args}}` (Gemini) 互转.

    target_syntax: "claude" | "codex" | "gemini"
    - "claude" / "codex": 保留 `$ARGUMENTS`, 把 `{{args}}` 转 `$ARGUMENTS`
    - "gemini": `$ARGUMENTS` → `{{args}}`
    """
    if target_syntax in ("claude", "codex"):
        return text.replace("{{args}}", "$ARGUMENTS")
    if target_syntax == "gemini":
        return text.replace("$ARGUMENTS", "{{args}}")
    return text


def _toml_triple_quote(value: str) -> str:
    """TOML triple-quoted string — 转义连续 3 个 quote 字符避免破解析.

    TOML triple-quoted basic strings 不需要转义 backslash 或单 quote; 但连续 3 个
    quote 字符要变成 2 quote + escape. 实际 Markdown 内极少出现三连引号, 简单
    fallback 即可.
    """
    triple = '"' * 3
    if triple in value:
        value = value.replace(triple, '""\\"')
    return f'{triple}\n{value}\n{triple}'


def markdown_to_toml(md_text: str) -> str:
    """Markdown skill (frontmatter + body) → Gemini CLI commands TOML.

    Gemini commands TOML 格式 (实证):
        description = "<short description>"
        prompt = '''
        <prompt body with {{args}} placeholders>
        '''

    实施:
    1. parse_frontmatter 拿 description (没就用 body 第一段当 fallback)
    2. body 内 $ARGUMENTS → {{args}} 转换让 Gemini 原生接住
    3. 拼 TOML 输出
    """
    fm, body = parse_frontmatter(md_text)
    description = fm.get("description", "").strip()
    if not description:
        # fallback: body 第一段非空行
        for para in body.split("\n\n"):
            stripped = para.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped.split("\n", 1)[0][:200]
                break

    # description 用 single-line basic string — 转义 " 和 \
    desc_escaped = description.replace("\\", "\\\\").replace('"', '\\"')

    body_gemini = replace_arguments_token(body, "gemini")
    prompt_block = _toml_triple_quote(body_gemini.rstrip())

    return f'description = "{desc_escaped}"\nprompt = {prompt_block}\n'
