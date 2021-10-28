import time
from json import loads as json_loads
from os import path as os_path
from sys import exit as sys_exit
from sys import argv as sys_argv
import io
from lxml import etree
from requests import session
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')


from PIL import ImageEnhance
from PIL import Image
import easyocr
import numpy

class Fudan:
    """
    建立与复旦服务器的会话，执行登录/登出操作
    """
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:76.0) Gecko/20100101 Firefox/76.0"

    # 初始化会话
    def __init__(self,
                 uid, psw,
                 url_login='https://uis.fudan.edu.cn/authserver/login',
                 url_code="https://zlapp.fudan.edu.cn/backend/default/code"):
        """
        初始化一个session，及登录信息
        :param uid: 学号
        :param psw: 密码
        :param url_login: 登录页，默认服务为空
        """
        self.session = session()
        self.session.headers['User-Agent'] = self.UA
        self.url_login = url_login
        self.url_code = url_code

        self.uid = uid
        self.psw = psw

    def _page_init(self):
        """
        检查是否能打开登录页面
        :return: 登录页page source
        """
        logging.debug("Initiating——")
        page_login = self.session.get(self.url_login)

        logging.debug("return status code " + str(page_login.status_code))

        if page_login.status_code == 200:
            logging.debug("Initiated——")
            return page_login.text
        else:
            logging.debug("Fail to open Login Page, Check your Internet connection\n")
            self.close()

    def login(self):
        """
        执行登录
        """
        page_login = self._page_init()

        logging.debug("parsing Login page——")
        html = etree.HTML(page_login, etree.HTMLParser())

        logging.debug("getting tokens")
        data = {
            "username": self.uid,
            "password": self.psw,
            "service" : "https://zlapp.fudan.edu.cn/site/ncov/fudanDaily"
        }

        # 获取登录页上的令牌
        data.update(
                zip(
                        html.xpath("/html/body/form/input/@name"),
                        html.xpath("/html/body/form/input/@value")
                )
        )

        headers = {
            "Host"      : "uis.fudan.edu.cn",
            "Origin"    : "https://uis.fudan.edu.cn",
            "Referer"   : self.url_login,
            "User-Agent": self.UA
        }

        logging.debug("Login ing——")
        post = self.session.post(
                self.url_login,
                data=data,
                headers=headers,
                allow_redirects=False)

        logging.debug("return status code %d" % post.status_code)

        if post.status_code == 302:
            logging.debug("登录成功")
        else:
            logging.debug("登录失败，请检查账号信息")
            self.close()

    def logout(self):
        """
        执行登出
        """
        exit_url = 'https://uis.fudan.edu.cn/authserver/logout?service=/authserver/login'
        expire = self.session.get(exit_url).headers.get('Set-Cookie')

        if '01-Jan-1970' in expire:
            logging.debug("登出完毕")
        else:
            logging.debug("登出异常")

    def close(self):
        """
        执行登出并关闭会话
        """
        self.logout()
        self.session.close()
        logging.debug("关闭会话")
        sys_exit()

class Zlapp(Fudan):
    last_info = ''

    def check(self):
        """
        检查
        """
        logging.debug("检测是否已提交")
        get_info = self.session.get(
                'https://zlapp.fudan.edu.cn/ncov/wap/fudan/get-info')
        last_info = get_info.json()

        logging.info("上一次提交日期为: %s " % last_info["d"]["info"]["date"])

        position = last_info["d"]["info"]['geo_api_info']
        position = json_loads(position)

        logging.info("上一次提交地址为: %s" % position['formattedAddress'])
        # logging.debug("上一次提交GPS为", position["position"])

        today = time.strftime("%Y%m%d", time.localtime())

        if last_info["d"]["info"]["date"] == today:
            logging.info("今日已提交")
            self.close()
        else:
            logging.info("未提交")
            self.last_info = last_info["d"]["info"]

    def read_captcha(self, img_byte):
        img = Image.open(io.BytesIO(img_byte)).convert('L')
        enh_bri = ImageEnhance.Brightness(img)
        new_img = enh_bri.enhance(factor=1.5)

        image = numpy.array(new_img)
        reader = easyocr.Reader(['en'])
        horizontal_list, free_list = reader.detect(image, optimal_num_chars=4)
        character = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        allow_list = list(character)
        allow_list.extend(list(character.lower()))

        result = reader.recognize(image,
                                allowlist=allow_list,
                                horizontal_list=horizontal_list[0],
                                free_list=free_list[0],
                                detail = 0)
        return result[0]


    def validate_code(self):
        img = self.session.get(self.url_code).content
        return self.read_captcha(img)

    def checkin(self):
        """
        提交
        """
        headers = {
            "Host"      : "zlapp.fudan.edu.cn",
            "Referer"   : "https://zlapp.fudan.edu.cn/site/ncov/fudanDaily?from=history",
            "DNT"       : "1",
            "TE"        : "Trailers",
            "User-Agent": self.UA
        }

        logging.debug("提交中")

        geo_api_info = json_loads(self.last_info["geo_api_info"])
        province = geo_api_info["addressComponent"].get("province", "")
        city = geo_api_info["addressComponent"].get("city", "") or province
        district = geo_api_info["addressComponent"].get("district", "")

        while True:
            code = self.validate_code()
            logging.info("验证码 {}".format(code))
            self.last_info.update(
                    {
                        "tw"      : "13",
                        "province": province,
                        "city"    : city,
                        "area"    : " ".join(set((province, city, district))),
                        # "ismoved" : 0,
                        "sfzx": "1",
                        "fxyy": "",
                        "code": code
                    }
            )
            # logging.info(self.last_info)


            save = self.session.post(
                    'https://zlapp.fudan.edu.cn/ncov/wap/fudan/save',
                    data=self.last_info,
                    headers=headers,
                    allow_redirects=False)
            # print(save.text)
            save_msg = json_loads(save.text)["m"]
            logging.info(save_msg)
            time.sleep(0.1)
            if(json_loads(save.text)["e"] != 1):
                break

def get_account():
    """
    获取账号信息
    """
    uid, psw = sys_argv[1].strip().split(' ')
    return uid, psw

if __name__ == '__main__':
    uid, psw = get_account()
    # logging.debug("ACCOUNT：" + uid + psw)
    zlapp_login = 'https://uis.fudan.edu.cn/authserver/login?' \
                  'service=https://zlapp.fudan.edu.cn/site/ncov/fudanDaily'
    code_url = "https://zlapp.fudan.edu.cn/backend/default/code"
    daily_fudan = Zlapp(uid, psw, url_login=zlapp_login, url_code=code_url)
    daily_fudan.login()

    daily_fudan.check()
    daily_fudan.checkin()
    # 再检查一遍
    daily_fudan.check()

    daily_fudan.close()
