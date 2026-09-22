import asyncio
import sys

import uvicorn

if sys.platform == "win32":
    # Required for psycopg async mode on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    config = uvicorn.Config("app.main:app", host="::", port=8000)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
