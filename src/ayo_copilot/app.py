from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    ...        # abrir el pool de Postgres
    yield
    ...        # cerrarlo

def create_app() -> FastAPI:
    app = FastAPI(title="AYO Copilot API", lifespan=lifespan)
    
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
