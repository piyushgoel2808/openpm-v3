from __future__ import annotations

from fastapi.responses import JSONResponse
from openenv.core.env_server import create_app

from openpm_env.env import OpenPMEnvironment
from openpm_env.models import PMAction, PMObservation

app = create_app(OpenPMEnvironment, PMAction, PMObservation, env_name="openpm_env")


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({
        "name": "openpm_env",
        "description": "OpenPM: deterministic project management RL environment",
        "endpoints": ["/reset", "/step", "/state", "/health"],
    })


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
