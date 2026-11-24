"""Is the app up, and can the sandbox and claude's terminal really build and run things."""

from fastapi import APIRouter

from verdict.api.deps import ContainerDep

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(container: ContainerDep) -> dict:
    return container.health.status()


@router.get("/environment")
def environment(container: ContainerDep, deep: bool = False) -> dict:
    return container.environment.check(deep)
