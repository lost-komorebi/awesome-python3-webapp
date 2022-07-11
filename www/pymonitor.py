#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'komorebi'

import os
import sys
import time
import subprocess  # subprocess可以实现进程的启动和终止

from watchdog.observers import Observer  # watchdog可以监控系统目录的变化
from watchdog.events import FileSystemEventHandler


def log(s):
    print('[Monitor] {}'.format(s))


class MyFileSystemEventHander(FileSystemEventHandler):

    def __init__(self, fn):
        super(MyFileSystemEventHander, self).__init__()
        self.restart = fn

    def on_any_event(self, event):
        print('>>>>>',event)
        if event.src_path.endswith('.py'):
            log('Python source file changed: {}'.format(event.src_path))
            self.restart()


command = ['echo', 'ok']
process = None


def kill_process():
    global process
    if process:
        log('Kill process [{}]...'.format(process.pid))
        process.kill()
        process.wait()
        log('Process ended with code {}'.format(process.returncode))
        process = None


def start_process():
    global process, command
    log('Start process {}...'.format(' '.join(command)))
    process = subprocess.Popen(
        command,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr)


def restart_process():
    kill_process()
    start_process()


def start_watch(path, callback):
    observer = Observer()
    observer.schedule(
        MyFileSystemEventHander(
            restart_process),
        path,
        recursive=True)
    observer.start()
    log('Watching directory {}...'.format(path))
    start_process()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == '__main__':
    argv = sys.argv[1:]
    if not argv:
        print('Usage: ./pymonitor your-script.py')
        exit(0)
    if argv[0] != 'python3':
        argv.insert(0, 'python3')
    command = argv
    path = os.path.abspath('.') # 获取当前目录的绝对路径
    start_watch(path, None)
