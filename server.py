#!/usr/bin/env python3
import logging
from typing import Any

import ujson
from pydantic import BaseModel, ValidationError, validator
from sanic import Sanic, Request, response, HTTPResponse
from sanic_jinja2 import SanicJinja2
from sanic_session import Session

from src import db_api
from src import tracker as trc


MSG_FMT = "[{asctime},{msecs:3.0f}] [{levelname:^8}] " \
          "[{module}:{funcName}] {message}"
DATE_FMT = "%d-%m-%Y %H:%M:%S"

logging.basicConfig(
    style='{',
    format=MSG_FMT,
    datefmt=DATE_FMT,
    level=logging.DEBUG,

)

app = Sanic(__name__)
app.static('/static', './static')

session = Session(app)
jinja = SanicJinja2(app, session=session)

log = trc.Log()
tracker = trc.Tracker(log)


class Note(BaseModel):
    material_id: int
    content: str
    chapter: int
    page: int

    @validator('content')
    def strip_content(cls,
                      content: str) -> str:
        return content.strip()

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
    try:
        tracker.start_material(material_id)
    except trc.BaseDBError as e:
        jinja.flash(request, str(e), 'error')
    else:
        jinja.flash(request, f"Material {material_id=} started", 'success')
    finally:
        return response.redirect('/material/queue')


@app.post('/materials/complete/<material_id:int>')
async def complete_material(request: Request,
                            material_id: int) -> HTTPResponse:
    try:
        tracker.complete_material(material_id)
    except trc.BaseDBError as e:
        jinja.flash(request, str(e), 'error')
    else:
        jinja.flash(request, f"Material {material_id=} completed", 'success')
    finally:
        return response.redirect('/materials/reading')


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
        'DATE_FORMAT': trc.DATE_FORMAT,
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
        'DATE_FORMAT': trc.DATE_FORMAT
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
        'DATE_FORMAT': trc.DATE_FORMAT,
        'EXPECTED_COUNT': trc.PAGES_PER_DAY
    }


@app.post('/reading_log')
async def add_reading_log(request: Request) -> HTTPResponse:
    pass


@app.get('/notes')
@jinja.template('notes.html')
async def get_notes(request: Request):
    material_id = request.args.get('material_id')
    try:
        notes = tracker.get_notes(material_id)
    except ValueError:
        jinja.flash(request, 'Enter an integer', 'error')
        return response.redirect('/notes')

    if not notes:
        jinja.flash(request, f'No notes {material_id=} found', 'error')
    else:
        jinja.flash(request, f"{len(notes)} notes found", 'success')

    titles = {
        note.material_id: db_api.get_title(note.material_id)
        for note in notes
    }
    return {
        'notes': notes,
        'titles': titles,
        'DATE_FORMAT': trc.DATE_FORMAT
    }


@app.get('/notes/add')
@jinja.template('add_note.html')
async def add_notes(request: Request) -> dict[str, Any]:
    return {
        'material_id': request.ctx.session.get('material_id', ''),
        'content': request.ctx.session.get('content', ''),
        'page': request.ctx.session.get('page', ''),
        'chapter': request.ctx.session.get('chapter', ''),
    }


@app.post('/notes/add')
async def add_notes(request: Request) -> HTTPResponse:
    key_val = {
        key: val[0]
        for key, val in request.form.items()
    }

    try:
        note = Note(**key_val)
    except ValidationError as e:
        context = ujson.dumps(e.errors(), indent=4)
        logging.warning(f"Validation error:\n{context}")

        jinja.flash(request, 'Validation error', 'error')
        return response.redirect('/notes/add')

    try:
        tracker.add_note(**note.dict())
    except trc.MaterialNotFound as e:
        jinja.flash(request, str(e), 'error')
    except ValueError as e:
        jinja.flash(request, str(e), 'error')
    else:
        jinja.flash(request, 'Note added', 'success')
        request.ctx.session.update(
            **note.dict(exclude={'content'})
        )
    finally:
        return response.redirect('/notes/add')


@app.get('/analytics')
@jinja.template('analytics.html')
async def analytics(request: Request) -> dict[str, Any]:
    pass


@app.get('/')
@jinja.template('index.html')
async def home(request: Request) -> None:
    pass


@app.exception(ValidationError)
def validation_error_handler(request: Request,
                             exception: ValidationError) -> HTTPResponse:
    context = ujson.dumps(exception.errors(), indent=4)
    logging.error(f"Validation error was not handled:\n{context}")

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

    logging.error(ujson.dumps(context, indent=4))
    return response.json(context, status=500, indent=4)


if __name__ == "__main__":
    app.run(
        port=8080,
        debug=True,
    )

