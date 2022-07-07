#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定义各种数据模型"""
__author__ = 'komorebi'

import time
import uuid

from orm import Model, StringField, BooleanField, FloatField, TextField


def next_id():
    """生成ID {:0>15d}将数字左边补零到15位，{:0<35s}将字符串右边补零到35位"""
    return '{:0>15d}{:0<35s}'.format(
        int(time.time() * 1000), uuid.uuid4().hex)  # hex以一个32位的字符串来表示uuid


class User(Model):
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id(), ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(50)')
    created_at = FloatField(default=time.time)


class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id(), ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(50)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(default=time.time)


class Comment(Model):
    __table__ = 'comments'

    id = StringField(primary_key=True, default=next_id(), ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)
