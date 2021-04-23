#!/usr/bin/env python3
from typing import Any

from pydantic import BaseModel, ValidationError
from sanic import Sanic, Request, response, HTTPResponse
from sanic_jinja2 import SanicJinja2

from src import db_api
from src.tracker import Tracker, Log, DATE_FORMAT, PAGES_PER_DAY


app = Sanic(__name__)
app.static('/static', './static')
jinja = SanicJinja2(app)

log = Log()
tracker = Tracker(log)


class Note(BaseModel):
    material_id: int
    content: str
    chapter: int
    page: int

    def __repr__(self) -> str:
        fields = ', '.join(
            f"{key}='{val}'"
            for key, val in self.dict().items()
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        return repr(self)


@app.get('/favicon.ico')
async def favicon(request: Request) -> HTTPResponse:
    return response.json({})


@app.get('/materials/queue')
@jinja.template('queue.html')
async def get_queue(request: Request) -> dict[str, Any]:
    return {
        'materials': tracker.queue
    }


@app.post('/materials/add')
async def add_material(request: Request) -> HTTPResponse:
    """ Add a material to the queue """
    pass


@app.post('/materials/start/<material_id:int>')
async def start_material(request: Request,
                         material_id: int) -> HTTPResponse:
    pass


@app.post('/materials/complete/<material_id:int>')
async def complete_material(request: Request,
                            materials_id: int) -> HTTPResponse:
    pass


@app.get('/materials/reading')
@jinja.template('reading.html')
async def get_reading_materials(request: Request) -> dict[str, Any]:
    # TODO: add statistics, make special method in tracker to
    #  calculate all statistics about the material

    materials = tracker.reading
    avg = log.average_of_every_materials

    statistics = {
        material.material_id: {
            'total': log.total_read(material.material_id),
            'average': avg[material.material_id],
            'remain': ''
        }
        for material, status in materials
    }

    return {
        'materials': materials,
        'DATE_FORMAT': DATE_FORMAT,
        'statistics': statistics
    }


@app.get('/materials/completed')
@jinja.template('completed.html')
async def get_completed_materials(request: Request) -> dict:
    # TODO: add statistics

    status = {
        status_.material_id: status_
        for status_ in db_api.get_status()
    }
    return {
        'materials': tracker.processed,
        'status': status,
        'DATE_FORMAT': DATE_FORMAT
    }


@app.get('/reading_log')
@jinja.template('reading_log.html')
async def get_reading_log(request: Request) -> dict[str, Any]:
    log_ = log.log
    titles = {
        info['material_id']: db_api.get_title(info['material_id'])
        for date, info in log_ .items()
    }

    return {
        'log': log_,
        'titles': titles,
        'DATE_FORMAT': DATE_FORMAT,
        'EXPECTED_COUNT': PAGES_PER_DAY
    }


@app.post('/reading_log')
async def add_reading_log(request: Request) -> HTTPResponse:
    pass


@app.get('/notes')
@jinja.template('notes.html')
async def get_notes(request: Request):
    if material_id := request.args.get('material_id'):
        material_id = int(material_id)
        notes = db_api.get_notes(materials_ids=[material_id])
    else:
        notes = db_api.get_notes()

    titles = {
        note.material_id: db_api.get_title(note.material_id)
        for note in notes
    }
    return {
        'notes': notes,
        'titles': titles,
        'DATE_FORMAT': DATE_FORMAT
    }


@app.get('/notes/add')
@jinja.template('add_note.html')
async def add_notes(request: Request) -> dict[str, Any]:
    # TODO: use cookies instead of headers.
    #  See Sanic#2124 why headers don't work
    return {
        'material_id': request.headers.get('material_id', ''),
        'content': request.headers.get('content', ''),
        'page': request.headers.get('page', ''),
        'chapter': request.headers.get('chapter', ''),
    }


@app.post('/notes/add')
async def add_notes(request: Request) -> HTTPResponse:
    key_val = {
        key: val[0]
        for key, val in request.form.items()
    }

    note = Note(**key_val)
    db_api.add_note(**note.dict())

    return response.redirect('/notes/add')


@app.get('/')
@jinja.template('index.html')
async def home(request: Request) -> None:
    pass


@app.exception(ValidationError)
def validation_error_handler(request: Request,
                             exception: ValidationError) -> HTTPResponse:
    return response.json(exception.errors(), status=400, indent=4)


@app.exception(Exception)
def error_handler(request: Request,
                  exception: Exception) -> HTTPResponse:
    try:
        ex_json = exception.json()
    except:
        ex_json = ''
    try:
        req_json = request.json
    except:
        req_json = ''

    context = {
        'ok': False,
        "wrong_request": req_json,
        "error": {
            "type": exception.__class__.__name__,
            "text": str(exception),
            "args": exception.args,
            "json": ex_json
        }
    }

    return response.json(context, status=500, indent=4)


if __name__ == "__main__":
    app.run(
        port=8080,
        debug=True,
    )

