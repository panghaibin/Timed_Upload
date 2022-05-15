import os
import time
import sqlite3
from datetime import datetime
from datetime import timedelta
from contextlib import closing
from flask_apscheduler import APScheduler
from utils import abs_path, get_time, get_config, status_map
from flask import Flask, render_template, request, session, redirect, url_for, g, Markup, send_from_directory


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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username.strip() == '' or password.strip() == '':
            return render_template('login.html', msg='请输入用户名和密码')
        password_from_db = query_db('select password from users where username = ?', [username], one=True)
        if password_from_db is not None and password == password_from_db.get('password'):
            session['username'] = username
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
    t += timedelta(minutes=1)
    t += timedelta(days=1) if t.hour >= 22 else timedelta()
    form_date = t.strftime('%Y-%m-%d')
    form_time = t.strftime('07:%M') if t.hour >= 22 or t.hour <= 5 else t.strftime('%H:%M')
    return render_template(
        'antigen.html',
        username=session['username'],
        name=name,
        date=form_date,
        time=form_time
    )


@app.route('/antigen-form', methods=['POST'])
def antigen_form():
    if 'username' not in session:
        return redirect(url_for('login'))

    type_map = {1: '抗原', 2: '核酸'}
    method_map = {1: '鼻腔拭子', 2: '鼻咽拭子', 3: '口腔拭子'}
    test_times_map = {1: '1', 2: '2'}
    result_map = {1: '阴性', 2: '阳性'}

    username = session['username']
    test_type = type_map.get(int(request.form.get('type', 0)))
    test_method = method_map.get(int(request.form.get('method', 0)))
    test_times = test_times_map.get(int(request.form.get('test_times', 0)))
    test_result = result_map.get(int(request.form.get('result', 0)))
    test_date = request.form.get('date')
    test_time = request.form.get('time')
    test_img = request.files.get('image')
    if None in [test_type, test_method, test_times, test_result, test_date, test_time]:
        return render_template('antigen-form.html', msg=Markup('请填写完整信息，<a href="/antigen">点击返回</a>'))
    test_date_time = datetime.strptime(test_date + ' ' + test_time, '%Y-%m-%d %H:%M')
    test_timestamp = time.mktime(test_date_time.timetuple())
    now_timestamp = time.time()
    if (test_timestamp - now_timestamp) < 3 * 60:
        test_timestamp = time.mktime(test_date_time.timetuple())
    test_img_path = os.path.join(UPLOAD_FOLDER, username)
    if not os.path.exists(test_img_path):
        os.mkdir(test_img_path)
    test_rimg_name = test_img.filename
    _ = test_rimg_name.split('.')
    _[-2] = str(int(time.time() * 1000))
    test_img_path = os.path.join(test_img_path, '.'.join(_))
    test_img.save(test_img_path)
    modify_db(
        'insert into history '
        '(username, schedule_time, test_type, test_method, test_times, test_result, '
        'test_img_path, test_rimg_name, status)'
        'values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [username, test_timestamp, test_type, test_method, test_times, test_result,
         test_img_path, test_rimg_name, 'pending']
    )
    return render_template(
        'antigen-form.html',
        msg=Markup('''信息提交成功！<a href="/antigen">返回</a><br><br><br>
        <a href="/history">查看所有记录</a><br><br><br>
        ''')
    )


@app.route('/history', methods=['GET', 'POST'])
def history():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    if request.method == 'GET':
        user_histories = query_db(
            'select * from history where status != ? and username = ? order by schedule_time desc',
            ['deleted', username],
            one=False
        )
        items = []
        for user_history in user_histories:
            item = {
                'id': user_history.get('id'),
                'status': status_map[user_history.get('status')],
                'time': datetime.fromtimestamp(user_history.get('schedule_time')).strftime('%Y-%m-%d %H:%M'),
                'type': user_history.get('test_type'),
                'method': user_history.get('test_method'),
                'times': user_history.get('test_times'),
                'result': user_history.get('test_result'),
                'img': './img/%s/%s' % (username, user_history.get('test_img_path').replace('\\', '/').split('/')[-1]),
            }
            items.append(item)
        return render_template('history.html', username=username, items=items)
    if request.method == 'POST':
        username = session['username']
        form_username = request.form.get('username')
        if username != form_username:
            return '403 Forbidden', 403
        delete_list = request.form.getlist('history')
        query = 'update history set status = ? where username = ? and ('
        query += ' or '.join(['id = ?'] * len(delete_list))
        query += ')'
        modify_db(query, ['deleted', username] + delete_list)
        return redirect(url_for('history'))


@app.route('/img/<username>/<img_name>')
def img(username, img_name):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, username), img_name)


if __name__ == '__main__':
    app.run()
