import os
from pathlib import Path

import uvicorn

from searchhub.api.app import create_app


def main() -> None:
    data_dir = os.environ.get("SEARCHHUB_DATA")
    uvicorn.run(
        create_app(data_dir=Path(data_dir) if data_dir else None),
        host=os.environ.get("SEARCHHUB_HOST", "0.0.0.0"),
        port=int(os.environ.get("SEARCHHUB_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
