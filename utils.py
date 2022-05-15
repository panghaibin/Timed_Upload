import logging
import os
import re
import rsa
import json
import time
import math
import random
import base64
import requests
import datetime
import traceback
from PIL import Image, ImageOps, ImageEnhance
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


def compress_img(img_path, transform=False):
    cur_img = Image.open(img_path)
    cur_img = ImageOps.exif_transpose(cur_img)

    if transform:
        raw_width, raw_height = cur_img.size
        angle = random.randint(1, 6)
        cur_img = cur_img.rotate(angle, expand=True)
        new_width, new_height = cur_img.size
        blank_width = int(math.tan(math.radians(angle)) * raw_height + 10)
        blank_height = int(math.tan(math.radians(angle)) * raw_width + 10)
        left = blank_width
        top = blank_height
        right = new_width - blank_width
        bottom = new_height - blank_height
        cur_img = cur_img.crop((left, top, right, bottom))

        width, height = cur_img.size
        crop_width = width * 0.96
        crop_height = height * 0.96
        left = random.randint(0, int(width - crop_width))
        top = random.randint(0, int(height - crop_height))
        right = left + crop_width
        bottom = top + crop_height
        cur_img = cur_img.crop((left, top, right, bottom))

        bri_enhancer = ImageEnhance.Brightness(cur_img)
        cur_img = bri_enhancer.enhance(random.randint(8, 12) / 10)
        col_enhancer = ImageEnhance.Color(cur_img)
        cur_img = col_enhancer.enhance(random.randint(9, 11) / 10)

    cps_time = get_time().strftime('%M%S%f')
    new_img_path = img_path.replace('.jpg', f'_{cps_time}_compress.jpg')
    target_size = 3 * 1024 * 1024
    quality = 90
    step = 5

    cur_img.save(new_img_path)
    cur_img_size = os.path.getsize(new_img_path)
    while cur_img_size > target_size and quality > 10:
        cur_img.save(new_img_path, quality=quality, optimize=True)
        cur_img = Image.open(new_img_path)
        cur_img_size = os.path.getsize(new_img_path)
        quality -= step

    return new_img_path


class AgUpload:
    def __init__(self, username, password, name, test_type, test_method, test_times, test_result, img_path, img_name):
        self.username = username
        self.password = password
        self.name = name
        self.session = None
        self._login()
        self.id_num = username

        self.img_path = img_path
        self.img_name = img_name
        self.img_cps_path = None
        self.img = None

        self.view_state = None
        self.view_state_generator = None
        self.t = get_time()
        self.t -= datetime.timedelta(minutes=2)
        self.test_times = test_times
        self.test_type = test_type
        self.test_method = test_method
        self.test_result = test_result
        self.test_check = None
        self.report_form = None
        self.file_form = None

    def _login(self):
        self.session = login(self.username, self.password)

    def _read_notice(self, notice_url):
        notice_html = self.session.get(url=notice_url).text
        notice_event_target = re.search(r'Submit\',name:\'(.*?)\',disabled:true', notice_html).group(1)
        notice_form = {
            '__EVENTTARGET': notice_event_target,
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': self.view_state,
            '__VIEWSTATEGENERATOR': self.view_state_generator,
            'F_TARGET': 'p1_ctl01_btnSubmit',
            'p1_ctl00_Collapsed': 'false',
            'p1_Collapsed': 'false',
            'F_STATE': 'eyJwMV9jdGwwMCI6eyJJRnJhbWVBdHRyaWJ1dGVzIjp7fX0sInAxIjp7IklGcmFtZUF0dHJpYnV0ZXMiOnt9fX0=',
        }
        notice_result = self.session.post(url=notice_url, data=notice_form)
        if 'HeSJCSelfUploads.aspx' in notice_result.url:
            return True
        else:
            return False

    def _get_report_form(self):
        ag_url = 'https://selfreport.shu.edu.cn/HSJC/HeSJCSelfUploads.aspx'
        ag_html = self.session.get(url=ag_url).text

        report_even_target = 'p1$P_Upload$btnUploadImage'
        self.view_state = re.search(r'id="__VIEWSTATE" value="(.*?)" /', ag_html).group(1)
        self.view_state_generator = re.search(r'id="__VIEWSTATEGENERATOR" value="(.*?)" /', ag_html).group(1)
        t = self.t
        test_date = t.strftime('%Y-%m-%d %H:%M')
        self.test_check = f'当天第{self.test_times}次({t.year}/{t.month}/{t.day}'

        ag_b64str = 'eyJwMV9Hb25nSGFvIjogeyJUZXh0IjogIiJ9LCAicDFfWGluZ01pbmciOiB7IlRleHQiOiAiIn0sICJwMV9QX1VwbG9hZF9DaGVuZ051byI6IHsiQ2hlY2tlZCI6IHRydWV9LCAicDFfUF9VcGxvYWRfY3RsMDAiOiB7IklGcmFtZUF0dHJpYnV0ZXMiOiB7fX0sICJwMV9QX1VwbG9hZF9TaGVuVFpLIjogeyJGX0l0ZW1zIjogW1si5ZCmIiwgIjxzcGFuIHN0eWxlPSdjb2xvcjpncmVlbic+5peg5Lul5LiK55eH54q2KE5vKTwvc3Bhbj4iLCAxXSwgWyLmmK8iLCAiPHNwYW4gc3R5bGU9J2NvbG9yOnJlZCc+5pyJ5Lul5LiK55eH54q25LmL5LiAKFllcyk8L3NwYW4+IiwgMV1dLCAiU2VsZWN0ZWRWYWx1ZSI6ICLlkKYifSwgInAxX1BfVXBsb2FkX0ppYW5DTFgiOiB7IkZfSXRlbXMiOiBbWyLmipfljp8iLCAiPHNwYW4gc3R5bGU9J2ZvbnQtd2VpZ2h0OmJvbGRlcjsnPuaKl+WOnyhBbnRpZ2VuIFRlc3QpPC9zcGFuPiIsIDFdLCBbIuaguOmFuCIsICLmoLjphbgoTnVjbGVpYyBBY2lkIFRlc3QpIiwgMV1dLCAiU2VsZWN0ZWRWYWx1ZSI6ICLmipfljp8ifSwgInAxX1BfVXBsb2FkX0NhaVlGUyI6IHsiRl9JdGVtcyI6IFtbIum8u+iFlOaLreWtkCIsICLpvLvohZTmi63lrZAoTm9zZSkiLCAxXSwgWyLpvLvlkr3mi63lrZAiLCAi6by75ZK95out5a2QKE5vc2UrVGhyb2F0KSIsIDFdLCBbIuWPo+iFlOaLreWtkCIsICLlj6PohZTmi63lrZAoVGhyb2F0KSIsIDFdXSwgIlNlbGVjdGVkVmFsdWUiOiAi6by76IWU5out5a2QIn0sICJwMV9QX1VwbG9hZF9IZVNKQ1JRIjogeyJUZXh0IjogIiJ9LCAicDFfUF9VcGxvYWRfQ2lTaHUiOiB7IkZfSXRlbXMiOiBbWyIxIiwgIuesrDHmrKEoRmlyc3QpIiwgMV0sIFsiMiIsICLnrKwy5qyhKFNlY29uZCkiLCAxXSwgWyIzIiwgIuesrDPmrKEoVGhpcmQpIiwgMV1dLCAiU2VsZWN0ZWRWYWx1ZSI6ICIxIn0sICJwMV9QX1VwbG9hZF9KaWFuQ0pHIjogeyJGX0l0ZW1zIjogW1si6Zi05oCnIiwgIjxzcGFuIHN0eWxlPSdjb2xvcjpncmVlbic+6Zi05oCnKE5lZ2F0aXZlKTwvc3Bhbj4iLCAxXSwgWyLpmLPmgKciLCAiPHNwYW4gc3R5bGU9J2NvbG9yOnJlZCc+6Ziz5oCnKFBvc2l0aXZlKTwvc3Bhbj4iLCAxXSwgWyLml6DmlYgiLCAi5peg5pWIKEludmFsaWQpIiwgMV0sIFsi5pqC5peg57uT5p6cIiwgIuaaguaXoOe7k+aenChObyBSZXN1bHQpIiwgMV1dLCAiU2VsZWN0ZWRWYWx1ZSI6ICLpmLTmgKcifSwgInAxX1BfVXBsb2FkIjogeyJJRnJhbWVBdHRyaWJ1dGVzIjoge319LCAicDFfR3JpZERhdGEiOiB7IlJlY29yZENvdW50IjogMCwgIkZfUm93cyI6IFtdLCAiSUZyYW1lQXR0cmlidXRlcyI6IHt9fSwgInAxIjogeyJJRnJhbWVBdHRyaWJ1dGVzIjoge319LCAiV19TaG93UGljIjogeyJJRnJhbWVBdHRyaWJ1dGVzIjoge319fQ=='
        ag_json = json.loads(base64.b64decode(ag_b64str).decode('utf-8'))
        ag_json['p1_GongHao']['Text'] = self.id_num
        ag_json['p1_XingMing']['Text'] = self.name
        ag_json['p1_P_Upload_HeSJCRQ']['Text'] = test_date
        ag_json['p1_P_Upload_CiShu']['SelectedValue'] = self.test_times
        ag_json['p1_P_Upload_JianCLX']['SelectedValue'] = self.test_type
        ag_json['p1_P_Upload_CaiYFS']['SelectedValue'] = self.test_method
        ag_json['p1_P_Upload_JianCJG']['SelectedValue'] = self.test_result
        fstate = base64.b64encode(json.dumps(ag_json, ensure_ascii=False).encode("utf-8")).decode("utf-8")

        self.report_form = {
            '__EVENTTARGET': report_even_target,
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': self.view_state,
            '__VIEWSTATEGENERATOR': self.view_state_generator,
            'p1$P_Upload$ChengNuo': 'p1_P_Upload_ChengNuo',
            'p1$P_Upload$ShenTZK': b'\xe5\x90\xa6'.decode(),
            'p1$P_Upload$JianCLX': self.test_type,
            'p1$P_Upload$CaiYFS': self.test_method,
            'p1$P_Upload$HeSJCRQ': test_date,
            'p1$P_Upload$CiShu': self.test_times,
            'p1$P_Upload$JianCJG': self.test_result,
            'p1_P_Upload_ctl00_Collapsed': 'false',
            'p1_P_Upload_Collapsed': 'false',
            'p1_GridData_Collapsed': 'false',
            'p1_GridData_HiddenColumns': '["p1_GridData_ctl00"]',
            'p1_Collapsed': 'false',
            'W_ShowPic_Collapsed': 'false',
            'W_ShowPic_Hidden': 'true',
            'F_STATE': fstate,
            'F_TARGET': 'p1_P_Upload_btnUploadImage',
            'X-FineUI-Ajax': 'true',
        }

    def _get_img_file(self):
        img_cps_path = compress_img(self.img_path)
        self.img = open(img_cps_path, 'rb')
        self.file_form = {
            'p1$P_Upload$FileHeSJCBG': (self.img_name, self.img, 'image/jpeg', {'Content-Type': 'image/jpeg'}),
        }
        self.img_cps_path = img_cps_path

    def upload(self):
        now = self.t.strftime('%Y-%m-%d %H:%M:%S')
        if not self.session:
            title = f'{self.id_num}登录失败'
            logging.error(title)
            return 'fail', f'{now}\n\n{title}'

        self._get_report_form()
        self._get_img_file()
        title = f'{self.id_num}的第{self.test_times}次结果'
        ag_upload = 'https://selfreport.shu.edu.cn/HSJC/HeSJCSelfUploads.aspx'
        ag_html = self.session.get(ag_upload).text
        if self.test_check in ag_html:
            title += '已上传过'
            logging.info(title)
            return 'uploaded', f'{now}\n\n{title}'

        upload_times = 0
        result_list = []
        while True:
            time.sleep(5)
            result = self.session.post(url=ag_upload, data=self.report_form, files=self.file_form).text
            upload_times += 1
            if '上传成功' in result or self.test_check in result or '更新失败' in result or upload_times >= 3:
                break
            elif '.aspx' in result.split('&#39;')[1]:
                notice_url = 'https://selfreport.shu.edu.cn' + result.split('&#39;')[1]
                self._read_notice(notice_url)
            logging.info(result)
            result_split = result.split('F.alert')
            if len(result_split) > 1:
                result_split = result_split[-1].split('&#39;')[1]
                result_list.append(result_split)
            self._get_report_form()
            self.img.close()
            os.remove(self.img_cps_path)
            self._get_img_file()

        self.img.close()

        if '上传成功' in result or self.test_check in result:
            title += '上传成功'
            return_ = 'success', f'{now}\n\n{title}'
        elif '更新失败' in result:
            title += '已上传过'
            return_ = 'uploaded', f'{now}\n\n{title}'
        else:
            title += '上传失败'
            logging.info(result)
            result = result.split('F.alert')
            if len(result) > 1:
                result = result[-1].split('&#39;')[1]
                result_list.append(result)
            result_str = '\n\n'.join(result_list)
            return_ = 'fail', f'{now}\n\n{title}\n\n{result_str}'
        logging.info(title)
        os.remove(self.img_cps_path)
        return return_
