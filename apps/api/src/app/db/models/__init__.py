"""所有表模型的聚合入口。

Alembic 的 autogenerate 只看得见已经 import 过的模型——Base.metadata 里没有
注册的类，它就会当成「表被删了」并生成 DROP。所以**每新增一个模型都必须
在这里 import 一次**，env.py 只 import 这一个模块。
"""

from app.db.models.user import User

__all__ = ["User"]
