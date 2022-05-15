import datetime
import os

abs_path = os.path.split(os.path.realpath(__file__))[0]


def get_time():
    t = datetime.datetime.utcnow()
    t += datetime.timedelta(hours=8)
    return t
