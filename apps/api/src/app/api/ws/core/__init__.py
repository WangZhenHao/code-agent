"""WS 的基础设施：信封之外的一切。

放在二级目录是为了让 `ws/` 顶层保持和 `chat/`、`agent/` 等模块同一形状——
`router.py + schemas.py + service.py` 三件套，一眼能对上仓库里的其它领域模块。
本文件不 re-export（理由同 `app/api/__init__.py`）。
"""
