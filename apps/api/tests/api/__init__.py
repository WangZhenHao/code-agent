"""API 层测试：路由、请求模型、业务编排。

对应 `src/app/api/`。这一层不直接执行 agent，所以用假对象替换 DB session /
ThreadSession / start_sandbox，断言落在「调了什么、带什么参数、什么顺序」上。
"""
