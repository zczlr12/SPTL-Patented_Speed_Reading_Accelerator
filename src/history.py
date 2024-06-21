import os
import re
import streamlit as st
from fileUploader import setup
from mainPage import config, limit


if __name__ == "__main__":
    config()
    num = limit()
    file_name = st.sidebar.selectbox("选择专利", os.listdir("inputs"),
                                     format_func=lambda file_name: re.split(r'_|-', file_name)[0], placeholder="请选择")
    st.title("🕒历史记录")
    if file_name:
        setup(num, file_name)
    else:
        st.write("暂无数据，请上传文件")