#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiomysql
__author__ = 'komorebi'

import logging

logging.basicConfig(level=logging.DEBUG)


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
        # sql.replace('?', '%s')将sql中的占位符?替换成%s
        await cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = await cur.fetchmany(size)  # 返回size条数的记录
        else:
            rs = await cur.fetchall()  # 返回查询结果所有记录
        await cur.close()  # 关闭游标
        logging.info('rows returned: {}'.format(len(rs)))  # 记录返回行数
        return rs  # 返回查询结果


async def execute(sql, args):
    """新增，删除，修改使用"""
    log(sql, args)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()  # 游标
            await cur.execute(sql.replace('?', '%s'), args)  # 执行sql
            affected = cur.rowcount  # 受影响行数
            await cur.close()  # 关闭游标
        except BaseException as e:
            raise
        return affected  # 返回受影响行数


def create_args_string(n):
    """生成指定长度的?数组，？作为mysql占位符"""
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
        # 从类属性中获取__table__作为表名，如果没有则将类名作为表名
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: {} (table: {}'.format(name, tableName))
        mappings = dict()  # 通过dict()创建字典mappings
        fields = []
        primaryKey = None
        for k, v in attrs.items(
        ):  # 这里的k就是字段名，v就是对应的数据例如{"id":1,"name":"xiaoming"}
            if isinstance(v, Field):  # 如果字段类型属于定义好的Field，则保存到mapping
                logging.info(' found mapping:{} ==> {}'.format(k, v))
                mappings[k] = v
                if v.primary_key:  # models.py中定义字段时会指明该字段primary_key是否为True
                    if primaryKey:  # 如果已经存在主键，则报错，一张表不能有两个主键
                        raise RuntimeError(
                            'Duplicate primary key for fields: {}'.format(k))
                    primaryKey = k  # 设置k字段为主键
                else:
                    fields.append(k)  # 非主键字段则加入到fields列表中
        if not primaryKey:  # 每张表都必须存在主键
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():  # 由于前面已经attrs中属于Field的属性的转移到了attrs.__mappings__中，所以这里移除attrs中这些属性
            attrs.pop(k)
        # fields = {'a':1,"b":2,'c':3},则escaped_fields=['`a`', '`b`',
        # '`c`'],等同于['`{}`'.format(i) for i in fields]
        escaped_fields = list(map(lambda f: '`{}`'.format(f), fields))
        attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
        attrs['__table__'] = tableName  # 保存表名
        attrs['__primary_key__'] = primaryKey  # 保存主键
        attrs['__fields__'] = fields  # 保存除主键外的其他列
        # 构造增删改查sql语句
        attrs['__select__'] = 'select {}, {} from {}'.format(
            primaryKey, ','.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `{}` ({}, {}) values ({})'.format(
            tableName, ','.join(escaped_fields), primaryKey, create_args_string(
                len(escaped_fields) + 1))
        attrs['__update__'] = 'update `{}` set {} where `{}`=?'.format(
            tableName,
            ','.join(
                map(
                    lambda f: '`{}`=?'.format(
                        mappings.get(f).name or f),
                    fields)),
            primaryKey)  # 这里的lambda等同于['`{}`=?'.format(i) for i in fields]
        attrs['__delete__'] = 'delete from `{}` where `{}`=?'.format(
            tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)  # 创建类，此时的attrs已经有了很大的改动


class Model(dict, metaclass=ModelMetaclass):
    """
    继承自dict类，可以使用dict有的方法
    metaclass=ModelMetaclass表明创建Model的子类时，要通过ModelMetaclass类的__new__方法来创建
    """

    def __init__(self, **kw):
        # 使用super()从父类中继承初始化方法
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        # 获取属性
        try:
            return self[key]
        except KeyError:
            raise AttributeError(
                r"'Model' object has no attribute '{}'".format(key))

    def __setattr__(self, key, value):
        # 设置属性
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)  # getattr方法获取对象的key属性，不存在则返回None

    def getValueOrDefault(self, key):  # 这里的key指得是字段名 如 id,email等
        """获取字段值或者默认值"""
        value = getattr(self, key, None)
        if value is None:  # 如果value为空，则尝试获取默认值
            # 这里的field指的是models中的字段类型，比如：StringField(primary_key=True,
            # default=next_id, ddl='varchar(50)')
            field = self.__mappings__[key]
            if field.default is not None:  # 如果field.default可调用就调用生成默认值，否则直接取field.default
                value = field.default() if callable(
                    field.default) else field.default  # callable检查对象是否可调用
                logging.debug(
                    'string default value for {}: {}'.format(
                        key, str(value)))
                setattr(self, key, value)  # 给key字段设置值
        return value  # 返回该字段的值

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        """
        根据where条件查询数据
        findAll('id>?', ['0'],orderBy='name desc',limit=(1,1))
        """
        sql = [cls.__select__]
        if where:  # 调用时示例: 'email=?'
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)  # 调用时示例： orderBy='name desc'
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)  # 调用时示例： limit = 1 or limit = (1,1)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: {}'.format(str(limit)))
        logging.info('SQL for findAll: {}\r\n ARGS:{}'.format(sql, args))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]  # **r表示以字典形式返回

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        """
        根据条件找出符合条件的第一条数据对应的值，不太明白这个函数在实际业务中有什么作用
        findNumber('email', 'id>?', [0])
        """
        sql = [
            'select {} as _num_ from `{}`'.format(
                selectField,
                cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        logging.info('SQL for findNumber: {}\r\n ARGS:{}'.format(sql, args))
        rs = await select(' '.join(sql), args, 1)  # 只返回满足条件的第一条数据
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod  # 该装饰器表明该方法为类方法，类不需要实例化就可以调用该方法
    async def find(cls, pk):
        """
        根据主键返回数据
        find('00165648325969327369a437c0b4951afcb743fe6f226b1000')
        """
        rs = await select('{} where `{}`=?'.format(cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        """
        保存数据入库
        u = User(
        email='test11111@test111.com',
        passwd='123456',
        name='kongniqiwa',
        image='imageurl'
        )
        u.save()
        """
        args = list(map(self.getValueOrDefault, self.__fields__)
                    )  # 获取除主键外其他列的值并保存到args列表中
        args.append(
            self.getValueOrDefault(
                self.__primary_key__))  # 获取主键的值并保存到args列表中
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning(
                'failed to insert record; affected rows: %s'.format(rows))

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        logging.info(self.__update__, args)
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning(
                'failed to update by primary key: affected rows: {}'.format(rows))

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning(
                'failed to remove by primary key: affected rows: {}'.format(rows))


class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key  # 是否是主键 True or False
        self.default = default  # 默认值

    def __str__(self):  # __class__指向该实例对应的类，__class__.__name__获取该实例对应的类的名字
        return '<{}, {}: {}>'.format(
            self.__class__.__name__,
            self.column_type,
            self.name)


class StringField(Field):

    def __init__(
            self,
            name=None,
            primary_key=False,
            default=None,
            ddl='varchar(100)'):
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
