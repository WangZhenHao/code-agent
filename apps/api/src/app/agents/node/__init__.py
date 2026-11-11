"""节点函数集合。

约定：每个节点是 `(State) -> dict`，只返回**要更新的字段**。
不要原地改 state——LangGraph 按返回的 dict 做增量合并，
原地改会绕过 reducer（messages 的 add_messages 就是这样生效的）。

导入方式必须写全子模块路径（`from app.agents.node.classify import classify`），
不能用 `from app.agents.node import classify`——子模块名与函数名同名，
那条写法拿到的是**模块对象**，传给 add_node 会报
"Expected a Runnable, callable or dict. Instead got an unsupported type: <class 'module'>"。
下面这些精确导入会把名字重新绑定成函数，之后 `from app.agents.node import classify`
才是函数。

当前阶段：四个节点都是占位实现，不调用模型、不访问沙箱。
"""

from app.agents.node.classify import classify
from app.agents.node.code_agent import code_agent
from app.agents.node.finish import finish
from app.agents.node.plan_agent import plan_agent

__all__ = ["classify", "plan_agent", "code_agent", "finish"]
