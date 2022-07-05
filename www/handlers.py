#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

from coroweb import get
from models import User


@get('/')
async def index():
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }
