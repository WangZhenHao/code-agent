"""Export the user API contract without importing the runtime sandbox client."""

import json
import sys
from pathlib import Path

from fastapi import FastAPI

from app.api.user.router import router as user_router


app = FastAPI(title="Code Agent User API")
app.include_router(user_router)

output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
