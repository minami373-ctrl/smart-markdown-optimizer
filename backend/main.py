"""FastAPI エントリ。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from routers import comparison, discount_timing, opportunities, overstock, products, simulations


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="見切り品ダイナミックプライシング・シミュレーター", lifespan=lifespan)
app.include_router(products.router)
app.include_router(simulations.router)
app.include_router(opportunities.router)
app.include_router(overstock.router)
app.include_router(comparison.router)
app.include_router(discount_timing.router)
