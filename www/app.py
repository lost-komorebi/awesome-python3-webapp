import time
import json
import os
import asyncio
from aiohttp import web
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from orm import create_pool
from coroweb import add_routes, add_static
import logging
from config import configs

logging.basicConfig(level=logging.INFO)


def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape=kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)),
            'templates')
    logging.info('set jinja2 template path: {}'.format(path))
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filter', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
        app['__templating__'] = env


async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: {} {}'.format(request.method, request.path))
        return (await handler(request))
    return logger


async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: {}'.format(str(request.__data__)))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: {}'.format(str(request.__data__)))
        return (await handler(request))


async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(
                    body=json.dumps(
                        r,
                        ensure_ascii=False,
                        default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                resp = web.Response(
                    body=app['__templating__'].get_template(template).render(
                        **r).encode('utf-8'))
                resp.content_type = 'text/html:charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response()


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'{}分钟前'.format(delta // 60)
    if delta < 86400:
        return u'{}分钟前'.format(delta // 3600)
    if delta < 604800:
        return u'{}分钟前'.format(delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'{}年{}月{}日'.format(dt.year, dt.month, dt.day)


async def init():

    host = configs.db.host
    port = configs.db.port
    user = configs.db.user
    password = configs.db.password
    db = configs.db.database

    await create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db)

    app = web.Application(middlewares=[logger_factory, response_factory])
    init_jinja2(app, filter=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')
    add_static(app)
    return app

if __name__ == '__main__':
    web.run_app(init(), host='127.0.0.1', port=9000)  # 启动
    logging.info('server started at http://127.0.0.1:9000...')
