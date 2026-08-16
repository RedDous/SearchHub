import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "searchhub.api.app:create_app",
        factory=True,
        host=os.environ.get("SEARCHHUB_HOST", "0.0.0.0"),
        port=int(os.environ.get("SEARCHHUB_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
