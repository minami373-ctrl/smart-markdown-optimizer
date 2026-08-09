"""FastAPI エントリ。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from routers import opportunities, products, simulations


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="見切り品ダイナミックプライシング・シミュレーター", lifespan=lifespan)
app.include_router(products.router)
app.include_router(simulations.router)
app.include_router(opportunities.router)
