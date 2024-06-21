import os
import datetime
import json
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from st_pages import Page, show_pages, hide_pages
import logging
import socket


def config():
    st.set_page_config('SPTL专利速读加速器-上海专利商标事务所有限公司', 'SPTL_icon.png', "wide")
    # 隐藏右边的菜单以及页脚
    hide_streamlit_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)
    corner = st.columns([5, 1])[1]
    corner.image('SPTL_logo.png')


def auxiliary(number):
    colour = 'green'
    if number >= 90:
        colour = 'red'
    elif number >= 80:
        colour = 'orange'
    return f'今日已调用 **:{colour}[{number}%]**，剩余 **:{colour}[{100 - number}%]**。'


def limit(sidebar=True):
    today = datetime.date.today().strftime('%Y-%m-%d')
    with open('noOfAccesses.json') as f:
        access_num = json.load(f)
    if access_num[0] != today:
        access_num = [today, 0]
        with open('noOfAccesses.json', 'w') as f:
            json.dump(access_num, f)
    number = access_num[1]
    if sidebar:
        return st.sidebar.progress(number, auxiliary(number))
    return st.progress(number, auxiliary(number))


if __name__ == "__main__":
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    logging.basicConfig(filename='record.log', format=f'%(asctime)s - {ip} - %(levelname)s: %(message)s',
                        level=logging.INFO)

    for path in ("inputs", "data", "trees", "mind_maps", "statistics"):  # 创建文件夹
        if not os.path.exists(path):
            os.mkdir(path)
    config()
    show_pages(
        [
            Page("mainPage.py", "首页", "🏠"),
            Page("fileUploader.py", "上传文件", "📤"),
            Page("history.py", "历史记录", "🕒"),
            Page("cost.py", "费用统计", "📊")
        ]
    )

    if 'state' not in st.session_state:
        st.session_state['state'] = 'login'

    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        config['preauthorized']
    )

    if st.session_state['state'] == 'main':
        st.title("🚀SPTL专利速读加速器")
        st.write(f"欢迎 *{st.session_state['name']}*")
        limit(False)
        if st.button("退出登录"):
            authenticator.cookie_manager.delete(authenticator.cookie_name)
            st.session_state['logout'] = True
            logging.info(f"{st.session_state['name']} 已退出登录")
            st.session_state['name'] = None
            st.session_state['username'] = None
            st.session_state['authentication_status'] = None
            st.session_state['state'] = 'login'
            st.experimental_rerun()

    else:
        hide_pages(["首页", "上传文件", "历史记录", "费用统计"])
        if st.session_state['state'] == 'login':
            with st.columns([1, 2, 1])[1]:
                authenticator.login('登录', 'main')
                if st.session_state['authentication_status']:
                    st.session_state['state'] = 'main'
                    logging.info(f"{st.session_state['name']} 已登录")
                    st.experimental_rerun()
                elif st.session_state['authentication_status'] is False:
                    st.error('账号或密码错误')
                if st.button("注册新用户"):
                    st.session_state['state'] = 'register'
                    st.experimental_rerun()
        elif st.session_state['state'] == 'register':
            try:
                if st.button("返回"):
                    st.session_state['state'] = 'login'
                    st.experimental_rerun()
                with st.columns([1, 2, 1])[1]:
                    if authenticator.register_user('注册新用户', preauthorization=False):
                        with open('config.yaml', 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success('用户注册成功')
            except Exception as e:
                st.error(e)