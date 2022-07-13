
# -*- coding: utf-8 -*-

__author__ = 'komorebi'


import os
import re
from datetime import datetime

from fabric.api import *

env.user = 'root'
env.sudo_user = 'root'
env.hosts = ['ec2-13-229-103-113.ap-southeast-1.compute.amazonaws.com']


_TAR_FILE = 'dist_awesome.tar.gz'


def bulid():
    includes = ['static', 'templates', '*.py']  # 需要压缩的目录和文件
    excludes = ['test.py', '.*', '*.pyc', '*.pyo']  # 不需要压缩的目录和文件
    local('rm -f dist/{}'.format(_TAR_FILE))  # local执行本地命令 删除上次的压缩文件
    with lcd(os.path.join(os.path.abspath('.'), 'www')):  # lcd用于切换本地目录进入www目录
        cmd = ['tar', '--dereference', '-czvf', '../dist/{}'.format(_TAR_FILE)]
        cmd.extend(['--exclude=\'{}\''.format(ex) for ex in excludes])
        cmd.extend(includes)
        local(' '.join(cmd))  # 运行命令


_REMOTE_TMP_TAR = '/tmp/{}'.format(_TAR_FILE)
_REMOTE_BASE_DIR = '/srv/awesome'


def deploy():
    newdir = 'www-{}'.format(datetime.now().strftime('%y-%m-%d_%H.%M.%S'))
    run('rm -f {}'.format(_REMOTE_TMP_TAR))  # run运行远程命令删除上次上传的文件
    # 上传本地文件_TAR_FILE到远程主机_REMOTE_TMP_TAR目录
    put('dist/{}'.format(_TAR_FILE), _REMOTE_TMP_TAR)
    with cd(_REMOTE_BASE_DIR):  # cd用来切换远程目录
        sudo('mkdir {}'.format(newdir))  # sudo执行远程命令新建目录
    with cd('{}/{}'.format(_REMOTE_BASE_DIR, newdir)):  # 进入newdir
        sudo('tar -xzvf {}'.format(_REMOTE_TMP_TAR))  # 解压最新的压缩包到newdir
    # 重置软连接
    with cd(_REMOTE_BASE_DIR):
        sudo('rm -f www')  # 取消软连接
        sudo('ln -s {} www'.format(newdir))  # 将www软连接到最新代码目录
        sudo('chown www-data:www-data www')  # 将www所有者设置为www-data
        # www-data是默认运行web服务的用户/组，一般在通过apt安装web服务程序时生成。搭建web服务的文件夹/文件一般要设置成www-data的。
        # 将newdir目录以及其子目录下的所有文件所有者设置为www-data
        sudo('chown -R www-data:www-data {}'.format(newdir))
    # settings 可以临时改变env参数一旦代码块运行结束则恢复原值，这里warn_only=True即使任务执行失败也只会警告而不会中止
    # 重启python服务和nginx
    with settings(warn_only=True):
        sudo('supervisorctl stop awesome')
        sudo('supervisorctl start awesome')
        sudo('/etc/init.d/nginx reload')
