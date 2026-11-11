"""Agent 层测试：图组装、节点行为、工具、中止链路。

对应 `src/app/agents/`。图的部分一律用 `build_graph()` 的裸图（不挂
checkpointer），工具部分用假沙箱，都不需要集群、数据库、Redis。
"""
