"""主键生成。

统一走这里，模型里只写 `default=new_id`。换生成策略（比如以后要 ULID 的有序性）
只改这一个文件，不用去动三张表的列定义。

用 cuid2 而不是 uuid4：12 位 vs 36 位，URL 和日志里短一半。cuid2 内部是
时间戳 + 随机盐 + 单调计数器 + 机器指纹，同毫秒内连续调用也不撞——这点比
「uuid4 截断成 12 位」强，后者截断后碰撞概率会显著上升。
"""

from cuid2 import Cuid

#: 所有用 new_id 的主键列长度，模型里写 String(ID_LENGTH) 引它，避免两边写死不同步
ID_LENGTH = 12

# Cuid 实例持有内部计数器，必须模块级复用一个，不能每次调用新建——
# 每次 new 一个 Cuid 计数器就从头开始，同毫秒内会失去单调性保证。
_generator = Cuid(length=ID_LENGTH)


def new_id() -> str:
    """生成一个 12 位 cuid2，如 `sm77bp0ssjsk`。

    直接当 mapped_column 的 default 用（可调用对象，SQLAlchemy 每次 insert 调一次）。
    """
    return _generator.generate()
