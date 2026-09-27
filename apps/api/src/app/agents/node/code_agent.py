"""codeAgent 节点：按计划读写沙箱内文件。"""

from app.agents.node.state import State


def code_agent(state: State) -> dict:
    """执行计划：读文件、写文件、打补丁。

    占位实现：刻意不绑定 app.agents.tools.filesystem 的工具。那三个函数
    （read_file / write_file / apply_patch）目前还是
    `raise NotImplementedError("尚未接入 sandbox 层")`——一旦 bind_tools，
    模型就会调用它们，然后在工具调用循环里反复抛异常、重试、烧 token。
    等 sandbox 层就绪后再改成本节点 bind_tools + while tool_calls 循环。

    待接入后要注意的点：
    - 工具抛异常不要让它冒泡出节点。LangGraph 会把节点异常直接终止整张图，
      而工具失败（文件不存在、补丁冲突）是**预期内**的情况，应该把错误信息
      作为 ToolMessage 回灌给模型，让它自己修正。
    - 循环要设上限（比如最多 N 轮工具调用），否则模型可能陷在
      "改错→再改→又错"里烧光配额。
    """
    return {"messages": [{"role": "assistant", "content": "[codeAgent] 占位：待接入沙箱工具"}]}
