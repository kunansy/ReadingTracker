from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from tracker.common import settings
from tracker.cards import db, schemas


router = APIRouter(
    prefix="/cards",
    tags=["cards"]
)

