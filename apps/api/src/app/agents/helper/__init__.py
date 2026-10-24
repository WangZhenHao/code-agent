"""编排辅助模块集合。

跑图与事件流已迁到 app/agents/threading/（Agent Streaming Protocol）；这里
保留中止相关（abort_agent）、中间件（middleware）、技能与提示词装配。

导入方式：写完整子模块路径，例如
    from app.agents.helper.abort_agent import signal_abort
"""
