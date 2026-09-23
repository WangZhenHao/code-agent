"""HTTP 接口层：按领域分子包，每个子包一个 router。"""

from app.api.router import api_router

__all__ = ["api_router"]
