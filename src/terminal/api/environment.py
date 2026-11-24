"""GET /environment: what claude's environment can really do."""

from fastapi import APIRouter

from terminal.environment.selftest import EnvironmentSelfTest


def environment_router(selftest: EnvironmentSelfTest) -> APIRouter:
    router = APIRouter()

    @router.get("/environment")
    async def environment(deep: bool = False) -> dict:
        """The environment claude works in: compilers, make, docker (client and daemon), and a real build."""
        return {"tools": await selftest.run(deep)}

    return router
