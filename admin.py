import os
import sys
import yaml
import sqlite3
from utils import get_config, abs_path, config_path

app_config = get_config(os.path.join(abs_path, config_path))
DATABASE = os.path.join(abs_path, app_config['DATABASE'])


def generate_secret_key():
    """
    Generate secret key
    """
    return os.urandom(24)


def save_secret_key(key):
    """
    Save secret key to config.yml
    """
    app_config['SECRET_KEY'] = key
    with open(os.path.join(abs_path, config_path), 'w') as f:
        yaml.dump(app_config, f)


def migrate_img_path():
    pre_path = os.path.join(abs_path, '')
    with sqlite3.connect(DATABASE) as db:
        query = "UPDATE history SET test_img_path = REPLACE(test_img_path, ?, '') WHERE test_img_path like ?;"
        db.cursor().execute(query, (pre_path, f'{pre_path}%'))
        query = "UPDATE history SET test_cps_path = REPLACE(test_cps_path, ?, '') WHERE test_cps_path like ?;"
        db.cursor().execute(query, (pre_path, f'{pre_path}%'))
        db.commit()


def main():
    if len(sys.argv) == 1:
        print('Usage: python3 admin.py [command]')
        sys.exit(1)
    if sys.argv[1] == 'generate':
        if input('Create a new secret key? (y/n): ').lower() == 'y':
            key = generate_secret_key()
            save_secret_key(key)
            print('Secret key generated:', key)
    else:
        print('Unknown command')
        sys.exit(1)


if __name__ == '__main__':
    main()
