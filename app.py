import os
import time
import random
import shutil
import sqlite3
import logging
from datetime import datetime
from datetime import timedelta
from contextlib import closing
from flask_apscheduler import APScheduler
from utils import abs_path, get_time, get_config, status_map, img_proc, get_img_str, get_random_img
from flask import send_from_directory, render_template, make_response, redirect, url_for, Flask, Markup, request, g, \
    session


class Config(object):
    JOBS = [
        {
            'id': 'job1',
            'func': 'cron:job',
            'trigger': 'interval',
            'minutes': 5
        }
    ]
    SCHEDULER_API_ENABLED = True


app = Flask(__name__)
aps = APScheduler()
app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

app_config = get_config('config.yml')
DATABASE = os.path.join(abs_path, app_config['DATABASE'])
UPLOAD_FOLDER = os.path.join(abs_path, app_config['UPLOAD_FOLDER'])
RANDOM_IMG_FOLDER = os.path.join(abs_path, app_config['RANDOM_IMG_FOLDER'])
app.secret_key = app_config['SECRET_KEY']
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)


def connect_db():
    return sqlite3.connect(DATABASE)


def get_connection():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = connect_db()
    return db


def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql', 'r') as fq:
            db.cursor().executescript(fq.read())
        db.commit()


def query_db(query, args=(), one=False):
    cur = g.db.execute(query, args)
    rv = [dict((cur.description[idx][0], value)
               for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv


def modify_db(insert, args=()):
    g.db.execute(insert, args)
    g.db.commit()


@app.before_request
def before_request():
    g.db = connect_db()
    session.permanent = True


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('antigen'))


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username.strip() == '' or password.strip() == '':
            return render_template('login.html', msg='请输入用户名和密码')
        user_in_db = query_db('select password, role_id from users where username = ?', [username], one=True)
        if user_in_db is not None and password == user_in_db.get('password'):
            session['username'] = username
            if user_in_db.get('role_id') == 1:
                session['role'] = 'admin'
                return redirect(url_for('history'))
            else:
                session['role'] = 'user'
            return redirect(url_for('antigen'))
        return render_template('login.html', msg='密码错误或用户不存在，请联系管理员', username=username)
    return render_template('login.html')


@app.route('/antigen', methods=['GET'])
def antigen():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    name = query_db('select name from users where username = ?', [username], one=True).get('name')
    t = get_time()
    delta_minutes = 5 - t.minute % 5
    t += timedelta(minutes=delta_minutes)
    t += timedelta(days=1) if t.hour >= 22 else timedelta()
    return render_template(
        'antigen.html',
        username=session['username'],
        name=name,
        month_list=[i for i in range(1, 13)],
        month=t.month,
        day_list=[i for i in range(1, 32)],
        day=t.day,
        hour_list=[i for i in range(0, 24)],
        hour=7 if t.hour >= 22 or t.hour <= 5 else t.hour,
        minute_list=[i for i in range(0, 60, 5)],
        minute=t.minute,
    )


@app.route('/antigen-form', methods=['POST'])
def antigen_form():
    if 'username' not in session:
        return redirect(url_for('login'))

    type_map = {1: '抗原', 2: '核酸'}
    method_map = {1: '鼻腔拭子', 2: '鼻咽拭子', 3: '口腔拭子'}
    test_times_map = {1: '1', 2: '2'}
    result_map = {1: '阴性', 2: '阳性'}
    suffix_list = ['jpg', 'jpeg', 'png', 'gif', 'bmp']

    username = session['username']
    type_ = type_map.get(int(request.form.get('type', 0)))
    method = method_map.get(int(request.form.get('method', 0)))
    times = test_times_map.get(int(request.form.get('test_times', 0)))
    result = result_map.get(int(request.form.get('result', 0)))
    month = request.form.get('month')
    day = request.form.get('day')
    hour = request.form.get('hour')
    minute = request.form.get('minute')

    random_img = request.form.get('random_img') == '1'
    img_ = request.files.get('image')
    rimg_name = img_.filename
    suffix = rimg_name.split('.')[-1]

    try:
        test_date_time = datetime.strptime(f'2022-{month}-{day} {hour}:{minute}', '%Y-%m-%d %H:%M')
    except Exception as e:
        logging.error(e)
        return render_template(
            'antigen-form.html',
            msg=Markup(f'日期格式错误，<a href="/antigen">返回重新上传</a>')
        ), 400
    test_timestamp = time.mktime(test_date_time.timetuple())

    if ('.' not in rimg_name or suffix not in suffix_list) and not random_img:
        return render_template(
            'antigen-form.html',
            msg=Markup('图片格式错误，<a href="/antigen">返回重新上传</a>')
        ), 400
    if None in [type_, method, times, result, month, day, hour, minute]:
        return render_template(
            'antigen-form.html',
            msg=Markup('请填写完整信息，<a href="/antigen">返回重新上传</a>')
        ), 400
    test_img_path = os.path.join(UPLOAD_FOLDER, username)
    if not os.path.exists(test_img_path):
        os.mkdir(test_img_path)
    if not random_img:
        test_img_path = os.path.join(test_img_path, f'{str(int(time.time() * 1000))}.{suffix}')
        img_.save(test_img_path)
        transform_img = request.form.get('img_transform') == '1'
        watermark_img = request.form.get('img_watermark') == '1'
        cps_required = os.path.getsize(test_img_path) > 3 * 1024 * 1024
        if not transform_img and not cps_required and not watermark_img:
            test_cps_path = test_img_path
        else:
            if watermark_img:
                random_min = random.randint(1, 5)
                t = test_date_time - timedelta(minutes=random_min)
                watermark_img = f'{t.month}/{t.day} {t.hour}:{t.minute}'
            try:
                test_cps_path = img_proc(test_img_path, transform=transform_img, watermark=watermark_img)
            except Exception as e:
                logging.error(e)
                return render_template(
                    'antigen-form.html',
                    msg=Markup(f'图片处理失败，<a href="/antigen">返回重新上传</a>')
                ), 500
    else:
        test_img_path = os.path.join(test_img_path, f'{str(int(time.time() * 1000))}.jpg')
        random_img_path = get_random_img(RANDOM_IMG_FOLDER)
        shutil.copy(random_img_path, test_img_path)
        test_cps_path = img_proc(test_img_path, transform=True)
        os.remove(test_img_path)
        test_img_path = ''

    modify_db(
        'insert into history '
        '(username, schedule_time, test_type, test_method, test_times, test_result, '
        'test_img_path, test_cps_path, test_rimg_name, status)'
        'values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [username, test_timestamp, type_, method, times, result,
         test_img_path, test_cps_path, rimg_name, 'pending']
    )
    return redirect(url_for('history'))


@app.route('/history', methods=['GET', 'POST'])
def history():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    if request.method == 'GET':
        thead = ['当前状态', '计划时间', '实际完成', '处理后图像', '原图', '次数', '类型', '方式', '结果', '操作', ]
        status_color_map = {
            'pending': '#ffc107',
            'running': '#ffc107',
            'success': '#28a745',
            'fail': '#dc3545',
            'uploaded': '#007bff',
            'deleted': '#6c757d',
            'error': '#dc3545',
        }
        role = session.get('role')
        if role == 'admin':
            thead.insert(0, '学号')
            thead.insert(1, '姓名')
            user_histories = query_db(
                'select * from history order by username asc, schedule_time desc'
            )
            username_name = {
                i['username']: i['name']
                for i in query_db('select username, name from users')
            }
        else:
            user_histories = query_db(
                'select * from history where status != ? and username = ? order by schedule_time desc',
                ['deleted', username]
            )
            username_name = {}
        items = []
        for user_history in user_histories:
            status = user_history.get('status')
            h_username = user_history.get('username')
            img_path = user_history.get('test_img_path')
            cps_path = user_history.get('test_cps_path')
            img_str = Markup(get_img_str(h_username, img_path, 'a'))
            cps_str = Markup(get_img_str(h_username, cps_path, 'img'))
            update_time = user_history.get('update_time')
            if update_time is None:
                update_time = '-'
            else:
                update_time = datetime.fromtimestamp(update_time).strftime('%m-%d %H:%M')
            item = {
                'id': user_history.get('id'),
                'status_color': status_color_map.get(status),
                'status': status_map.get(status),
                'sch_time': datetime.fromtimestamp(user_history.get('schedule_time')).strftime('%m-%d %H:%M'),
                'real_time': update_time,
                'type': user_history.get('test_type'),
                'method': user_history.get('test_method'),
                'times': user_history.get('test_times'),
                'result': user_history.get('test_result'),
                'img': img_str,
                'cps': cps_str,
            }
            if role == 'admin':
                item.update({
                    'username': h_username,
                    'name': username_name.get(h_username),
                })
            items.append(item)
        return render_template('history.html', username=username, items=items, role=role, thead=thead)
    if request.method == 'POST':
        action_map = {
            'delete': 'deleted',
        }
        username = session['username']
        form_username = request.form.get('username')
        action = action_map.get(request.form.get('action'))
        delete_list = request.form.getlist('history')
        if not delete_list:
            return redirect(url_for('history'))
        if username != form_username or action is None:
            return '403 Forbidden', 403
        if session.get('role') == 'admin':
            query = 'update history set status = ? where username = ? or ('
        else:
            query = 'update history set status = ? where username = ? and ('
        query += ' or '.join(['id = ?'] * len(delete_list))
        query += ')'
        modify_db(query, [action, username] + delete_list)
        return redirect(url_for('history'))


@app.route('/img/<username>/<img_name>')
def img(username, img_name):
    if session.get('role') != 'admin' and session.get('username') != username:
        return '403 Forbidden', 403
    response = make_response(send_from_directory(os.path.join(UPLOAD_FOLDER, username), img_name))
    response.headers['Content-Type'] = 'image/jpeg'
    response.headers['Cache-Control'] = 'max-age=2592000'
    return response


@app.route('/img_show/<username>/<img_name>')
def img_show(username, img_name):
    if session.get('role') != 'admin' and session.get('username') != username:
        return '403 Forbidden', 403
    html = Markup(f'<img src="/img/{username}/{img_name}" alt="{img_name}" style="height:100%; width: auto;">')
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html'
    response.headers['Cache-Control'] = 'max-age=2592000'
    return response


if __name__ == '__main__':
    app.run()
