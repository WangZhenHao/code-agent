"""技能包（skill）加载：从 `public/skills/` 读技能包的元信息与内容。

## 技能包在哪、为什么不在沙箱里

技能包是**服务端随源码发布的资源**（`apps/api/public/skills/`），不是沙箱里的
文件。所以这里全部走主机文件系统，跟 `tools/` 里那批操作沙箱的工具是两回事：
那个 `to_sandbox_path` 在这里一点用都没有，路径语义完全不同。

两个调用方共用本模块，且必须共用：
  - `agent_prompt.generate_system_prompt` 列出"有哪些技能、各自干什么"；
  - `tools/read_skill` 按名称读出具体内容。
两边如果各自解析一遍 frontmatter，很快就会出现"提示词里写的名字读不出来"这类
只读漂移，所以 `list_skills` 是唯一真源。

## 技能包的目录约定

    public/skills/<name>/SKILL.md          # 入口文件，头部是 frontmatter
    public/skills/<name>/references/*.md   # 可选的子文件，按需读取

`SKILL.md` 必须存在，`name`/`description` 写在文件头的 `---` 块里：

    ---
    name: frontend-design
    description: Guidance for distinctive, intentional visual design ...
    ---

frontmatter 用手写解析而不是 PyYAML：只需要两个标量字段，为它往依赖里加一个
库不划算（也避免 YAML 的隐式类型转换把 `description: yes` 变成一个 bool）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 技能包根目录。`__file__` 是 src/app/agents/helper/skill_loader.py，
# parents: [0]=helper [1]=agents [2]=app [3]=src [4]=api → apps/api/public/skills。
#
# 用源码相对路径而不是配置项：这是一份随代码走的常量资源，和 settings 里那些
# 「按部署环境变化」的值不是一类东西（settings.py 的 _ENV_FILE 也是这么定位的）。
SKILLS_DIR = Path(__file__).resolve().parents[4] / "public" / "skills"

# 入口文件名。约定俗成，也是正文里"读入口就附上子文件列表"那个判断的依据。
ENTRY_FILE = "SKILL.md"

# 单次返回的行数上限，与 read_file 的默认值一致：够看完整指导，又不会撑爆上下文。
DEFAULT_LIMIT = 2000
MAX_LIMIT = 10000

# frontmatter 缺失 description 时的占位。空字符串会让提示词里出现 `- **name** — `
# 这种断尾，模型容易当成"这个技能没内容可读"。
NO_DESCRIPTION = "（无描述）"


class SkillError(Exception):
    """技能包层的可预期错误。

    与 `SandboxToolError` 同构、但独立：调用方要区分"技能包不存在/路径越界"
    （把原因回灌给模型让它自己改）和"资源目录读不了"（是部署问题）。
    """


@dataclass(frozen=True)
class SkillInfo:
    """一个技能包的元信息。`dir` 指向它在磁盘上的目录。"""

    name: str
    description: str
    dir: Path


def _strip_frontmatter(text: str) -> tuple[str, int]:
    """剥掉开头的 `---` frontmatter 块，返回 (正文, 被剥掉的行数)。

    返回行数是给行号用的：剥掉之后行号要接着 frontmatter 继续数，
    否则模型按行号引用（"第 12 行"）时对不上原文。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text, 0
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :]), i + 1
    # 有开头没结尾：整段都算 frontmatter，正文为空。
    return "", len(lines)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """解析开头 `---` 块里的 `key: value`。

    只认第一段 frontmatter（文件必须以 `---` 开头）；正文里出现的 `---` 分隔线
    不会被误当作 frontmatter——遇到第一个闭合的 `---` 就停。

    容错取向：解析不出来就返回空 dict，让调用方用目录名/占位描述兜底。
    一个技能包的元信息写坏了，不该让整个系统提示词生成失败。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        # 去引号：description 里带冒号时，写 `description: "a: b"` 比转义更常见。
        value = value.strip().strip('"').strip("'")
        if key:
            fields[key] = value
    return fields


def list_skills() -> list[SkillInfo]:
    """列出全部技能包，按名称排序。

    目录不存在、单个技能包读不出 frontmatter，都只跳过而不抛——这个函数的唯一
    用途是拼提示词，任何一处坏数据都不该让整次对话起不来。真正读内容时
    （`read_skill`）才严格报错，那时模型能看见原因并自己纠正。
    """
    if not SKILLS_DIR.is_dir():
        return []

    skills: list[SkillInfo] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / ENTRY_FILE
        if not skill_md.is_file():
            continue

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fields = _parse_frontmatter(text)
        # name 以目录名为准而不是 frontmatter：目录名是"能读出来的那个名字"，
        # 提示词里报给模型的 name 必须真的能被 read_skill 命中。
        skills.append(
            SkillInfo(
                name=entry.name,
                description=fields.get("description") or NO_DESCRIPTION,
                dir=entry,
            )
        )
    return skills


def get_skill(name: str) -> SkillInfo:
    """按名称取一个技能包，不存在时抛 SkillError。

    错误文案带上可用名称列表：模型拿到后能直接改名重试，不用先猜、再调用一次
    列出工具。这是"错误信息要能驱动下一步动作"的通常做法。
    """
    wanted = (name or "").strip()
    if not wanted:
        raise SkillError("技能包名称不能为空")

    for skill in list_skills():
        if skill.name == wanted:
            return skill

    available = ", ".join(s.name for s in list_skills()) or "（无）"
    raise SkillError(f"没有名为 {wanted!r} 的技能包。可用技能包：{available}")


def resolve_skill_path(skill: SkillInfo, path: str) -> Path:
    """把技能包内的相对路径解析成绝对路径，越界一律拒绝。

    `read_skill` 的 `path` 来自模型，属于不可信输入。三层防护缺一不可：
      - 控制字符（NUL 会在 syscall 层截断路径，是种绕过）；
      - 绝对路径（`/etc/passwd` 会直接把 skill 目录甩在后面）；
      - `..` 与 symlink 逃逸（resolve 之后必须仍在 skill 目录下）。
    真实路径用 resolve() 判定，所以 `references/../../x` 和指向外部的软链
    都过不了最后那道 has_relative_to 检查。
    """
    rel = (path or "").strip().replace("\\", "/")
    if not rel:
        rel = ENTRY_FILE

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in rel):
        raise SkillError(f"路径含控制字符，拒绝处理：{path!r}")
    if rel.startswith("/"):
        raise SkillError(f"path 必须是技能包内的相对路径：{path!r}")

    target = (skill.dir / rel).resolve()
    if not target.is_relative_to(skill.dir.resolve()):
        raise SkillError(f"路径不能跳出技能包目录：{path!r}")
    return target


def list_skill_files(skill: SkillInfo) -> list[str]:
    """列出技能包内的全部子文件（不含入口文件），按路径排序。

    相对技能包目录、用 `/` 分隔，与传给 `read_skill(path=...)` 的写法一致——
    返回的字符串可以直接原样当参数用。
    """
    files: list[str] = []
    for path in sorted(skill.dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(skill.dir).as_posix()
        if rel == ENTRY_FILE:
            continue
        files.append(rel)
    return files


def format_skill_list(skills: list[SkillInfo]) -> str:
    """把技能包列表渲染成提示词里的几行（供 system prompt 使用）。"""
    if not skills:
        return "（当前没有可用技能包）"
    return "\n".join(f"- **{s.name}** — {s.description}" for s in skills)


def read_skill(
    name: str,
    path: str = ENTRY_FILE,
    offset: int = 1,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """读技能包内容，返回给模型看的文本。

    默认读入口文件 SKILL.md：开头的 frontmatter 会被剥掉（name/description
    已经在系统提示词的"可用技能包"一节里给过模型了），并在返回值后面附上该技能包
    的全部子文件列表——模型看到 `references/QUERIES.md` 才知道有东西可以继续读，
    否则它会以为 SKILL.md 就是全部。

    子文件则只在正文前给一行来源标注（不再重复整个文件列表），因为读子文件时
    模型已经在入口那一轮见过完整清单了。
    """
    if limit <= 0:
        raise SkillError("limit 必须大于 0")
    limit = min(int(limit), MAX_LIMIT)
    start = max(int(offset), 1)

    skill = get_skill(name)
    target = resolve_skill_path(skill, path)

    if not target.is_file():
        files = list_skill_files(skill)
        hint = (
            f"\n该技能包现有文件：\n" + "\n".join(f"- {f}" for f in files)
            if files
            else "\n该技能包没有子文件。"
        )
        raise SkillError(f"技能包内没有文件 {path!r}。{hint}")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SkillError(f"读取技能包文件失败：{path}（{exc}）") from exc

    rel = target.relative_to(skill.dir.resolve()).as_posix()
    header = f"# 技能包 {skill.name} / {rel}"

    # 入口文件的 frontmatter（name/description）在"可用技能包"一节已经给过模型了，
    # 正文里再读一遍纯属浪费 token——列表里每项都在，而正文可能上千行。
    skipped = 0
    if rel == ENTRY_FILE:
        content, skipped = _strip_frontmatter(content)
    lines = content.splitlines()
    if not lines:
        return f"{header}\n\n(空文件)"

    total = len(lines)
    if start > total:
        raise SkillError(
            f"offset={start} 超出文件末尾（{skill.name}/{rel} 共 {total} 行）"
        )

    # 行号从 1 起，按**剥掉 frontmatter 之后**的正文数。为什么不接着原文数：
    # 分页提示里的 offset 用的是这套编号，正文行号必须跟它同一套坐标，
    # 否则模型照着一个行号去传 offset，两套编号会互相错位（差的就是 frontmatter 那几行）。
    window = lines[start - 1 : start - 1 + limit]
    width = len(str(start - 1 + len(window)))
    body = "\n".join(
        f"{i:>{width}}\t{text}" for i, text in enumerate(window, start=start)
    )
    parts = [header, body]

    shown_end = start - 1 + len(window)
    if shown_end < total:
        parts.append(
            f"... [仅显示第 {start}-{shown_end} 行，共 {total} 行。"
            f"继续读请用 offset={shown_end + 1}]"
        )
    elif rel == ENTRY_FILE:
        # 只在"读完了入口文件"时附文件清单：读子文件时模型已知情，重复是浪费。
        files = list_skill_files(skill)
        if files:
            parts.append(
                "该技能包的全部子文件（可用 read_skill 的 path 参数读取）：\n"
                + "\n".join(f"- {f}" for f in files)
            )
        else:
            parts.append("该技能包没有其他子文件。")

    return "\n\n".join(parts)
