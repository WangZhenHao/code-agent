"""WS 的基础设施：信封之外的一切。

放在二级目录是为了让 `ws/` 顶层保持和 `chat/`、`agent/` 等模块同一形状——
`router.py + schemas.py`，一眼能对上仓库里的其它领域模块。ws 没有 `service.py`：
业务逻辑只有「预览状态」一处，和推送形状共用地放在 `api/sandbox/preview.py`。
本文件不 re-export（理由同 `app/api/__init__.py`）。
"""
