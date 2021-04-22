#!/usr/bin/env python3
from typing import Any

from sanic import Sanic, Request, response
from sanic_jinja2 import SanicJinja2

from src.tracker import Tracker, Log


app = Sanic(__name__)
app.static('/static', './static')
jinja = SanicJinja2(app)

log = Log()
tracker = Tracker(log)


@app.get('/materials/queue')
@jinja.template('queue.html')
async def get_queue(request: Request) -> dict[str, Any]:
    return {
        'materials': tracker.queue
    }


@app.post('/materials/add')
async def add_material(request: Request) -> response.HTTPResponse:
    """ Add a material to the queue """
    pass


@app.post('/materials/start/<material_id:int>')
async def start_material(request: Request,
                         material_id: int) -> response.HTTPResponse:
    pass


@app.post('/materials/complete/<material_id:int>')
async def complete_material(request: Request,
                            materials_id: int) -> response.HTTPResponse:
    pass


@app.get('/materials/reading')
async def get_reading_materials(request: Request) -> response.HTTPResponse:
    pass


@app.get('/materials/completed')
async def get_completed_materials(request: Request) -> response.HTTPResponse:
    pass


@app.get('/reading_log')
async def get_reading_log(request: Request) -> response.HTTPResponse:
    pass


@app.post('/reading_log')
async def add_reading_log(request: Request) -> response.HTTPResponse:
    pass


@app.get('/notes')
async def get_notes(request: Request) -> response.HTTPResponse:
    pass


@app.post('/notes')
async def add_notes(request: Request) -> response.HTTPResponse:
    pass


@app.get('/')
async def home(request: Request) -> response.HTTPResponse:
    pass


@app.exception(Exception)
def error_handler(request: Request,
                  exception: Exception) -> response.HTTPResponse:
    try:
        json = exception.json()
    except AttributeError:
        json = ''

    context = {
        'ok': False,
        "wrong_request": request.json,
        "error": {
            "type": exception.__class__.__name__,
            "text": str(exception),
            "args": exception.args,
            "json": json
        }
    }

    return response.json(context, status=500, indent=4)


if __name__ == "__main__":
    app.run(
        port=8080,
        debug=True,
    )

