import streamlit as st
import akshare as ak
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import json
import os

# 页面设置
st.set_page_config(page_title="个股盯盘助手", layout="wide", initial_sidebar_state="expanded")

# 隐藏右上角菜单
hide_menu_style = """
        <style>
        #MainMenu {visibility: hidden;}
        .stDeployButton {display: none !important;}
        [data-testid="stAppDeployButton"] {display: none !important;}
        [data-testid="stElementToolbar"] {display: none !important;}
        [data-testid="stHeader"] { background: rgba(0,0,0,0); }
        footer {visibility: hidden;}
        </style>
        """
st.markdown(hide_menu_style, unsafe_allow_html=True)

st.title("📈 个股压力/支撑 & 信息面助手")

# ==========================================
# 🌟 自选股数据管理（兼容云端）
# ==========================================
def load_watchlist():
    if "watchlist" not in st.session_state:
        return {}
    return st.session_state.watchlist

def save_watchlist(wl):
    st.session_state.watchlist = wl

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "current_code" not in st.session_state:
    st.session_state.current_code = "600519"
if "current_name" not in st.session_state:
    st.session_state.current_name = "贵州茅台"

# === 获取全市场股票代码与名称对照表 ===
@st.cache_data(ttl=86400)
def get_all_stocks():
    try:
        df = ak.stock_info_a_code_name()
        df['code'] = df['code'].astype(str).str.zfill(6)
        return df
    except:
        return pd.DataFrame()

with st.spinner("正在加载基础数据..."):
    all_stocks = get_all_stocks()

# ==========================================
# 侧边栏
# ==========================================
st.sidebar.subheader("⭐ 我的自选股")
if not st.session_state.watchlist:
    st.sidebar.caption("暂无自选股，请在下方添加。")
else:
    for code, name in list(st.session_state.watchlist.items()):
        col1, col2 = st.sidebar.columns([3, 1])
        if col1.button(f"{name}", key=f"btn_{code}", use_container_width=True):
            st.session_state.current_code = code
            st.session_state.current_name = name
            st.rerun()
        if col2.button("❌", key=f"del_{code}"):
            del st.session_state.watchlist[code]
            save_watchlist(st.session_state.watchlist)
            st.rerun()

st.sidebar.divider()

with st.sidebar.expander("➕ 添加自选股"):
    add_input = st.text_input("输入股票名称或代码", key="add_input", label_visibility="collapsed")
    if st.button("添加到自选", use_container_width=True):
        if add_input and not all_stocks.empty:
            match = all_stocks[(all_stocks['name'].str.contains(add_input)) | (all_stocks['code'] == add_input)]
            if not match.empty:
                new_code = match.iloc[0]['code']
                new_name = match.iloc[0]['name']
                st.session_state.watchlist[new_code] = new_name
                save_watchlist(st.session_state.watchlist)
                st.success(f"已添加 {new_name}")
                st.rerun()
            else:
                st.error("未找到该股票")

st.sidebar.divider()
st.sidebar.subheader("🔍 手动查询")
query_name = st.sidebar.text_input("输入股票名称（如：贵州茅台）", "").strip()
query_code = st.sidebar.text_input("或直接输入股票代码", "").strip()

lookback = st.sidebar.slider("回看交易日", 60, 400, 250)
show_ma = st.sidebar.multiselect("显示均线", [5, 10, 20, 60], default=[5, 20, 60])

st.sidebar.divider()
st.sidebar.subheader("🚨 智能预警")
enable_alert = st.sidebar.checkbox("开启支撑/压力位破位警报", value=True)

# === 解析当前查询 ===
if query_code:
    st.session_state.current_code = query_code
    local_dict = {"600519": "贵州茅台", "600667": "太极实业", "000001": "平安银行", "605299": "舒华体育"}
    st.session_state.current_name = local_dict.get(query_code, query_code)
    try:
        info = ak.stock_individual_info_em(symbol=query_code)
        st.session_state.current_name = info.loc[info['item'] == '股票简称', 'value'].values[0]
    except Exception:
        try:
            df = ak.stock_bid_ask_em(symbol=query_code)
            st.session_state.current_name = df.loc[df['item'] == '名称', 'value'].values[0]
        except Exception:
            pass
elif query_name:
    if not all_stocks.empty:
        match = all_stocks[all_stocks['name'].str.contains(query_name)]
        if not match.empty:
            st.session_state.current_code = match.iloc[0]['code']
            st.session_state.current_name = match.iloc[0]['name']
            st.sidebar.success(f"✅ 自动匹配到代码：{st.session_state.current_code}")
        else:
            st.sidebar.error(f"❌ 未找到名称包含“{query_name}”的股票")
            st.stop()

code = st.session_state.current_code
name_hint = st.session_state.current_name

if not code:
    st.warning("👈 请点击左侧自选股，或输入股票代码/名称。")
    st.stop()

# ==========================================
# 数据获取模块
# ==========================================
@st.cache_data(ttl=5)
def load_order_book(c):
    try:
        df = ak.stock_bid_ask_em(symbol=c)
        if df.empty: return None
        return dict(zip(df['item'], df['value']))
    except Exception:
        return None

def clean_data(df):
    df.columns = [str(col).strip().lower() for col in df.columns]
    rename_map = {'日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'}
    df = df.rename(columns=rename_map)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').drop_duplicates(subset=['date'])
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.dropna(subset=['open', 'high', 'low', 'close'])

@st.cache_data(ttl=600)
def load_daily(c, n):
    end = pd.Timestamp.today().strftime('%Y%m%d')
    start = (pd.Timestamp.today() - pd.Timedelta(days=n*2)).strftime('%Y%m%d')
    try:
        df = ak.stock_zh_a_hist_em(symbol=c, period="daily", start_date=start, end_date=end, adjust="qfq")
        if not df.empty: return clean_data(df), "东方财富"
    except Exception: pass
    try:
        prefix = "sh" if c.startswith("6") else "sz"
        df = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{c}", start_date=start, end_date=end, adjust="qfq")
        if not df.empty: return clean_data(df), "腾讯财经"
    except Exception: pass
    return pd.DataFrame(), "无"

# 🌟 新增：获取分时数据
@st.cache_data(ttl=60)
def load_intraday(c):
    try:
        # 使用东财分时接口
        df = ak.stock_intraday_em(symbol=c)
        if not df.empty:
            df['时间'] = pd.to_datetime(df['时间'])
            df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
            df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
            df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce')
            
            # 计算均价（累计成交额 / 累计成交量）
            df['cum_amt'] = df['成交额'].cumsum()
            df['cum_vol'] = df['成交量'].cumsum()
            # 避免除零
            df['均价'] = df.apply(lambda row: row['cum_amt'] / row['cum_vol'] if row['cum_vol'] > 0 else row['最新价'], axis=1)
            return df
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=600)
def load_fund_flow(c):
    try:
        market_id = "1" if c.startswith("6") else "0"
        url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {"lmt": "10", "klt": "101", "secid": f"{market_id}.{c}", "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, params=params, headers=headers, timeout=8)
        data = res.json()
        if data.get("data") and data["data"].get("klines"):
            parsed = []
            for k in data["data"]["klines"]:
                parts = k.split(",")
                parsed.append({'日期': pd.to_datetime(parts[0]), '收盘价': float(parts[11]), '涨跌幅': float(parts[12]), '主力净流入-净额': float(parts[1]), '超大单净流入-净额': float(parts[5]), '大单净流入-净额': float(parts[4])})
            return pd.DataFrame(parsed), None
        return pd.DataFrame(), "东财接口返回空数据。"
    except Exception:
        return pd.DataFrame(), "服务器拒绝连接（非交易时段或接口维护）。"

@st.cache_data(ttl=300)
def load_news(c):
    stock_news = []
    try:
        df_news = ak.stock_news_em(symbol=c)
        for _, row in df_news.iterrows():
            stock_news.append({"time": row.get("发布时间", ""), "title": row.get("新闻标题", ""), "url": row.get("新闻链接", ""), "content": row.get("新闻内容", "")})
    except: pass
    return stock_news

@st.cache_data(ttl=600)
def load_concept_heat():
    try:
        df = ak.stock_board_concept_name_em()
        if not df.empty:
            df = df.sort_values(by="涨跌幅", ascending=False).head(15)
            res_df = pd.DataFrame({
                "板块名称": df["板块名称"],
                "最新价": df["最新价"],
                "涨跌幅": df["涨跌幅"].apply(lambda x: f"{x}%"),
                "主力净流入": (df["主力净流入-净额"] / 100000000).apply(lambda x: f"{x:.2f} 亿")
            })
            return res_df, None
        return pd.DataFrame(), "接口返回为空。"
    except Exception as e:
        return pd.DataFrame(), "由于云端网络限制，海外IP暂时无法获取国内板块接口。"

def compute_levels(df):
    last = df.iloc[-1]
    pivot = (last['high'] + last['low'] + last['close']) / 3
    r1 = 2 * pivot - last['low']
    s1 = 2 * pivot - last['high']
    r2 = pivot + (last['high'] - last['low'])
    s2 = pivot - (last['high'] - last['low'])
    df['tr'] = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
    atr = df['tr'].rolling(14).mean().iloc[-1]
    return {
        "range": [last['close'] - atr, last['close'] + atr], "atr": atr,
        "resist": [{"price": r1, "labels": ["枢轴点R1"]}, {"price": r2, "labels": ["枢轴点R2"]}],
        "support": [{"price": s1, "labels": ["枢轴点S1"]}, {"price": s2, "labels": ["枢轴点S2"]}]
    }

with st.spinner("正在拉取行情、分时、盘口与资金数据..."):
    df_daily, source_name = load_daily(code, lookback)
    fund_df, fund_err = load_fund_flow(code)
    order_book = load_order_book(code)
    intraday_df = load_intraday(code)
    concept_df, concept_err = load_concept_heat()

if df_daily.empty:
    st.warning(f"暂时无法获取代码 {code} 的数据。")
    st.stop()

st.caption(f"当前查询：{name_hint} (代码: {code}) | K线数据源：{source_name}")
res = compute_levels(df_daily)
last = df_daily.iloc[-1]
cur_price = float(last["close"])

# 预警逻辑
if enable_alert:
    sup1 = res['support'][0]['price']
    res1 = res['resist'][0]['price']
    if cur_price < sup1:
        st.toast(f"⚠️ 警报：{name_hint} 已跌破第一支撑位 {sup1:.2f}！", icon="🚨")
        st.error(f"⚠️ **破位警报**：当前价 `{cur_price:.2f}` 已跌破第一支撑位 `{sup1:.2f}`！注意风险控制！")
    elif cur_price > res1:
        st.toast(f"🚀 提示：{name_hint} 已突破第一压力位 {res1:.2f}！", icon="🚀")
        st.success(f"🚀 **突破提示**：当前价 `{cur_price:.2f}` 已强势突破第一压力位 `{res1:.2f}`！")

# 页面展示
c1, c2, c3, c4 = st.columns(4)
c1.metric("最新价 (日线)", f"{cur_price:.2f}")
c2.metric("明日波动", f"{res['range'][0]:.2f} ~ {res['range'][1]:.2f}", f"ATR14={res['atr']:.2f}")
c3.metric("第一压力", f"{res['resist'][0]['price']:.2f}")
c4.metric("第一支撑", f"{res['support'][0]['price']:.2f}")

if order_book:
    st.markdown("#### ⚡ 实时盘口五档")
    col_sell, col_buy = st.columns(2)
    with col_sell:
        st.caption("🔴 卖盘 (挂单量)")
        sell_data = [{"档位": f"卖{i}", "价格": order_book.get(f"卖{i}", 0.0), "挂单量": order_book.get(f"卖{i}量", 0) / 100} for i in range(5, 0, -1)]
        st.dataframe(pd.DataFrame(sell_data), hide_index=True, use_container_width=True)
    with col_buy:
        st.caption("🟢 买盘 (挂单量)")
        buy_data = [{"档位": f"买{i}", "价格": order_book.get(f"买{i}", 0.0), "挂单量": order_book.get(f"买{i}量", 0) / 100} for i in range(1, 6)]
        st.dataframe(pd.DataFrame(buy_data), hide_index=True, use_container_width=True)
else:
    st.info("💡 盘口数据暂不可用（可能处于非交易时段）。")

st.divider()

# ==========================================
# 标签页 (新增分时图作为第一个Tab)
# ==========================================
tab0, tab1, tab2, tab3, tab4 = st.tabs(["⏱️ 当日分时图", "📈 日K线图", "📍 价位明细", "💰 资金流向 (近10日)", "📰 个股新闻 & 🔥 板块热度"])

# === ⏱️ 分时图 Tab ===
with tab0:
    if intraday_df.empty:
        st.info("💡 分时数据暂不可用（可能处于非交易时段或接口维护）。请在开盘时间查看！")
    else:
        # 获取昨收价
        prev_close = df_daily.iloc[-2]['close'] if len(df_daily) >= 2 else df_daily.iloc[-1]['close']
        
        fig_intra = go.Figure()
        
        # 绘制价格线 (蓝色)
        fig_intra.add_trace(go.Scatter(
            x=intraday_df['时间'], y=intraday_df['最新价'], 
            mode='lines', name='最新价', 
            line=dict(color='#1E90FF', width=2)
        ))
        
        # 绘制均价线 (黄色)
        fig_intra.add_trace(go.Scatter(
            x=intraday_df['时间'], y=intraday_df['均价'], 
            mode='lines', name='均价', 
            line=dict(color='orange', width=1.5)
        ))
        
        # 绘制昨收线 (灰色虚线)
        fig_intra.add_hline(y=prev_close, line_dash="dash", line_color="gray", annotation_text=f"昨收: {prev_close:.2f}", annotation_position="top left")
        
        # 设置坐标轴
        fig_intra.update_xaxes(type='date', tickformat='%H:%M', title_text="时间", nticks=10)
        fig_intra.update_yaxes(title_text="价格")
        fig_intra.update_layout(
            height=500, 
            margin=dict(l=10, r=10, t=30, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_intra, use_container_width=True, config={'locale': 'zh-CN', 'displaylogo': False})

# === 📈 日K线图 Tab ===
with tab1:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_daily["date"], open=df_daily["open"], high=df_daily["high"], low=df_daily["low"], close=df_daily["close"],
        name="日K", increasing_line_color="red", decreasing_line_color="green",
        hovertext=df_daily.apply(lambda row: f"日期: {row['date'].strftime('%Y-%m-%d')}<br>开盘: {row['open']:.2f}<br>最高: {row['high']:.2f}<br>最低: {row['low']:.2f}<br>收盘: {row['close']:.2f}", axis=1),
        hoverinfo="text"
    ))
    for m in show_ma:
        fig.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["close"].rolling(m).mean(), name=f"{m}日均线", line=dict(width=1)))

    for i, lv in enumerate(res["resist"][:2]):
        fig.add_hline(y=lv["price"], line_dash="dash", line_color="orange", annotation_text=f"压力{i+1}: {lv['price']:.2f}", annotation_position="top right" if i==0 else "bottom right")
    for i, lv in enumerate(res["support"][:2]):
        fig.add_hline(y=lv["price"], line_dash="dash", line_color="blue", annotation_text=f"支撑{i+1}: {lv['price']:.2f}", annotation_position="top left" if i==0 else "bottom left")

    fig.update_xaxes(type='date', tickformat='%Y-%m-%d', title_text="日期")
    fig.update_yaxes(title_text="价格")
    fig.update_layout(
        height=500, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=50, b=10), 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config={'locale': 'zh-CN', 'displaylogo': False})

# === 📍 价位明细 Tab ===
with tab2:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("压力位")
        for i, lv in enumerate(res["resist"]):
            st.write(f"**{lv['price']:.2f}**　依据：{' / '.join(lv['labels'])}")
    with col_b:
        st.subheader("支撑位")
        for i, lv in enumerate(res["support"]):
            st.write(f"**{lv['price']:.2f}**　依据：{' / '.join(lv['labels'])}")

# === 💰 资金流向 Tab ===
with tab3:
    if fund_df.empty:
        st.warning(f"💡 资金流向获取失败：{fund_err}")
        st.info("👨‍💻 原因：东方财富的资金接口通常在夜间会关闭维护。请在明天 A 股开盘后再来查看。")
    else:
        latest_fund = fund_df.iloc[-1]
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("主力净流入 (万元)", f"{float(latest_fund['主力净流入-净额'])/10000:.2f}")
        fc2.metric("超大单净流入 (万元)", f"{float(latest_fund['超大单净流入-净额'])/10000:.2f}")
        fc3.metric("大单净流入 (万元)", f"{float(latest_fund['大单净流入-净额'])/10000:.2f}")
        
        fund_df['主力净额(万)'] = fund_df['主力净流入-净额'] / 10000
        fig_fund = px.bar(fund_df, x='日期', y='主力净额(万)', color='主力净额(万)', color_continuous_scale=['green', 'red'], title="近10日主力资金净流入 (万元)")
        fig_fund.update_xaxes(type='date', tickformat='%Y-%m-%d', title_text="日期")
        fig_fund.update_yaxes(title_text="净流入金额 (万元)")
        fig_fund.update_layout(height=400, coloraxis_showscale=False)
        st.plotly_chart(fig_fund, use_container_width=True, config={'locale': 'zh-CN', 'displaylogo': False})

# === 📰 个股新闻 & 🔥 板块热度 Tab ===
with tab4:
    col_news, col_heat = st.columns([1, 1])
    with col_news:
        st.subheader("📰 个股新闻")
        news = load_news(code)
        if not news:
            st.info("暂时没有获取到相关新闻。")
        for n in news[:10]:
            st.markdown(f"**[{n['time']}]** [{n['title']}]({n['url']})")
            st.divider()
            
    with col_heat:
        st.subheader("🔥 概念板块热度 TOP 15")
        st.caption("按涨跌幅排序，观察今天资金主要攻击了哪些方向。")
        if concept_df.empty:
            st.warning(f"暂时无法获取板块热度数据。原因：{concept_err}")
        else:
            st.dataframe(concept_df, hide_index=True, use_container_width=True)