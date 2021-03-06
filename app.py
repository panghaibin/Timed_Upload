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
from utils import abs_path, get_time, get_config, status_map, img_proc, get_img_str, get_random_img, config_path, \
    role_map, datetime_from_str, status_color_map
from flask import send_from_directory, render_template, make_response, redirect, url_for, Flask, Markup, request, g, \
    session


class Config(object):
    JOBS = [
        {
            'id': 'job1',
            'func': 'cron:pending_run',
            'trigger': 'interval',
            'seconds': 90
        },
        {
            'id': 'job2',
            'func': 'cron:notice_err_rerun',
            'trigger': 'interval',
            'minutes': 5
        },
    ]
    SCHEDULER_API_ENABLED = True


app = Flask(__name__)
aps = APScheduler()
app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

app_config = get_config(os.path.join(abs_path, config_path))
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
    if 'username' not in session and request.endpoint not in ['login', 'register']:
        return redirect(url_for('login'))

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
    session.pop('role', None)
    session.pop('users', None)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username.strip() == '' or password.strip() == '':
            return render_template('login.html', msg='???????????????????????????')
        user_in_db = query_db('select password, role_id from users where username = ?', [username], one=True)
        if user_in_db is not None and password == user_in_db.get('password'):
            session['username'] = username
            role = role_map.get(user_in_db.get('role_id'))
            session['role'] = role
            if role == 'admin':
                all_users = query_db('select username from users')
                session['users'] = [user.get('username') for user in all_users]
                return redirect(url_for('history'))
            users = session.get('users', [])
            users.append(username)
            users = list(set(users))
            session['users'] = users
            return redirect(url_for('antigen'))
        return render_template('login.html', msg='???????????????????????????????????????????????????', username=username)
    return render_template('login.html')


@app.route('/antigen', methods=['GET'])
def antigen():
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
        day=t.day,
        hour_list=[i for i in range(0, 24)],
        hour=7 if t.hour >= 22 or t.hour <= 5 else t.hour,
        minute_list=[i for i in range(0, 60, 5)],
        minute=t.minute,
    )


@app.route('/antigen-edit/<history_id>', methods=['GET'])
def antigen_edit(history_id):
    if not history_id:
        return redirect(url_for('history'))

    username = session['username']
    h_detail = query_db(
        'select * from history where username = ? and id = ? and status = ?',
        [username, history_id, 'pending'],
        one=True
    )
    if h_detail is None:
        return redirect(url_for('history'))

    type_map = {'??????': 1, '??????': 2}
    method_map = {'????????????': 1, '????????????': 2, '????????????': 3}
    test_times_map = {'1': 1, '2': 2}

    name = query_db('select name from users where username = ?', [username], one=True).get('name')
    t = datetime.fromtimestamp(h_detail.get('schedule_time'))
    return render_template(
        'antigen-edit.html',
        username=session['username'],
        name=name,
        history_id=history_id,
        month_list=[i for i in range(1, 13)],
        month=t.month,
        day=t.day,
        hour_list=[i for i in range(0, 24)],
        hour=t.hour,
        minute_list=[i for i in range(0, 60, 5)],
        minute=t.minute,
        type=type_map.get(h_detail.get('test_type')),
        method=method_map.get(h_detail.get('test_method')),
        test_times=test_times_map.get(h_detail.get('test_times')),
        img=get_img_str(username, h_detail.get('test_cps_path'), 'url'),
    )


@app.route('/antigen-form', methods=['POST'])
def antigen_form():
    action = request.form.get('action')
    if action not in ['edit', 'add']:
        return redirect(url_for('antigen'))

    type_map = {1: '??????', 2: '??????'}
    method_map = {1: '????????????', 2: '????????????', 3: '????????????'}
    test_times_map = {1: '1', 2: '2'}
    result_map = {1: '??????', 2: '??????'}
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

    try:
        test_date_time = datetime.strptime(f'2022-{month}-{day} {hour}:{minute}', '%Y-%m-%d %H:%M')
        test_timestamp = time.mktime(test_date_time.timetuple())
    except Exception as e:
        logging.error(e)
        return render_template(
            'antigen-form.html',
            msg=Markup(f'?????????????????????<a href="javascript:void(0)" onclick="javascript:history.back(-1);">??????????????????</a>')
        ), 400

    if None in [type_, method, times, result, month, day, hour, minute]:
        return render_template(
            'antigen-form.html',
            msg=Markup('????????????????????????<a href="javascript:void(0)" onclick="javascript:history.back(-1);">??????????????????</a>')
        ), 400

    if action == 'add':
        random_img = request.form.get('random_img') == '1'
        img_ = request.files.get('image')
        rimg_name = img_.filename
        suffix = rimg_name.split('.')[-1]

        if ('.' not in rimg_name or suffix not in suffix_list) and not random_img:
            return render_template(
                'antigen-form.html',
                msg=Markup('?????????????????????<a href="/antigen">??????????????????</a>')
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
                    random_min = random.randint(0, 4)
                    t = test_date_time - timedelta(minutes=random_min)
                    watermark_img = f'{t.month}/{t.day} {t.hour}:%02d' % t.minute
                try:
                    test_cps_path = img_proc(test_img_path, transform=transform_img, watermark=watermark_img)
                except Exception as e:
                    logging.error(e)
                    return render_template(
                        'antigen-form.html',
                        msg=Markup(f'?????????????????????<a href="/antigen">??????????????????</a>')
                    ), 500
        else:
            rimg_name = f'IMG_{test_date_time.strftime("%Y%m%d_%H%M%S")}.jpg'
            test_img_path = os.path.join(test_img_path, f'{str(int(time.time() * 1000))}.jpg')
            random_img_path = get_random_img(RANDOM_IMG_FOLDER)
            shutil.copy(random_img_path, test_img_path)
            random_min = random.randint(0, 4)
            t = test_date_time - timedelta(minutes=random_min)
            watermark_img = f'{t.month}/{t.day} {t.hour}:%02d' % t.minute
            test_cps_path = img_proc(test_img_path, transform=True, watermark=watermark_img)
            os.remove(test_img_path)
            test_img_path = ''

        test_img_path = test_img_path.replace(os.path.join(abs_path, ''), '')
        test_cps_path = test_cps_path.replace(os.path.join(abs_path, ''), '')
        modify_db(
            'insert into history '
            '(username, schedule_time, test_type, test_method, test_times, test_result, '
            'test_img_path, test_cps_path, test_rimg_name, status)'
            'values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [username, test_timestamp, type_, method, times, result,
             test_img_path, test_cps_path, rimg_name, 'pending']
        )
    elif action == 'edit':
        history_id = int(request.form.get('history_id'))
        modify_db(
            'update history set '
            'schedule_time = ?, test_type = ?, test_method = ?, test_times = ? where username = ? and id = ?',
            [test_timestamp, type_, method, times, username, history_id]
        )
    return redirect(url_for('history'))


@app.route('/history', methods=['GET', 'POST'])
def history():
    username = session['username']
    if request.method == 'GET':
        thead = ['????????????', '????????????', '????????????', '???????????????', '??????', '??????', '??????', '??????', '??????', '??????', ]
        filter_status = request.args.get('status')
        filter_status = filter_status if filter_status in status_map.keys() else None
        role = session.get('role')
        if role == 'admin':
            thead.insert(0, '??????')
            thead.insert(1, '??????')
            thead.insert(2, '????????????')
            thead.insert(0, 'ID')
            if not filter_status:
                query = 'select h.*, u.name from history h inner join users u on h.username = u.username' \
                        ' order by username asc, schedule_time desc'
                user_histories = query_db(query)
            else:
                query = 'select h.*, u.name from history h inner join users u on h.username = u.username' \
                        ' where status = ? order by username asc, schedule_time desc'
                user_histories = query_db(query, [filter_status])
        else:
            if not filter_status:
                query = 'select * from history where status != ? and username = ? order by schedule_time desc'
                user_histories = query_db(query, ['deleted', username])
            else:
                query = 'select * from history where status = ? and username = ? order by schedule_time desc'
                user_histories = query_db(query, [filter_status, username])
        items = []
        for i, user_history in enumerate(user_histories):
            status = user_history.get('status')
            h_username = user_history.get('username')
            img_path = user_history.get('test_img_path')
            cps_path = user_history.get('test_cps_path')
            img_str = Markup(get_img_str(h_username, img_path, 'a'))
            cps_type = 'img' if i == 0 else 'a'
            cps_str = Markup(get_img_str(h_username, cps_path, cps_type))
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
                upload_time = datetime_from_str(img_path + cps_path)
                item.update({
                    'username': h_username,
                    'name': user_history.get('name'),
                    'upload_time': upload_time,
                })
            items.append(item)

        status_types = status_map.copy()
        if role != 'admin':
            user_status = query_db(
                'select distinct status from history where username = ?', [username]
            )
            user_status = [s.get('status') for s in user_status]
            status_types = {k: v for k, v in status_types.items() if k in user_status and k != 'deleted'}
        return render_template(
            'history.html',
            username=username,
            items=items,
            role=role,
            thead=thead,
            status=filter_status,
            status_types=status_types,
        )

    if request.form.get('action') == 'edit':
        history_id = request.form.get('history_id')
        return redirect(url_for('antigen_edit', history_id=history_id))
    action_map = {
        'delete': 'deleted',
    }
    username = session['username']
    form_username = request.form.get('username')
    action = action_map.get(request.form.get('action'))
    delete_list = request.form.getlist('history_id')
    if not delete_list:
        return redirect(url_for('history'))
    if username != form_username or action is None:
        return '403 Forbidden', 403
    if session.get('role') == 'admin':
        modify_db(
            'update history set status = ? where id in (%s)' % ','.join('?' * len(delete_list)),
            [action] + delete_list
        )
    else:
        modify_db(
            'update history set status = ? where username = ? and id in (%s)' % ','.join('?' * len(delete_list)),
            [action, username] + delete_list
        )
    return redirect(url_for('history', **{'status': request.args.get('status')}))


@app.route('/account', methods=['GET', 'POST'])
def account():
    username = session['username']
    name = query_db('select name from users where username = ?;', [username], one=True)['name']
    users = session.get('users', [])
    users_name = [
        {'username': u['username'], 'name': u['name']}
        for u in query_db('select username, name from users where username in (%s);' % ','.join(['?'] * len(users)),
                          users)
    ]
    if request.method == 'GET':
        return render_template('account.html', username=username, name=name, users=users_name)

    action = request.form.get('action')
    value = request.form.get('value')
    if action == 'switch':
        if value not in users:
            return '403 Forbidden', 403
        session['username'] = value
        role_id = query_db('select role_id from users where username = ?', [value], one=True)['role_id']
        role = role_map.get(role_id)
        session['role'] = role
        return redirect(url_for('account'))
    if action == 'logout':
        users.remove(value)
        session['users'] = users
        if not users:
            session.clear()
            return redirect(url_for('login'))
        if username == value:
            session['username'] = users[0]
            role_id = query_db('select role_id from users where username = ?', [users[0]], one=True)['role_id']
            role = role_map.get(role_id)
            session['role'] = role
        return redirect(url_for('account'))


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
