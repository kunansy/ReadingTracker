#!/usr/bin/env python3
from collections import defaultdict
from typing import Any

import ujson
from pydantic import ValidationError
from sanic import Sanic, Request, response, HTTPResponse, exceptions
from sanic.log import logger as sanic_logger
from sanic_jinja2 import SanicJinja2
from sanic_session import Session

from src import logger as logger_, settings
from src import tracker as trc
from src import validators
from src import exceptions as ex


app = Sanic(__name__, log_config=logger_.LOGGING_CONFIG)
app.static('/static', './static')

session = Session(app)
jinja = SanicJinja2(app, session=session, enable_async=True)

log = trc.Log(full_info=True)
tracker = trc.Tracker(log)
cards = trc.Cards()


async def get_form_items(request: Request) -> dict[str, Any]:
    return {
        key: val[0]
        for key, val in request.form.items()
    }

@app.get('/')
async def home(request: Request) -> HTTPResponse:
    return response.redirect('/materials/queue')


if __name__ == "__main__":
    app.run(
        port=8080,
        debug=True,
        workers=1,
        access_log=False
    )
