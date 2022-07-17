#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

import hashlib

from coroweb import get, post
from models import User, Blog, next_id, Comment
import time
import re
import json
import hashlib
import logging
import markdown2
from apis import APIValueError, APIError, APIPermissionError, Page, APIResourceNotFoundError
from aiohttp import web
from config import configs


@get('/')
async def index(*, page='1'):
    """首页"""
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')  # 查询blog总数
    page = Page(num)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs
    }


@get('/api/users')
async def api_get_users(*, page='1'):
    """获取所有user"""
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')  # 查询user总数
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)


_RE_EMAIL = re.compile(
    r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret
max_age_limit = configs.session.max_age


@post('/api/users')  # register.html调用了该接口
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():  # 校验各个字段
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])  # 对email进行唯一性校验
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email as already in use.')
    uid = next_id()
    sha1_passwd = '{}:{}'.format(uid, passwd)
    user = User(id=uid,
                name=name.strip(),
                email=email,
                passwd=hashlib.sha1(
                    sha1_passwd.encode('utf-8')).hexdigest(),  # 密码加密处理
                image='http://www.gravatar.com/avatar/{}?d=mm&s=120'.format(
                    hashlib.md5(email.encode('utf-8')).hexdigest())  # 保存头像URL
                )
    await user.save()  # 保存入库
    # 设置cookies 并返回
    r = web.Response()  # TODO 不知道这个r从哪里来的
    r.set_cookie(
        COOKIE_NAME,  # cookie名称
        user2cookie(  # 用来生成cookie的方法
            user,
            max_age_limit),
        max_age=max_age_limit,  # cookie有效时间，单位为秒，这里设置为1天
        httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    logging.info("user information >>>>", user)
    return r


@get('/register')
async def register():
    return {
        '__template__': 'register.html'
    }


@get('/signin')
async def signin():
    return {
        '__template__': 'signin.html'
    }


@get('/signout')
async def signout(request):
    # HTTP Referer是header的一部分，当浏览器向web服务器发送请求的时候，一般会带上Referer，
    # 告诉服务器该网页是从哪个页面链接过来的，服务器因此可以获得一些信息用于处理。
    cookie_str = request.cookies.get(COOKIE_NAME)
    user = await cookie2user(cookie_str)
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')  # 返回到来源页或者首页
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0,
                 httponly=True)  # max_age=0让cookie立马失效
    logging.info('user {} signed out.'.format(user.name))
    return r


@post('/api/authenticate')  # signin.html调用了该函数
async def authenticate(*, email, passwd):
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'email and passwd not correct.')
    user = users[0]
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))  # 根据用户输入的密码加密后和数据库比对是否一致
    if user.passwd != sha1.hexdigest():
        raise APIValueError('password', 'email and passwd not correct.')
    r = web.Response()
    r.set_cookie(
        COOKIE_NAME,
        user2cookie(
            user,
            max_age_limit),
        max_age=max_age_limit,
        httponly=True)
    user.passwd = '******'  # 将用户密码返回给前端时隐藏处理
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


def user2cookie(user, max_age):
    """
    生成cookies
    "用户id" + "过期时间" + SHA1("用户id" + "用户口令" + "过期时间" + "SecretKey")
    在浏览器上看到的 Cookie: awesession=00165708895850858cd826b0ac34e00a5cbd154f30b16ea000-1657177387-640fb14285b7f3b30595926ae0bd97506119bafb
    """
    expires = str(int(time.time() + max_age))  # 过期时间等于当前时间加上max_age
    s = '{}-{}-{}-{}'.format(user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)


async def cookie2user(cookie_str):
    """根据cookie找user"""
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():  # 比较有效时间
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '{}-{}-{}-{}'.format(uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():  # 比对cookie
            logging.info('invalid sha1')
            return None
        user.passwd = '******'  # 将用户密码返回给前端时隐藏处理
        return user
    except Exception as e:
        logging.exception(e)
        return None


def check_admin(request):
    """判断当前登陆人是否是管理员"""
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


def get_page_index(page_str):
    """对传入的页码进行处理，若页码不合法则默认返回第一页"""
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def text2html(text):
    """将一些字符转义"""
    lines = map(
        lambda s: '<p>{}</p>'.format(
            s.replace(
                '&', '&amp;').replace(
                '<', '&lt;').replace(
                    '>', '&gt;')), filter(
                        lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


@get('/blog/{id}')
async def get_blog(id):
    """根据id获取blog及其评论"""
    blog = await Blog.find(id)
    comments = await Comment.findAll(
        'blog_id=?',
        [id],
        orderBy='created_at desc'
    )
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)  # 让blog支持markdown
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


@get('/manage/blogs/create')
async def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }


@get('/manage/blogs/edit')
async def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/{}'.format(id)
    }


@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)


@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog


@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty')
    blog = Blog(
        user_id=request.__user__.id,
        user_name=request.__user__.name,
        user_image=request.__user__.image,
        name=name.strip(),
        summary=summary.strip(),
        content=content.strip())
    await blog.save()
    return blog


@post('/api/blogs/{id}')
async def api_edit_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog  # todo 应该返回详情页或列表页


@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')  # 获取blog总数
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/manage/blogs')
async def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }


@get('/manage/')
async def manage():
    return 'redirect:/manage/comments'


@get('/manage/comments')
async def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }


@get('/manage/users')
async def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }


@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)


@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(
        blog_id=blog.id,
        user_id=user.id,
        user_name=user.name,
        user_image=user.image,
        content=content.strip())
    await comment.save()
    return comment


@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)
