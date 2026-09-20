import asyncio
from app.agents.runner import run_planner, checkpointer_lifespan
from app.core.security import CurrentUser

async def test():
    async with checkpointer_lifespan():
        user = CurrentUser(id="7c101839-19a6-4dc5-88c1-ab8bb8bf8f30", email="ishaniverma847@gmail.com")
        await run_planner("2f551785-3da9-4906-8112-b98137b4adeb", user)

if __name__ == "__main__":
    asyncio.run(test())
