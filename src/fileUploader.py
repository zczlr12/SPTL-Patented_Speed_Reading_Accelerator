import os
import re
import json
import datetime
import math
import fitz
import pandas as pd
import streamlit as st
import socket
import logging
import base64
import requests
import openai
import tiktoken
from pyecharts.charts import Tree
from pyecharts import options as opts
from streamlit_echarts import st_pyecharts
from PIL import Image
import platform
import pytesseract
from mainPage import config, auxiliary, limit
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)  # for exponential backoff

hostname = socket.gethostname()
ip = socket.gethostbyname(hostname)
logging.basicConfig(filename='record.log', format=f'%(asctime)s - {ip} - %(levelname)s: %(message)s',
                    level=logging.INFO)

openai.api_key = "fa836280571c4c5ba3130e9ff80b44fd"    # Azure 的密钥
openai.api_base = "https://myopenairesource-test001.openai.azure.com/"  # Azure 的终结点
openai.api_type = "azure"
openai.api_version = "2023-06-01-preview"  # API 版本，未来可能会变
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

subtitles = ('摘要', '权利要求', '所属领域', '背景技术', '目的', '技术方案', '有益技术效果')
ch_en = (('摘要', 'ABSTRACT'), ('所属领域', 'FIELD'), ('背景技术', 'BACKGROUND'), ('技术方案', 'SUMMARY'))


# 在树中添加文本
def add_item(children_list, name):
    children_list.append({"name": name, "children": [{}]})


def split_paragraph(content):
    paragraphs = re.split(r'[\[【]\d{4}[]】］]', content)  # 以”[00xx]”分段
    if len(paragraphs) <= 1:
        paragraphs = re.split(r'\s+\n|\n\s+', content)
    if len(paragraphs) <= 1:
        paragraphs = content.split('\n')
    return [re.sub(r'\s*\n\s*', '', paragraph) for paragraph in paragraphs if len(paragraph) > 3]


# 以substring作为段落开头分段
def split_claims(substring, content):
    indexes = []  # 段落首个字符在content中的索引值
    res = []
    f = re.finditer(substring, content, re.DOTALL)
    for i in f:
        indexes.append(i.span()[0])
    if not indexes:
        return content
    for i in range(len(indexes)):
        if indexes[i] != indexes[-1]:
            res.append(content[indexes[i]:indexes[i+1]])
        else:
            res.append(content[indexes[-1]:])
    return res


# 自动换行
def line_wrap(text, width=29):
    wrapped_text = ""
    char_num = len(text)
    row_num = math.ceil(char_num / width)
    if char_num <= width:
        return text
    for i in range(row_num):
        start = i * width
        end = start + width
        if i != row_num - 1:
            wrapped_text += text[start:end] + '\n'
        else:
            wrapped_text += text[start:]
    return wrapped_text


def search_content(pattern, content):
    try:
        content = re.search(pattern, content, re.DOTALL).group(1)
        return re.sub(r'[\[【]\d{4}[]］】]', '\n', content)
    except (TypeError, AttributeError):
        return ""


# 翻译函数，word 需要翻译的内容
def translate(text):
    # 有道词典 api
    url = 'http://fanyi.youdao.com/translate?smartresult=dict&smartresult=rule&smartresult=ugc&sessionFrom=null'
    # 传输的参数，其中 i 为需要翻译的内容
    key = {
        'type': "AUTO",
        'i': text,
        "doctype": "json",
        "version": "2.1",
        "keyfrom": "fanyi.web",
        "ue": "UTF-8",
        "action": "FY_BY_CLICKBUTTON",
        "typoResult": "true"
    }
    # key 这个字典为发送给有道词典服务器的内容
    response = requests.post(url, data=key)
    # 判断服务器是否相应成功
    if response.status_code == 200:
        out = ''
        in_outs = json.loads(response.text)['translateResult'][0]
        for in_out in in_outs:
            if in_out['tgt']:
                out += in_out['tgt']
            else:
                return "翻译结果为空"
        return out
    return "有道词典调用失败"


# 把文本改成该写入叶子节点的格式
@retry(  # 防止因连接问题报错
    retry=retry_if_exception_type((openai.error.APIConnectionError, openai.error.ServiceUnavailableError,
                                   openai.error.Timeout, openai.error.APIError)),
    wait=wait_random_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(10)
)
def paragraphing(num, content, if_translate, summarize=False, lang='中国', df=None, title=None, index=""):
    prompt = "将以下段落概括到50字以内："
    if lang != '中国':
        prompt = "Summarize the following paragraph(s) in 50 words:"
    content = re.sub(r"\s*\n\s*", "", content)  # 去除换行符
    if content:
        if summarize:
            with open('noOfAccesses.json') as f:
                access_num = json.load(f)
            if access_num[1] < 100:
                today = datetime.date.today().strftime('%Y-%m-%d')
                original = content
                completion = openai.ChatCompletion.create(  # gpt-35-turbo
                    engine="Test001ToCheckIfSuccess",
                    messages=[{"role": "system", "content": prompt + '\n' + content}]
                )
                content = completion['choices'][0]["message"]["content"]
                df.loc[title + index] = [len(encoding.encode(original)), len(encoding.encode(content))]
                if access_num[0] != today:
                    access_num = [today, 0]
                access_num[1] += 1
                num.progress(access_num[1], auxiliary(access_num[1]))
                with open('noOfAccesses.json', 'w') as f:
                    json.dump(access_num, f)
            else:
                content = "调用次数已达到上限"
        if if_translate and not re.search(r'[\u4e00-\u9fa5]', content):
            content = translate(content)
    else:
        content = "暂未获取"
    if index:
        content = index + "、" + content
    return line_wrap(content), df  # 返回自动换行之后的内容


def display_label(path, content):
    if os.path.exists(path):
        return "🔁重新" + content
    return "确认" + content


def ocr_reader(page, page_index, option):
    ocr_ports = {'通道二': (8000, 'PaddleOCR'), '通道三': (8010, 'EasyOCR')}
    rotate = int(0)
    # 每个尺寸的缩放系数为1.3，这将为我们生成分辨率提高2.6的图像。
    # 此处若是不做设置，默认图片大小为：792X612, dpi=96
    zoom_x = 4  # (新型颅内支架Enterprise_省略_弹簧圈栓塞治疗颅内微小宽颈动脉瘤_黄海东.33333333-->1056x816)   (2-->1584x1224)
    zoom_y = 4
    mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix._writeIMG("page.png", 1)
    with Image.open("page.png") as im:
        if page_index == 0:
            im = im.crop((100, 1000, 1260, 3200))
            im.save("page.png")
        if option == '通道一':
            return pytesseract.image_to_string(im, 'chi_sim')
    with open("page.png", 'rb') as f:
        data = f.read()
    data = base64.b64encode(data).decode('ascii')
    try:
        return json.loads(requests.post(f"http://127.0.0.1:{ocr_ports[option][0]}/{ocr_ports[option][1]}/",
                                        json={"data": data}).content)
    except Exception as e:
        st.error(e)


def identification(file_name):
    with fitz.open("./inputs/" + file_name) as doc:
        return not doc[0].get_text("text")


def preprocess(texts):
    text = '\n'.join(texts).strip()
    if re.search(r'[\[{]\d{4}]', text):
        text.replace('\n', '')
        return re.sub(r'[\[{]\d{4}]', '\n', text.replace('\n', '')).strip()
    return text


def extract_paragraphs(file_name, data_file, ocr_option):
    data = {'名称': '', '摘要': '', '权利要求': [], '所属领域': '', '背景技术': '', '目的': [], '技术方案': [], '有益技术效果': []}
    bar = None
    if ocr_option:
        bar = st.progress(0.0, f'正在初始化OCR')
    with fitz.open("./inputs/" + file_name) as doc:
        claims = ""
        instr = ""
        total = doc.page_count
        for i in range(total):
            page = doc[i]
            text = page.get_text("text", sort=True)  # 按顺序提取文字
            if ocr_option:
                bar.progress(i / total, f'正在读取第{i + 1}/{total}页……')
                text = ocr_reader(page, i, ocr_option)
            if i == 0:
                try:
                    data['名称'] = re.compile(r"名称(.+)\S{4}\s*摘要", re.DOTALL).search(text).group(1)  # 根节点
                except (TypeError, AttributeError):
                    data['名称'] = re.split(r'-|_', file_name, 1)[-1]
                data['摘要'] = search_content(r"摘要(.+。)", text)
            elif re.search(r'权\s*利\s+要\s*求\s*书', text, re.DOTALL):  # 权利要求书
                try:
                    claims += re.search(r'页(.+[^\d\s])', text, re.DOTALL).group(1)
                except (TypeError, AttributeError):
                    claims += text
            else:  # 说明书
                try:
                    instr += re.search(r'页(.+[^\d\s])', text, re.DOTALL).group(1)
                except (TypeError, AttributeError):
                    instr += text
    if ocr_option:
        bar.progress(1.0, '读取完成')

    purpose = ""
    method = ""
    rest = []
    methods = []
    benefits = []
    is_benefits = False
    is_purpose = False
    start = False
    # 权利要求书
    data['权利要求'] = split_claims(r'\n.{2,5}一\s*种', claims)  # 每段开头为"1. 一种"
    data['所属领域'] = search_content(r'技术领域(.+)背景技术', instr)
    background = search_content(r'背景技术(.+)发明内容', instr)
    data['背景技术'] = background
    # 专利内容
    try:
        if "附图说明" in instr:
            content = re.compile(r'发明内容(.+)附图说明', re.DOTALL).search(instr).group(1)
        else:
            content = re.compile(r'发明内容(.+)具体实施方式', re.DOTALL).search(instr).group(1)
    except (TypeError, AttributeError):
        content = ""
    paragraphs = split_paragraph(content)
    para_num = len(paragraphs)
    for i in range(para_num):
        if i == 0 and len(paragraphs[i]) <= 200:  # 专利内容第一段
            purpose += paragraphs[i]
            if re.search(r'要解决的问题.?$', re.sub(r'\s', '', paragraphs[i])):
                is_purpose = True
        elif i == para_num - 1:  # 专利内容最后一段
            if "下面" not in paragraphs[i]:
                benefits.append(paragraphs[-1])
        else:
            if re.search(r'解决问题的方法.?$', re.sub(r'\s', '', paragraphs[i])):
                is_purpose = False
            if is_purpose:
                purpose += paragraphs[i]
            elif is_benefits:
                benefits.append(paragraphs[i])
            elif re.search(r'有益效果|优点', re.sub(r'\s', '', paragraphs[i])):  # 有益技术效果起始段
                is_benefits = True
                if len(paragraphs[i]) > 30:
                    benefits.append(paragraphs[i])
            else:
                rest.append(paragraphs[i])
    for paragraph in rest:  # 技术方案可以分段的情况
        if re.match(r"[^\u4e00-\u9fa5]*一种", paragraph) or re.search(r"提供.*一种", paragraph) or \
                re.search(r"提出.*一种", paragraph):
            start = True
            if method:
                methods.append(method)
            method = ""
        if start:
            method += paragraph
    methods.append(method)
    if not methods[0]:  # 技术方案无法分段的情况
        methods = []
        for paragraph in rest:
            method += paragraph
        methods.append(method)
    if not purpose:
        try:
            purpose = split_paragraph(background)[-1]
        except IndexError:
            pass
    temp = re.split(r'，|,', purpose, 1)
    if len(temp[0]) < 8:
        purpose = temp[-1]
    if len(benefits) > 4:
        benefits = ''.join(benefits)
    data['目的'] = purpose
    data['技术方案'] = methods
    data['有益技术效果'] = benefits
    with open(data_file, 'w') as f:
        json.dump(data, f)


def extract_paragraphs_en(file_name, data_file):
    result = ""
    results = []
    subtitles_en = []
    data = {'名称': re.split(r'-|_', file_name, 1)[-1].replace('.pdf', '').replace('+', ' '), '摘要': '', '权利要求': '',
            '所属领域': '', '背景技术': '', '目的': '', '技术方案': '', '有益技术效果': ''}
    bar = st.progress(0.0, f'正在读取……')
    with fitz.open("./inputs/" + file_name) as doc:
        total = doc.page_count
        for i in range(total):
            page = doc[i]
            bar.progress(i / total, f'正在读取第{i + 1}/{total}页……')
            rotate = int(0)
            # 每个尺寸的缩放系数为1.3，这将为我们生成分辨率提高2.6的图像。
            # 此处若是不做设置，默认图片大小为：792X612, dpi=96
            zoom_x = 4  # (新型颅内支架Enterprise_省略_弹簧圈栓塞治疗颅内微小宽颈动脉瘤_黄海东.33333333-->1056x816)   (2-->1584x1224)
            zoom_y = 4
            mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix._writeIMG("page.png", 1)
            with Image.open("page.png") as im:
                if i == 0:
                    abstract = pytesseract.image_to_string(im.crop((1240, 325, 2180, 3015)))
                    try:
                        abstract = re.search(r'ABSTRACT(.+\.)', abstract, re.DOTALL).group(1)
                        data['摘要'] = re.sub(r' \(\d+\)', '', abstract.replace('-\n', '').replace('\n', ' ')).strip()
                    except AttributeError:
                        pass
                else:
                    result += '\n' + pytesseract.image_to_string(im)
    bar.progress(1.0, '读取完成')
    paragraphs = result.split('\n\n')
    for paragraph in paragraphs:
        if len(paragraph) > 2 and (len(paragraph) > 20 or paragraph.isupper() or re.match(r'\d', paragraph)):
            results.append(paragraph.replace('-\n', '').replace('\n', ' '))
    for i, paragraph in enumerate(results):
        if paragraph.isupper():
            subtitles_en.append((i, paragraph))
        elif re.match(r'1\.|1-\d+\.', paragraph):
            data['权利要求'] = '\n'.join(results[i:])
    for i, subtitle_en in enumerate(subtitles_en):
        for ch, en in ch_en:
            if en in subtitle_en[1]:
                data[ch] = preprocess(results[subtitle_en[0] + 1: subtitles_en[i + 1][0]])
    with open(data_file, 'w') as f:
        json.dump(data, f)


def data2tree(number, data_file, tree_file, lang, if_translate, summarize, df, statistics, num):
    tree_list = []
    summarize_progress = None
    with open(data_file) as f:
        data = json.load(f)
    if summarize:
        summarize_progress = st.progress(0.0)
    summarize_index = 0
    for subtitle in subtitles:
        children = []
        contents = data[subtitle]
        summarization = subtitle in summarize
        if summarization:
            summarize_progress.progress(summarize_index / len(summarize), f'正在概括“{summarize[summarize_index]}”……')
            summarize_index += 1
        if type(contents) == list:
            if not contents:
                contents = ['']
            content_num = len(contents)
            for i in range(content_num):
                res, df = paragraphing(num, contents[i], if_translate, summarization, lang, df, subtitle,
                                       str(i + 1) if content_num > 1 else '')
                children.append({'name': res, 'children': [{}]})
        else:
            res, df = paragraphing(num, contents, if_translate, summarization, lang, df, subtitle)
            children.append({'name': res, 'children': [{}]})
        tree_list.append({'name': subtitle, 'children': children})
    if summarize:
        summarize_progress.progress(1.0, f'概括完成。')
    total = df.sum(0)
    price = total.sum() * 0.00004
    with open("prices.json") as f:
        price_data = json.load(f)
    today = datetime.date.today().strftime('%Y-%m-%d')
    if today in price_data:
        price_data[today] += price
    else:
        price_data[today] = price
    with open("prices.json", 'w') as f:
        json.dump(price_data, f)
    df.loc['总计'] = total
    df.to_csv(statistics)
    series = [{'name': number + '\n' + data['名称'], 'children': tree_list}]
    with open(tree_file, 'w') as f:
        json.dump(series, f)


def uploader(num):
    st.header('批量设置', divider="rainbow")
    col1, col2, col3, col4 = st.columns(4)
    auto = col1.checkbox('按文件名自动判断专利的国家', True)
    if_summarize = col2.checkbox('批量概括', True)
    if_replace = col3.checkbox('覆盖原有内容', True)
    if_translate = col4.checkbox('概括时自动翻译全英文的内容', True)
    left, right = st.columns(2)
    lang = left.radio('请选择专利的国家：', ('中国', '美国'), disabled=auto, horizontal=True, captions=('', '暂只支持通道一'))
    ocr_option = right.radio('请选择读取中文扫描件的OCR通道：', ('通道一', '通道二', '通道三'),
                             disabled=not auto and lang != '中国',
                             horizontal=True, captions=('分段效果较好', '速度较快', '精度较高'))
    summarize = st.multiselect('选择需要概括的段落：', subtitles, ['权利要求', '背景技术', '技术方案'],
                               placeholder='请选择', disabled=not if_summarize)
    if_read = st.button("批量读取以下已上传的文件", use_container_width=True)
    st.header('上传通道', divider="rainbow")
    uploaded_files = st.file_uploader('上传PDF文件', type='pdf', accept_multiple_files=True)
    if uploaded_files:
        st.session_state['files'] = uploaded_files
    for file in st.session_state['files']:
        file_name = file.name
        number = re.split(r'-|_', file_name)[0]
        data_file = f'./data/{number}.json'
        tree_file = f'./trees/{number}.json'
        statistics = f'./statistics/{number}.csv'
        df = pd.DataFrame(columns=['输入', '输出'])
        with open("./inputs/" + file_name, "wb") as code:
            code.write(file.getvalue())
        if if_read:
            if not os.path.exists(data_file) or if_replace:
                if auto:
                    if not re.match(r'CN', number):
                        lang = '美国'
                    else:
                        lang = '中国'
                if lang == '中国':
                    temp = ocr_option
                    if not identification(file_name):
                        temp = None
                    extract_paragraphs(file_name, data_file, temp)
                else:
                    extract_paragraphs_en(file_name, data_file)
            if if_summarize and (not os.path.exists(tree_file) or if_replace):
                data2tree(number, data_file, tree_file, lang, if_translate, summarize, df, statistics, num)
        if st.button(file_name, use_container_width=True):
            st.session_state['page'] = file_name
            st.experimental_rerun()


def setup(num, file_name):
    ocr_option = None
    number = re.split(r'-|_', file_name)[0]
    data_file = f'./data/{number}.json'
    tree_file = f'./trees/{number}.json'
    mind_map = f'./mind_maps/{number}.png'
    statistics = f'./statistics/{number}.csv'
    df = pd.DataFrame(columns=['输入', '输出'])
    st.header(number, divider="rainbow")
    with st.expander("原文件预览"):
        with open("inputs/" + file_name, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" ' \
                      f'width="800" height="900" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
    left, right = st.columns(2)
    lang = left.radio('请选择专利的国家：', ('中国', '美国'), 1 if not re.match(r'CN', number) else 0,
                      horizontal=True, captions=('', '暂只支持通道一'))
    is_scanned = identification(file_name)
    if is_scanned:
        ocr_option = right.radio('检测为扫描件，请选择OCR通道：', ('通道一', '通道二', '通道三'), disabled=lang != '中国',
                                 horizontal=True, captions=('分段效果较好', '速度较快', '精度较高'))
    remain = left.checkbox('读取时保留原思维导图', not is_scanned)
    if_translate = right.checkbox('自动翻译全英文的内容', True)
    if st.button(display_label(data_file, '读取'), use_container_width=True) \
            or not (os.path.exists(data_file) or is_scanned):
        if lang == '中国':
            extract_paragraphs(file_name, data_file, ocr_option)
        else:
            extract_paragraphs_en(file_name, data_file)
        if os.path.exists(tree_file) and not remain:
            os.remove(tree_file)
        st.experimental_rerun()
    if os.path.exists(data_file):
        summarize = st.multiselect('选择需要概括的段落：', subtitles, ['权利要求', '背景技术', '技术方案'], placeholder='请选择')
        if st.button(display_label(tree_file, '概括'), use_container_width=True):
            data2tree(number, data_file, tree_file, lang, if_translate, summarize, df, statistics, num)
            st.experimental_rerun()
        if os.path.exists(tree_file):
            selected = []
            display = []
            with open(tree_file) as f:
                series = json.load(f)
            st.write('选择需要展示的段落：')
            cols = st.columns(8)
            select_all = cols[0].checkbox('全选', True)
            for i in range(7):
                if cols[i + 1].checkbox(subtitles[i], select_all):
                    display.append(subtitles[i])
            for item in series[0]['children']:
                if item['name'] in display:
                    selected.append(item)
            series[0]['children'] = selected
            left, right = st.columns([1.4, 1])
            with left:
                height = st.number_input('设置高度', min_value=300, value=1200, step=100)
                tree = (
                    Tree(init_opts=opts.InitOpts(width="1000px", height=f"{height}px", bg_color='white'))
                    .add("",
                         series,
                         symbol_size=5,
                         pos_top="10%",
                         pos_left="10%",
                         pos_bottom="10%",
                         pos_right="10%",
                         initial_tree_depth=10,
                         label_opts=opts.LabelOpts(position="right", distance=2, font_size=10,
                                                   background_color='white'),
                         leaves_label_opts=opts.LabelOpts(position="right", distance=2, font_size=10,
                                                          background_color='white'))
                    .set_global_opts(title_opts=opts.TitleOpts(title=f"{number} 概览"))
                )
                st_pyecharts(tree, height=f"{height}px")
                if st.button(display_label(mind_map, '渲染为图片'), use_container_width=True):
                    with st.spinner('正在渲染图片……'):
                        tree.render()
                        res = os.system(f"python makeSnapshot.py {number}")
                    if res:
                        st.error('导航超时，请重试。', icon='🕒')
                    else:
                        st.success('渲染成功。', icon='✔')
                if os.path.exists(mind_map):
                    with open(mind_map, 'rb') as png:
                        st.download_button('下载图片', png, f'{number}.png', 'image/png', use_container_width=True)

            with right:
                for level2 in series[0]['children']:
                    with st.expander(level2['name']):
                        for level3 in level2['children']:
                            st.write(level3['name'].replace('\n', ''))
                st.write('令牌数统计')
                if os.path.exists(statistics):
                    df = pd.read_csv(statistics)
                    price = df.iloc[len(df) - 1, 1:].sum() * 0.00004
                    st.dataframe(df.rename(columns={'Unnamed: 0': '类别'}), use_container_width=True, hide_index=True)
                    st.write(f'总费用：**:blue[{price:.5f}]** 元')
                else:
                    st.write("暂无数据。")


if __name__ == "__main__":
    config()
    if 'page' not in st.session_state:
        st.session_state['page'] = 'main'
    if 'files' not in st.session_state:
        st.session_state['files'] = []
    num = limit()
    st.title("📤上传文件")
    if 'name' in st.session_state and st.session_state['name']:
        if st.session_state['page'] == 'main':
            uploader(num)
        else:
            if st.button('返回'):
                st.session_state['page'] = 'main'
                st.experimental_rerun()
            setup(num, st.session_state['page'])
    else:
        st.warning('登录已失效，请返回首页重新登录。', icon='🕒')