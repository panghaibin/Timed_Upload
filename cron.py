import os
import time
import sqlite3
import logging
from utils import AgUpload, get_config, abs_path, send_msg, status_map

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
app_config = get_config('config.yml')
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


def set_history(id_, status):
    with sqlite3.connect(DATABASE) as db:
        query = "UPDATE history SET status = ? WHERE id = ?"
        db.cursor().execute(query, (status, id_))
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
    for i, task in enumerate(pending):
        if task['schedule_time'] > time.time():
            continue
        set_history(task['id'], 'running')
        username = task['username']
        test_type = task['test_type']
        test_method = task['test_method']
        test_times = task['test_times']
        test_result = task['test_result']
        test_img_path = task['test_img_path']
        test_rimg_name = task['test_rimg_name']

        user_info = get_user_info(username)
        password = user_info['password']
        name = user_info['name']

        ag = AgUpload(
            username, password, name, test_type, test_method, test_times, test_result, test_img_path, test_rimg_name
        )
        status, result = ag.upload()
        set_history(task['id'], status)
        title = f'Ag第{test_times}次{status_map[status]}'
        user_config = get_user_config(username, ['api_type', 'api_key'])
        if not user_config:
            user_config = get_user_config('admin', ['api_type', 'api_key'])
        api_type = int(user_config['api_type'])
        api_key = user_config['api_key']
        send_result = send_msg(title, result, api_type, api_key)
        logging.info('消息发送成功') if send_result else logging.info('消息发送失败')
        if i < len(pending) - 1:
            time.sleep(5 * 60)
