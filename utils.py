import os
import re
import rsa
import json
import time
import base64
import requests
import datetime
import traceback
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

abs_path = os.path.split(os.path.realpath(__file__))[0]


def get_time():
    t = datetime.datetime.utcnow()
    t += datetime.timedelta(hours=8)
    return t


def encryptPass(password):
    key_str = '''-----BEGIN PUBLIC KEY-----
    MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDl/aCgRl9f/4ON9MewoVnV58OL
    OU2ALBi2FKc5yIsfSpivKxe7A6FitJjHva3WpM7gvVOinMehp6if2UNIkbaN+plW
    f5IwqEVxsNZpeixc4GsbY9dXEk3WtRjwGSyDLySzEESH/kpJVoxO7ijRYqU+2oSR
    wTBNePOk1H+LRQokgQIDAQAB
    -----END PUBLIC KEY-----'''
    pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(key_str.encode('utf-8'))
    crypto = base64.b64encode(rsa.encrypt(password.encode('utf-8'), pub_key)).decode()
    return crypto


def login(username, password, try_once=False):
    default_url = "https://selfreport.shu.edu.cn/Default.aspx"
    form_data = {
        'username': username,
        'password': encryptPass(password),
        'login_submit': None,
    }
    login_times = 0
    while True:
        try:
            session = requests.Session()
            session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (' \
                                            'KHTML, like Gecko) Chrome/34.0.1847.131 Safari/537.36'
            session.trust_env = False
            session.keep_alive = False
            retry = Retry(connect=5, backoff_factor=60)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            sso = session.get(url=default_url)
            post_index = session.post(url=sso.url, data=form_data, allow_redirects=False)
            index = session.get(url='https://newsso.shu.edu.cn/oauth/authorize?client_id=WUHWfrntnWYHZfzQ5QvXUCVy'
                                    '&response_type=code&scope=1&redirect_uri=https%3A%2F%2Fselfreport.shu.edu.cn'
                                    '%2FLoginSSO.aspx%3FReturnUrl%3D%252fDefault.aspx&state=')
            login_times += 1
            notice_url = 'https://selfreport.shu.edu.cn/DayReportNotice.aspx'
            view_msg_url = 'https://selfreport.shu.edu.cn/ViewMessage.aspx'
            if index.url == default_url and index.status_code == 200:
                if '需要更新' in index.text:
                    cleanIndex(session, index.text, 'cancel_archive_dialog', default_url, default_url)
                return session
            elif index.url.startswith(view_msg_url):
                view_times = 0
                while view_times < 10:
                    index = session.get(url=default_url)
                    view_times += 1
                    if index.url == default_url:
                        print('已阅读%s条强制消息' % view_times)
                        return session
            elif index.url == notice_url:
                if cleanIndex(session, index.text, 'read_notice', notice_url, default_url):
                    return session
            elif 'message.login.passwordError' in post_index.text:
                if login_times > 2:
                    print('用户密码错误')
                    return False
            else:
                print('出现未知错误，历史记录调试信息：')
                print([u.url for u in index.history] + [index.url])
        except Exception as e:
            print(e)
            traceback.print_exc()

        del session

        if try_once:
            return False
        if login_times > 10:
            print('尝试登录次数过多')
            return False
        time.sleep(60)


def cleanIndex(session, html, target, target_url, index_url):
    view_state = re.search(r'id="__VIEWSTATE" value="(.*?)" /', html).group(1)
    view_state_generator = re.search(r'id="__VIEWSTATEGENERATOR" value="(.*?)" /', html).group(1)
    form_data = {
        '__VIEWSTATE': view_state,
        '__VIEWSTATEGENERATOR': view_state_generator,
    }
    if target == 'read_notice':
        form_data.update({
            '__EVENTTARGET': 'p1$ctl01$btnSubmit',
            '__EVENTARGUMENT': '',
            'F_TARGET': 'p1_ctl01_btnSubmit',
            'p1_ctl00_Collapsed': 'false',
            'p1_Collapsed': 'false',
            'F_STATE': 'eyJwMV9jdGwwMCI6eyJJRnJhbWVBdHRyaWJ1dGVzIjp7fX0sInAxIjp7IklGcmFtZUF0dHJpYnV0ZXMiOnt9fX0=',
        })
    elif target == 'cancel_archive_dialog':
        form_data.update({
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': 'EArchiveCancel',
            'frmConfirm_ContentPanel1_Collapsed': 'false',
            'frmConfirm_Collapsed': 'false',
            'frmConfirm_Hidden': 'true',
            'F_STATE': 'eyJmcm1Db25maXJtX0NvbnRlbnRQYW5lbDEiOnsiSUZyYW1lQXR0cmlidXRlF_STATEcyI6e319LCJmcm1Db25maXJtIjp'
                       '7IklGcmFtZUF0dHJpYnV0ZXMiOnt9fX0=',
        })
    else:
        return False
    index = session.post(url=target_url, data=form_data)
    if index.url == index_url:
        return True


def html2JsLine(html):
    js = re.search(r'F\.load.*]>', html).group(0)
    split = js.split(';var ')
    return split


def jsLine2Json(js):
    return json.loads(js[js.find('=') + 1:])
