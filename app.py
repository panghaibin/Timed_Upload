import yaml
import sqlite3
from datetime import timedelta
from contextlib import closing
from flask import Flask, render_template, request, session, redirect, url_for, g

app = Flask(__name__)

with open('config.yml', 'r', encoding='utf-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
app.secret_key = config['SECRET_KEY']
DATABASE = config['DATABASE']
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


@app.route('/antigen')
def antigen():
    if 'username' not in session:
        return redirect(url_for('login'))
    return 'antigen'


@app.route('/history')
def history():
    if 'username' not in session:
        return redirect(url_for('login'))
    return 'history'


if __name__ == '__main__':
    app.run(debug=True)
