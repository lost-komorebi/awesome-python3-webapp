#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

import time
import json
import os
from aiohttp import web  # 异步框架aiohttp
from datetime import datetime
from jinja2 import Environment, FileSystemLoader  # 前端模板引擎jinja2
from orm import create_pool
from coroweb import add_routes, add_static
import logging
from config import configs
from handlers import COOKIE_NAME, cookie2user

logging.basicConfig(level=logging.INFO)


def init_jinja2(app, **kw):
    """
    该函数用来初始化jinja2环境
    """
    logging.info('init jinja2...')
    """设置初始化jinja2的一些环境参数"""
    options = dict(
        autoescape=kw.get('autoescape', True),  # 为True表示自动转义
        block_start_string=kw.get('block_start_string', '{%'),  # 块开始标识
        block_end_string=kw.get('block_end_string', '%}'),  # 块结束标识
        variable_start_string=kw.get('variable_start_string', '{{'),  # 变量开始标识
        variable_end_string=kw.get('variable_end_string', '}}'),  # 变量结束标识
        # 为True表示修改模版文件立即生效，刷新网页就可以看到修改后的效果
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        """path即templates文件夹路径"""
        path = os.path.join(  # path拼接路径
            os.path.dirname(  # dirname获取文件所在文件夹路径
                os.path.abspath(__file__)),  # __file__ 获取文件路径，abspath获取绝对路径
            'templates')
    logging.info('set jinja2 template path: {}'.format(path))
    env = Environment(  # Environment()生成一个jinja2环境实例
        # FileSystemLoader Load templates from a directory in the file system.
        loader=FileSystemLoader(path),
        **options)  # 通过加载上文path路径生成一个jinja2环境
    filters = kw.get('filter', None)  # 过滤器可以过滤过滤数据，也可以改变内容的展示效果
    if filters is not None:
        for name, f in filters.items():  # 将自定义的过滤器加入到系统自带的过滤器中
            env.filters[name] = f
    app['__templating__'] = env  # 将env赋值给app['__templating__']


async def logger_factory(app, handler):
    """打印请求方式和路由"""
    async def logger(request):
        logging.info('Request: {} {}'.format(request.method, request.path))
        return (await handler(request))
    return logger


async def data_factory(app, handler):
    """获取请求的参数，并绑定到request.__data__上"""
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: {}'.format(str(request.__data__)))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: {}'.format(str(request.__data__)))
        return (await handler(request))
    return parse_data


async def response_factory(app, handler):
    """把任何类型的返回值最后都统一封装成一个web.Response对象"""
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)  # 这里的handler其实就是RequestHandler(app, fn)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):  # 如果是重定向就返回重定向后面的部分
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')  # 获取模版
            if template is None:
                resp = web.Response(
                    body=json.dumps(
                        r,
                        ensure_ascii=False,  # 汉字会正常显示不会被显示成ascii码表示
                        default=lambda o: o.__dict__).encode('utf-8'))
                """
                json.dumps 当 default 被指定时，其应该是一个函数，每当某个对象无法被序列化时它会被调用。
                它应该返回该对象的一个可以被 JSON 编码的版本或者引发一个 TypeError。
                如果没有被指定，则会直接引发 TypeError。
                __dict__属性：查看对象内部所有属性名和属性值组成的字典
                """
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                r['__user__'] = request.__user__  # 返回user信息给前端展示
                resp = web.Response(
                    body=app['__templating__'].get_template(template).render(
                        **r).encode('utf-8'))
                resp.content_type = 'text/html; charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp.body
    return response


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: {} {}'.format(request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)  # 从cookies获取cookie
        if cookie_str:
            user = await cookie2user(cookie_str)  # 根据cookie取得用户信息
            if user:
                logging.info('set current user: {}'.format(user.email))
                request.__user__ = user  # 将user赋值给request.__user__以便返回给前端
        if request.path.startswith(
                '/manage/') and (request.__user__ is None or not request.__user__.admin):
            # 需要管理员账号才可以访问manage相关页面
            return web.HTTPFound('/signin')
        return (await handler(request))
    return auth


def datetime_filter(t):
    """时间处理函数，将时间处理成易读形式"""
    delta = int(time.time() - t)  # time.time()返回当前unix timestamp
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

    app = web.Application(
        middlewares=[
            logger_factory,
            response_factory,
            auth_factory
        ])  # 初始化一个web服务实例
    init_jinja2(app, filter=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')  # 将handlers.py中所有路由添加到app中
    add_static(app)  # 添加静态资源目录
    return app

if __name__ == '__main__':
    web.run_app(init(), host='127.0.0.1', port=9000)  # 启动
    logging.info('server started at http://127.0.0.1:9000...')
