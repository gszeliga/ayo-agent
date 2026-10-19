import uvicorn

def main() -> None:
    #print("Hello from ayo-agent!")
    uvicorn.run("ayo_agent.bootstrap:create_agent", factory=True, host="127.0.0.1", port=8000)
