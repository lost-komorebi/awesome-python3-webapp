#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

"""默认配置文件，适用于本地开发环境"""

configs = {
    'db': {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'ormuser',
        'password': 'password',
        'database': 'awesome'
    },
    'session': {'secret': 'AwEsOmE', 'max_age': 86400}
}
