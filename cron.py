import os
import time
import sqlite3
import logging
from datetime import datetime
from utils import AgUpload, get_config, abs_path, send_msg, status_map, config_path, get_time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
app_config = get_config(os.path.join(abs_path, config_path))
DATABASE = os.path.join(abs_path, app_config['DATABASE'])


def get_history(id_=None, username=None, status=None):
    with sqlite3.connect(DATABASE) as db:
        if id_:
            query = "SELECT * FROM history WHERE id = ?"
            cur = db.cursor().execute(query, (id_,))
        elif username:
            query = "SELECT * FROM history WHERE username = ?"
            cur = db.cursor().execute(query, (username,))
        elif status:
            query = "SELECT * FROM history WHERE status = ?"
            cur = db.cursor().execute(query, (status,))
        else:
            return []
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
        return rv


def set_history(id_, status, update_time=None):
    with sqlite3.connect(DATABASE) as db:
        if not update_time:
            query = "UPDATE history SET status = ? WHERE id = ?"
            db.cursor().execute(query, (status, id_))
        else:
            query = "UPDATE history SET status = ?, update_time = ? WHERE id = ?"
            db.cursor().execute(query, (status, update_time, id_))
        db.commit()


def get_user_info(username):
    with sqlite3.connect(DATABASE) as db:
        query = "SELECT * FROM users WHERE username = ?"
        cur = db.cursor().execute(query, (username,))
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
        return rv[0]


def get_user_config(username, config_names):
    config = {}
    with sqlite3.connect(DATABASE) as db:
        for config_name in config_names:
            query = "SELECT * FROM config WHERE username = ? and config_name = ?"
            cur = db.cursor().execute(query, (username, config_name))
            rv = [dict((cur.description[idx][0], value)
                       for idx, value in enumerate(row)) for row in cur.fetchall()]
            if not rv:
                return None
            config[config_name] = rv[0]['config_value']
    return config


def job():
    pending = get_history(status='pending')
    running = []
    for task in pending:
        if task['schedule_time'] <= time.time():
            running.append(task)
            set_history(task['id'], 'running')
            # 暂时先只一个任务
            break
    for i, task in enumerate(running):
        username = task['username']
        type_ = task['test_type']
        method = task['test_method']
        times = task['test_times']
        result = task['test_result']
        img_path = os.path.join(abs_path, task['test_cps_path'])
        rimg_name = task['test_rimg_name']

        user_info = get_user_info(username)
        password = user_info['password']
        name = user_info['name']

        schedule_time = task['schedule_time']
        schedule_time = datetime.fromtimestamp(schedule_time)

        try:
            ag = AgUpload(username, password, name, type_, method, times, result, img_path, rimg_name, schedule_time)
            status, result = ag.upload()
        except Exception as e:
            logging.exception(e)
            now = get_time().strftime('%Y-%m-%d %H:%M:%S')
            cron = schedule_time.strftime('%Y-%m-%d %H:%M')
            status, result = 'error', f'{now}\n\n{username}运行时错误\n\n计划时间：{cron}\n\n{e}'
        set_history(task['id'], status, time.time())
        day = schedule_time.strftime('%m-%d')
        title = f'{username[-4:]} {day}第{times}次{status_map[status]}'
        user_config = get_user_config(username, ['api_type', 'api_key'])
        if not user_config:
            user_config = get_user_config('admin', ['api_type', 'api_key'])
        api_type = int(user_config['api_type'])
        api_key = user_config['api_key']
        send_result = send_msg(title, result, api_type, api_key)
        logging.info('消息发送成功') if send_result else logging.info('消息发送失败')
        if i < len(running) - 1:
            time.sleep(5 * 60)
