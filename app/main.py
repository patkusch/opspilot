"""OpsPilot API — chat an intent, the agent plans, you approve, it acts and proves it."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .store import STORE

app = FastAPI(title="OpsPilot", version="0.1.0")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class PlanReq(BaseModel):
    intent: str


class RunReq(BaseModel):
    intent: str
    operator: str


@app.get("/api/state")
def get_state():
    return STORE.state()


@app.post("/api/plan")
def post_plan(req: PlanReq):
    return STORE.plan(req.intent).model_dump()


@app.post("/api/run")
def post_run(req: RunReq):
    try:
        return STORE.run(req.intent, req.operator).model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/reset")
def post_reset():
    STORE.reset()
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
