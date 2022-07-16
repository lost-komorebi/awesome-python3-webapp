#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'
import config_default
import os


class Dict(dict):
    """
    继承自dict类，可以使用dict有的方法
    该Dict类可以通过d.key方式来代码d['key']方式取值和设值
    """

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(
                r"'Dict' object has no attribute '{}'".format(key))

    def __setattr__(self, key, value):
        self[key] = value


def merge(defaults, override):
    """以override为主合并配置文件数据"""
    r = {}
    for k, v in defaults.items():
        if k in override:
            if isinstance(v, dict):  # 如果是嵌套字典，则再次merge
                r[k] = merge(v, override[k])
            else:
                r[k] = override[k]  # 将override的值覆盖defaults
        else:
            r[k] = v  # 如果override不存在的值，则不做改动
    return r


def toDict(d):
    """
    将d转化成自己定义的Dict类型，可以通过d.key代替d['key']来取值或设值
    """
    D = Dict()

    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D


configs = config_default.configs
if os.environ['app_env'] == 'pro':
    try:
        import config_override
        configs = merge(configs, config_override.configs)
    except ImportError:
        pass


configs = toDict(configs)
