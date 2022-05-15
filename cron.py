import os
import time
import sqlite3
import logging
from utils import AgUpload, get_config, abs_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
config = get_config('config.yml')
DATABASE = os.path.join(abs_path, config['DATABASE'])


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


def cron_task():
    pending = get_history(status='pending')
    for task in pending:
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
        logging.info(result)
