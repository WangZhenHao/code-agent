"""文件读写工具。

约定：所有路径都是沙箱内的路径，由 sandbox 层解析，不是 API 进程所在机器的路径。
"""


def read_file(path: str) -> str:
    """读取沙箱内文件。"""
    raise NotImplementedError("read_file 尚未接入 sandbox 层")


def write_file(path: str, content: str) -> None:
    """写入沙箱内文件。"""
    raise NotImplementedError("write_file 尚未接入 sandbox 层")


def apply_patch(path: str, patch: str) -> None:
    """对沙箱内文件应用补丁。"""
    raise NotImplementedError("apply_patch 尚未接入 sandbox 层")
