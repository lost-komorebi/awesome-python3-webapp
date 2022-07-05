#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = 'komorebi'

import os.path
from apis import APIError
from urllib import parse
from aiohttp import web
import functools
import asyncio
import inspect
import logging

logging.basicConfig(level=logging.INFO)


def get(path):
    """
    定义装饰器获取URL路径
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'  # 给函数添加__method__属性
        wrapper.__route__ = path  # 给函数添加__route__属性
        return wrapper
    return decorator


def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator


def get_required_kw_args(fn):
    """获取函数的没有默认值的命名关键字参数"""
    args = []
    # 获取函数fn的参数，返回由键(key)为参数名，值(value)为Parameter对象的有序字典(OrderedDict)
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # 如果该参数是命名关键字参数（定义函数时出现在*或者*args后的参数）且没有默认值
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):
    """获取函数的命名关键字参数"""
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:  # 如果该参数是命名关键字参数（定义函数时出现在*或者*args后的参数）
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):
    """判断函数是否存在命名关键字参数"""
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:  # 如果该参数是命名关键字参数（定义函数时出现在*或者*args后的参数）
            return True


def has_var_kw_arg(fn):
    """判断函数是否存在关键字参数**kw"""
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:  # 如果该参数是关键词参数**kw
            return True


def has_request_arg(fn):
    """判断函数是否有requests参数"""
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'requests':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind !=
                      inspect.Parameter.VAR_KEYWORD):  # 参数类型不是可变参数,不是命名关键词参数（定义函数时出现在*或者*args后的参数）,不是关键词参数**kw
            raise ValueError(
                'request parameter must be the last named parameter in function: {}{}'.format(
                    fn.__name__, str(sig)))
        return found


# RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，
# URL函数不一定是一个coroutine，因此我们用RequestHandler()来封装一个URL处理函数。
# 调用URL函数，然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求
class RequestHandler(object):
    """
    任何请求都会进入这个类
    将请求的任何参数都变成self._func(**kw)的形式
    """

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._name_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request):
        kw = None
        # 如果函数参数存在关键字参数**kw或存在命名关键字参数（定义函数时出现在*或者*args后的参数）或者存在requests参数
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':  # 请求方式为POST
                if not request.content_type:  # 如果request未带有content_type则报错
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith(
                        'application/json'):  # 请求参数示例：{"Name": "John Smith", "Age": 23}
                    params = await request.json()  # 获取请求参数
                    if not isinstance(params, dict):  # 请求参数必须为字典
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                # 'application/x-www-form-urlencoded'示例：Name=John+Smith&Age=23；'multipart/form-data'表示文件上传
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest(
                        'Unsupported Content-Type:{}'.format(request.content_type))
            if request.method == 'GET':
                qs = request.query_string  # url的参数  比如/?page=2&id=10&name=john
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(
                            qs, True).items():  # parse.parse_qs解析请求URL的字符串参数并以字典形式返回
                        kw[k] = v[0]  # 将请求参数组装成dict
        if kw is None:
            kw = dict(**request.match_info)  # 从URL获取参数，比如'/blog/{id}' 里面的ID
        else:  # 走到这里说明kw不为空
            if not self._has_var_kw_arg and self._name_kw_args:  # 不存在关键词参数但存在命名关键词参数
                copy = dict()
                for name in self._name_kw_args:  # 如果request中的命名关键词参数在kw中，则将kw该key的值覆盖copy中该key的值，即参数的值以kw为准
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            for k, v in request.match_info.items():
                if k in kw:  # 当出现重复参数，只给予警告信息
                    logging.warning(
                        'Duplicate arg name in named arg and kw args:{}'.format(K))
                kw[k] = v
        # 如果函数有requests参数，则赋值给kw['request'] = request
        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_args:
            for name in self._required_kw_args:
                if name not in kw:  # 如果请求参数中少传了参数则报错
                    return web.HTTPBadRequest(
                        'Missing argument:{}'.format(name))
        logging.info('call with args:{}'.format(str(kw)))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    """添加静态资源"""
    path = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)),
        'static')  # 获取静态资源目录
    app.router.add_static('/static/', path)  # 添加静态资源
    logging.info('add static {} => {}'.format('/static/', path))


def add_route(app, fn):
    method = getattr(fn, '__method__', None)  # 获取请求方式
    path = getattr(fn, '__route__', None)  # 获取路由
    if path is None or method is None:
        raise ValueError('@get or @post not defined in {}.'.format(str(fn)))
    # if not asyncio.iscoroutinefunction(  # iscoroutinefunction 判断是否是协程方法
    #         fn) and not inspect.isgeneratorfunction(fn):  # isgeneratorfunction判断是否是生成器
    #     fn = asyncio.coroutine(fn)
    # 该部分注释掉也可以，官网写到会自动将普通的handler转化为coroutine
    # https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.UrlDispatcher.add_route
    logging.info(
        'add route {} {}=> {}({})'.format(
            method, path, fn.__name__, ','.join(
                inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))  # 添加路由


def add_routes(app, module_name):
    """自动扫描module_name模块中所有函数，将符合条件的函数全部加入到app的路由中"""
    n = module_name.rfind('.')  # rfind返回字符串最后一次出现的位置
    if n == (-1):  # -1表示未找到,表示传入的模块名未带有.py后缀
        mod = __import__(module_name, globals(), locals()
                         )  # __import__导入module_name模块
    else:  # 表示传入的模块名带有.py后缀，比如handlers.py
        name = module_name[:n + 1]
        mod = getattr(__import__(
            module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'): # 跳过_开头的函数名，不是我们定义的
            continue
        fn = getattr(mod, attr)
        if callable(fn):  # 如果fn可以调用，且有__method__和__route__属性，因为定义的@get和@post函数处理后一定会有这两个属性
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)
