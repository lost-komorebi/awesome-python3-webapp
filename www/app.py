import logging;

logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime

from aiohttp import web


async def index(request):
    """定义首页"""
    await asyncio.sleep(0.5)
    return web.Response(body=b'<h1>Awesome</h1>',
                        content_type="text/html")  # 添加返回内容，content_type指定响应格式


async def hello(request):
    await asyncio.sleep(0.5)
    text = '<h1>hello, {}</h1>'.format(request.match_info['name'])  # match_info读取路由中变量
    return web.Response(body=text.encode('utf-8'),
                        content_type="text/html")


def init():
    app = web.Application()
    app.router.add_get('/', index)  # 添加路由
    app.router.add_get('/hello/{name}', hello)  # 添加路由
    web.run_app(app, host='127.0.0.1', port=9000)  # 启动
    logging.info('server started at http://127.0.0.1:9000...')


if __name__ == '__main__':
    init()
