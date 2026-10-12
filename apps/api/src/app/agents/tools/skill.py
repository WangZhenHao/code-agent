"""read_skill 工具：按名称读取技能包的指导内容。

技能包（skill）是服务端发布的一批专项领域指导文档（见
`agents/helper/skill_loader.py` 顶部的目录约定），存放在 API 主机上，
不在沙箱里。所以这个工具**不接收 sandbox 参数**——它在 build_tools 里
跟其余成员签名不同，这一点在工厂那里也注释说明了。

反过来，沙箱里的 `read_file` 也读不到技能包：两者的文件系统不是同一个。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.agents.helper.skill_loader import (
    DEFAULT_LIMIT,
    SkillError,
    read_skill as _read_skill,
)

DESCRIPTION = """读取技能包（skill）的指导内容。

用于：任务涉及某个专项领域时，按名称加载该技能包的完整指导。
技能包名称必须来自系统提示词里"可用技能包"一节列出的名称。

行为说明：
- 默认读取入口文件 SKILL.md，返回内容带行号，并附带该技能包的全部子文件列表。
- 用 path 读取技能包内的子文件，例如 path="references/QUERIES.md"。
- 文件较长时用 offset/limit 只读一部分（默认 2000 行）。
- 技能包在服务端，与沙箱工作目录无关，因此不要传 /workspace 路径。"""


def read_skill(
    name: str,
    path: str = "SKILL.md",
    offset: int = 1,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """读技能包内容。错误（名称不存在、路径越界、文件缺失）转成文本返回。

    异常处理没有复用 `_common.safe_call`：那个是把**沙箱**工具的错误转文本，
    且对非 SandboxToolError 的异常会带上类名（`错误：ValueError: ...`），
    那对模型是无用噪音。这里只需要兜住 SkillError，其余异常让它冒泡——真出现
    的就是 bug，不该被伪装成一条"错误："文本混进正常对话流。

    也不抛异常出去的原因见 `_common.safe_call` 的注释：LangGraph 会把节点里
    冒泡的异常当致命错误终止整张图，而"技能包名写错"是模型能自己纠正的小事。
    """
    try:
        return _read_skill(name, path, offset, limit)
    except SkillError as exc:
        return f"错误：{exc}"


def build_read_skill_tool() -> BaseTool:
    """产出 read_skill 工具。

    注意：没有 sandbox 参数。它读的是主机上的技能包目录，与沙箱实例无关，
    所以调用方不需要（也不该）为它准备沙箱——建工具时连沙箱都还没建也成立。
    """

    @tool("read_skill", description=DESCRIPTION)
    def _read_skill_tool(
        name: str,
        path: str = "SKILL.md",
        offset: int = 1,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        return read_skill(name, path, offset, limit)

    return _read_skill_tool
