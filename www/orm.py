#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

import logging;

logging.basicConfig(level=logging.INFO)
import aiomysql
import asyncio


def log(sql, args=()):
    # 定义函数打印sql
    logging.info('SQL: {}\r\n ARGS:{}'.format(sql, args))


async def create_pool(**kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(  # 建立数据库连接
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),  # 注意此处是utf8而不是utf-8
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),  # 连接池最大值
        minsize=kw.get('minsize', 1)  # 连接池最小值
    )


async def select(sql, args, size=None):  # size指最多返回多少条
    """查询使用"""
    log(sql, args)
    global __pool
    with (await __pool) as conn:  # with语句用于自动处理异常
        cur = await conn.cursor(aiomysql.DictCursor)  # 使用游标
        await cur.execute(sql.replace('?', '%s'), args or ())  # sql.replace('?', '%s')将sql中的占位符?替换成%s
        if size:
            rs = await cur.fetchmany(size)  # 返回size条数的记录
        else:
            rs = await cur.fetchall()  # 返回查询结果所有记录
        await cur.close()  # 关闭游标
        logging.info('rows returned: %s' % len(rs))  # 记录返回行数
        return rs  # 返回查询结果


async def execute(sql, args):
    """新增，删除，修改使用"""
    log(sql, args)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()  # 游标
            print(sql.replace('?', '%s'), args)
            await cur.execute(sql.replace('?', '%s'), args)  # 执行sql
            affected = cur.rowcount  # 受影响行数
            await cur.close()  # 关闭游标
        except BaseException as e:
            raise
        return affected


def create_args_string(n):
    result = []
    for _ in range(n):
        result.append('?')
    return ','.join(result)


class ModelMetaclass(type):
    """类名以Metaclass则表示为元类，创建元类继承自type"""

    def __new__(cls, name, bases, attrs):
        """
        :param cls: 当前准备创建的类的对象
        :param name: 类的名字
        :param bases: 类继承的父类集合
        :param attrs: 类的方法集合
        """
        if name == 'Model':  # 创建Model类时不做任何改动，依然使用type的__new__方法创建类，真正作用的地方是Model的子类
            return type.__new__(cls, name, bases, attrs)
        tableName = attrs.get('__table__', None) or name  # 从类属性中获取__table__作为表名，如果没有则将类名作为表名
        logging.info('found model: {} (table: {}'.format(name, tableName))
        mappings = dict()  # 通过dict()创建字典mappings
        fields = []
        primaryKey = None
        for k, v in attrs.items():  # 这里的k就是字段名，v就是对应的数据例如{"id":1,"name":"xiaoming"}
            if isinstance(v, Field):  # 如果字段实例属于定义好的Field，则保存到mapping
                logging.info(' found mapping:{} ==> {}'.format(k, v))
                mappings[k] = v
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for fields: {}'.format(k))
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():  # 由于前面已经attrs中属于Field的属性的转移到了attrs.__mappings__中，所以这里移除attrs中这些属性
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`{}`'.format(f),
                                  fields))  # fields = {'a':1,"b":2,'c':3},则escaped_fields=['`a`', '`b`', '`c`']
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields
        # 构造增删改查sql语句
        attrs['__select__'] = 'select {}, {} from {}'.format(primaryKey, ','.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `{}` ({}, {}) values ({})'.format(tableName, ','.join(escaped_fields),
                                                                             primaryKey, create_args_string(
                len(escaped_fields) + 1))
        attrs['__update__'] = 'update `{}` set {} where `{}`=?'.format(tableName, ','.join
        (map(lambda f: '`{}`=?'.format(mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `{}` where `{}`=?'.format(tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)  # 创建类，此时的attrs已经有了很大的改动


class Model(dict, metaclass=ModelMetaclass):
    """
    继承自dict类，可以使用dict有的方法
    metaclass=ModelMetaclass表明创建Model的子类时，要通过ModelMetaclass类的__new__方法来创建
    """

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        # 获取属性
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '{}'".format(key))

    def __setattr__(self, key, value):
        # 设置属性
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)  # getattr方法获取对象的key属性，不存在则返回None

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:  # 如果value为空，则从attrs.__mappings__中通过key取值
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default  # callable检查对象是否可调用
                logging.debug('string default value for {}: {}'.format(key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def find(cls, pk):
        'find object by primary key.'
        rs = await select('{} where `{}`=?'.format(cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record; affected rows: %s'.format(rows))


class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):  # __class__指向该实例对应的类，__class__.__name__获取该实例对应的类的名字
        return '<{}, {}: {}>'.format(self.__class__.__name__, self.column_type, self.name)


class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class BooleanField(Field):

    def __init__(self, name=None, primary_key=False, default=False):
        super().__init__(name, 'boolean', primary_key, default)


class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.00):
        super().__init__(name, 'float', primary_key, default)


class TextField(Field):

    def __init__(self, name=None, primary_key=False, default=''):
        super().__init__(name, 'text', primary_key, default)
