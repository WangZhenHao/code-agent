"""classify 节点：判断需求该走规划还是直接改代码。"""

from app.agents.node.state import State


def classify(state: State) -> dict:
    """判断这条需求该走规划（planAgent）还是直接动手（codeAgent）。

    占位实现：固定返回 "plan"。

    待接入 LLM 后：
    1. 让模型读 state["messages"]，输出 plan / agent 之一；
    2. **必须先做白名单校验再写回**。Branch 是 Literal，但那是静态类型层面的
       约束，运行期拿到一个模型瞎编的字符串（比如 "PLAN"、"planning"）照样能塞进
       state，然后在 add_conditional_edges 那里抛异常——报错信息会指向路由，
       而真正的错因在模型输出，排查会绕远路。
    3. 判别器用 temperature=0，让它别自由发挥。
    """
    return {"mode": state.get("mode")}  # 占位实现，固定返回 plan
