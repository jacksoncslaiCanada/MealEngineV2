import logging
import os
import subprocess
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

if __name__ == "__main__":
    # Run database migrations before starting the server
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
