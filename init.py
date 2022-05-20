import os
import yaml
import sqlite3


with sqlite3.connect('database.db') as db:
    with open('schema.sql', 'r') as f:
        db.cursor().executescript(f.read())
    # 测试
    db.cursor().execute('INSERT INTO users (username, password, name, role_id) VALUES (?, ?, ?, ?)',
                        ('admin', 'admin', '管理员', 1))
    db.commit()

key = os.urandom(24)
random_img_folder = 'uploads/ag_img'
database = 'database.db'
upload_folder = 'uploads'
app_config = {'SECRET_KEY': key, 'UPLOAD_FOLDER': upload_folder, 'RANDOM_IMG_FOLDER': random_img_folder,
              'DATABASE': database}
with open('config.yml', 'w') as f:
    yaml.dump(app_config, f)
