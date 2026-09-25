"""短信下发通道。

当前只有 Console 实现：验证码打到日志，debug 下还会出现在接口响应里，
方便前端联调。接真实服务商（阿里云 / 腾讯云 / 云片）时，
新写一个类实现 SmsSender 协议，改 get_sms_sender 的分支即可，
业务侧（api/user/service.py）一行都不用动。
"""

from typing import Protocol

from app.settings import settings


class SmsSender(Protocol):
    """下发一条验证码短信。实现方只负责「尽力送出去」，不负责校验。"""

    async def send_code(self, phone: str, code: str) -> None: ...


class ConsoleSmsSender:
    """开发用：只打日志，不发真短信。

    code 同时会随响应返回（见 api/user/router.py，仅 debug 开启），
    所以本地联调不必翻日志。
    """

    async def send_code(self, phone: str, code: str) -> None:
        import logging

        logging.getLogger(__name__).warning(
            "[开发模式] 未真正发送短信 phone=%s code=%s", phone, code
        )


def get_sms_sender() -> SmsSender:
    """FastAPI 依赖：`sender: SmsSender = Depends(get_sms_sender)`。

    现在恒返回 Console 实现。以后加阿里云时，在这里按 settings 里的
    provider 字段分支即可；调用方拿到的一直是 SmsSender，不受影响。
    """
    _ = settings  # 预留：以后按配置选实现
    return ConsoleSmsSender()
