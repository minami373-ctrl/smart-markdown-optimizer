"""FastAPI エントリ。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="見切り品ダイナミックプライシング・シミュレーター", lifespan=lifespan)
