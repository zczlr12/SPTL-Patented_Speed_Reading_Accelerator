import json
import datetime
import streamlit as st
from pyecharts.charts import Line
import pyecharts.options as opts
from streamlit_echarts import st_pyecharts
from mainPage import config, limit


def formatting(data):
    temp = datetime.datetime.strptime(min(data), '%Y-%m-%d')
    last_date = datetime.datetime.today()
    date_list = []
    price_list = []
    while temp <= last_date:
        xdata = temp.strftime("%Y-%m-%d")
        date_list.append(xdata)
        if xdata in data:
            price_list.append(round(data[xdata], 5))
        else:
            price_list.append(0)
        temp += datetime.timedelta(days=1)
    return date_list, price_list


if __name__ == "__main__":
    config()
    limit()
    st.title("📊费用统计")
    with st.spinner('加载中……'):
        with open("prices.json") as f:
            date_list, price_list = formatting(json.load(f))

        line = (
            Line()
            .add_xaxis(date_list)
            .add_yaxis('', price_list, is_symbol_show=False, areastyle_opts=opts.AreaStyleOpts(0.3))
            .set_global_opts(title_opts=opts.TitleOpts(title='费用统计'),
                             tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
                             xaxis_opts=opts.AxisOpts(name='日期'),
                             yaxis_opts=opts.AxisOpts(name='费用（元）'),
                             datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100),
                                            opts.DataZoomOpts(range_start=0, range_end=100, orient="vertical")])
        )
        st_pyecharts(line, height="500px")