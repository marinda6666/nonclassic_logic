"""Stateless HTTP API. All fuzzy computations are performed on the server."""
import logging
import math
import secrets
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import fuzzy as F
from .clustering import analyze

app = FastAPI(title='Weibull Lab API', version='2.0.0', docs_url='/api/docs',
              redoc_url='/api/redoc', openapi_url='/api/openapi.json')
logger = logging.getLogger('uvicorn.error')
STATIC = Path(__file__).resolve().parent.parent / 'static'


class Model(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class Value(Model):
    name: str = Field(min_length=1, max_length=80)
    type: Literal['weibull', 'cuts'] = 'weibull'
    shape: float | None = Field(default=None, ge=1, le=20)
    scale: float | None = Field(default=None, ge=.05, le=1000)
    shift: float = Field(default=0, ge=-10000, le=10000)
    cuts: list[tuple[float, float]] | None = Field(default=None, min_length=101, max_length=101)


class Generation(Model):
    count: Annotated[int, Field(strict=True, ge=100, le=300)] = 150
    seed: Annotated[int, Field(strict=True, ge=0, le=4294967295)] | None = None


class Options(Model):
    metric: Literal['cuts', 'center', 'alpha'] = 'cuts'
    alpha: float = Field(default=.5, ge=F.EPS, le=1)
    mode: Literal['fixed', 'threshold'] = 'fixed'
    k: Annotated[int, Field(strict=True, ge=1, le=10)] = 3
    threshold: float | None = Field(default=None, ge=0)


class Operation(Model):
    a: Value
    b: Value
    operation: Literal['+', '-', '*', '/', 'compare']
    name: str = Field(default='Результат', min_length=1, max_length=80)


class ClusterRequest(Model):
    items: list[Value] = Field(min_length=2, max_length=500)
    options: Options = Field(default_factory=Options)


class LogEntry(Model):
    time: str = Field(max_length=100)
    action: str = Field(max_length=200)
    details: object = None


class Project(Model):
    format: Literal['weibull-lab']
    version: Literal[1]
    epsilon: float
    levels: list[float] = Field(min_length=101, max_length=101)
    items: list[Value] = Field(max_length=500)
    analysisOptions: Options | None = None
    logs: list[LogEntry] = Field(default_factory=list, max_length=10000)


def unpack(value):
    return F.validate(value.model_dump(exclude_none=True))


@app.middleware('http')
async def limits_and_headers(request: Request, call_next):
    # Read bounded chunks before JSON parsing, including chunked requests.
    if request.url.path.startswith('/api/') and request.method == 'POST':
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 15_000_000:
                return JSONResponse(status_code=413, content={'detail': 'Файл больше 15 МБ.'})
        request._body = bytes(data)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(ValueError)
async def invalid_value(request, error):
    return JSONResponse(status_code=422, content={'detail': str(error)})


@app.get('/healthz', tags=['System'])
def health():
    return {'status': 'ok', 'backend': 'python-fastapi'}


@app.get('/api/config', tags=['System'])
def config():
    return {'epsilon': F.EPS, 'levels': F.LEVELS, 'backend': 'Python / FastAPI'}


@app.post('/api/generate', tags=['Fuzzy quantities'])
def generate(body: Generation):
    seed = body.seed if body.seed is not None else secrets.randbits(32)
    values = F.generate(body.count, seed)
    logger.info('generate count=%s seed=%s', body.count, seed)
    return {'items': values, 'seed': seed, 'generator': 'uniform-v2'}


@app.post('/api/values', tags=['Fuzzy quantities'])
def value(body: Value):
    result = unpack(body)
    logger.info('value name=%s type=%s', result['name'], result['type'])
    return result


@app.post('/api/operations', tags=['Fuzzy quantities'])
def operation(body: Operation):
    a, b = unpack(body.a), unpack(body.b)
    logger.info('operation=%s a=%s b=%s', body.operation, a['name'], b['name'])
    if body.operation == 'compare':
        return F.compare(a, b)
    return F.arithmetic(a, b, body.operation, body.name)


@app.post('/api/cluster', tags=['Clustering'])
def cluster(body: ClusterRequest):
    result = analyze([unpack(v) for v in body.items], body.options.model_dump())
    logger.info('cluster n=%s mode=%s groups=%s silhouette=%s', len(body.items), result['mode'],
                len(result['groups']), result['silhouette'])
    return result


@app.post('/api/projects/validate', tags=['Projects'])
def project(body: Project):
    F.check(body.epsilon == F.EPS and all(math.isclose(a, b, rel_tol=1e-14, abs_tol=1e-15)
            for a, b in zip(body.levels, F.LEVELS)), 'Неподдерживаемая сетка α-срезов.')
    items = [unpack(v) for v in body.items]
    options = body.analysisOptions.model_dump() if body.analysisOptions else None
    result = analyze(items, options) if options else None
    return {'items': items, 'analysis': result, 'logs': [v.model_dump() for v in body.logs]}


# Mount only public artifacts, never the source tree or server configuration.
if STATIC.exists():
    app.mount('/', StaticFiles(directory=STATIC, html=True), name='frontend')
else:
    # A source checkout can be run with Uvicorn without copying frontend files.
    root = Path(__file__).resolve().parent.parent

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(root / 'index.html')

    @app.get('/app.js', include_in_schema=False)
    def frontend_script():
        return FileResponse(root / 'app.js', media_type='application/javascript')

    @app.get('/styles.css', include_in_schema=False)
    def frontend_styles():
        return FileResponse(root / 'styles.css', media_type='text/css')

    for folder in ['docs', 'examples']:
        if (root / folder).exists():
            app.mount('/' + folder, StaticFiles(directory=root / folder), name=folder)
