import uvicorn


def main() -> None:
    # print("Hello from ayo-agent!")
    uvicorn.run("ayo_copilot.app:create_app", factory=True, host="127.0.0.1", port=8000)
