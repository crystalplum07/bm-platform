# step7.py —— Step 7「关键年报指标」独立模块
# 从 app.py 拆分而来，依赖：streamlit、pandas、numpy、plotly，以及 st.session_state['integrated_data']（由 Step 6 写入）

import pandas as pd
from report_i18n import extract_ai_response_text, localized_st as st
import requests
import re
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from plotly.subplots import make_subplots
import streamlit.components.v1 as components


def get_color_map(all_cos):
    # Create a unique key based on the current selection of companies
    current_selection_key = tuple(sorted(all_cos))
    
    # Check if we need to rebuild the color map (either it doesn't exist, or the selection changed)
    if 'company_color_map' not in st.session_state or st.session_state.get('_last_color_selection') != current_selection_key:
        PRESET_COLORS = ["#C00000", "#0865EE", "#FEAED7", "#92D050", "#7030A0", "#EF9867", "#61CBF4", "#C7A0F7", "#FFC000", "#00A19D"]
        # Rebuild the map for the new selection
        st.session_state['company_color_map'] = {co: PRESET_COLORS[i % len(PRESET_COLORS)] for i, co in enumerate(all_cos)}
        # Store the current selection key so we know when it changes next time
        st.session_state['_last_color_selection'] = current_selection_key
        
    return st.session_state['company_color_map']

def filter_df_by_period(df, year, month=None):
    """
    按报告期筛选数据
    year: 年份（整数或字符串）
    month: 月份（整数或字符串），可选
    """
    df_filtered = df[df["报告年份"].astype(str) == str(year)]
    if month is not None and "报告月份" in df.columns:
        df_filtered = df_filtered[df_filtered["报告月份"].astype(str) == str(month)]
    return df_filtered


def format_period_label(year, month):
    """格式化显示报告期标签：统一为"x年x月"格式（单行，给下拉框等纯文本场景用）"""
    if month is None:
        return f"{year}年"
    return f"{year}年{month}月"


def format_period_label_ml(year, month):
    """格式化报告期标签：年/月换行显示（给图表坐标轴、柱子名称等 Plotly 场景用，避免"2024年6月2025年6月"这种挤在一起的情况）"""
    if month is None:
        return f"{year}年"
    return f"{year}年<br>{month}月"


def get_period_from_data(df):
    """
    从数据中提取可用的报告期列表
    返回: [(year, month), ...] 按时间正序排列
    """
    df_copy = df.copy()
    df_copy['报告年份'] = df_copy['报告年份'].astype(str).str.replace(".0", "", regex=False).str.strip()
    
    if '报告月份' in df_copy.columns:
        df_copy['报告月份'] = df_copy['报告月份'].astype(str).str.replace(".0", "", regex=False).str.strip()
        df_copy.loc[df_copy['报告月份'].isin(['nan', 'None', '', 'NaT']), '报告月份'] = np.nan
    else:
        df_copy['报告月份'] = np.nan
    df_copy['报告月份'] = df_copy['报告月份'].fillna("12")
    
    periods = []
    for _, row in df_copy[['报告年份', '报告月份']].drop_duplicates().iterrows():
        if row['报告年份'].isdigit() and row['报告月份'].isdigit():
            periods.append((int(row['报告年份']), int(row['报告月份'])))
    
    return sorted(set(periods))

# 然后在 show_step_7_content 内部调用：
# color_map = get_color_map(all_cos)
def show_step_7_content():
    # 将全局字体配置提到最开头
    COMMON_TITLE_FONT = dict(size=18, color="#00338D", family="Microsoft YaHei")

    # ==========================================
    # 1. 样式与前端注入 ( CSS & JS)
    # ==========================================

    st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: rgba(255,255,255,0.95) !important; border-right: 1px solid #EAEAEA !important; box-shadow: 2px 0px 15px rgba(0,0,0,0.08) !important; }
    .nav-floating-sign { position: fixed; left: 0; top: 50%; transform: translateY(-50%); background: rgba(0, 51, 141, 0.85); color: white; padding: 14px 6px; border-radius: 0 10px 10px 0; writing-mode: vertical-rl; text-orientation: mixed; font-size: 17px; line-height: 1.15; font-weight: bold; letter-spacing: 1px; max-height: 230px; overflow: hidden; z-index: 9999; cursor: pointer; box-shadow: 3px 3px 12px rgba(0,0,0,0.25); transition: all 0.2s; }
    .nav-floating-sign:hover { background: rgba(0, 51, 141, 1); padding-left: 10px; }
   
    /* 放在 @media print { } 块的外面 */
    .stPlotlyChart {
        width: 100% !important;
        min-width: 0 !important;
    }
    .print-only { display: none !important; }
    /* 专门给封面封底用的样式类 */
    .cover-page {
        position: relative !important;
        width: 338.67mm !important;
        height: 190.5mm !important;
        margin: 0 !important;
        padding: 0 !important;
        page-break-after: always !important;
        overflow: hidden !important;
        background: transparent !important;
    }
    .cover-page img { width: 100% !important; height: 100% !important; object-fit: cover !important; display: block !important; }
    /* Streamlit网页模式去掉container两侧padding */
    .block-container {
        padding-top:0 !important;
        padding-right:10px !important;
        padding-left:10px !important;
        margin-top:0 !important;
    }
    /* 封面封底强制颜色不被浏览器覆盖 */
    .cover-text {
        forced-color-adjust: none !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
        color: white !important;
        -webkit-text-fill-color: white !important;
    }
    .element-container:first-child{
        margin-top:0 !important;
        padding-top:0 !important;
    }
    @media print {
        @page {
            size: 338.67mm 190.5mm;
            margin: 10mm;
            @bottom-center {
                content: counter(page);
                font-size: 12px;
                color: #666;
                font-family: Microsoft YaHei, sans-serif;
            }     
        }
        .print-only { display: block !important; }
        html,body{
            width:338.67mm!important;
            height:190.5mm!important;
            overflow:hidden!important;
            zoom:100%!important;
        }
        .main .block-container{
            width:338.67mm !important;
            max-width:338.67mm !important;
            min-width:338.67mm !important;
        
            padding-top:0!important;
            padding-bottom:0!important;
            padding-left:10mm!important;
            padding-right:10mm!important;
        }
        .block-container {
            padding-top: 0rem !important;
        }
        /* ===== 隐藏所有交互元素 ===== */
        .no-print, h1, .nav-floating-sign,
        [data-testid="collapsedControl"], header, footer,
        [data-testid="stHeader"], [data-testid="stSidebar"],
        section[data-testid="stSidebar"],
        [data-testid="stToolbar"], button[kind="secondary"],
        input, .stSlider, [data-testid="stSelectbox"],
        [data-testid="stRadio"], [data-testid="stExpander"],
        .stAlert,
        button[role="tab"],
        div[role="tablist"],
        [data-baseweb="tab-list"],
        hr { display: none !important; }

        /* ===== 页面布局撑满纸张 ===== */
        .page-break-container {
            break-inside: avoid !important;
            margin: 0 !important;              /* 清掉容器 margin，防溢出变空白页 */
            padding: 0 !important;
            padding-bottom: 0mm !important;    /* 只留很小的底部间距 */
        }
        .stApp {
            max-width: 100% !important;
            width: 100% !important;
        }
        
        /* 保留两列并排布局的例外 */
        /* ⭐ PDF打印时强制双列 */
        
        .keep-columns [data-testid="stHorizontalBlock"]{
            display:flex!important;
            flex-wrap:nowrap!important;
            align-items:flex-start!important;
            justify-content:space-between!important;
            gap:0!important;
            width:100%!important;
        }
        .keep-columns [data-testid="stHorizontalBlock"]>div{
            width:49%!important;
            min-width:49%!important;
            max-width:49%!important;
            flex:0 0 49%!important;
            overflow:hidden!important;
            page-break-inside:avoid!important;
            break-inside:avoid!important;
        }


        /* ===== 分页标题 ===== */
        .page-break-title {
            break-before: page !important;      /* 用新语法替代 page-break-before */
            padding-top: 10px !important;       /* 原来 40px，缩小防撑出空白 */
            margin-top: 0 !important;
            text-align: left !important;
        }

        /* ===== 标题 ===== */
        h2 {
            display: block !important;
            text-align: left !important;
            color: #00338D !important;
            font-size: 30px !important;
            font-weight: bold !important;
            border-bottom: 2px solid #00338D !important;
            padding-bottom: 6px !important;
            margin: 14px 0 10px 0 !important;
        }
        h3:not(.no-print) {
            display: block !important;
            text-align: left !important;
            color: #00338D !important;
            font-size: 30px !important;
            font-weight: bold !important;
            margin: 10px 0 8px 0 !important;
            page-break-after: avoid !important;
        }

        /* ===== 图表 ===== */
        .plotly-graph-div,
        .stPlotlyChart {
            width: 100% !important;
            max-width: 100% !important;
            height: auto !important;
            page-break-inside: avoid !important;
            display: block !important;
        }

        /* ===== 表格 ===== */
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {
            zoom: 0.65 !important;
            margin: 0 auto 20px auto !important;
            max-width: 100% !important;
            page-break-inside: auto !important;
        }
        div[data-testid="stTable"] tr {
            page-break-inside: avoid !important;
        }

        .element-container {
            page-break-inside: avoid !important;
            width: 100% !important;
        }
        .pdf-page-break {
                break-before: page !important;
                page-break-before: always !important;
                height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
        
            table {
                page-break-inside: auto !important;
            }
            tr {
                page-break-inside: avoid !important;
                page-break-after: auto !important;
            }
            td, th {
                page-break-inside: avoid !important;
            }
            thead {
                display: table-header-group !important;
            }
        }
    }

    /* 纵向打印微调 */
    @media print and (orientation: portrait) {
        .stPlotlyChart { margin-bottom: 10mm !important; }
    }
    /* 横向打印微调 */
    @media print and (orientation: landscape) {
        .stPlotlyChart { margin-bottom: 6mm !important; }
    }

    .stPlotlyChart, div[data-testid="stDataFrame"] { display: flex !important; justify-content: center !important; }
    .highlight-blue-box { border: 1.5px solid rgba(0,51,141,0.85) !important; border-radius: 12px !important; padding: 10px !important; background: rgba(0,51,141,0.02) !important; box-shadow: 0px 4px 12px rgba(0,51,141,0.12) !important; margin-bottom: 25px !important; }
    </style>
    <div class="nav-floating-sign" id="custom-nav-trigger">展开导航栏</div>
    """, unsafe_allow_html=True)

    components.html("""<script>let t = setInterval(() => { const d = window.parent.document; const b = d.getElementById("custom-nav-trigger"); const c = d.querySelector('[data-testid="collapsedControl"]') || d.querySelector('button[kind="header"]'); if(b && c) { b.onclick = () => c.click(); clearInterval(t); } }, 500);</script>""", height=0, width=0)

    # ==========================================
    # 2. 数据检查与年份提取
    # ==========================================
    if 'integrated_data' not in st.session_state or st.session_state['integrated_data'] is None:
        st.warning("⚠️ 请先在 Step 6 完成数据集成。")
        st.stop()
        
    df_raw = st.session_state['integrated_data'].copy()
    NUM_COLS = ["(百万)人民币", "(亿元)人民币", "(百万)原币", "(亿元)原币", "人民币", "原币", "数值", "值"]

    TEXT_FIELDS = ["折现率假设","VFA是否RW折现率","非金融风险的置信水平"]
    
    NUM_COLS = ["(百万)人民币", "(亿元)人民币", "(百万)原币", "(亿元)原币", "人民币", "原币", "数值", "值"]
    
    for c in NUM_COLS:
        if c in df_raw.columns:
            mask = ~df_raw["字段名"].astype(str).str.strip().str.contains(
                "|".join(TEXT_FIELDS),
                na=False
            )
            s = df_raw.loc[mask, c].astype(str).str.strip()
            s = s.replace(["未披露", "—", "-", "", "nan", "None", "null"], np.nan)
            s = s.str.replace(",", "", regex=False).str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
            df_raw.loc[mask, c] = pd.to_numeric(s, errors="coerce")
    if '公司类型' not in df_raw.columns: df_raw['公司类型'] = "未分类"

    # ==========================================
    # 🌟【报告期改造·地基层】兼容"报告月份"缺失的老数据，构建"任意时点比较"能力
    # ==========================================
    df_raw['报告年份'] = df_raw['报告年份'].astype(str).str.replace(".0", "", regex=False).str.strip()
    if '报告月份' in df_raw.columns:
        # 老数据没有这一列 → NaN；有值的先清洗成不带小数点的字符串
        df_raw['报告月份'] = df_raw['报告月份'].astype(str).str.replace(".0", "", regex=False).str.strip()
        df_raw.loc[df_raw['报告月份'].isin(['nan', 'None', '', 'NaT']), '报告月份'] = np.nan
    else:
        df_raw['报告月份'] = np.nan
    # 🌟 缺失月份一律当作"年报/12月"处理，保证老数据、宽表数据不受影响
    df_raw['报告月份'] = df_raw['报告月份'].fillna("12")

    # 构建"报告期"池：数据里实际存在的所有 (年份, 月份) 组合，按时间正序排列
    _period_df = df_raw[['报告年份', '报告月份']].drop_duplicates()
    _period_df = _period_df[_period_df['报告年份'].str.isdigit() & _period_df['报告月份'].str.isdigit()]
    available_periods = sorted(
        [(int(r['报告年份']), int(r['报告月份'])) for _, r in _period_df.iterrows()]
    )
    if not available_periods:
        available_periods = [(2025, 12), (2023, 12)]

    def _period_label(p):
        return format_period_label(p[0], p[1])

    period_options = [_period_label(p) for p in available_periods]
    period_lookup = dict(zip(period_options, available_periods))

    c_period1, c_period2 = st.columns(2)
    with c_period1:
        _cur_label = st.selectbox("本期", period_options, index=len(period_options) - 1, key="step7_current_period")
    with c_period2:
        _default_cmp_idx = max(0, len(period_options) - 2)
        _cmp_label = st.selectbox("对比期", period_options, index=_default_cmp_idx, key="step7_comparison_period")

    current_period = period_lookup[_cur_label]      # (年份:int, 月份:int)
    comparison_period = period_lookup[_cmp_label]    # (年份:int, 月份:int)

    # 🌟 兼容层：还没迁移到 current_period/comparison_period 的函数（约91处）继续用这两个变量，行为不变
    latest_year, prev_year = current_period[0], comparison_period[0]
    valid_years = sorted(set(str(y) for y, m in available_periods))

    st.markdown("<h3 class='no-print' style='font-weight:700;'>🖼️ 公司级对标报告</h3>", unsafe_allow_html=True)

# ==========================================
    # 3. 必须先加载配置表（从而驱动后续侧边栏）
    # ==========================================
    notes_dict, ordered_modules = {}, []
    def generate_custom_analysis(m_id, df, cos, cy, py):
        """根据m_id和数据自动生成分析内容-自定义，返回字符串"""
        
        def gv(field, period):
            """获取某字段某报告期所有公司的值，返回 {公司: 值} dict"""
            if isinstance(period, tuple):
                yr, mn = period
            else:
                yr, mn = period, None
            yr = str(int(yr)) if yr == int(yr) else str(yr)
            out = {}
            for co in cos:
                msk = (df['公司']==co) & \
                      (df['报告年份'].astype(str).str.replace('.0','',regex=False)==yr) & \
                      (df['字段名']==field)
                if mn is not None and '报告月份' in df.columns:
                    msk = msk & (df['报告月份'].astype(str).str.replace('.0','',regex=False)==str(mn).replace('.0',''))
                s = df[msk]['(百万)人民币']
                # ⭐ 与图表取数逻辑（_scatter_field_getter）保持一致：同一公司/期间/字段若命中多行，只取第一条，
                # 不再 sum() 求和——求和在数据存在重复行时会把数值不合理地放大甚至变号，导致文本和图表对不上。
                if s.empty:
                    out[co] = None
                else:
                    v = s.iloc[0]
                    out[co] = None if pd.isna(v) else v
            return out
    
        def lbl(period):
            if isinstance(period, tuple):
                return format_period_label(period[0], period[1])
            return f"{int(period)}年"

        def rise_fall(field):
            cv, pv = gv(field, cy), gv(field, py)
            rises, falls = [], []
            for co in cos:
                c, p = cv.get(co), pv.get(co)
                # ✅ None 表示未披露，跳过；p==0 无法计算增幅，也跳过
                if c is None or p is None or p == 0: continue
                chg = (c - p) / abs(p)
                (rises if chg >= 0 else falls).append((co, chg))
            parts = []
            if rises:
                rises.sort(key=lambda x: -x[1])
                parts.append(f"{len(rises)}家公司上升，其中{rises[0][0]}增幅最大（+{rises[0][1]:.1%}）")
            if falls:
                falls.sort(key=lambda x: x[1])
                parts.append(f"{len(falls)}家公司下降，其中{falls[0][0]}降幅最大（{falls[0][1]:.1%}）")
            return "；".join(parts) + "。" if parts else ""
    
        def trend_only(field):
            cv, pv = gv(field, cy), gv(field, py)
            rises, falls, vals = [], [], []
            for co in cos:
                c, p = cv.get(co), pv.get(co)
                if c is None or p is None: continue  # ✅ 未披露跳过
                vals.append(c)
                (rises if c >= p else falls).append(co)
            parts = []
            if rises: parts.append(f"{len(rises)}家上升")
            if falls: parts.append(f"{len(falls)}家下降")
            if vals: parts.append(f"{lbl(cy)}均值为{sum(vals)/len(vals)/1e4:.1f}亿元")
            return "；".join(parts) + "。" if parts else ""
    
        def composition(fields_dict, year):
            field_list = list(fields_dict.keys())
            totals = {co: 0 for co in cos}
            vals = {f: {} for f in field_list}
            for f in field_list:
                fv = gv(f, year)
                for co in cos:
                    v = fv.get(co)  # ✅ 不用 or 0，保留 None
                    vals[f][co] = abs(v) if v is not None else 0
                    if v is not None:
                        totals[co] += abs(v)
        
            # ✅ 只统计有真实数据的公司
            disclosed_cos = [co for co in cos if totals[co] > 0]
            if not disclosed_cos:
                return ""
        
            dominant_counts = {f: 0 for f in field_list}
            pcts = {f: {} for f in field_list}
            for co in disclosed_cos:  # ✅ 只遍历披露公司
                tot = totals[co]
                best_f = max(field_list, key=lambda f: vals[f].get(co, 0))
                dominant_counts[best_f] += 1
                for f in field_list:
                    pcts[f][co] = vals[f].get(co, 0) / tot * 100
        
            main_field = max(dominant_counts, key=dominant_counts.get)
            main_name = fields_dict[main_field]
            avg_pct = sum(pcts[main_field].values()) / len(pcts[main_field]) if pcts[main_field] else 0
            max_co = max(pcts[main_field], key=pcts[main_field].get) if pcts[main_field] else ""
            max_pct = pcts[main_field].get(max_co, 0)
        
            return (f"{len(disclosed_cos)}家披露公司中，主要构成部分为{main_name}，"
                    f"该项目占比均值约{avg_pct:.1f}%，"
                    f"其中{max_co}占比最高（{max_pct:.1f}%）。")
    
        # ==================== 分类路由 ====================
        try:
# --- 🌟 专属定制逻辑：综合净资产 ---
            if m_id == "csm_equity":
                # 图表上的“综合净资产” = 期末股东权益 + CSM期末余额 * 0.75
                cv_eq, pv_eq = gv("期末股东权益", cy), gv("期末股东权益", py)
                cv_csm, pv_csm = gv("CSM期末余额", cy), gv("CSM期末余额", py)
                
                rises, falls = [], []
                for co in cos:
                    # 获取当期和前期的权益和CSM，如果缺失则视为0
                    c_e, p_e = cv_eq.get(co) or 0, pv_eq.get(co) or 0
                    c_c, p_c = cv_csm.get(co) or 0, pv_csm.get(co) or 0
                    
                    # 按照图表的逻辑，计算两年的“综合净资产”
                    c_total = c_e + c_c * 0.75
                    p_total = p_e + p_c * 0.75
                    
                    if p_total == 0: continue # 分母为0则跳过
                    
                    chg = (c_total - p_total) / abs(p_total)
                    (rises if chg >= 0 else falls).append((co, chg))
                
                parts = []
                if rises:
                    rises.sort(key=lambda x: -x[1])
                    parts.append(f"{len(rises)}家上升，其中{rises[0][0]}增幅最大（+{rises[0][1]:.1%}）")
                if falls:
                    falls.sort(key=lambda x: x[1])
                    parts.append(f"{len(falls)}家下降，其中{falls[0][0]}降幅最大（{falls[0][1]:.1%}）")
                
                return "综合净资产方面，" + "；".join(parts) + "。" if parts else "综合净资产较去年无明显变动。"
            
            if m_id == "nb_lost":
                cv, pv = gv("新业务亏损合同（LC）——非PAA", cy), gv("新业务亏损合同（LC）——非PAA", py)
                # ✅ 取负数，和图表展示保持一致
                cv = {co: -v if v is not None else None for co, v in cv.items()}
                pv = {co: -v if v is not None else None for co, v in pv.items()}
                rises, falls = [], []
                for co in cos:
                    c, p = cv.get(co), pv.get(co)
                    if c is None or p is None or p == 0: continue
                    chg = (c - p) / abs(p)
                    (rises if chg >= 0 else falls).append((co, chg))
                parts = []
                if rises:
                    rises.sort(key=lambda x: -x[1])
                    parts.append(f"{len(rises)}家公司上升，其中{rises[0][0]}增幅最大（+{rises[0][1]:.1%}）")
                if falls:
                    falls.sort(key=lambda x: x[1])
                    parts.append(f"{len(falls)}家公司下降，其中{falls[0][0]}降幅最大（{falls[0][1]:.1%}）")
                return "；".join(parts) + "。" if parts else ""
            # 涨跌型
            if m_id == "inc_total":   return rise_fall("保险服务收入合计")
            if m_id == "exp_total":   return rise_fall("保险服务费用合计")
            if m_id == "perf_total":  return rise_fall("保险服务业绩")
            if m_id == "inv_return":  return rise_fall("净投资回报")
            if m_id == "uw_profit":   return rise_fall("承保财务净损益")
            if m_id == "inv_profit":  return rise_fall("投资利润")
            if m_id == "net_profit":  return rise_fall("净利润")
            if m_id == "oci_profit":  return rise_fall("其他综合收益")
            if m_id == "total_profit":return rise_fall("综合收益总额")
            if m_id == "asset_trend": return rise_fall("总资产")
            if m_id == "equity_trend":return rise_fall("期末股东权益")
            if m_id == "csm_bal":     return rise_fall("CSM期末余额")
            if m_id == "nb_csm":      return rise_fall("新业务CSM（集团口径）")
    
            # 构成型（最新年）
            if m_id == "comp_1":
                return composition({
                    "采用保费分配法计量的保险合同保险服务收入": "PAA合同收入",
                    "未采用保费分配法计量的保险合同保险服务收入": "非PAA合同收入"
                }, cy)
            if m_id == "comp_2":
                return composition({
                    "合同服务边际的摊销": "合同服务边际释放",
                    "非金融风险调整的变动": "非金融风险调整变动",
                    "预计当期发生的保险服务费用": "预期保险服务费用",
                    "保险获取现金流的摊销（保险服务收入）": "保险获取现金流摊销",
                }, cy)
            if m_id == "exp_1":
                return composition({
                    "保险获取现金流的摊销（保险服务费用）": "保险获取现金流摊销",
                    "亏损部分的确认及转回": "亏损部分确认及转回",
                    "当期发生的赔款及其他相关费用": "当期赔款及费用",
                    "已发生赔款负债相关的履约现金流量变动": "已发生赔款负债变动",
                }, cy)
            if m_id == "asset_struct":
                return composition({
                    "债权投资": "债权投资(AC)",
                    "其他债权投资": "其他债权投资(FVOCI)",
                    "交易性金融资产": "交易性金融资产(FVTPL)",
                    "其他权益工具投资": "其他权益工具(指定FVOCI)",
                }, cy)
            if m_id == "csm_trans":
                return composition({
                    f"采用公允价值法计量的合同期末负债": "公允价值法",
                    f"采用修正追溯调整法计量的合同期末负债": "修正追溯法",
                    f"其他合同期末负债": "其他合同",
                }, cy)
            if m_id in ["csm_comp_lat", "csm_comp_pre"]:
                y = cy if m_id == "csm_comp_lat" else py
                return composition({
                    "新业务CSM（集团口径）": "新业务CSM",
                    "CSM计息": "CSM计息",
                    "CSM调整": "CSM调整",
                }, y)
    
            # 散点图型（X-Y相关性 + 各维度最大值）
            if m_id == "sc_profit_ratio":
                inc = gv("保险服务收入合计", cy)
                exp = gv("保险服务费用合计", cy)
                xs, ys, labels = [], [], []
                for co in cos:
                    i_v, e_v = inc.get(co), exp.get(co)
                    if i_v is None or i_v == 0:
                        continue
                    margin = (i_v - (e_v if e_v is not None else 0)) / i_v * 100
                    xs.append(i_v); ys.append(margin); labels.append(co)
                if len(xs) < 2:
                    return ""
                # np 已在模块顶部全局导入，此处不再局部 import（局部 import 会让 np 在本函数所有分支里都变成局部变量）
                z = float(np.corrcoef(xs, ys)[0, 1])
                if not np.isfinite(z):
                    return ""
                ix_x = max(range(len(xs)), key=lambda k: xs[k])
                ix_y = max(range(len(ys)), key=lambda k: ys[k])
                a_co, x_val = labels[ix_x], xs[ix_x] / divisor
                b_co, y_val = labels[ix_y], ys[ix_y]
                if z >= 0.3:
                    concl = "规模越大、利润率越高的正相关趋势较明显"
                elif z <= -0.3:
                    concl = "规模越大、利润率反而越低，呈负相关"
                else:
                    concl = "未观察到简单的收入规模越大、利润率越高的结论"
                return (f"规模与保险服务利润率的相关系数为{z:.2f}：{concl}，其中：<br>"
                        f"①规模领先：{a_co}保险服务收入{x_val:.1f}{unit_label}；"
                        f"②盈利质量领先：{b_co}保险服务利润率{y_val:.1f}%。")

            if m_id == "gr_qual_ratio":
                inc_cy, inc_py = gv("保险服务收入合计", cy), gv("保险服务收入合计", py)
                exp_cy, exp_py = gv("保险服务费用合计", cy), gv("保险服务费用合计", py)
                quad = []
                for co in cos:
                    i_cy, i_py = inc_cy.get(co), inc_py.get(co)
                    e_cy, e_py = exp_cy.get(co), exp_py.get(co)
                    if i_cy is None or i_py is None or i_py == 0 or i_cy == 0:
                        continue
                    growth = (i_cy / i_py - 1) * 100
                    m_cy = (i_cy - (e_cy if e_cy is not None else 0)) / i_cy * 100
                    m_py = (i_py - (e_py if e_py is not None else 0)) / i_py * 100
                    quad.append((co, growth, m_cy - m_py))
                if not quad:
                    return ""
                win = [t for t in quad if t[1] > 0 and t[2] > 0]
                win_names = "、".join(t[0] for t in win) if win else "无"
                best = max(quad, key=lambda t: t[2])
                worst = min(quad, key=lambda t: t[2])
                return (f"同时观察收入增长与利润率变动，零轴划分“量增/量减、质升/质降”四象限：<br>"
                        f"①{len(win)}家公司实现“量增质升”：{win_names}；"
                        f"②{best[0]}改善最多（+{best[2]:.1f}%），{worst[0]}承压最重（{worst[2]:.1f}%）。")
    
            # ==================== 双引擎盈利 ====================
            if m_id == "uw_inv_comboratio":
                # 公式需与图表 create_dual_engine_profit_chart 的 x_calc/y_calc 保持一致
                inc, exp = gv("保险服务收入合计", cy), gv("保险服务费用合计", cy)
                nr, uw, re_uw = gv("净投资回报", cy), gv("承保财务损益", cy), gv("分出再保险财务损益", cy)
                co_data = []
                for co in cos:
                    i, e = inc.get(co), exp.get(co)
                    n, u, r = nr.get(co), uw.get(co), re_uw.get(co)
                    if i is None or i == 0 or n is None or n == 0:
                        continue
                    ins_margin = (i - (e if e is not None else 0)) / i * 100
                    inv_profit = n + (u if u is not None else 0) + (r if r is not None else 0)
                    inv_margin = inv_profit / n * 100
                    # 投资服务利润率的分母是净投资回报本身；净投资回报为负时比率方向会反转，不再具有"越大越好"的可比含义
                    co_data.append({'公司': co, '保险利润率': ins_margin, '投资利润率': inv_margin, '净投资回报为正': n > 0})
                if not co_data: return ""
                ins_med = np.median([d['保险利润率'] for d in co_data])
                inv_med = np.median([d['投资利润率'] for d in co_data])
                ins_p75 = np.percentile([d['保险利润率'] for d in co_data], 75)
                inv_p75 = np.percentile([d['投资利润率'] for d in co_data], 75)
                parts = []
                for label, cond in [("保险投资服务利润双高效驱动", lambda d: d['保险利润率'] >= ins_p75 and d['投资利润率'] >= inv_p75),
                                    ("主要由保险服务利润驱动", lambda d: d['保险利润率'] >= ins_med and d['投资利润率'] < inv_med),
                                    ("主要由投资服务利润驱动", lambda d: d['保险利润率'] < ins_med and d['投资利润率'] >= inv_med)]:
                    names = [d['公司'] for d in co_data if cond(d)]
                    if names: parts.append(f"{'、'.join(names)}{label}")
                intro = "，".join(parts) + "：" if parts else ""
                ins_leader = max(co_data, key=lambda x: x['保险利润率'])
                # "最高"优先只在净投资回报为正（比率方向正常）的公司中比较；若当期全部为负，才退回全体比较并加提示
                inv_candidates = [d for d in co_data if d['净投资回报为正']]
                inv_leader = max(inv_candidates or co_data, key=lambda x: x['投资利润率'])
                inv_note = "" if inv_candidates else "（注：当期各公司净投资回报均为负，该比率方向反转，数值仅供参考）"
                return (f"{intro}<br>①保险服务利润率最高：{ins_leader['公司']}{ins_leader['保险利润率']:.1f}%；"
                        f"②投资服务利润率最高：{inv_leader['公司']}{inv_leader['投资利润率']:.1f}%{inv_note}。")
            
            # ==================== 资产负债匹配 ====================
            if m_id == "alm_ratio":
                rows = []
                for co in cos:
                    eq_cy, eq_py, liab_oci, fvoci_bond = gv("期末股东权益", cy).get(co), gv("期末股东权益", py).get(co), gv("可转损益的负债OCI", cy).get(co), gv("FVOCI债券公允价值", cy).get(co)
                    if any(v is None for v in [eq_cy, eq_py, liab_oci, fvoci_bond]): continue
                    avg_eq = (eq_cy + eq_py) / 2
                    if avg_eq == 0: continue
                    x, y = liab_oci / avg_eq * 100, fvoci_bond / avg_eq * 100
                    mismatch = abs(x + y)
                    if np.isfinite(mismatch): rows.append((co, x, y, mismatch))
                if not rows: return ""
                min_m, max_m = min(rows, key=lambda t: t[3]), max(rows, key=lambda t: t[3])
                return f"越接近Y=-X虚线，表示资产端与负债端OCI的方向和幅度越匹配：<br>①当期OCI错配率最小：{min_m[0]}（{min_m[3]:.1f}%）；②当期OCI错配率最大：{max_m[0]}（{max_m[3]:.1f}%）。"
           
            # ==================== 综合净资产-规模与价值 ====================
            if m_id == "nas_sv_ratio":
                # 公式需与图表 create_nas_sv_chart 的 x_calc/y_calc 保持一致：
                # X=总资产增长率；Y=综合净资产增长率，综合净资产=期末股东权益+CSM期末余额×0.75
                ta_cy, ta_py = gv("总资产", cy), gv("总资产", py)
                eq_cy, eq_py = gv("期末股东权益", cy), gv("期末股东权益", py)
                csm_cy, csm_py = gv("CSM期末余额", cy), gv("CSM期末余额", py)
                rows = []
                for co in cos:
                    a_cy, a_py = ta_cy.get(co), ta_py.get(co)
                    e_cy, e_py = eq_cy.get(co), eq_py.get(co)
                    if a_cy is None or a_py is None or a_py == 0 or e_cy is None or e_py is None or e_py == 0:
                        continue
                    comp_cy = e_cy + (csm_cy.get(co) or 0) * 0.75
                    comp_py = e_py + (csm_py.get(co) or 0) * 0.75
                    if comp_py == 0:
                        continue
                    x = (a_cy / a_py - 1) * 100
                    y = (comp_cy / comp_py - 1) * 100
                    rows.append((co, x, y))
                if not rows: return ""
                total = len(rows)
                below = sum(1 for _, x, y in rows if y < x)
                x_leader = max(rows, key=lambda t: t[1])
                y_leader = max(rows, key=lambda t: t[2])
                return (f"{below}/{total}家位于Y=X虚线下方，说明总资产扩张快于综合净资产积累（含股东分红）：<br>①总资产增速最高：{x_leader[0]}{x_leader[1]:.1f}%；②综合净资产增速最高：{y_leader[0]}{y_leader[1]:.1f}%。")

            # ==================== 综合净资产-资本积累与未赚利润储备 ====================
            if m_id == "nas_pf_ratio":
                # 公式需与图表 create_nas_pf_chart 的 x_calc/y_calc 保持一致：X=净资产增长率，Y=CSM增长率
                eq_cy, eq_py = gv("期末股东权益", cy), gv("期末股东权益", py)
                csm_cy, csm_py = gv("CSM期末余额", cy), gv("CSM期末余额", py)
                rows = []
                for co in cos:
                    e_cy, e_py = eq_cy.get(co), eq_py.get(co)
                    c_cy, c_py = csm_cy.get(co), csm_py.get(co)
                    if e_cy is None or e_py is None or e_py == 0 or c_cy is None or c_py is None or c_py == 0:
                        continue
                    x = (e_cy / e_py - 1) * 100
                    y = (c_cy / c_py - 1) * 100
                    rows.append((co, x, y))
                if not rows: return ""
                x_med = np.median([r[1] for r in rows])
                y_med = np.median([r[2] for r in rows])
                # 净资产增长（高于中位数），CSM 减少
                group_a = [co for co, x, y in rows if x >= x_med and y < 0]
                # 净资产增长不明显（低于中位数），CSM 大幅增加（高于中位数）
                group_b = [co for co, x, y in rows if x < x_med and y >= y_med]
                a_txt = "、".join(group_a) if group_a else "无"
                b_txt = "、".join(group_b) if group_b else "无"
                x_leader = max(rows, key=lambda t: t[1])
                y_leader = max(rows, key=lambda t: t[2])
                return (f"{a_txt}主要为净资产增长，CSM减少；相反，{b_txt}净资产增长不明显，CSM大幅增加：<br>①净资产增速最高：{x_leader[0]}{x_leader[1]:.1f}%；②CSM增速最高：{y_leader[0]}{y_leader[1]:.1f}%。")

            # ==================== 股东回报 ====================
            if m_id == "shr_ret_ratio":
                # 公式需与图表 create_shr_ret_chart 的 x_calc/y_calc 保持一致：X=净资产（绝对额），Y=ROE
                eq_cy, eq_py = gv("期末股东权益", cy), gv("期末股东权益", py)
                profit_cy = gv("净利润", cy)
                rows = []
                for co in cos:
                    e_cy, e_py, p = eq_cy.get(co), eq_py.get(co), profit_cy.get(co)
                    if e_cy is None or e_py is None or p is None:
                        continue
                    avg_eq = (e_cy + e_py) / 2
                    if avg_eq == 0:
                        continue
                    roe = p / avg_eq * 100
                    rows.append((co, e_cy / divisor, roe))
                if not rows: return ""
                scale_leader = max(rows, key=lambda t: t[1])
                roe_leader = max(rows, key=lambda t: t[2])
                roe_med = np.median([r[2] for r in rows])
                return (f"净资产规模与ROE并非天然正相关，实际盈利能力还需结合一次性收益、分红/增资等因素综合判断：<br>①净资产规模最大：{scale_leader[0]}{scale_leader[1]:.1f}{unit_label}；②ROE最高：{roe_leader[0]}{roe_leader[2]:.1f}%；样本ROE中位数约{roe_med:.1f}%。")

            # ==================== 新业务质量 ====================
            if m_id == "nb_qual_ratio":
                # 公式需与图表 create_nb_qual_chart 的 x_calc/y_calc（含 _nb_ifrs_margin）保持一致：
                # X=新业务CSM增长率；Y=新业务IFRS利润率变动率=本期新业务IFRS利润率-对比期新业务IFRS利润率
                csm_cy, csm_py = gv("新业务CSM（集团口径）", cy), gv("新业务CSM（集团口径）", py)
                lc_cy, lc_py = gv("新业务亏损合同（LC）——非PAA", cy), gv("新业务亏损合同（LC）——非PAA", py)
                pv_cy, pv_py = gv("新业务未来现金流入现值", cy), gv("新业务未来现金流入现值", py)
                rows = []
                for co in cos:
                    c_cy, c_py = csm_cy.get(co), csm_py.get(co)
                    p_cy, p_py = pv_cy.get(co), pv_py.get(co)
                    if c_cy is None or c_py is None or c_py == 0 or p_cy is None or p_cy == 0 or p_py is None or p_py == 0:
                        continue
                    x = (c_cy / c_py - 1) * 100
                    m_cy = (c_cy + (lc_cy.get(co) or 0)) / p_cy * 100
                    m_py = (c_py + (lc_py.get(co) or 0)) / p_py * 100
                    y = m_cy - m_py
                    rows.append((co, x, y))
                if not rows: return ""
                total = len(rows)
                win = [co for co, x, y in rows if x > 0 and y > 0]
                win_txt = "、".join(win) if win else "无"
                worst = min(rows, key=lambda t: t[1] + t[2])
                stable_cnt = sum(1 for _, _, y in rows if abs(y) <= 3)
                stable_txt = f"；③大部分公司新业务IFRS利润率基本保持稳定（{stable_cnt}/{total}家变动幅度在±3%以内）" if stable_cnt > total / 2 else ""
                return f"从新业务CSM的量与新业务IFRS利润率的价同时判断新业务质量，零轴形成量价四象限：<br>①量价同时改善：{win_txt}；②综合承压最明显：{worst[0]}{stable_txt}。"
            
            # 趋势型（两年比较，说上升/下降）
            if m_id == "csm_ratio":
                cv = {co: None for co in cos}
                pv = {co: None for co in cos}
                for co in cos:
                    df_co = df[df['公司']==co]
                    def get_ratio(yr):
                        if isinstance(yr, tuple):
                            y_, m_ = yr
                        else:
                            y_, m_ = yr, None
                        def s(k):
                            msk = (df_co['报告年份'].astype(str).str.replace('.0','',regex=False)==str(y_).replace('.0','')) & (df_co['字段名'].str.contains(k,na=False))
                            if m_ is not None and '报告月份' in df_co.columns:
                                msk = msk & (df_co['报告月份'].astype(str).str.replace('.0','',regex=False)==str(m_).replace('.0',''))
                            return df_co[msk]['(百万)人民币'].sum()
                        a,b,c = s('CSM期末'),s('LRC非亏损部分期末'),s('LRC亏损部分期末')
                        denom = b+c-a
                        return a/denom if denom!=0 else None
                    cv[co] = get_ratio(cy)
                    pv[co] = get_ratio(py)
                rises, falls, vals = [], [], []
                for co in cos:
                    c, p = cv.get(co), pv.get(co)
                    if c is None or p is None: continue
                    vals.append(c)
                    (rises if c >= p else falls).append(co)
                avg = sum(vals)/len(vals) if vals else 0
                parts = []
                if rises: parts.append(f"{'、'.join(rises)}占比上升")
                if falls: parts.append(f"{'、'.join(falls)}占比下降")
                parts.append(f"{lbl(cy)}均值约{avg:.1%}")
                return "；".join(parts) + "。"
    
            if m_id == "nb_struct":
                # 新业务CSM利润率趋势
                cy_v = gv("新业务CSM（集团口径）", cy)
                cy_pv = gv("新业务未来现金流入现值（盈利）", cy)
                py_v = gv("新业务CSM（集团口径）", py)
                py_pv = gv("新业务未来现金流入现值（盈利）", py)
                rises, falls, vals = [], [], []
                for co in cos:
                    c = cy_v.get(co,0) / cy_pv.get(co,1) if cy_pv.get(co) else None
                    p = py_v.get(co,0) / py_pv.get(co,1) if py_pv.get(co) else None
                    if c is None or p is None: continue
                    vals.append(c)
                    (rises if c >= p else falls).append(co)
                avg = sum(vals)/len(vals) if vals else 0
                parts = []
                if rises: parts.append(f"{'、'.join(rises)}CSM利润率上升")
                if falls: parts.append(f"{'、'.join(falls)}CSM利润率下降")
                parts.append(f"{lbl(cy)}均值约{avg:.1%}")
                return "；".join(parts) + "。"
    
            if m_id == "exp_struct":
                # 各项占比最大的公司
                acq = gv("获取费用", cy)
                maint = gv("维持费用", cy)
                non_ = gv("非履约费用", cy)
                max_acq = max((co for co in cos if acq.get(co)), key=lambda c: acq.get(c,0), default="")
                max_maint = max((co for co in cos if maint.get(co)), key=lambda c: maint.get(c,0), default="")
                max_non = max((co for co in cos if non_.get(co)), key=lambda c: non_.get(c,0), default="")
                return (f"获取费用绝对金额最高：{max_acq}；"
                        f"维持费用绝对金额最高：{max_maint}；"
                        f"非履约费用绝对金额最高：{max_non}。")
    
            if m_id == "tax_profit":
                return f"各公司税前利润与净利润对比详见图表，关注有效税率变动情况。"
    
            if m_id == "prof_mix":
                ins = gv("保险利润", cy)
                inv = gv("投资利润", cy)
                ins_dom, inv_dom, no_data = [], [], []
                for co in cos:
                    c_ins = ins.get(co) or 0
                    c_inv = inv.get(co) or 0
                    tot = c_ins + c_inv
                    if tot == 0:
                        no_data.append(co)  # ✅ 没数据的单独列出，不乱归类
                        continue
                    ins_pct = c_ins / tot
                    (ins_dom if ins_pct >= 0.5 else inv_dom).append(
                        f"{co}（保险利润占比{ins_pct:.0%}）"
                    )
                parts = []
                if ins_dom: parts.append(f"保险利润占主导：{'、'.join(ins_dom)}")
                if inv_dom: parts.append(f"投资利润占主导：{'、'.join(inv_dom)}")
                if no_data: parts.append(f"未披露：{'、'.join(no_data)}")
                return "；".join(parts) + "。" if parts else ""
    
        except Exception as e:
            return f"（自动生成失败：{e}）"
    
        return ""  # 无话术的m_id返回空
    st.markdown("<div class='no-print'>", unsafe_allow_html=True)
    with st.expander("📥公司内容分析与注释输入", expanded=False):
        st.markdown("""
            <div style='background:linear-gradient(135deg,#00338D,#0865EE); 
            border-radius:10px; padding:14px 18px; margin-bottom:16px;
            display:flex; align-items:center; justify-content:space-between;'>
                <span style='color:white; font-size:15px; font-weight:bold;'>
                    获取官方注释表模板
                </span>
                <span style='color:rgba(255,255,255,0.8); font-size:12px;'>
                    需要安全码验证
                </span>
            </div>
        """, unsafe_allow_html=True)
    
        col_pwd, col_btn = st.columns([3, 1])
        with col_pwd:
            pwd_input = st.text_input("", placeholder="请输入安全码...", 
                                       type="password", key="template_pwd",
                                       label_visibility="collapsed")
        with col_btn:
            check_btn = st.button("🔓验证下载", use_container_width=True)
    
        if check_btn:
            # 🌟 核心修复 1：一点击按钮，立刻清空之前的旧文件缓存
            if 'filled_notes_excel' in st.session_state:
                del st.session_state['filled_notes_excel']
                
            if pwd_input == "KPMG666":
                try:
                    import requests
                    from io import BytesIO
                    import openpyxl
        
                    url = "https://raw.githubusercontent.com/crystalplum07/bm-platform/main/templates/step7-%E5%9B%BE%E7%89%87%E5%86%85%E5%AE%B9%E5%88%86%E6%9E%90%E5%92%8C%E6%B3%A8%E9%87%8A%E6%A8%A1%E6%9D%BF.xlsx"
                    r = requests.get(url, timeout=15)
        
                    if r.status_code == 200:
                        wb = openpyxl.load_workbook(BytesIO(r.content))
                        ws = wb.active
                        header = {cell.value: cell.column for cell in ws[1]}
                        mid_col = header.get('模块ID')
                        custom_col = header.get('分析内容-自定义')
        
                        if mid_col and custom_col and 'integrated_data' in st.session_state:
                            df_for_gen = st.session_state['integrated_data'].copy()
                            _cos = st.session_state.get('selected_cos_cache', [])
                            _valid_years = sorted([y for y in df_for_gen['报告年份'].dropna().astype(str).str.replace(".0","",regex=False).unique() if y.isdigit()])
                            _cy = int(_valid_years[-1]) if _valid_years else 2025
                            _py = int(_valid_years[-2]) if len(_valid_years) > 1 else 2024
        
                            for row in ws.iter_rows(min_row=2):
                                m_id_val = row[mid_col - 1].value
                                if not m_id_val: continue
                                generated = generate_custom_analysis(
                                    str(m_id_val).strip(), df_for_gen, _cos, _cy, _py
                                )
                                if generated:
                                    row[custom_col - 1].value = generated
        
                        output = BytesIO()
                        wb.save(output)
                        output.seek(0)
                        
                        # 🌟 核心修复 2：只有走到这一步，完全成功了，才把文件放入缓存
                        st.session_state['filled_notes_excel'] = output.getvalue()
                        st.success("✅ 验证成功，分析内容已自动填充，请点击下方按钮下载")
                    else:
                        st.error("❌ 文件获取失败")
                except Exception as e:
                    st.error(f"❌ 错误：{e}")
            else:
                st.error("❌ 安全码错误")
        
        # ✅ 下载按钮：严格依赖本次验证成功放入的 session_state
        if 'filled_notes_excel' in st.session_state:
            st.download_button(
                label="🔓点击下载（已自动填充分析内容）",
                data=st.session_state['filled_notes_excel'],
                file_name=f"注释表_{st.session_state.get('selected_cos_cache', [''])[0] if st.session_state.get('selected_cos_cache') else ''}_{2025}年.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
        st.divider()        
        use_default = st.toggle("使用默认注释表", value=True, key="use_default_notes")
        df_notes = None
        if use_default:
            try:
                df_notes = pd.read_excel("https://raw.githubusercontent.com/crystalplum07/bm-platform/main/templates/step7-%E5%9B%BE%E7%89%87%E5%86%85%E5%AE%B9%E5%88%86%E6%9E%90%E5%92%8C%E6%B3%A8%E9%87%8A%E6%A8%A1%E6%9D%BF.xlsx")
                st.session_state['step7_default_df_notes'] = df_notes.copy()
                st.session_state['step7_notes_active_source'] = 'default'
                st.success("✅ 内置默认注释表加载成功")
            except Exception as e:
                cached_default = st.session_state.get('step7_default_df_notes')
                if isinstance(cached_default, pd.DataFrame) and not cached_default.empty:
                    df_notes = cached_default.copy()
                    st.warning("⚠️ 默认注释表暂时无法重新下载，继续使用本次会话缓存。")
                else:
                    st.error(f"❌ 加载失败：{e}")
        else:
            st.info("💡 请上传包含【图片文件名】【模块ID】【一级分类】【二级分类】【对应图表名称】【分析内容】【注释内容】的 Excel")
            notes_file = st.file_uploader(
                "上传 Excel", type=['xlsx', 'xls'], key="step7_notes_uploader"
            )
            if notes_file:
                df_notes = pd.read_excel(notes_file)
                st.session_state['step7_custom_df_notes'] = df_notes.copy()
                st.session_state['step7_custom_notes_name'] = getattr(notes_file, 'name', '')
                st.session_state['step7_notes_active_source'] = 'custom'
            else:
                cached_custom = st.session_state.get('step7_custom_df_notes')
                if isinstance(cached_custom, pd.DataFrame) and not cached_custom.empty:
                    df_notes = cached_custom.copy()
                    cached_name = st.session_state.get('step7_custom_notes_name', '已上传文件')
                    st.caption(f"继续使用本次会话已读取的注释表：{cached_name}")

        if df_notes is not None:
            # 统一清洗文本前后的空格
            for col in ['一级分类', '二级分类', '对应图表名称', '模块ID']:
                if col in df_notes.columns:
                    df_notes[col] = df_notes[col].astype(str).str.strip().replace(['nan', 'NaN', 'NAN', 'None'], '')
            
            # 🌟 核心智能归类补丁：如果二级分类为空白，强制塞入“全部”
            if '二级分类' in df_notes.columns:
                df_notes['二级分类'] = df_notes['二级分类'].apply(lambda x: "全部" if str(x).strip() == "" else str(x).strip())
            
            has_img = '图片文件名' in df_notes.columns
            for _, r in df_notes.iterrows():
                m_id = str(r.get('模块ID', '')).strip()
                if not m_id: continue
                img_val = str(r.get('图片文件名', '')).strip() if has_img and pd.notna(r.get('图片文件名')) else ''
                notes_dict[m_id] = {
                    'title': str(r.get('对应图表名称', '')).strip(),
                    # ✅ 拆成两个字段分别读取
                    'analysis_default': str(r.get('分析内容-默认', '')).strip() if pd.notna(r.get('分析内容-默认')) else '',
                    'analysis_custom': str(r.get('分析内容-自定义', '')).strip() if pd.notna(r.get('分析内容-自定义')) else '',
                    'note': str(r.get('注释内容', '')).strip() if pd.notna(r.get('注释内容')) else '',
                    'image_file': img_val if img_val.lower() != 'nan' else ''
                }
                if m_id not in ordered_modules: ordered_modules.append(m_id)
            # 存入全局缓存
            st.session_state['df_notes'] = df_notes
            st.session_state['step7_df_notes'] = df_notes.copy()
    st.markdown("</div>", unsafe_allow_html=True)
    # ==========================================
    # 4. 侧边栏：智能多级联动导航（防越界护盾版）
    # ==========================================
    print_mode, active_m_id, active_level_context = False, None, ""
    with st.sidebar:
        st.markdown("<h3 style='color: #00338D; font-size: 18px;'>公司报告导航</h3>", unsafe_allow_html=True)
        if 'df_notes' in st.session_state and st.session_state['df_notes'] is not None and not st.session_state['df_notes'].empty:
            df_n = st.session_state['df_notes']
            
            # 过滤提取有效的一级分类
            first_levels = [x for x in df_n['一级分类'].unique() if str(x).strip() != ""]
            main_nav = st.radio("📁 一级模块", first_levels + ["🖨️ 一键显示全部 (打印/导出)"], key="s7_m")

            if main_nav == "🖨️ 一键显示全部 (打印/导出)":
                print_mode = True
                if not st.session_state.get("pdf_export_mode", False):
                    st.info('竖版适合文字多的页面，横版适合宽图表。勾选"背景图形"以保留颜色。')
                    components.html("""
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        <button onclick="printAs('portrait')" style="width:100%; padding:11px; background:#00338D; color:white; border:none; border-radius:6px; cursor:pointer; font-weight:bold; font-size:13px;">
                            🖨️ 导出竖版 A4 PDF
                        </button>
                        <button onclick="printAs('widescreen')" style="width:100%; padding:11px; background:#008578; color:white; border:none; border-radius:6px; cursor:pointer; font-weight:bold; font-size:13px;">
                            🖨️ 导出横版 16:9 PDF
                        </button>
                    </div>
                    <script>
                    // 页面加载时就注入默认横版 16:9，不等用户点
                    (function() {
                        const doc = window.parent.document;
                        const old = doc.getElementById('dynamic-print-style');
                        if (old) old.remove();
                        const style = doc.createElement('style');
                        style.id = 'dynamic-print-style';
                        // 把 widescreen 那个改成
                        style.innerHTML = '@page { size: 338.67mm 190.5mm; margin: 8mm 12mm; } @page :first { margin: 0mm; } @page :last { margin: 0mm; }';
                        doc.head.appendChild(style);
                    })();
                    
                    function printAs(mode) {
                        const doc = window.parent.document;
                        const old = doc.getElementById('dynamic-print-style');
                        if (old) old.remove();
                        const style = doc.createElement('style');
                        style.id = 'dynamic-print-style';
                        if (mode === 'widescreen') {
                            style.innerHTML =
                            '@page { size: landscape; margin: 5mm; }';
                        } else {
                            style.innerHTML =
                            '@page { size: A4 portrait; margin: 10mm; }';
                        }
                        doc.head.appendChild(style);
                        setTimeout(() => window.parent.print(), 150);
                    }
                    </script>
                    """, height=100)         
            else:
                df_sub1 = df_n[df_n['一级分类'] == main_nav]
                
                # 🌟 获取真实的二级分类列表（去除“全部”这个名字，稍后我们手动加上去，保证“全部”永远在第一位）
                raw_sec_levels = [x for x in df_sub1['二级分类'].unique() if x != "全部"]
                
                # 如果这个一级分类下，所有的图表都没有二级分类（即 raw_sec_levels 为空）
                if len(raw_sec_levels) == 0:
                    charts = [x for x in df_sub1['对应图表名称'].unique() if x]
                    chart_nav = st.radio("具体图表", charts, key="s7_c")
                    matched = df_sub1[df_sub1['对应图表名称'] == chart_nav]
                    active_m_id = matched.iloc[0]['模块ID'] if not matched.empty else None
                else:
                    # 如果有正常的二级分类，则强行加上“全部”作为第一选项
                    sub_nav = st.radio("📂 二级模块", ["全部"] + raw_sec_levels, key="s7_s")

                    if sub_nav != "全部":
                        df_sub2 = df_sub1[df_sub1['二级分类'] == sub_nav]
                        charts = [x for x in df_sub2['对应图表名称'].unique() if x]
                        chart_nav = st.radio("具体图表", charts, key="s7_c")
                        matched = df_sub2[df_sub2['对应图表名称'] == chart_nav]
                        active_m_id = matched.iloc[0]['模块ID'] if not matched.empty else None
                    else:
                        # 🌟 选择了“全部”，展示该一级分类下的所有图表（包括那些原本没有二级分类而被归入“全部”的图）
                        charts = [x for x in df_sub1['对应图表名称'].unique() if x]
                        chart_nav = st.radio("具体图表 (当前二级：全部)", charts, key="s7_c_all")
                        matched = df_sub1[df_sub1['对应图表名称'] == chart_nav]
                        active_m_id = matched.iloc[0]['模块ID'] if not matched.empty else None
        else:
            st.warning("⚠️ 请先加载包含层级信息的注释表")

    # ==========================================
    # 5. 全局配置与图片上传 (UI极致压缩)
    # ==========================================
    st.markdown("<div class='no-print'>", unsafe_allow_html=True)
    with st.expander("⚙️ 公司级图表设置与图片覆盖", expanded=False):
        # --- 第一排：基础设置 ---
        c0, c1, c2, c3, c4 = st.columns([1, 2, 1, 1, 1])   
        with c0:
            type_options = sorted([
                str(x).strip() for x in df_raw["公司类型"].dropna().unique()
                if str(x).strip() not in ["", "nan", "None"]
            ])
        
            if "s7_company_types" not in st.session_state:
                st.session_state["s7_company_types"] = ["全部"]

            # 兼容旧会话中残留的英文显示值；组件内部始终使用中文原始值。
            type_value_aliases = {
                "All": "全部",
                "Leading": "头部",
                "Top tier": "头部",
                "Foreign-invested": "外资系",
                "Bank-affiliated": "银行系",
                "Mid-sized": "中型",
                "Small": "小型",
                "Pension": "养老",
                "Health": "健康",
            }
            canonical_type_options = ["全部"] + type_options
            saved_types = st.session_state.get("s7_company_types", ["全部"])
            saved_types = [
                type_value_aliases.get(str(value), value)
                for value in saved_types
            ]
            saved_types = [
                value for value in saved_types if value in canonical_type_options
            ] or ["全部"]
            st.session_state["s7_company_types"] = saved_types
        
            selected_types_raw = st.multiselect(
                "公司类型",
                options=canonical_type_options,
                default=saved_types,
                key="s7_company_types"
            )
        
            # 规则：选“全部”或清空 = 全部；否则按勾选类型筛选
            if (not selected_types_raw) or ("全部" in selected_types_raw):
                selected_types = ["全部"]
                df_filtered = df_raw.copy()
            else:
                selected_types = selected_types_raw
                df_filtered = df_raw[df_raw["公司类型"].astype(str).str.strip().isin(selected_types)].copy()
        with c1: 
            raw_ordered_cos = list(dict.fromkeys(df_filtered['公司'].dropna().tolist()))
            selected_cos = st.multiselect("展示公司", options=raw_ordered_cos, default=raw_ordered_cos)
        with c2: 
            unit_label = st.selectbox("显示单位", ["十亿元", "亿元", "百万元", "十万元"])
            divisor = {"十亿元": 1000, "亿元": 100, "百万元": 1, "十万元": 0.1}[unit_label]
        with c3: highlight_co = st.selectbox("特定追踪", ["无"] + selected_cos)
        with c4: enable_ai = st.toggle("一键AI分析", value=False)
        
        # --- 第二排：🌟 新增的自定义排序功能 ---
        st.markdown("<hr style='margin: 5px 0 15px 0;'>", unsafe_allow_html=True)
        sc1, sc2, sc3 = st.columns([2, 2, 3])
        with sc1:
            # 抓取当前数据中所有可用的指标字段
            available_fields = sorted([str(x) for x in df_filtered['字段名'].unique() if str(x).strip() not in ['nan', 'None', '']])
            sort_field = st.selectbox("📊 图表展示顺序依据", ["默认（总资产 降序）"] + available_fields)
        with sc2:
            sort_order = st.radio("排序方向", ["降序 (从大到小) ⬇️", "升序 (从小到大) ⬆️"], horizontal=True)

        # 🌟 核心引擎：在传给后续画图程序前，对 selected_cos 进行洗牌重排
        # 判断：默认选项 → 使用【总资产】降序；否则使用用户选择字段
        if selected_cos:
            # 确定最终用来排序的字段、升降序
            if sort_field == "默认（总资产 降序）":
                active_sort_field = "总资产"
                is_desc = True
            else:
                active_sort_field = sort_field
                is_desc = "降序" in sort_order

            # 提取所选指标在【本期】的数据
            _sort_cy_mask = df_filtered['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(current_period[0]).replace('.0', '')
            if current_period[1] is not None and '报告月份' in df_filtered.columns:
                _sort_cy_mask = _sort_cy_mask & (df_filtered['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(current_period[1]).replace('.0', ''))
            df_sort = df_filtered[(df_filtered['字段名'] == active_sort_field) & _sort_cy_mask]

            # 兜底判断：找不到总资产/目标指标数据时，维持原始顺序
            if df_sort.empty:
                if sort_field != "默认（总资产 降序）":
                    st.warning(f"⚠️ {format_period_label(current_period[0], current_period[1])}暂无【{active_sort_field}】数据，保持原始顺序")
            else:
                val_col = "(百万)人民币" if "(百万)人民币" in df_sort.columns else df_sort.columns[-1]

                # 建立 公司名称 -> 数值 的映射字典
                sort_map = {}
                for _, r in df_sort.iterrows():
                    val = pd.to_numeric(r.get(val_col, np.nan), errors='coerce')
                    sort_map[str(r['公司']).strip()] = val

                # 缺失数据兜底规则
                default_val = float('-inf') if is_desc else float('inf')
                # 统一清洗公司名称，防止空格匹配失败
                selected_cos = sorted(
                    selected_cos,
                    key=lambda x: sort_map.get(str(x).strip()) if pd.notna(sort_map.get(str(x).strip())) else default_val,
                    reverse=is_desc
                )

        # ✅ 将洗牌后的公司列表写入缓存，下方图表直接取用
        st.session_state['selected_cos_cache'] = selected_cos

        HIGHLIGHT_COLOR, HL_BOX_LINE, HL_BOX_FILL = "#00338D", "rgba(0,51,141,0.35)", "rgba(0,51,141,0.03)"
        
        # --- 第三排：图片上传 ---
        st.markdown("---")
        st.caption("📸 手动上传图片（png或jpg）")
        if 'manual_upload_images' not in st.session_state: st.session_state.manual_upload_images = {}
        uploaded_files = st.file_uploader(
            "拖入截图文件",
            type=['png', 'jpg'],
            accept_multiple_files=True,
            key="step7_screenshot_uploader",
        )
        
        if uploaded_files and ordered_modules:
            code_rendered_mids = {"summary_table", "csm_growth_chart", "another_code_chart"} 
            non_code_modules = [m for m in ordered_modules if m not in code_rendered_mids]
            
            cols = st.columns(2)
            for i, file in enumerate(uploaded_files):
                with cols[i % 2]:
                    get_name = lambda m: "不匹配/跳过" if m == "不匹配/跳过" else notes_dict.get(m, {}).get('title', m)
                    sel_mid = st.selectbox(
                        f"图片 {file.name} 对应：", 
                        options=["不匹配/跳过"] + non_code_modules, 
                        format_func=get_name, 
                        key=f"up_{i}"
                    )
                    if sel_mid != "不匹配/跳过": 
                        st.session_state.manual_upload_images[sel_mid] = file
                    st.image(file, use_column_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    # ==========================================
    # 6. AI 引擎与辅助显示函数 (去重并压缩逻辑)
    # ==========================================
    @st.cache_data(show_spinner=False)
    def _call_llm_api_cached(data_str, field_name, period_label, unit_str, user_api_key, api_base, api_model):
        try:
            import openai
            client = openai.OpenAI(api_key=user_api_key, base_url=api_base)
            prompt = f"你是资深四大精算专家。几家险企{period_label}【{field_name}】数据(单位:{unit_str}):{data_str}。请一句话点评(指出极值与趋势)，不超60字。"
            res = client.chat.completions.create(model=api_model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
            return f"<b><span style='color:#00338D'></span></b> {extract_ai_response_text(res)}"
        except Exception as e: return f"<span style='color:#C00000; font-size:12px;'>⚠️ AI报错: {str(e)}</span>"

    def generate_ai_insight(df, field_name, is_pct=False):
        if not enable_ai or df is None or df.empty or not field_name: return ""
        try:
            cy_label = format_period_label(current_period[0], current_period[1])
            _cy_mask = df['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(current_period[0]).replace('.0', '')
            if current_period[1] is not None and '报告月份' in df.columns:
                _cy_mask = _cy_mask & (df['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(current_period[1]).replace('.0', ''))
            d_sub = df[(df.get('字段名', df.get('指标名称', pd.Series(''))).str.contains(field_name, na=False)) & _cy_mask & (df['公司'].isin(selected_cos))] if '字段名' in df.columns or '指标名称' in df.columns else df[df['公司'].isin(selected_cos)]
            if d_sub.empty: return ""
            val_col = "(百万)人民币" if "(百万)人民币" in d_sub.columns else d_sub.columns[-1]

            ukey, ubase, umodel = st.session_state.get('api_key', "").strip(), st.session_state.get('base_url', "https://api.deepseek.com"), st.session_state.get('model_name', "deepseek-flash")
            if ukey:
                return _call_llm_api_cached(", ".join([f"{r['公司']}:{r[val_col]:.2f}" for _, r in d_sub.iterrows()]), field_name, cy_label, "百分比" if is_pct else unit_label, ukey, ubase, umodel)
            avg, max_r, min_r, fmt, mlt = d_sub[val_col].mean(), d_sub.loc[d_sub[val_col].idxmax()], d_sub.loc[d_sub[val_col].idxmin()], "{:.1f}%" if is_pct else "{:.1f}", 100 if is_pct else (1/divisor)
            return f"<b> </b>{cy_label}【{field_name}】均值 <b>{fmt.format(avg*mlt)}</b>。<b>{max_r['公司']}</b> 最高，<b>{min_r['公司']}</b> 最低。"
        except Exception as e: return f"<span style='color:#C00000;'>⚠️ 数据报错: {e}</span>"

    def join_note_parts(*parts):
        """用中文分号连接注释片段，并仅在整条注释末尾保留句号。"""
        cleaned = []
        for part in parts:
            if part is None:
                continue
            text = str(part).strip()
            if not text or text.lower() == "nan":
                continue
            text = re.sub(r"[；;。．.]+\s*$", "", text)
            if text:
                cleaned.append(text)
        return "；".join(cleaned) + "。" if cleaned else ""

    def display_bottom_note(nt_text):
        if nt_text and str(nt_text).lower() != 'nan':
            normalized_note = join_note_parts(nt_text)
            st.markdown(f'<div style="text-align: left;margin-top: 1px; margin-bottom: 0px; padding-left: 5px;text-align: left;"><p style="margin: 0; color: #888; font-size: 12px; font-style: italic;">* 注释：{normalized_note}</p></div>', unsafe_allow_html=True)

    def show_chart(fig,p_mode,m_id=None):
        if not fig:return
        if p_mode:
            # 打印页面的 CSS（.plotly-graph-div{width:100%!important;height:auto!important}）会强制图表铺满页面宽度
            SCATTER_PRINT_H = 425
            H={"csm_trans":440,"oci_deep":280,"nb_struct":125,"csm_ratio_trend":450,"nb_margin_trend":450,"csm_maturity_table":460,
               "uw_inv_comboratio":SCATTER_PRINT_H,"sc_profit_ratio":SCATTER_PRINT_H,"gr_qual_ratio":SCATTER_PRINT_H,"alm_ratio":SCATTER_PRINT_H,
               "nas_sv_ratio":SCATTER_PRINT_H,"nas_pf_ratio":SCATTER_PRINT_H,"shr_ret_ratio":SCATTER_PRINT_H,"nb_qual_ratio":SCATTER_PRINT_H}
            h=H.get(m_id,380)
            fig.update_layout(
                autosize=False,
                width=1500,
                height=h,
                margin=dict(t=35,b=15,l=15,r=15)
            )
            st.plotly_chart(fig,use_container_width=False,config={"displayModeBar":False})
        else:
            fig.update_layout(autosize=True)
            st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})


    # ==========================================
    # 📊 图表生成核心逻辑区 (已剥离内置标题，完全适配动态引擎)
    # ==========================================

    # --- 1.新业务相关比例 ---
    def create_financial_summary_table(df, cos, highlight_co="无", current_period=None, comparison_period=None):
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)
        col_names, c1, c2, c3, c4, c5, c6, c7, c8 = [], [], [], [], [], [], [], [], []
        for co in cos:
            df_co = df[df['公司'] == co]
            def get_val(y, kw, m=None):
                mask = (df_co['报告年份'].astype(str)==str(y)) & (df_co['字段名']==kw)
                dedup_cols = ['公司','报告年份','字段名']
                if m is not None and '报告月份' in df_co.columns:
                    mask = mask & (df_co['报告月份'].astype(str)==str(m))
                    dedup_cols = ['公司','报告年份','报告月份','字段名']
                s = df_co[mask].drop_duplicates(subset=dedup_cols)['(百万)人民币']
                if s.empty: return None
                v = s.sum(min_count=1)
                return None if pd.isna(v) else v
            def calc(n, d, is_growth=False):
                if n is None or d is None: return "未披露"
                if d == 0: return "-"
                ratio = (n / d) - 1 if is_growth else (n / d)
                is_positive = n > d if is_growth else ratio >= 0
                return f"{abs(ratio):.0%}" if is_positive else f"-{abs(ratio):.0%}"
            eq_cy, eq_py = get_val(cy, '期末股东权益', cy_month), get_val(py, '期末股东权益', py_month)
            np_cy, np_py = get_val(cy, '净利润', cy_month), get_val(py, '净利润', py_month)
            csm_end, csm_beg = get_val(cy, 'CSM期末余额', cy_month), get_val(cy, 'CSM期初余额', cy_month)
            nb_cy, nb_py = get_val(cy, '新业务CSM（集团口径）', cy_month), get_val(py, '新业务CSM（集团口径）', py_month)
            amort_cy, rev_cy, rev_py = get_val(cy, 'CSM摊销', cy_month), get_val(cy, '保险服务收入合计', cy_month), get_val(py, '保险服务收入合计', py_month)
            liab_cy, liab_py = get_val(cy, '期末保险合同负债总额', cy_month), get_val(py, '期末保险合同负债总额', py_month)
            paa_cy, paa_py = get_val(cy, 'PAA期末余额合计', cy_month), get_val(py, 'PAA期末余额合计', py_month)
            col_names.append(co)
            c1.append(calc(eq_cy, eq_py, True)); c2.append(calc(np_cy, np_py, True))
            c3.append(calc(csm_end, csm_beg, True)); c4.append(calc(nb_cy, nb_py, True))
            c5.append("未披露" if amort_cy is None or csm_end is None else ("-" if (denom5:=csm_end-amort_cy)==0 else f"{abs(-amort_cy/denom5):.0%}"))
            c6.append("未披露" if nb_cy is None or amort_cy is None else ("-" if amort_cy==0 else f"{abs(-nb_cy/amort_cy):.0%}"))
            c7.append(calc(rev_cy, rev_py, True))
            c8.append("未披露" if any(v is None for v in [liab_cy, paa_cy, liab_py, paa_py]) else calc(liab_cy+paa_cy, liab_py+paa_py, True))
        headers = ["公司名称", "净资产<br>%变化", "净利润<br>%变化", "CSM<br>%变化", "NB CSM<br>%变化", "CSM摊销比例", "CSM持续率", "保险服务收入<br>%变化", "保险合同净负债余额<br>%变化"]
        current_hl = str(highlight_co).strip()
        html = "<table style='width:100%;border-collapse:collapse;font-family:sans-serif;font-size:11px;margin-bottom:15px;'><tr style='background-color:#00338D;color:white;text-align:center;font-weight:bold;'>"
        for idx, h in enumerate(headers):
            html += f"<th style='padding:6px 4px;{'text-align:left;' if idx==0 else 'text-align:center;'}border:1.5px solid white;'>{h}</th>"
        html += "</tr>"
        for i, co in enumerate(col_names):
            row_vals = [c1[i], c2[i], c3[i], c4[i], c5[i], c6[i], c7[i], c8[i]]
            is_hl = (str(co).strip() == current_hl)
            bg = HL_BOX_FILL if is_hl else ("white" if i % 2 == 0 else "#F8F9FA")
            base = f"background-color:{bg};padding:4px;font-size:11px;" + ("border-top:1.5px solid #00338D;border-bottom:1.5px solid #00338D;font-weight:bold;" if is_hl else "border:1px solid #EAEAEA;")
            s_first = base + f"text-align:left;color:#333333;{'border-left:1.5px solid #00338D;' if is_hl else ''}"
            s_mid = base + f"text-align:center;{'color:#00338D;border-left:none;border-right:none;' if is_hl else 'color:#444444;'}"
            s_last = base + f"text-align:center;{'color:#00338D;border-right:1.5px solid #00338D;border-left:none;' if is_hl else 'color:#444444;'}"
            html += f"<tr><td style='{s_first}'>{co}</td>"
            for idx, v in enumerate(row_vals):
                style = s_last if idx == len(row_vals)-1 else s_mid
                if v == "未披露":
                    cell_style = style.replace(f"background-color:{bg};", "background-color:#CDCDCD;").replace("color:#444444;", "color:white;").replace("color:#00338D;", "color:white;")
                    html += f"<td style='{cell_style}'>未披露</td>"
                else:
                    html += f"<td style='{style}'>{v}</td>"
            html += "</tr>"
        return html + "</table>"  
    
    # --- 2.柱状图和比例环 ---
    def create_profit_mixed_chart(df, cos, title_prefix, show_lbl, gap, div, unit_str, highlight_co="无",
                                   current_period=None, comparison_period=None, selected_cos=None):
        """
        混合利润图（已改造 ✅）
        显示保险利润 vs 投资利润的圆环图 + 柱状图组合
        """
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        
        if current_period is None or comparison_period is None:
            # 兜底：使用数据中的年份
            years = sorted(df['报告年份'].dropna().astype(str).unique())
            if len(years) >= 2:
                py, cy = years[-2], years[-1]
            else:
                py, cy = years[-1], years[-1]
            cy_label, py_label = f"{cy}年", f"{py}年"
            cy_label_sl, py_label_sl = cy_label, py_label
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            cy = str(cy_year)
            py = str(py_year)
            cy_label, py_label = format_period_label_ml(cy_year, cy_month), format_period_label_ml(py_year, py_month)
            cy_label_sl, py_label_sl = format_period_label(cy_year, cy_month), format_period_label(py_year, py_month)
        
        colors = {'PI': '#FFD6EB', 'PS': '#00B8F5', 'CI': '#FD349C', 'CS': '#00338D'}
        n = len(selected_cos)
        sub_titles = [f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos]
        
        # 动态计算安全间距
        safe_h_gap = 0.03 if n <= 1 else min(0.03, 0.8 / (n - 1))
        
        fig = make_subplots(
            rows=2, cols=n,
            row_heights=[0.18, 0.82],
            subplot_titles=sub_titles,
            shared_yaxes=True,
            vertical_spacing=0.15,
            horizontal_spacing=safe_h_gap,
            specs=[[{"type": "domain"}] * n, [{"type": "xy"}] * n]
        )
        
        txt = dict(textposition='outside', textfont=dict(size=12), constraintext='none', cliponaxis=False) if show_lbl else dict()
        
        # 过滤数据：先按报告期筛选
        df_filtered = df.copy()
        if '报告月份' in df_filtered.columns:
            # 如果有报告月份，按报告期精确筛选
            df_cy = filter_df_by_period(df_filtered, cy_year, cy_month) if current_period else df_filtered[df_filtered['报告年份'].astype(str) == cy]
            df_py = filter_df_by_period(df_filtered, py_year, py_month) if comparison_period else df_filtered[df_filtered['报告年份'].astype(str) == py]
        else:
            df_cy = df_filtered[df_filtered['报告年份'].astype(str) == cy]
            df_py = df_filtered[df_filtered['报告年份'].astype(str) == py]
        
        for i, co in enumerate(selected_cos):
            col, df_c_cy = i + 1, df_cy[df_cy['公司'] == co]
            df_c_py = df_py[df_py['公司'] == co]
            
            def v(df_c, f):
                return df_c[df_c['字段名'] == f]['(百万)人民币'].sum() / div
            
            pi, ps = v(df_c_py, '投资利润'), v(df_c_py, '保险利润')
            ci, cs = v(df_c_cy, '投资利润'), v(df_c_cy, '保险利润')
            
            tot_c = ci + cs
            pct_ci = (ci / tot_c * 100) if tot_c != 0 else 0
            pct_cs = (cs / tot_c * 100) if tot_c != 0 else 0
            
            # 圆环显示值
            if ci >= 0 and cs >= 0:
                v_ci, v_cs = ci, cs
            elif ci > 0 and cs <= 0:
                v_ci, v_cs = 1, 0
            elif ci <= 0 and cs > 0:
                v_ci, v_cs = 0, 1
            else:
                v_ci, v_cs = abs(ci), abs(cs)
            
            htext = [
                f"投资利润: {ci:.1f}<br>实际占比: {pct_ci:.1f}%",
                f"保险利润: {cs:.1f}<br>实际占比: {pct_cs:.1f}%"
            ]
            
            fig.add_trace(go.Pie(
                labels=['投资', '保险'],
                values=[v_ci, v_cs],
                marker_colors=[colors['CI'], colors['CS']],
                hole=0.75,
                textinfo='none',
                hovertext=htext,
                hoverinfo='label+text',
                showlegend=False,
                sort=False
            ), row=1, col=col)
    
            if i == 0:
                for nm, cl in [(f"{py_label_sl} 投资利润", colors['PI']), (f"{py_label_sl} 保险利润", colors['PS']),
                               (f"{cy_label_sl} 投资利润", colors['CI']), (f"{cy_label_sl} 保险利润", colors['CS'])]:
                    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                               marker=dict(color=cl, symbol='square', size=15), name=nm, showlegend=True), row=2, col=col)
            
            x_lbl = [py_label, cy_label]
            fig.add_trace(go.Bar(x=x_lbl, y=[pi, ci], marker_color=[colors['PI'], colors['CI']],
                                 text=[f"{pi:.0f}", f"{ci:.0f}"] if show_lbl else None,
                                 showlegend=False, **txt), row=2, col=col)
            fig.add_trace(go.Bar(x=x_lbl, y=[ps, cs], marker_color=[colors['PS'], colors['CS']],
                                 text=[f"{ps:.0f}", f"{cs:.0f}"] if show_lbl else None,
                                 showlegend=False, **txt), row=2, col=col)
            
            is_hl = (str(co).strip() == str(highlight_co).strip())
            bg_fill = HL_BOX_FILL if is_hl else "rgba(0,0,0,0)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="lightgray", width=1)
            fig.add_shape(type="rect", xref=f"x{col if col > 1 else ''} domain", yref="paper",
                          x0=-0.05, x1=1.05, y0=0, y1=1.13, fillcolor=bg_fill, line=line_dict, layer="below")
        
        for ann in fig.layout.annotations:
            if "<b>" in str(ann.text):
                ann.update(y=1.05, font=dict(size=13, weight="bold"))
        
        fig.update_layout(
            barmode='group', bargap=gap, bargroupgap=0.0, height=500,
            margin=dict(t=50, b=100, l=40, r=20),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.15)
        )
        fig.update_xaxes(type='category', showgrid=False, tickangle=0, tickfont=dict(color='gray'))
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor='lightgray', showticklabels=False)
        return fig

    # --- 3.保险服务收入等单指标柱状图（已改造 ✅） ---
    def create_kpmg_chart(df, field_name, title_prefix, show_labels, pct_font_size, global_gap,
                           highlight_co="无", current_period=None, comparison_period=None,
                           divisor=1, selected_cos=None):
        if selected_cos is None:
            selected_cos = []
        d = df[df['公司'].isin(selected_cos)].copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)

        if current_period is None or comparison_period is None:
            # 兜底：老逻辑，只按年份取（不区分月份）
            years = sorted(d['报告年份'].dropna().unique())
            py_year = years[-2] if len(years) >= 2 else years[-1]
            cy_year = years[-1] if years else None
            py_month = cy_month = None
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period

        if field_name == "保险服务业绩":
            df_inc = d[d['字段名'] == "保险服务收入合计"].copy()
            df_exp = d[d['字段名'] == "保险服务费用合计"].copy()
            if '报告月份' in d.columns and current_period is not None:
                df_inc = df_inc.set_index(['公司', '报告年份', '报告月份'])['(百万)人民币']
                df_exp = df_exp.set_index(['公司', '报告年份', '报告月份'])['(百万)人民币']
                res_series = df_inc - df_exp
                df_plot = res_series.reset_index(); df_plot.columns = ['公司', '报告年份', '报告月份', 'value']
            else:
                df_inc = df_inc.set_index(['公司', '报告年份'])['(百万)人民币']
                df_exp = df_exp.set_index(['公司', '报告年份'])['(百万)人民币']
                res_series = df_inc - df_exp
                df_plot = res_series.reset_index(); df_plot.columns = ['公司', '报告年份', 'value']
        else:
            df_plot = d[d['字段名'] == field_name].copy().rename(columns={'(百万)人民币': 'value'})

        df_plot['value'] = df_plot['value'] / divisor
        y_old, y_new = str(py_year), str(cy_year)
        fig = go.Figure()
        color_map = {(y_old, str(py_month)): "#1E49E2", (y_new, str(cy_month)): "#00338D"}
        
        # 🌟 提前计算全局极值，用来设定灰色占位柱的高度和标签偏移量
        valid_vals = df_plot['value'].dropna()
        all_max = valid_vals.max() if not valid_vals.empty else 100
        abs_max = valid_vals.abs().max() if not valid_vals.empty else 100
        fixed_offset = all_max * 0.2 
        placeholder_h = abs_max * 0.15 if abs_max > 0 else 10

        def _pick(yr, mo):
            # 🌟 有月份的话，年份+月份一起过滤，避免同一年份多个月份的数据混在一起
            if mo is not None and '报告月份' in df_plot.columns:
                return df_plot[(df_plot['报告年份'] == str(yr)) & (df_plot['报告月份'].astype(str) == str(mo))]
            return df_plot[df_plot['报告年份'] == str(yr)]

        for yr, mo in [(y_old, py_month), (y_new, cy_month)]:
            df_yr = _pick(yr, mo).set_index('公司').reindex(selected_cos).reset_index()
            
            # 🌟 动态构建图表参数：遇到空值自动换成灰色“未披露”柱子
            y_vals, m_colors, t_texts, t_colors, t_pos = [], [], [], [], []
            for v in df_yr['value']:
                if pd.isna(v):  # 如果数据缺失
                    y_vals.append(placeholder_h)
                    m_colors.append("#CDCDCD")
                    t_texts.append("未披露")
                    t_colors.append("white")
                    t_pos.append("inside")
                else:           # 如果有真实数据
                    y_vals.append(v)
                    m_colors.append(color_map[(yr, str(mo))])
                    t_texts.append(f"{v:.1f}" if show_labels and v != 0 else "")
                    t_colors.append("#333333")
                    t_pos.append("outside")

            fig.add_trace(go.Bar(
                name=format_period_label(yr, mo), 
                x=df_yr['公司'], 
                y=y_vals, 
                marker_color=m_colors, 
                text=t_texts, 
                textposition=t_pos, 
                textfont=dict(size=12, color=t_colors),
                cliponaxis=False,
                textangle=0,          # 🌟 强行让文字横向显示
                constraintext='none'  # 🌟 防止柱子过窄导致文字被隐藏
            ))

        df_old, df_new = _pick(y_old, py_month).set_index('公司'), _pick(y_new, cy_month).set_index('公司')
        for co in selected_cos:
            if co in df_old.index and co in df_new.index:
                v_old, v_new = df_old.loc[co, 'value'], df_new.loc[co, 'value']
                # 增加了安全判断，只有两期数据都有，才去画增长箭头
                if pd.notna(v_old) and pd.notna(v_new) and v_old != 0:
                    pct = (v_new - v_old) / abs(v_old)
                    color, arrow = ("#FD349C", "↗") if pct >= 0 else ("#269924", "↘")
                    fig.add_annotation(x=co, y=max(v_old, v_new) + fixed_offset, text=f"<b>{arrow} {pct:.1%}</b>", showarrow=False, font=dict(color=color, size=pct_font_size), xshift=15)
                    
        if highlight_co in selected_cos:
            idx = selected_cos.index(highlight_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx - 0.45, x1=idx + 0.45, y0=-0.08, y1=1, fillcolor=HL_BOX_FILL, line=dict(color=HL_BOX_LINE, width=1.5), layer="below")
            
        fig.update_layout(barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', bargroupgap=0.0, bargap=global_gap, legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="right", x=1), margin=dict(t=40, b=40, l=20, r=20), height=450)
        fig.update_xaxes(showgrid=False, zeroline=False, showline=False)
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1, showline=False)
        return fig

    # --- 4.保险业务构成1 ---
    # --- 4.保险业务构成1（已改造 ✅） ---
    def create_kpmg_composition_chart(df, fields, title_prefix, show_labels, label_size, bar_width, co_font_size,
                                       highlight_co="无", current_period=None, comparison_period=None,
                                       divisor=1, selected_cos=None):
        if selected_cos is None:
            selected_cos = []
        d = df[df['公司'].isin(selected_cos)].copy()
        d_struct = d[d['字段名'].isin(fields)].copy()
        d_struct['报告年份'] = d_struct['报告年份'].astype(str).str.replace(".0", "", regex=False)

        if current_period is not None and comparison_period is not None:
            # 🌟 有本期/对比期，就只展示这两个报告期，年份+月份一起过滤，避免同年多个月份混在一起
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            def _lbl(y, m): return format_period_label_ml(y, m)
            keep_periods = {(str(py_year), str(py_month)): _lbl(py_year, py_month),
                             (str(cy_year), str(cy_month)): _lbl(cy_year, cy_month)}
            period_order = [_lbl(py_year, py_month), _lbl(cy_year, cy_month)]
            if '报告月份' in d_struct.columns:
                d_struct['__period_key'] = list(zip(d_struct['报告年份'], d_struct['报告月份'].astype(str)))
            else:
                d_struct['__period_key'] = list(zip(d_struct['报告年份'], [str(cy_month)] * len(d_struct)))
            d_struct = d_struct[d_struct['__period_key'].isin(keep_periods.keys())]
            d_struct['报告年份'] = d_struct['__period_key'].map(keep_periods)
        else:
            # 兜底：老逻辑，展示数据里全部年份
            d_struct['报告年份'] = d_struct['报告年份'] + "年"
            period_order = None

        available_cos = [co for co in selected_cos if co in d_struct['公司'].unique()]
        if not available_cos: return go.Figure().add_annotation(text="无对应数据", showarrow=False)
        titles = [f"<b>{co}</b>" for co in available_cos]
        fig = make_subplots(rows=1, cols=len(available_cos), shared_yaxes=True, column_titles=titles, horizontal_spacing=0.015)
        short_names = {fields[0]: "采用保费分配法", fields[1]: "未采用保费分配法"}
        
        for i, co in enumerate(available_cos):
            d_co = d_struct[d_struct['公司'] == co].pivot(index='报告年份', columns='字段名', values='(百万)人民币')
            for f in fields:
                if f not in d_co.columns: d_co[f] = 0
            d_co = d_co.reindex(period_order if period_order is not None else sorted(d_co.index.tolist()))
            d_co['Total'] = d_co.sum(axis=1).replace(0, 1)
            paa_val, non_paa_val = d_co[fields[0]] / d_co['Total'] * 100, d_co[fields[1]] / d_co['Total'] * 100
            
            fig.add_trace(go.Bar(x=d_co.index, y=non_paa_val, name=short_names[fields[1]] if i == 0 else None, marker_color="rgb(227,207,251)", text=[f"{v:.0f}%" if v > 0 else "" for v in non_paa_val] if show_labels else None, textposition='inside', insidetextanchor='middle', textfont=dict(size=label_size), constraintext='none', textangle=0, width=bar_width, showlegend=(i == 0), legendgroup="group2", hoverinfo="none"), row=1, col=i+1)
            fig.add_trace(go.Bar(x=d_co.index, y=paa_val, name=short_names[fields[0]] if i == 0 else None, marker_color="#510DBC", text=[f"{v:.0f}%" if v > 0 else "" for v in paa_val] if show_labels else None, textposition='inside', insidetextanchor='middle', textfont=dict(size=label_size), constraintext='none', textangle=0, width=bar_width, showlegend=(i == 0), legendgroup="group1", hoverinfo="none"), row=1, col=i+1)

            is_hl = (str(co).strip() == str(highlight_co).strip())
            bg_fill = HL_BOX_FILL   if is_hl else "rgba(0,0,0,0)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="#E0E0E0", width=1)
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=-0.06, x1=1.06, y0=-0.1, y1=1.12, fillcolor=bg_fill, line=line_dict, layer="above", row=1, col=i+1)

        fig.update_layout(barmode='stack', height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=50, b=80, l=10, r=10), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
        for ann in fig.layout.annotations:
            if "<b>" in str(ann.text): ann.update(y=1.03, font=dict(size=co_font_size, color="#00338D"))
        return fig


    # --- 5.保险业务构成2 ---
    def create_kpmg_multi_composition_chart(df, field_map, color_map, title_prefix, show_labels, label_size,
                                             bar_width, co_font_size, highlight_co="无",
                                             current_period=None, comparison_period=None,
                                             selected_cos=None, divisor=1):
        """多组分构成图：只展示选中的本期与对比期两个时点"""
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        if current_period is None or comparison_period is None:
            years = sorted(df['报告年份'].dropna().astype(str).unique())
            curr_year, comp_year = years[-1], years[-2] if len(years) >= 2 else years[-1]
            curr_month, comp_month = None, None
        else:
            curr_year, curr_month = current_period
            comp_year, comp_month = comparison_period
        fields = list(field_map.keys())
        _dedup_cols = ['公司', '报告年份', '字段名']
        if '报告月份' in df.columns:
            _dedup_cols = ['公司', '报告年份', '报告月份', '字段名']
        d = df[df['公司'].isin(selected_cos)].drop_duplicates(subset=_dedup_cols, keep='first').copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)
        def _pkey(y, m):
            return f"{y}-{m}" if m is not None else str(y)
        curr_key, comp_key = _pkey(curr_year, curr_month), _pkey(comp_year, comp_month)
        d['__period_key'] = d['报告年份'] + ('-' + d['报告月份'] if '报告月份' in d.columns else '')
        d = d[d['__period_key'].isin([comp_key, curr_key])]
        if d.empty:
            return go.Figure(), pd.DataFrame()
        d_p = d[d['字段名'].isin(fields)].pivot_table(index=['公司', '__period_key'], columns='字段名', values='(百万)人民币', aggfunc='first').fillna(0)
        exist_dp_fs = [f for f in fields if f in d_p.columns]
        d_p['Total'] = d_p[exist_dp_fs].abs().sum(axis=1).replace(0, 1) if exist_dp_fs else 1
        for f in fields:
            d_p[field_map[f]] = d_p[f] / d_p['Total'] * 100 if f in d_p.columns else 0
        period_order = [comp_key, curr_key]
        lbl_map = {comp_key: format_period_label(comp_year, comp_month), curr_key: format_period_label(curr_year, curr_month)}
        lbl_ml_map = {comp_key: format_period_label_ml(comp_year, comp_month), curr_key: format_period_label_ml(curr_year, curr_month)}
        df_avg = d_p[[field_map[f] for f in fields]].groupby('__period_key').mean().reindex(period_order)
        df_avg.index = [lbl_map.get(k, k) for k in df_avg.index]
        av_cos = [co for co in selected_cos if co in d['公司'].unique()]
        if not av_cos:
            return go.Figure(), df_avg
        titles = [f"<b>{co}</b>" for co in av_cos]
        fig = make_subplots(rows=1, cols=len(av_cos), shared_yaxes=True, horizontal_spacing=0.015, column_titles=titles)
        for i, co in enumerate(av_cos):
            col_idx, d_co = i + 1, d[d['公司'] == co]
            d_co_p = d_co[d_co['字段名'].isin(fields)].pivot_table(index='__period_key', columns='字段名', values='(百万)人民币', aggfunc='first').reindex(period_order).fillna(0)
            valid_fields = [f for f in fields if f in d_co_p.columns]
            raw_total = d_co_p[valid_fields].abs().sum(axis=1) if valid_fields else pd.Series(0, index=d_co_p.index)
            d_co_p['Total'] = raw_total.replace(0, 1)
            x_labels = [lbl_ml_map.get(k, k) for k in d_co_p.index]
            for f, d_n in field_map.items():
                val = d_co_p.get(f, 0) / d_co_p['Total'] * 100
                txt_c = "white" if any(x in color_map[f] for x in ["30, 73, 226", "114, 19, 234", "0, 163, 161"]) else "black"
                fig.add_trace(go.Bar(x=x_labels, y=val, name=d_n if i == 0 else None, marker_color=color_map[f],
                    text=[f"{v:.0f}%" if abs(v) >= 1 else "" for v in val] if show_labels else None,
                    textangle=0, textposition='inside', insidetextanchor='middle',
                    textfont=dict(size=label_size, color=txt_c), constraintext='none', cliponaxis=False,
                    width=bar_width, showlegend=(i == 0), legendgroup=f), row=1, col=col_idx)
            missing_y = [100 if v == 0 else 0 for v in raw_total]
            missing_t = ["未披露" if v == 0 else "" for v in raw_total]
            fig.add_trace(go.Bar(x=x_labels, y=missing_y, marker_color="#CDCDCD", text=missing_t,
                textangle=0, textposition='inside', insidetextanchor='middle',
                textfont=dict(size=12, color="white"), constraintext='none', cliponaxis=False,
                width=bar_width, showlegend=False, hoverinfo='skip'), row=1, col=col_idx)
            is_hl = (str(co).strip() == str(highlight_co).strip())
            bg_fill = HL_BOX_FILL if is_hl else "rgba(0,0,0,0)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="rgba(0,0,0,0)", width=0)
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=-0.06, x1=1.06, y0=-0.1, y1=1.08,
                          fillcolor=bg_fill, line=line_dict, layer="above", row=1, col=col_idx)
        fig.update_layout(barmode='relative', height=400, margin=dict(t=50, b=80, l=20, r=20),
            legend=dict(orientation="h", yanchor="top", y=-0.17, xanchor="center", x=0.5, font=dict(size=10)),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        for ann in fig.layout.annotations:
            if "<b>" in str(ann.text):
                ann.update(y=1, font=dict(size=co_font_size, color="#00338D"))
        return fig, df_avg
    
    def create_kpmg_exp_chart(df, field_map, color_map, title_prefix, show_labels, label_size,
                              bar_width, co_font_size, highlight_co="无",
                              current_period=None, comparison_period=None,
                              selected_cos=None, divisor=1):
        """
        费用构成图（已改造 ✅）
        用于保险服务费用构成
        """
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        
        if current_period is None or comparison_period is None:
            years = sorted(df['报告年份'].dropna().astype(str).unique())
            if len(years) >= 2:
                period_list = [years[-2], years[-1]]
            else:
                period_list = [years[-1], years[-1]]
            curr_year, comp_year = period_list[-1], period_list[-2]
            curr_month, comp_month = None, None
        else:
            curr_year, curr_month = current_period
            comp_year, comp_month = comparison_period
            period_list = [str(comp_year), str(curr_year)]
        
        fields = list(field_map.keys())
        _dedup_cols = ['公司', '报告年份', '字段名']
        if '报告月份' in df.columns:
            _dedup_cols = ['公司', '报告年份', '报告月份', '字段名']
        d = df[df['公司'].isin(selected_cos)].drop_duplicates(subset=_dedup_cols, keep='first').copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)

        # 🌟 构造报告期唯一 key（年份+月份），同年不同月也能区分成两根柱
        def _pkey(y, m):
            return f"{y}-{m}" if m is not None else str(y)
        comp_key = _pkey(comp_year, comp_month)
        curr_key = _pkey(curr_year, curr_month)
        period_order = [comp_key, curr_key] if comp_key != curr_key else [comp_key]  # 对比期在前
        lbl_map = {comp_key: format_period_label(comp_year, comp_month), curr_key: format_period_label(curr_year, curr_month)}
        lbl_ml_map = {comp_key: format_period_label_ml(comp_year, comp_month), curr_key: format_period_label_ml(curr_year, curr_month)}
        if '报告月份' in d.columns:
            d['__period_key'] = d['报告年份'] + '-' + d['报告月份']
        else:
            d['__period_key'] = d['报告年份']

        d_filtered = d[d['__period_key'].isin(period_order)].copy()
        
        d_p = d_filtered[d_filtered['字段名'].isin(fields)].pivot_table(
            index=['公司', '__period_key'], columns='字段名', values='(百万)人民币', aggfunc='first'
        ).fillna(0)

        if d_p.empty:
            return go.Figure(), pd.DataFrame()

        exist_p_fs = [f for f in fields if f in d_p.columns]
        d_p['Total'] = d_p[exist_p_fs].abs().sum(axis=1).replace(0, 1) if exist_p_fs else 1
        for f in fields:
            d_p[field_map[f]] = d_p[f] / d_p['Total'] * 100 if f in d_p.columns else 0

        all_yrs = period_order
        df_avg = d_p[[field_map[f] for f in fields]].groupby('__period_key').mean().reindex(all_yrs)
        df_avg.index = [lbl_map.get(k, k) for k in df_avg.index]
        
        av_cos = [co for co in selected_cos if co in d_filtered['公司'].unique()]
        if not av_cos:
            return go.Figure(), pd.DataFrame()
        
        titles = [f"<b>{co}</b>" for co in av_cos]
        fig = make_subplots(rows=1, cols=len(av_cos), shared_yaxes=True, horizontal_spacing=0.015, column_titles=titles)
        
        for i, co in enumerate(av_cos):
            col_idx = i + 1
            d_co = d_filtered[d_filtered['公司'] == co]

            d_co_p = d_co[d_co['字段名'].isin(fields)].pivot_table(
                index='__period_key', columns='字段名', values='(百万)人民币', aggfunc='first'
            ).reindex(all_yrs).fillna(0)

            valid_fields = [f for f in fields if f in d_co_p.columns]
            if not valid_fields:
                d_co_p['Total'] = 1.0
            else:
                d_co_p['Total'] = d_co_p[valid_fields].abs().sum(axis=1).replace(0, 1)

            x_labels = [lbl_ml_map.get(k, k) for k in d_co_p.index]
            
            for f, d_n in field_map.items():
                val = d_co_p.get(f, 0) / d_co_p['Total'] * 100
                txt_c = "white" if any(x in color_map[f] for x in ["30, 73, 226", "114, 19, 234", "0, 163, 161"]) else "black"
                fig.add_trace(go.Bar(
                    x=x_labels, y=val, name=d_n if i == 0 else None,
                    marker_color=color_map[f],
                    text=[f"{v:.0f}%" if abs(v) >= 1 else "" for v in val] if show_labels else None,
                    textangle=0, textposition='inside', insidetextanchor='middle',
                    textfont=dict(size=label_size, color=txt_c),
                    constraintext='none', cliponaxis=False, width=bar_width,
                    showlegend=(i == 0), legendgroup=f
                ), row=1, col=col_idx)
            
            is_hl = (str(co).strip() == str(highlight_co).strip())
            bg_fill = HL_BOX_FILL if is_hl else "rgba(0,0,0,0)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="rgba(0,0,0,0)", width=0)
            fig.add_shape(type="rect", xref="x domain", yref="y domain",
                          x0=-0.06, x1=1.06, y0=-0.1, y1=1.08,
                          fillcolor=bg_fill, line=line_dict, layer="above", row=1, col=col_idx)
        
        fig.add_hline(y=0, line_color="orange", line_width=1.5, layer="below")
        
        fig.update_layout(
            barmode='relative', height=400,
            margin=dict(t=50, b=80, l=10, r=10),
            legend=dict(orientation="h", yanchor="top", y=-0.17, xanchor="center", x=0.5, font=dict(size=10)),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        for ann in fig.layout.annotations:
            if "<b>" in str(ann.text):
                ann.update(y=1, font=dict(size=co_font_size, color="#00338D"))
        
        return fig, df_avg 

    #--------利润贡献--------
    # --- 6.保险利润构成拆分（已改造 ✅） ---
    def create_profit_composition_chart(df, selected_cos, target_period, show_labels, label_size, bar_width, co_font_size, highlight_co="无", divisor=1):
        source_fields = ["合同服务边际的摊销","非金融风险调整的变动","亏损部分的确认及转回","采用保费分配法计量的保险合同保险业绩","保险利润","再保净损益"]
        # 🌟 target_period 现在是 (年份, 月份) 二元组；兼容老式的单一年份传参
        if isinstance(target_period, tuple):
            t_year, t_month = target_period
        else:
            t_year, t_month = target_period, None
        year_str = str(t_year).replace(".0", "")
        d_sub = df[(df['报告年份'].astype(str).str.replace(".0", "", regex=False) == year_str) & df['公司'].isin(selected_cos) & df['字段名'].isin(source_fields)].copy()
        if t_month is not None and '报告月份' in d_sub.columns:
            d_sub = d_sub[d_sub['报告月份'].astype(str) == str(t_month)]
        if d_sub.empty: return None, None

        d_pivot = d_sub.pivot_table(index='公司', columns='字段名', values='(百万)人民币', aggfunc='sum')
        
        for f in source_fields:
            if f not in d_pivot.columns:
                d_pivot[f] = np.nan
        
        d_pivot = d_pivot.reindex(selected_cos)
        
        profit = pd.to_numeric(d_pivot['保险利润'], errors='coerce')
        csm_amort = pd.to_numeric(d_pivot['合同服务边际的摊销'], errors='coerce')
        
        safe_profit = profit.mask(profit.abs() < 1e-9, np.nan)
        contrib_val = csm_amort / safe_profit * 100
        
        contribution_df = pd.DataFrame(contrib_val).transpose()
        contribution_df.index = ["合同服务边际释放的贡献"]

        # 🌟 修复：把 .all() 改成了 .any()，实现“只要缺一个，全盘皆灰”的严格一票否决逻辑
        no_data_cos = set(co for co in selected_cos if co in d_pivot.index and d_pivot.loc[co, source_fields].isna().any())

        d_pivot = d_pivot.fillna(0)  # 填0用于后续计算

        d_pivot['营运偏差及其他_展示'] = d_pivot['保险利润']-d_pivot['合同服务边际的摊销']-d_pivot['非金融风险调整的变动']+d_pivot['亏损部分的确认及转回']-d_pivot['采用保费分配法计量的保险合同保险业绩']-d_pivot['再保净损益']
        d_pivot['合同服务边际的释放_展示'] = d_pivot['合同服务边际的摊销']
        d_pivot['非金融风险调整的变动_展示'] = d_pivot['非金融风险调整的变动']
        d_pivot['亏损部分的确认及转回_展示'] = -d_pivot['亏损部分的确认及转回']
        d_pivot['保费分配法业务净损益_展示'] = d_pivot['采用保费分配法计量的保险合同保险业绩']
        d_pivot['再保净损益_展示'] = d_pivot['再保净损益']

        display_mapping = [
            ("亏损部分的确认及转回_展示","亏损部分的确认及转回","rgb(190,190,190)"),
            ("合同服务边际的释放_展示","合同服务边际的释放","rgb(30,73,226)"),
            ("非金融风险调整的变动_展示","非金融风险调整的变动","rgb(118,210,255)"),
            ("营运偏差及其他_展示","营运偏差及其他","rgb(114,19,214)"),
            ("保费分配法业务净损益_展示","保费分配法业务净损益","rgb(253,52,156)"),
            ("再保净损益_展示","再保净损益","rgb(9,142,126)"),
        ]
        d_pivot['Total'] = d_pivot[[i[0] for i in display_mapping]].abs().sum(axis=1).replace(0,1)

        fig = go.Figure()
        x_indices = list(range(len(d_pivot.index)))
        no_data_x = [list(d_pivot.index).index(co) for co in no_data_cos if co in d_pivot.index]

        # ✅ 先画灰色未披露占位柱。高度设为 100（因为 Y 轴范围是 -45 到 +105）
        if no_data_x:
            fig.add_trace(go.Bar(x=no_data_x, y=[100]*len(no_data_x), marker_color="#CDCDCD", width=bar_width,
                showlegend=False, text=["未披露"]*len(no_data_x), textposition='inside',
                insidetextanchor='middle', textangle=0, textfont=dict(size=label_size, color="white"), constraintext='none'))

        for col_name, legend_name, color in display_mapping:
            vals_pct = (d_pivot[col_name] / d_pivot['Total'] * 100)
            # ✅ 未披露公司值强制为0，不覆盖灰柱
            vals_pct = [0 if co in no_data_cos else v for co, v in zip(d_pivot.index, vals_pct)]
            txt_color = "white" if any(x in color for x in ["30, 73, 226","30,73,226","114, 19, 214","114,19,214","9, 142, 126","9,142,126"]) else "black"
            fig.add_trace(go.Bar(name=legend_name, x=x_indices, y=vals_pct, width=bar_width, marker_color=color,
                text=[f"{v:.0f}%" if abs(v)>=2 else "" for v in vals_pct] if show_labels else None,
                textposition='inside', textangle=0, insidetextanchor='middle',
                textfont=dict(size=label_size, color=txt_color), constraintext='none'))

        fig.update_layout(barmode='relative', height=550, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=20, b=80, l=220, r=80),
            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="right", x=-0.05, traceorder="reversed", font=dict(size=11, color="#00338D")),
            yaxis=dict(side='right', showgrid=False, range=[-45,105], tickmode='array', showticklabels=True,
                tickvals=[-40,-20,0,20,40,60,80,100], ticktext=["-40%","-20%","0%","20%","40%","60%","80%","100%"],
                zeroline=True, zerolinecolor="#F7860C"))

        if highlight_co and highlight_co != "无" and highlight_co in d_pivot.index:
            idx = list(d_pivot.index).index(highlight_co)
            # 🌟 修复常量的缺失，直接写入颜色值
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=0, y1=1.08, fillcolor="rgba(0, 51, 141, 0.05)", line=dict(color="rgba(0, 51, 141, 0.85)", width=1.5), layer="above")

        fig.update_xaxes(showgrid=False, zeroline=False, tickvals=x_indices,
            ticktext=[f"<span style='font-size:{co_font_size}px;color:#00338D;'><b>{co}</b></span>" for co in d_pivot.index], side="top")
        
        return fig, contribution_df

    # --- 数据预处理补充 (7,8用) ---
    target_fields = ['净投资回报', '承保财务损益', '分出再保险财务损益']
    df_clean = df_filtered[df_filtered['字段名'].isin(target_fields)].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名'], keep='first')
    df_pivot_5 = df_clean.pivot_table(index=['公司', '报告年份', '报告月份'], columns='字段名', values='(百万)人民币').fillna(0).reset_index()
    df_pivot_5['承保财务净损益'] = -df_pivot_5.get('承保财务损益',0) - df_pivot_5.get('分出再保险财务损益',0)
    df_pivot_5['投资利润'] = df_pivot_5.get('净投资回报',0) - df_pivot_5['承保财务净损益']
    df_plot_final = df_pivot_5.melt(id_vars=['公司', '报告年份', '报告月份'], value_vars=['净投资回报', '承保财务净损益', '投资利润'], var_name='指标名称', value_name='value')
    df_profit_raw = df_filtered[(df_filtered['字段名'].isin(['投资利润', '保险利润'])) & (df_filtered['公司'].isin(selected_cos))].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名'], keep='first').copy()
    df_profit_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)

# --- 7.投资收益、承保损益单柱图 ---
    def create_simple_kpmg_chart(df_source, field_name, title, show_labels, p_size, g_gap,
                                  highlight_co="无", current_period=None, comparison_period=None,
                                  selected_cos=None, divisor=1):
        """
        简单柱状图（已改造 ✅）
        用于净投资回报、承保财务净损益、投资利润
        """
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        
        if current_period is None or comparison_period is None:
            years = sorted(df_source['报告年份'].dropna().astype(str).unique())
            if len(years) >= 2:
                py, cy = years[-2], years[-1]
            else:
                py, cy = years[-1], years[-1]
            cy_year, cy_month = int(cy), None
            py_year, py_month = int(py), None
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            cy, py = str(cy_year), str(py_year)
        
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)
        
        # 按报告期筛选
        d_cy = filter_df_by_period(d, cy_year, cy_month) if current_period else d[d['报告年份'] == cy]
        d_py = filter_df_by_period(d, py_year, py_month) if comparison_period else d[d['报告年份'] == py]
        
        d_cy['value'] = d_cy['value'] / divisor
        d_py['value'] = d_py['value'] / divisor
        
        # 重新索引以匹配 selected_cos 的顺序
        d_cy = d_cy.set_index('公司').reindex(selected_cos).reset_index()
        d_py = d_py.set_index('公司').reindex(selected_cos).reset_index()
        d_cy['value'] = d_cy['value'].fillna(0)
        d_py['value'] = d_py['value'].fillna(0)
        
        fig = go.Figure()
        x_indices = list(range(len(selected_cos)))
        
        # 计算全局极值
        valid_vals = pd.concat([d_cy['value'], d_py['value']]).dropna()
        all_max = valid_vals.max() if not valid_vals.empty else 100
        abs_max = valid_vals.abs().max() if not valid_vals.empty else 100
        off = abs_max * 0.3
        placeholder_h = abs_max * 0.15 if abs_max > 0 else 10
        
        cy_label = format_period_label(cy_year, cy_month) if current_period else f"{cy}年"
        py_label = format_period_label(py_year, py_month) if comparison_period else f"{py}年"
        
        # 对比期柱子（浅蓝色，对比期在前）
        y_vals_py, m_colors_py, t_texts_py, t_colors_py, t_pos_py = [], [], [], [], []
        for v in d_py['value']:
            if pd.isna(v) or v == 0:
                y_vals_py.append(placeholder_h)
                m_colors_py.append("#CDCDCD")
                t_texts_py.append("未披露")
                t_colors_py.append("white")
                t_pos_py.append("inside")
            else:
                y_vals_py.append(v)
                m_colors_py.append("#1E49E2")
                t_texts_py.append(f"{v:.1f}" if show_labels and v != 0 else "")
                t_colors_py.append("#333333")
                t_pos_py.append("outside")

        fig.add_trace(go.Bar(
            name=py_label,
            x=x_indices,
            y=y_vals_py,
            marker_color=m_colors_py,
            text=t_texts_py,
            textposition=t_pos_py,
            textfont=dict(size=12, color=t_colors_py),
            cliponaxis=False,
            textangle=0,
            constraintext='none'
        ))

        # 当前期柱子（深蓝色，本期在后）
        y_vals_cy, m_colors_cy, t_texts_cy, t_colors_cy, t_pos_cy = [], [], [], [], []
        for v in d_cy['value']:
            if pd.isna(v) or v == 0:
                y_vals_cy.append(placeholder_h)
                m_colors_cy.append("#CDCDCD")
                t_texts_cy.append("未披露")
                t_colors_cy.append("white")
                t_pos_cy.append("inside")
            else:
                y_vals_cy.append(v)
                m_colors_cy.append("#00338D")
                t_texts_cy.append(f"{v:.1f}" if show_labels and v != 0 else "")
                t_colors_cy.append("#333333")
                t_pos_cy.append("outside")

        fig.add_trace(go.Bar(
            name=cy_label,
            x=x_indices,
            y=y_vals_cy,
            marker_color=m_colors_cy,
            text=t_texts_cy,
            textposition=t_pos_cy,
            textfont=dict(size=12, color=t_colors_cy),
            cliponaxis=False,
            textangle=0,
            constraintext='none'
        ))
        
        # 增长率箭头
        df_old, df_new = d_py.set_index('公司'), d_cy.set_index('公司')
        for i, co in enumerate(selected_cos):
            if co in df_old.index and co in df_new.index:
                v0, v1 = df_old.loc[co, 'value'], df_new.loc[co, 'value']
                if pd.notna(v0) and pd.notna(v1) and v0 != 0:
                    pct = (v1 - v0) / abs(v0)
                    arr, col = ("↗", "#FD349C") if pct >= 0 else ("↘", "#269924")
                    y_pos = max(v0, v1) + off
                    fig.add_annotation(
                        x=i, y=y_pos,
                        text=f"<b>{arr} {pct:.1%}</b>",
                        showarrow=False,
                        font=dict(color=col, size=p_size),
                        xshift=10
                    )
        
        fig.update_layout(
            barmode='group',
            bargroupgap=0.0,
            bargap=g_gap,
            margin=dict(t=40, b=60, l=20, r=20),
            height=500,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1)
        )
        
        # 高亮公司
        current_hl = str(highlight_co).strip()
        clean_cos = [str(c).strip() for c in selected_cos]
        if current_hl in clean_cos:
            idx = clean_cos.index(current_hl)
            fig.add_shape(
                type="rect", xref="x", yref="paper",
                x0=idx - 0.46, x1=idx + 0.46,
                y0=-0.12, y1=1.05,
                fillcolor=HL_BOX_FILL,
                line=dict(color=HL_BOX_LINE, width=1.5),
                layer="above"
            )
        
        x_labels = [f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos]
        fig.update_xaxes(showgrid=False, zeroline=False, tickvals=x_indices, ticktext=x_labels)
        
        # 动态Y轴范围
        y_top = max(0, all_max) + off * 1.2
        y_bottom = min(0, valid_vals.min()) * 1.15 if not valid_vals.empty else 0
        fig.update_yaxes(
            showgrid=False,
            zeroline=True,
            zerolinecolor="#E0E0E0",
            zerolinewidth=1,
            range=[y_bottom, y_top]
        )
        return fig
    # --- 9.税前和净利润补充计算 ---
    cy, cy_month = current_period
    py, py_month = comparison_period
    period_mask = (
        ((df_filtered['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(cy)) & 
         (df_filtered['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(cy_month))) |
        ((df_filtered['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(py)) & 
         (df_filtered['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(py_month)))
    )
    df_tax_sub = df_filtered[
        (df_filtered['字段名'].isin(['税前利润总额', '净利润'])) & 
        (df_filtered['公司'].isin(selected_cos)) & 
        period_mask
    ].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名'])
    df_tax_pivot = df_tax_sub.pivot_table(index=['公司', '报告年份', '报告月份'], columns='字段名', values='(百万)人民币').fillna(0).reset_index()
    denom = df_tax_pivot['税前利润总额'].replace(0, np.nan)  # ✅ 在pivot之后
    df_tax_pivot['有效税率'] = np.where(
        df_tax_pivot['税前利润总额'] != 0,
        (df_tax_pivot['税前利润总额'] - df_tax_pivot['净利润']) / denom,  # ✅ 用denom不用原列
        0
    )
    df_tax_pivot = df_tax_pivot.sort_values(['公司', '报告年份', '报告月份'])  # ⚠️ 排序必须在下面这行转换文字之前做，不然按字符串排序月份顺序会乱
    df_tax_pivot['报告年份'] = df_tax_pivot.apply(lambda r: format_period_label_ml(r['报告年份'], r['报告月份']), axis=1)
    
    def create_tax_subplot_chart(df_pivot, selected_cos, show_labels, bar_width, label_size, co_font_size, co_y_offset, highlight_co="无"):
        av_cos = [c for c in selected_cos if c in df_pivot['公司'].unique()]
        if not av_cos: return go.Figure()
        
        cols = ['税前利润总额', '净利润']
        g_max, g_min = df_pivot[cols].max().max()/divisor, df_pivot[cols].min().min()/divisor
        # 🌟 修复 1：动态计算 Y 轴底部边界。如果有负数，底部延伸；否则为 0
        y_top, y_bot, lbl_y, ph_h = g_max*1.25, min(0, g_min*1.2), g_max*1.15, g_max*0.4
        all_yrs = df_pivot['报告年份'].astype(str).unique().tolist() # 🌟 不再 sorted()：报告年份此时已是文字标签，字符串排序会把顺序搞乱；df_pivot 传入前已按真实年月排好序，用 .unique() 保留原有出现顺序即可
        
        n = len(av_cos)
        fig = make_subplots(rows=1, cols=n, shared_yaxes=True, column_titles=[f"<b><span style='color:#00338D;'>{c}</span></b>" for c in av_cos], horizontal_spacing=0.03 if n<=1 else min(0.03, 0.8/(n-1)))
        
        for nm, c in zip(cols, ['#1E49E2', '#C7A0F7']): fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color=c), name=nm, showlegend=True), row=1, col=1)

        for i, co in enumerate(av_cos):
            # 🌟 不再按'报告年份'重新排序：这一列在函数外已经被换成文字标签（比如"2025年<br>6月"），
            # 字符串排序会把"12月"排到"6月"前面（'1'<'6'），导致同年不同月份顺序错乱。
            # df_pivot 传进来之前已经按真实的年份+月份数值排好序了，这里维持原有行序即可。
            ci, d = i+1, df_pivot[df_pivot['公司']==co]
            x, yp, yn, tr = d['报告年份'].astype(str).tolist(), (d[cols[0]]/divisor).tolist(), (d[cols[1]]/divisor).tolist(), d['有效税率'].tolist()
            pr, nr, pt, nt, my, mt = [], [], [], [], [], []
            
            for vp, vn in zip(yp, yn):
                if (pd.isna(vp) or vp==0) and (pd.isna(vn) or vn==0):
                    pr.append(0); nr.append(0); pt.append(""); nt.append(""); my.append(ph_h); mt.append("未披露")
                else:
                    pr.append(vp); nr.append(vn); pt.append(f"{vp:.1f}" if show_labels and pd.notna(vp) else ""); nt.append(f"{vn:.1f}" if show_labels and pd.notna(vn) else ""); my.append(0); mt.append("")
                    
            for yy, c, t, og in [(pr, '#1E49E2', pt, 1), (nr, '#C7A0F7', nt, 2)]: fig.add_trace(go.Bar(x=x, y=yy, marker_color=c, text=t, textposition='outside', textfont=dict(size=label_size), width=bar_width, offsetgroup=og, showlegend=False, cliponaxis=False), row=1, col=ci)
            fig.add_trace(go.Bar(x=x, y=my, marker_color="#CDCDCD", text=mt, textposition='inside', insidetextanchor='middle', textfont=dict(size=12, color="white"), width=bar_width*2, showlegend=False, cliponaxis=False, hoverinfo='skip'), row=1, col=ci)
            
            for j, yr in enumerate(x):
                if pd.notna(tr[j]) and mt[j] == "": fig.add_annotation(x=yr, y=lbl_y, text=f"<b>{tr[j]:.0%}</b>", showarrow=False, font=dict(size=label_size+2, color="#97014F" if tr[j]>=0 else "#269924"), xref=f"x{ci}" if ci>1 else "x", yref="y1")
            
            hl = (str(co).strip() == str(highlight_co).strip())
            fig.add_shape(type="rect", xref=f"x{ci} domain" if ci>1 else "x domain", yref="paper", x0=-0.05, x1=1.05, y0=-0.12, y1=1.1, line=dict(color=HL_BOX_LINE if hl else "rgba(200, 200, 200, 0.3)", width=1.5 if hl else 1), fillcolor=HL_BOX_FILL   if hl else "rgba(0,0,0,0)", layer="above")

        fig.update_layout(height=550, margin=dict(t=40, b=100, l=20, r=20), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
        for i in range(1, n+1):
            # 🌟 修复 2：强行写入 categoryorder 和 categoryarray，锁死年份显示
            fig.update_xaxes(type='category', categoryorder='array', categoryarray=all_yrs, showline=True, linecolor='lightgray', linewidth=1, showgrid=False, tickfont=dict(size=10), zeroline=False, ticks="", ticklen=0, row=1, col=i)
            # 应用包含负数的新范围，开启 zeroline 分界线
            fig.update_yaxes(showline=False, showgrid=False, showticklabels=False, zeroline=True, zerolinecolor="#E0E0E0", range=[y_bot, y_top], row=1, col=i)
        for a in fig.layout.annotations:
            if "span" in a.text: a.update(y=co_y_offset, font_size=co_font_size)
            
        return fig

    # --- 10.综合收益变动趋势补充 ---
    df_fin_raw = df_filtered[(df_filtered['字段名'].isin(['净利润', '其他综合收益', '综合收益总额'])) & (df_filtered['公司'].isin(selected_cos))].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名'], keep='first').copy()
    df_fin_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)
    
    def create_financial_trend_chart_v5(df_source, field_name, title, show_labels, p_size, g_gap, highlight_co="无",
                                         current_period=None, comparison_period=None):
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'], d['value'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False), d['value'] / divisor 
        fig, x_idx, hl_co = go.Figure(), list(range(len(selected_cos))), str(highlight_co).strip()

        if current_period is None or comparison_period is None:
            cy_p, py_p, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy_p, cy_month = current_period
            py_p, py_month = comparison_period

        def _pick(yr, mo):
            m = d[d['报告年份'] == str(yr)]
            if mo is not None and '报告月份' in d.columns:
                m = m[m['报告月份'].astype(str) == str(mo)]
            return m
        
        # 🌟 提前计算出全局最大值，用来决定灰色“未披露”柱子的合适高度 (大概是最大值的 15%)
        valid_vals = d['value'].dropna()
        max_val = valid_vals.max() - valid_vals.min() if not valid_vals.empty else 100
        abs_max = valid_vals.abs().max() if not valid_vals.empty else 100
        placeholder_h = abs_max * 0.15 if abs_max > 0 else 10
        
        for yr, mo, col in [(py_p, py_month, "rgb(15, 101, 253)"), (cy_p, cy_month, "rgb(0, 51, 141)")]:
            df_yr = _pick(yr, mo).set_index('公司').reindex(selected_cos).reset_index()
            
            # 🌟 动态构建图表参数：让每一个柱子都能自定义
            y_vals, m_colors, t_texts, t_colors, t_pos = [], [], [], [], []
            for v in df_yr['value']:
                if pd.isna(v):  # 如果没有数据
                    y_vals.append(placeholder_h)
                    m_colors.append("#CDCDCD")
                    t_texts.append("未披露")
                    t_colors.append("white")
                    t_pos.append("inside")
                else:           # 如果有数据
                    y_vals.append(v)
                    m_colors.append(col)
                    t_texts.append(f"{v:.1f}" if show_labels and v != 0 else "")
                    t_colors.append("#333333") # 正常标签文字颜色
                    t_pos.append("outside")
                    
            fig.add_trace(go.Bar(
                name=format_period_label(yr, mo), 
                x=x_idx, 
                y=y_vals, 
                marker_color=m_colors, 
                text=t_texts, 
                textposition=t_pos, 
                textfont=dict(size=12, color=t_colors), 
                cliponaxis=False,
                textangle=0,            # 🌟 核心修改 1：强制文字角度为 0（绝对横向显示）
                constraintext='none'    # 🌟 核心修改 2：解除文字变形/隐藏限制，防止柱子太窄直接不显示字
            ))
            
        off, df_old, df_new = max_val * 0.12, _pick(py_p, py_month).set_index('公司'), _pick(cy_p, cy_month).set_index('公司')
        
        for i, co in enumerate(selected_cos):
            if co in df_old.index and co in df_new.index:
                v0, v1 = df_old.loc[co, 'value'], df_new.loc[co, 'value']
                # 🌟 增加了防御机制：必须保证两年都有正常数据才去算增长率箭头，防止报错
                if pd.notna(v0) and v0 != 0 and pd.notna(v1):
                    pct = (v1 - v0) / abs(v0)
                    fig.add_annotation(x=i, y=(max(v0, v1)+off if v1>=0 else min(v0, v1)-off), text=f"<b>{'↗' if pct>=0 else '↘'} {pct:.1%}</b>", showarrow=False, font=dict(color="#FD349C" if pct>=0 else "#269924", size=p_size), xshift=10, valign="bottom" if v1>=0 else "top")
                
        fig.update_layout(barmode='group', bargroupgap=0, bargap=g_gap, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=60, l=40, r=40), height=500, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.12, y1=1.05, fillcolor=HL_BOX_FILL  , line=dict(color=HL_BOX_LINE, width=1.5), layer="above")
    
        fig.update_xaxes(showline=False, showgrid=False, zeroline=False, tickvals=x_idx, ticktext=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos], ticks="", ticklen=0)
        fig.update_yaxes(showgrid=False, zeroline=True)
        return fig

    # --- 11.资产端分类 ---
    def create_asset_composition_chart(df, selected_cos, field_map, color_map, title_prefix, show_labels, label_size, bar_width, co_font_size, highlight_co="无",
                                        current_period=None, comparison_period=None):
        fields = list(field_map.keys())
        d_struct = df[(df['公司'].isin(selected_cos)) & (df['字段名'].isin(fields))].copy()
        d_struct['报告年份'] = d_struct['报告年份'].astype(str).str.replace(".0", "", regex=False)

        if current_period is None or comparison_period is None:
            cy_p, py_p, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy_p, cy_month = current_period
            py_p, py_month = comparison_period

        if '报告月份' in d_struct.columns:
            d_struct['报告月份'] = d_struct['报告月份'].astype(str).str.replace(".0", "", regex=False)
            keep = {(str(py_p), str(py_month)): format_period_label_ml(py_p, py_month),
                    (str(cy_p), str(cy_month)): format_period_label_ml(cy_p, cy_month)}
            d_struct['__key'] = list(zip(d_struct['报告年份'], d_struct['报告月份']))
            d_struct = d_struct[d_struct['__key'].isin(keep.keys())]
            d_struct['报告年份'] = d_struct['__key'].map(keep)
        else:
            keep_labels = {str(py_p): format_period_label_ml(py_p, None), str(cy_p): format_period_label_ml(cy_p, None)}
            d_struct = d_struct[d_struct['报告年份'].isin(keep_labels.keys())]
            d_struct['报告年份'] = d_struct['报告年份'].map(keep_labels)

        all_yrs = [format_period_label_ml(py_p, py_month), format_period_label_ml(cy_p, cy_month)]
        av_cos = [co for co in selected_cos if co in d_struct['公司'].unique()]
        if not av_cos: return go.Figure()

        hl_co = str(highlight_co).strip()
        fig = make_subplots(rows=1, cols=len(av_cos), shared_yaxes=True, column_titles=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in av_cos], horizontal_spacing=0.015)
        for i, co in enumerate(av_cos):
            d_co = d_struct[d_struct['公司'] == co].pivot(index='报告年份', columns='字段名', values='(百万)人民币').reindex(all_yrs).fillna(0)
            for f in fields:
                if f not in d_co.columns: d_co[f] = 0
            raw_total = d_co.sum(axis=1)
            d_co['T'] = raw_total.replace(0, 1) 
            for fn in fields:
                val_pct = d_co[fn] / d_co['T'] * 100
                fig.add_trace(go.Bar(x=d_co.index, y=val_pct, name=field_map[fn] if i==0 else None, marker_color=color_map[fn], text=[f"{v:.0f}%" if show_labels and raw_total.iloc[idx]>0 else "" for idx, v in enumerate(val_pct)], textposition='inside', insidetextanchor='middle', textfont=dict(size=label_size, color="white" if fn in ["FVOCI", "指定FVOCI", "AC"] else "black"), constraintext='none', textangle=0, cliponaxis=False, width=bar_width, showlegend=(i==0), legendgroup=fn, hoverinfo="skip"), row=1, col=i+1)
            fig.add_trace(go.Bar(x=d_co.index, y=[100 if t==0 else 0 for t in raw_total], name="未披露", marker_color="#CDCDCD", text=["未披露" if t==0 else "" for t in raw_total], textposition='inside', insidetextanchor='middle', textfont=dict(size=label_size, color="white"), constraintext='none', textangle=0, cliponaxis=False, width=bar_width, showlegend=False, hoverinfo="skip"), row=1, col=i+1)
            
            is_hl = (str(co).strip() == hl_co)
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=-0.06, x1=1.06, y0=-0.12, y1=1.12, fillcolor=HL_BOX_FILL   if is_hl else "rgba(0,0,0,0)", line=dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="rgba(0,0,0,0)", width=0), layer="above", row=1, col=i+1)

        fig.update_layout(barmode='stack', height=550, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', uniformtext=dict(minsize=label_size, mode='show'), margin=dict(t=50, b=120, l=40, r=40), legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, font=dict(size=11), itemsizing="constant"))
        for i in range(1, len(av_cos) + 1):
            fig.update_xaxes(showgrid=False, showline=False, zeroline=False, tickfont=dict(size=10), ticks="", ticklen=0, row=1, col=i)
            fig.update_yaxes(showgrid=False, range=[0, 101], showline=False, zeroline=False, tickvals=[0, 25, 50, 75, 100], ticktext=["0%", "25%", "50%", "75%", "100%"], showticklabels=(i==1), row=1, col=i)
        for ann in fig.layout.annotations:
            ann.update(y=ann.y + 0.05, font_size=co_font_size)
        return fig
  
    # --- 12. OCI变动分析 ---
    def create_oci_chart(df_raw, period, title, show_labels, co_font_size, bar_gap, selected_cos, highlight_co="无"):
        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        oci_fields = ['可转损益OCI合计', '不可转损益OCI合计', '净利润', '综合收益总额']
        d_sub = df_raw[(df_raw['字段名'].isin(oci_fields)) & (df_raw['报告年份'].astype(str) == str(t_year).replace(".0", ""))]
        if t_month is not None and '报告月份' in d_sub.columns:
            d_sub = d_sub[d_sub['报告月份'].astype(str) == str(t_month)]
        d_sub = d_sub.drop_duplicates(subset=['公司', '报告年份', '字段名'], keep='last').copy()
        if d_sub.empty: return go.Figure().update_layout(paper_bgcolor='rgba(0,0,0,0)')
        
        df_pivot = d_sub.pivot_table(index='公司', columns='字段名', values='(百万)人民币', aggfunc='sum').fillna(0)
        for f in oci_fields:
            if f not in df_pivot.columns: df_pivot[f] = 0.0
        df_pivot = df_pivot / divisor
        df_pivot['other'] = df_pivot['综合收益总额'] - df_pivot['净利润'] - df_pivot['可转损益OCI合计'] - df_pivot['不可转损益OCI合计']
        mc = {"净利润": {"c": "rgb(0,176,240)", "n": "净利润"}, "可转损益OCI合计": {"c": "rgb(253,52,156)", "n": "可转损益负债OCI变动+FVOCI债券公允价值变动"}, "不可转损益OCI合计": {"c": "rgb(114,19,234)", "n": "不可转损益负债OCI变动+FVOCI股权公允价值变动"}, "other": {"c": "rgb(127,127,127)", "n": "其他"}, "综合收益总额": {"c": "rgb(172,234,255)", "n": "综合收益总额"}}
        
        av_cos, hl_co = [c for c in selected_cos if c in df_pivot.index], str(highlight_co).strip()
        if not av_cos: return go.Figure()
        all_vals = df_pivot[['净利润', '可转损益OCI合计', '不可转损益OCI合计', 'other', '综合收益总额']].values.flatten()
        max_val, min_val = np.nanmax(all_vals), np.nanmin(all_vals)
        buffer = (max_val - min_val) * 0.8
        y_range = [min_val - buffer if min_val < 0 else min_val - abs(min_val)*0.3, max_val + buffer]
        
        fig = make_subplots(rows=1, cols=len(av_cos), shared_yaxes=True, horizontal_spacing=0.015, subplot_titles=[f"<b><span style='color:#00338D;'>{co}</span></b>" for co in av_cos])
        for col_idx, co in enumerate(av_cos):
            for m_key, m_info in mc.items():
                val = df_pivot.loc[co].get(m_key, 0)
                fig.add_trace(go.Bar(name=m_info["n"], x=[m_key], y=[val], text=[f"{val:.0f}" if (show_labels and val!=0) else ""], textposition='outside', textfont=dict(size=11, color='#00338D'), marker_color=m_info["c"], width=0.8, legendgroup=m_key, showlegend=(col_idx==0), cliponaxis=False, constraintext='none'), row=1, col=col_idx+1)
            
            is_hl = (str(co).strip() == hl_co)
            bg_fill = HL_BOX_FILL   if is_hl else "rgba(240, 240, 240, 0.35)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="rgba(210, 210, 210, 0.6)", width=1)
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=-0.04, x1=1.04, y0=-0.04, y1=1.13, fillcolor=bg_fill, line=line_dict, layer="above" if is_hl else "below", row=1, col=col_idx+1)
            fig.update_xaxes(showticklabels=False, showline=False, zeroline=False, showgrid=False, ticks="", ticklen=0, row=1, col=col_idx+1)
            
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', barmode='group', bargap=bar_gap, height=420, margin=dict(t=50, b=40, l=40, r=30), legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, font=dict(size=11)))
        fig.update_yaxes(range=y_range, showline=False, zeroline=False, showgrid=False, gridcolor='rgba(0,0,0,0)', gridwidth=0, row=1, col="all")
        for ann in fig.layout.annotations: ann.update(y=1.03, font_size=co_font_size)
        return fig

    # --- 13. OCI变动分析2 ---   
    def create_asset_liab_oci_chart(df_raw, selected_cos, bar_gap, co_font_size, show_labels, highlight_co="无",
                                     current_period=None, comparison_period=None):
        if current_period is None or comparison_period is None:
            periods = [(latest_year if i == 1 else prev_year, None) for i in range(2)]
        else:
            periods = [comparison_period, current_period]
        yr_labels = [format_period_label_ml(y, m) for y, m in periods]

        d, fns = df_raw[df_raw['字段名'].isin(['可转损益的负债OCI', 'FVOCI债券公允价值'])].copy(), ['可转损益的负债OCI', 'FVOCI债券公允价值']
        d['v'] = d['(百万)人民币'] / divisor
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)
        av_cos = [c for c in selected_cos if c in d['公司'].unique()]
        if not av_cos: return go.Figure()
        
        def gv(c, period, f):
            y, m = period
            mask = (d['公司']==c) & (d['报告年份']==str(y)) & (d['字段名']==f)
            if m is not None and '报告月份' in d.columns:
                mask = mask & (d['报告月份']==str(m))
            return d[mask]['v'].sum()
        all_v = [gv(c, p, f) for c in av_cos for p in periods for f in fns]
        g_max, g_min = max(all_v+[0.1]), min(all_v+[-0.1])
        ph_h, n, colors = max(abs(g_max), abs(g_min))*0.4, len(av_cos), {fns[0]: "rgb(0, 184, 245)", fns[1]: "rgb(253, 52, 156)"}
        
        fig = make_subplots(rows=1, cols=n, shared_yaxes=True, horizontal_spacing=0.01 if n<=1 else min(0.01, 0.8/(n-1)), subplot_titles=[f"<b><span style='color:#00338D;'>{c}</span></b>" for c in av_cos])
        for fn, c in colors.items(): fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color=c), name=fn, showlegend=True), row=1, col=1)
        
        for i, co in enumerate(av_cos):
            ci, x_lbl, v1, v2, t1, t2, my = i+1, yr_labels, [], [], [], [], []
            for p in periods:
                val1, val2 = gv(co, p, fns[0]), gv(co, p, fns[1])
                m = (val1==0 and val2==0) 
                v1.append(0 if m else val1); v2.append(0 if m else val2); my.append(ph_h if m else 0)
                t1.append("" if m else (f"{val1:.0f}" if show_labels and val1!=0 else ""))
                t2.append("" if m else (f"{val2:.0f}" if show_labels and val2!=0 else ""))
                if m: fig.add_annotation(x=format_period_label_ml(*p), y=ph_h/2, text="未披露", showarrow=False, font=dict(color="white", size=12), xref=f"x{ci}" if ci>1 else "x", yref="y1", xanchor="center", yanchor="middle")

            # 🌟 核心修改：将单一颜色改为列表 [上一年颜色, 最新年颜色]
            c1_list = ["#ACEAFF", colors[fns[0]]]
            c2_list = ["#FFD6E8", colors[fns[1]]]

            fig.add_trace(go.Bar(x=x_lbl, y=v1, marker_color=c1_list, text=t1, textposition='outside', textfont=dict(size=11, color='#00338D'), width=0.4, offsetgroup=1, showlegend=False, cliponaxis=False, constraintext='none'), row=1, col=ci)
            fig.add_trace(go.Bar(x=x_lbl, y=v2, marker_color=c2_list, text=t2, textposition='outside', textfont=dict(size=11, color='#00338D'), width=0.4, offsetgroup=2, showlegend=False, cliponaxis=False, constraintext='none'), row=1, col=ci)
            fig.add_trace(go.Bar(x=x_lbl, y=my, marker_color="#CDCDCD", width=0.8, offset=-0.4, showlegend=False, cliponaxis=False, hoverinfo='skip'), row=1, col=ci) 
            
            hl = (str(co).strip() == str(highlight_co).strip())
            xref_str = f"x{ci} domain" if ci > 1 else "x domain"
            yref_str = "y domain"
            fig.add_shape(type="rect",
                xref=xref_str, yref=yref_str,
                x0=-0.06, x1=1.06, y0=0, y1=1.08,
                fillcolor=HL_BOX_FILL if hl else "rgba(245,245,245,0.5)",
                line=dict(color=HL_BOX_LINE   if hl else "#CCCCCC", width=1.5 if hl else 1),
                layer="below")       
        fig.update_layout(barmode='group', bargap=bar_gap, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=420, margin=dict(t=50, b=80, l=20, r=20), legend=dict(orientation="h", yanchor="top", y=-0.28, x=0.5, xanchor="center"))
        y_rng = [g_min - abs(g_min)*0.3, g_max + abs(g_max)*0.3]
        
        for i in range(1, n+1):
            fig.update_xaxes(type='category', categoryorder='array', categoryarray=x_lbl, showline=False, zeroline=False, showgrid=False, ticks="", ticklen=0, row=1, col=i)
            fig.update_yaxes(range=y_rng, showline=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02, showgrid=False, gridcolor='rgba(0,0,0,0)', gridwidth=0, row=1, col=i)
        for ann in fig.layout.annotations:
            if "span" in str(ann.text): ann.update(y=1.08, font_size=co_font_size)
            
        return fig
    
    # --- 14. 计算 OCI 分析表 ---
    def calculate_oci_analysis_table(df_raw, selected_cos, highlight_co="无", current_period=None, comparison_period=None):
        f = ['AC', 'FVOCI', 'FVTPL', '指定FVOCI', 'FVOCI债券公允价值', '可转损益的负债OCI',  '期末保险合同负债总额', '可转损益OCI合计']
        df = df_raw.copy()
        df['报告年份'], df['公司'], df['字段名'] = df['报告年份'].astype(str).str.replace('.0','',regex=False).str.strip(), df['公司'].astype(str).str.strip(), df['字段名'].astype(str).str.strip()
        val_col = next((c for c in ["(百万)人民币", "(百万)原币", "数值", "值"] if c in df.columns), df.columns[-1])
        if current_period is None or comparison_period is None:
            cy, cy_month, py, py_month = latest_year, None, prev_year, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_str, py_str = str(cy).replace('.0', ''), str(py).replace('.0', '')
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)

        def _mask(d, y_str, m):
            msk = d['报告年份'] == y_str
            if m is not None and '报告月份' in d.columns:
                msk = msk & (d['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(m).replace('.0', ''))
            return msk
        
        # 🌟 先收集所有公司的数据，准备按列生成
        metrics = {k: [] for k in ["py_r", "cy_r", "f_c", "l_c", "tot", "oci_ratio"]}
        for co in selected_cos:
            d_co, data = df[(df['公司'].str.contains(co, na=False)) | (df['公司']==co)], {}
            for y, m in [(py, py_month), (cy, cy_month)]:
                y_str = str(y).replace('.0', '')
                for fn in f:
                    vs = d_co[_mask(d_co, y_str, m) & (d_co['字段名']==fn)][val_col]
                    if vs.empty: vs = d_co[_mask(d_co, y_str, m) & (d_co['字段名'].str.contains(fn, na=False))][val_col]
                    data[f"{fn}_{y_str}"] = vs.iloc[0] if not vs.empty and pd.notna(vs.iloc[0]) else 0

                    def to_num(v):
                        try:
                            if v is None or str(v).strip() in ["", "nan", "None", "未披露", "—", "-"]:
                                return 0.0
                            return float(str(v).replace(",", "").replace("(", "-").replace(")", ""))
                        except:
                            return 0.0
                    
                    def gr(y):
                        total = sum(to_num(data.get(f"{k}_{y}", 0)) for k in ['AC', 'FVOCI', 'FVTPL', '指定FVOCI'])
                        fvoci = to_num(data.get(f"FVOCI_{y}", 0))
                        return fvoci / total if abs(total) > 1e-9 else "未披露"
            v_fc, v_fp, v_lc, v_lp = data[f"FVOCI债券公允价值_{cy_str}"], data[f"FVOCI债券公允价值_{py_str}"], data[f"可转损益的负债OCI_{cy_str}"], data[f"可转损益的负债OCI_{py_str}"]
            # 负债OCI占比
            v_oci = to_num(data.get(f"可转损益OCI合计_{cy_str}", 0))
            v_liab = to_num(data.get(f"期末保险合同负债总额_{cy_str}", 0))
            
            r_oci = "未披露" if abs(v_liab) < 1e-9 else v_oci / v_liab            
            r_f = "未披露" if v_fc==0 and v_fp==0 else (v_fc/v_fp if v_fp!=0 else 0)
            r_l = "未披露" if v_lc==0 and v_lp==0 else (v_lc/v_lp if v_lp!=0 else 0)
            r_tot = "未披露" if r_f=="未披露" or r_l=="未披露" else (r_f/r_l if r_l!=0 else 0)

            metrics["py_r"].append(gr(py_str)); metrics["cy_r"].append(gr(cy_str))
            metrics["f_c"].append(r_f); metrics["l_c"].append(r_l); metrics["tot"].append(r_tot)
            metrics["oci_ratio"].append(r_oci)  
        # 🌟 开始生成 HTML：列名为公司，行名为指标。极简紧凑样式
        hl_co = str(highlight_co).strip()
        html = "<table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:11px; margin-top:-20px; margin-bottom:15px; text-align:center;'>"
        # 表头：首列是"项目"，后面全是"公司名"
        html += "<tr style='background-color:#00338D; color:white; font-weight:bold;'><th style='padding:4px 3px; border:1px solid white; text-align:left; white-space:nowrap;'>项目</th>"
        for co in selected_cos:
            is_hl = (str(co).strip() == hl_co)
            # 高亮公司的表头稍微深一点
            html += f"<th style='padding:4px 3px; border:1px solid white; background-color:{'#002266' if is_hl else '#00338D'};'>{co}</th>"
        html += "</tr>"

        # 逐行写入指标数据
        rows = [(f"FVOCI占比({py_label})", "py_r"), (f"FVOCI占比({cy_label})", "cy_r"), ("FVOCI变动", "f_c"), ("负债OCI变动", "l_c"), ("资负匹配率", "tot"),("负债OCI占比", "oci_ratio")]
        for idx, (lbl, key) in enumerate(rows):
            bg = "#F8F9FA" if idx % 2 == 0 else "white"
            html += f"<tr style='background-color:{bg}; color:#333;'><td style='padding:4px 3px; border:1px solid #EAEAEA; text-align:left; font-weight:bold; white-space:nowrap;'>{lbl}</td>"
            
            for i, co in enumerate(selected_cos):
                val, is_hl = metrics[key][i], (str(co).strip() == hl_co)
                # 复杂的样式控制：未披露优先 > 高亮优先 > 普通
                td_bg = "#CDCDCD" if val == "未披露" else ("rgba(0,51,141,0.08)" if is_hl else bg)
                tc = "white" if val == "未披露" else ("#00338D" if is_hl else "#333")
                fw = "bold" if is_hl and val != "未披露" else "normal"
                brd = "1.5px solid #00338D" if is_hl else "1px solid #EAEAEA"
                v_str = "未披露" if val == "未披露" else f"{val:.1%}"
                
                html += f"<td style='padding:3px 2px; border:{brd}; background-color:{td_bg}; color:{tc}; font-weight:{fw};'>{v_str}</td>"
            html += "</tr>"

        return html + "</table>", cy_label, py_label


# --- 15.净资产与总资产 ---
    def create_asset_trend_chart(df_source, field_name, title, show_labels, p_size, g_gap,
                                  highlight_co="无", current_period=None, comparison_period=None,
                                  selected_cos=None, divisor=1):
        """
        资产/净资产趋势图（已改造 ✅）
        用于总资产、期末股东权益
        """
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        
        if current_period is None or comparison_period is None:
            years = sorted(df_source['报告年份'].dropna().astype(str).unique())
            if len(years) >= 2:
                py, cy = years[-2], years[-1]
            else:
                py, cy = years[-1], years[-1]
            cy_year, cy_month = int(cy), None
            py_year, py_month = int(py), None
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            cy, py = str(cy_year), str(py_year)
        
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)
        
        d_cy = filter_df_by_period(d, cy_year, cy_month) if current_period else d[d['报告年份'] == cy]
        d_py = filter_df_by_period(d, py_year, py_month) if comparison_period else d[d['报告年份'] == py]
        
        # 聚合（如果有多行同一公司同一报告期）
        d_cy = d_cy.groupby('公司')['value'].sum().reset_index()
        d_py = d_py.groupby('公司')['value'].sum().reset_index()
        
        d_cy['value'] = d_cy['value'] / divisor
        d_py['value'] = d_py['value'] / divisor
        
        d_cy = d_cy.set_index('公司').reindex(selected_cos).reset_index()
        d_py = d_py.set_index('公司').reindex(selected_cos).reset_index()
        d_cy['value'] = d_cy['value'].fillna(0)
        d_py['value'] = d_py['value'].fillna(0)
        
        fig, x_idx, hl_co = go.Figure(), list(range(len(selected_cos))), str(highlight_co).strip()
        
        valid_vals = pd.concat([d_cy['value'], d_py['value']]).dropna()
        all_max = valid_vals.max() if not valid_vals.empty else 100
        abs_max = valid_vals.abs().max() if not valid_vals.empty else 100
        off = (valid_vals.max() - valid_vals.min()) * 0.12 if not valid_vals.empty else 12
        placeholder_h = abs_max * 0.15 if abs_max > 0 else 10
        
        cy_label = format_period_label(cy_year, cy_month) if current_period else f"{cy}年"
        py_label = format_period_label(py_year, py_month) if comparison_period else f"{py}年"
        
        # 对比期柱子（浅蓝色，对比期在前）
        y_vals_py, m_colors_py, t_texts_py, t_colors_py, t_pos_py = [], [], [], [], []
        for v in d_py['value']:
            if pd.isna(v) or v == 0:
                y_vals_py.append(placeholder_h)
                m_colors_py.append("#CDCDCD")
                t_texts_py.append("未披露")
                t_colors_py.append("white")
                t_pos_py.append("inside")
            else:
                y_vals_py.append(v)
                m_colors_py.append("#1E49E2")
                t_texts_py.append(f"{v:.1f}" if show_labels and v != 0 else "")
                t_colors_py.append("#333333")
                t_pos_py.append("outside")

        fig.add_trace(go.Bar(
            name=py_label,
            x=x_idx,
            y=y_vals_py,
            marker_color=m_colors_py,
            text=t_texts_py,
            textposition=t_pos_py,
            textfont=dict(size=12, color=t_colors_py),
            cliponaxis=False,
            textangle=0,
            constraintext='none'
        ))

        # 当前期柱子（深蓝色，本期在后）
        y_vals_cy, m_colors_cy, t_texts_cy, t_colors_cy, t_pos_cy = [], [], [], [], []
        for v in d_cy['value']:
            if pd.isna(v) or v == 0:
                y_vals_cy.append(placeholder_h)
                m_colors_cy.append("#CDCDCD")
                t_texts_cy.append("未披露")
                t_colors_cy.append("white")
                t_pos_cy.append("inside")
            else:
                y_vals_cy.append(v)
                m_colors_cy.append("#00338D")
                t_texts_cy.append(f"{v:.1f}" if show_labels and v != 0 else "")
                t_colors_cy.append("#333333")
                t_pos_cy.append("outside")

        fig.add_trace(go.Bar(
            name=cy_label,
            x=x_idx,
            y=y_vals_cy,
            marker_color=m_colors_cy,
            text=t_texts_cy,
            textposition=t_pos_cy,
            textfont=dict(size=12, color=t_colors_cy),
            cliponaxis=False,
            textangle=0,
            constraintext='none'
        ))
        
        # 增长率箭头
        df_old, df_new = d_py.set_index('公司'), d_cy.set_index('公司')
        for i, co in enumerate(selected_cos):
            if co in df_old.index and co in df_new.index:
                v0, v1 = df_old.loc[co, 'value'], df_new.loc[co, 'value']
                if pd.notna(v0) and pd.notna(v1) and v0 != 0:
                    pct = (v1 - v0) / abs(v0)
                    y_pos = max(v0, v1) + off if v1 >= 0 else min(v0, v1) - off
                    fig.add_annotation(
                        x=i, y=y_pos,
                        text=f"<b>{'↗' if pct >= 0 else '↘'} {pct:.1%}</b>",
                        showarrow=False,
                        font=dict(color="#FD349C" if pct >= 0 else "#269924", size=p_size),
                        xshift=10,
                        valign="bottom" if v1 >= 0 else "top"
                    )
        
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(
                type="rect", xref="x", yref="paper",
                x0=idx - 0.46, x1=idx + 0.46,
                y0=-0.12, y1=1.05,
                fillcolor=HL_BOX_FILL,
                line=dict(color=HL_BOX_LINE, width=1.5),
                layer="above"
            )
        
        fig.update_layout(
            barmode='group',
            bargroupgap=0,
            bargap=g_gap,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=40, b=60, l=40, r=40),
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(
            showline=False, showgrid=False, zeroline=False,
            tickvals=x_idx,
            ticktext=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos],
            ticks="", ticklen=0
        )
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02)
        return fig
    
    def create_equity_change_detail_table(df_raw, period, cos, divisor=1, unit_label="", highlight_co="无"):
        df = df_raw.copy()
        df["报告年份"] = df["报告年份"].astype(str).str.replace(".0", "", regex=False).str.strip()
        df["公司"] = df["公司"].astype(str).str.strip()
        df["字段名"] = df["字段名"].astype(str).str.strip()

        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        year_str = str(t_year)
        period_label = format_period_label(t_year, t_month)
    
        fields = [
            ("1", "净利润", "净利润"),
            ("2", "其他综合收益", "其他综合收益"),
            ("3", "股东权益分配", "股东权益分配"),
           # ("4", "股东增资", "股东增资"),
           # ("5", "发债", "发债"),
           # ("6", "子公司合并", "子公司合并"),
            #("7", "其他权益变动", "其他权益变动"),
            #("8=sum(1-7)", "净资产变动值", "净资产变动值"),
            ("4", "其他权益变动", "其他权益变动"),
            ("5=sum(1-4)", "净资产变动值", "净资产变动值"),
        ]
    
        val_col = "(百万)人民币" if "(百万)人民币" in df.columns else df.columns[-1]
    
        msk = (df["报告年份"] == year_str) & (df["公司"].isin(cos)) & (df["字段名"].isin([x[2] for x in fields]))
        if t_month is not None and '报告月份' in df.columns:
            msk = msk & (df["报告月份"].astype(str) == str(t_month))
        d = df[msk].drop_duplicates(subset=["公司", "报告年份", "字段名"], keep="first").copy()
    
        def to_num(v):
            if pd.isna(v):
                return np.nan
            s = str(v).strip()
            if s.lower() in ["", "nan", "none", "null", "未披露", "—", "-"]:
                return np.nan
            try:
                return float(
                    s.replace(",", "")
                     .replace("(", "-")
                     .replace(")", "")
                )
            except:
                return np.nan
    
        data_map = {}
        for _, r in d.iterrows():
            data_map[(str(r["公司"]).strip(), str(r["字段名"]).strip())] = to_num(r.get(val_col, np.nan))
    
        # 如果没有“净资产变动值”，就用 1-7 自动求和
        for co in cos:
            co = str(co).strip()
            raw_net_change = data_map.get((co, "净资产变动值"), np.nan)
            if pd.isna(raw_net_change):
                vals = [data_map.get((co, f[2]), np.nan) for f in fields[:7]]
                vals_valid = [x for x in vals if pd.notna(x)]
                if vals_valid:
                    data_map[(co, "净资产变动值")] = sum(vals_valid)
    
        def fmt(v):
            if pd.isna(v):
                return "未披露", True
            v = v / divisor
            if abs(v) < 1e-9:
                return "0.0", False
            return f"{v:,.1f}", False
    
        current_hl = str(highlight_co).strip()
    
        html = (
            "<style>"
            "@media print {"
            ".equity-detail-wrap { margin-top:4px!important; margin-bottom:6px!important; }"
            ".equity-detail-title { font-size:10px!important; margin-bottom:3px!important; }"
            ".equity-detail-table { font-size:8.5px!important; }"
            ".equity-detail-table th { padding:3px 4px!important; line-height:1.15!important; }"
            ".equity-detail-table td { padding:2.5px 4px!important; line-height:1.15!important; }"
            "}"
            "</style>"
            "<div class='equity-detail-wrap' style='margin-top:8px; margin-bottom:10px;'>"
            f"<div class='equity-detail-title' style='font-size:13px; font-weight:bold; color:#00338D; margin-bottom:5px;'>"
            f"{period_label}净资产变动明细表（I9切换后）"
            + (f"（单位：{unit_label}）" if unit_label else "")
            + "</div>"
        )
    
        html += (
            "<table class='equity-detail-table' style='width:100%; border-collapse:collapse; "
            "font-family:Microsoft YaHei, sans-serif; font-size:11px; table-layout:fixed;'>"
        )
    
        html += (
            "<tr style='background-color:#00338D; color:white; text-align:center; font-weight:bold;'>"
            "<th style='padding:5px 6px; border:1px solid white; width:10%;'>序号</th>"
            "<th style='padding:5px 6px; border:1px solid white; width:16%;'>项目</th>"
        )
    
        for co in cos:
            co_str = str(co).strip()
            html += f"<th style='padding:5px 6px; border:1px solid white;'>{co_str}</th>"
    
        html += "</tr>"
    
        for row_idx, (no, display_name, field_name) in enumerate(fields):
            row_bg = "#F8F9FA" if row_idx % 2 == 0 else "white"
    
            html += f"<tr style='background-color:{row_bg};'>"
            html += f"<td style='padding:4px 6px; text-align:center; border:1px solid #EAEAEA; color:#333;'>{no}</td>"
            html += f"<td style='padding:4px 6px; text-align:left; border:1px solid #EAEAEA; font-weight:bold; color:#333;'>{display_name}</td>"
    
            for co in cos:
                co_str = str(co).strip()
                val, missing = fmt(data_map.get((co_str, field_name), np.nan))
    
                if co_str == current_hl:
                    cell_style = (
                        "background-color:rgba(0,51,141,0.08); color:#00338D; "
                        "font-weight:bold; border:1px solid #00338D;"
                    )
                elif missing:
                    cell_style = "background-color:#CDCDCD; color:white; border:1px solid #EAEAEA;"
                else:
                    cell_style = "color:#333; border:1px solid #EAEAEA;"
    
                html += f"<td style='padding:4px 6px; text-align:center; {cell_style}'>{val}</td>"
    
            html += "</tr>"
    
        html += "</table></div>"
        return html 
         
    # --- 16. CSM 趋势 ---
    def create_csm_trend_chart(df_source, field_name, title, show_labels, p_size, g_gap,
                                highlight_co="无", current_period=None, comparison_period=None,
                                selected_cos=None, divisor=1):
        """CSM趋势图：只展示选中的本期与对比期两个时点对比"""
        if selected_cos is None:
            selected_cos = st.session_state.get('selected_cos_cache', [])
        if current_period is None or comparison_period is None:
            years = sorted(df_source['报告年份'].dropna().astype(str).unique())
            py, cy = (years[-2], years[-1]) if len(years) >= 2 else (years[-1], years[-1])
            cy_year, cy_month, py_year, py_month = int(cy), None, int(py), None
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            cy, py = str(cy_year), str(py_year)
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False)
        if '报告月份' in d.columns:
            d['报告月份'] = d['报告月份'].astype(str).str.replace(".0", "", regex=False)
        period_list, yrs = [(py_year, py_month), (cy_year, cy_month)], [format_period_label(y, m) for y, m in [(py_year, py_month), (cy_year, cy_month)]]
        d['value'] = d['value'] / divisor
        hl_co, x_idx = str(highlight_co).strip(), list(range(len(selected_cos)))
        c_map = {yrs[-1]: "#00338D", yrs[-2]: "#0F65FD"} if len(yrs) >= 2 else {yrs[0]: "#00338D"}
        all_vals = d['value'].dropna()
        all_vals = all_vals[all_vals != 0]
        y_max, y_min = (all_vals.max(), all_vals.min()) if not all_vals.empty else (100, 0)
        off, placeholder_h = (y_max - y_min) * 0.12 if not all_vals.empty else 12, y_max * 0.15 if y_max > 0 else 10
        fig = go.Figure()
        for yr in yrs:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color=c_map.get(yr, "gray")), name=yr))
        y_data, t_data, c_data, p_data, fc_data = {yr: [] for yr in yrs}, {yr: [] for yr in yrs}, {yr: [] for yr in yrs}, {yr: [] for yr in yrs}, {yr: [] for yr in yrs}
        for i, co in enumerate(selected_cos):
            co_vals = [filter_df_by_period(d, y, m)[filter_df_by_period(d, y, m)['公司'] == co]['value'].sum() if (y := yr_val[0]) and (m := yr_val[1]) is not None else d[(d['报告年份'] == str(yr_val[0])) & (d['公司'] == co)]['value'].sum() for yr_val in period_list]
            co_vals = [v if pd.notna(v) else np.nan for v in co_vals]
            if all(pd.isna(v) or v == 0 for v in co_vals):
                for yr in yrs:
                    y_data[yr].append(placeholder_h); t_data[yr].append(""); c_data[yr].append("#CDCDCD"); p_data[yr].append("inside"); fc_data[yr].append("white")
                fig.add_annotation(x=i, y=placeholder_h/2, text="未披露", showarrow=False, font=dict(color="white", size=11), xanchor="center", yanchor="middle")
            else:
                for idx, yr in enumerate(yrs):
                    v = co_vals[idx]
                    if pd.isna(v) or v == 0:
                        y_data[yr].append(placeholder_h); t_data[yr].append("未披露"); c_data[yr].append("#CDCDCD"); p_data[yr].append("inside"); fc_data[yr].append("white")
                    else:
                        y_data[yr].append(v); t_data[yr].append(f"{v:.0f}" if show_labels else ""); c_data[yr].append(c_map.get(yr, "gray")); p_data[yr].append("outside"); fc_data[yr].append("#333")
        for yr in yrs:
            fig.add_trace(go.Bar(name=yr, x=x_idx, y=y_data[yr], marker_color=c_data[yr], text=t_data[yr], textposition=p_data[yr], textfont=dict(size=12, color=fc_data[yr]), cliponaxis=False, showlegend=False))
        if len(yrs) >= 2:
            valid_yrs = [yr for yr in yrs if any(v != 0 and v != placeholder_h for v in y_data[yr])]
            if len(valid_yrs) >= 2:
                yr_old, yr_new = valid_yrs[-2], valid_yrs[-1]
                for i, co in enumerate(selected_cos):
                    v0, v1 = y_data[yr_old][i], y_data[yr_new][i]
                    if v0 != 0 and v0 != placeholder_h and v1 != 0 and v1 != placeholder_h:
                        pct = (v1 - v0) / abs(v0)
                        y_pos = max(v0, v1) + off if v1 >= 0 else min(v0, v1) - off
                        fig.add_annotation(x=i, y=y_pos, text=f"<b>{'↗' if pct >= 0 else '↘'} {pct:.1%}</b>", showarrow=False, font=dict(color="#FD349C" if pct >= 0 else "#269924", size=p_size), xshift=15, valign="bottom" if v1 >= 0 else "top")
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.12, y1=1.05, fillcolor=HL_BOX_FILL, line=dict(color=HL_BOX_LINE, width=1.5), layer="above")
        r_top = max(y_max + (y_max - y_min) * 0.15, placeholder_h * 1.3)
        fig.update_layout(barmode='group', bargroupgap=0, bargap=g_gap, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=60, l=40, r=40), height=450, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_xaxes(showline=False, showgrid=False, zeroline=False, tickvals=x_idx, ticktext=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos], ticks="", ticklen=0)
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02, range=[0 if y_min >= 0 else y_min * 1.2, r_top])
        return fig
    
    # --- CSM占比 ---
    def create_csm_ratio_chart(df, cos, show_lbl, gap, highlight_co="无",
                               current_period=None, comparison_period=None):
        """
        CSM占比图（已改造 ✅）
        显示 CSM / (LRC非亏损 + LRC亏损 - CSM) 的占比
        """
        if current_period is None or comparison_period is None:
            years = sorted(df['报告年份'].dropna().astype(str).unique())
            if len(years) >= 2:
                py, cy = years[-2], years[-1]
            else:
                py, cy = years[-1], years[-1]
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period
            cy, py = str(cy_year), str(py_year)
        
        c_bar_py, c_bar_cy = '#C7A0F7', '#1E49E2'
        c_line_py, c_line_cy = '#7213EA', '#00338D'
        hl_co, fig, x_idx = str(highlight_co).strip(), go.Figure(), list(range(len(cos)))
        
        # 辅助函数：按报告期筛选
        def filter_by_period(df_in, year, month=None):
            df_f = df_in[df_in['报告年份'].astype(str) == str(year)]
            if month is not None and '报告月份' in df_f.columns:
                df_f = df_f[df_f['报告月份'].astype(str) == str(month)]
            return df_f
        
        def get_r(y, month=None):
            data = []
            for co in cos:
                df_filtered = filter_by_period(df, y, month)
                c_df = df_filtered[df_filtered['公司'] == co]
                v = lambda k: c_df[c_df['字段名'].str.contains(k, regex=False, na=False)]['(百万)人民币'].sum()
                a, b, c = v('CSM期末'), v('LRC非亏损部分期末余额（非PAA）'), v('LRC亏损部分期末余额（非PAA）')
                denom = b + c - a
                data.append(a / denom if denom != 0 else np.nan)
            return data
        
        # 获取对比期和当前期的数据
        py_month = comparison_period[1] if comparison_period else None
        cy_month = current_period[1] if current_period else None
        py_label = format_period_label(py_year, py_month) if comparison_period else f"{py}年"
        cy_label = format_period_label(cy_year, cy_month) if current_period else f"{cy}年"

        y_py = get_r(py, py_month)
        y_cy = get_r(cy, cy_month)
        
        valid_py = [v for v in y_py if pd.notna(v)]
        valid_cy = [v for v in y_cy if pd.notna(v)]
        avg_py = np.mean(valid_py) if valid_py else 0
        avg_cy = np.mean(valid_cy) if valid_cy else 0
        
        all_valid_vals = valid_py + valid_cy
        y_max_val = max(all_valid_vals) if all_valid_vals else 0
        y_min_val = min(all_valid_vals) if all_valid_vals else 0
        
        y_range_top = y_max_val * 1.15 + 0.05
        y_range_bot = y_min_val * 1.15 - 0.05 if y_min_val < 0 else 0
        placeholder_h = max(abs(y_max_val), abs(y_min_val)) * 0.15 if all_valid_vals else 0.1
        
        # 图例
        for clr, lbl in [(c_bar_py, py_label), (c_bar_cy, cy_label)]:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                       marker=dict(symbol="square", size=10, color=clr), name=lbl))
        
        y_vals_py, t_vals_py, c_vals_py, p_vals_py, fc_vals_py = [], [], [], [], []
        y_vals_cy, t_vals_cy, c_vals_cy, p_vals_cy, fc_vals_cy = [], [], [], [], []
        
        for i, co in enumerate(cos):
            v_p, v_c = y_py[i], y_cy[i]
            m_p, m_c = (pd.isna(v_p) or v_p == 0), (pd.isna(v_c) or v_c == 0)
            
            if m_p and m_c:
                y_vals_py.append(placeholder_h)
                y_vals_cy.append(placeholder_h)
                t_vals_py.append("")
                t_vals_cy.append("")
                c_vals_py.append("#CDCDCD")
                c_vals_cy.append("#CDCDCD")
                p_vals_py.append("inside")
                p_vals_cy.append("inside")
                fc_vals_py.append("white")
                fc_vals_cy.append("white")
                fig.add_annotation(x=i, y=placeholder_h/2, text="未披露", showarrow=False,
                                  font=dict(color="white", size=11), xanchor="center", yanchor="middle")
            else:
                if m_p:
                    y_vals_py.append(placeholder_h)
                    t_vals_py.append("未披露")
                    c_vals_py.append("#CDCDCD")
                    p_vals_py.append("inside")
                    fc_vals_py.append("white")
                else:
                    y_vals_py.append(v_p)
                    t_vals_py.append(f"{v_p:.1%}" if show_lbl else "")
                    c_vals_py.append(c_bar_py)
                    p_vals_py.append("outside")
                    fc_vals_py.append("#333")
                
                if m_c:
                    y_vals_cy.append(placeholder_h)
                    t_vals_cy.append("未披露")
                    c_vals_cy.append("#CDCDCD")
                    p_vals_cy.append("inside")
                    fc_vals_cy.append("white")
                else:
                    y_vals_cy.append(v_c)
                    t_vals_cy.append(f"{v_c:.1%}" if show_lbl else "")
                    c_vals_cy.append(c_bar_cy)
                    p_vals_cy.append("outside")
                    fc_vals_cy.append("#333")
        
        fig.add_trace(go.Bar(name=py_label, x=x_idx, y=y_vals_py, marker_color=c_vals_py,
                             text=t_vals_py, textposition=p_vals_py,
                             textfont=dict(size=12, color=fc_vals_py),
                             cliponaxis=False, showlegend=False))
        fig.add_trace(go.Bar(name=cy_label, x=x_idx, y=y_vals_cy, marker_color=c_vals_cy,
                             text=t_vals_cy, textposition=p_vals_cy,
                             textfont=dict(size=12, color=fc_vals_cy),
                             cliponaxis=False, showlegend=False))
        
        too_close = abs(avg_py - avg_cy) < y_range_top * 0.05
        for i, (avg, clr, lbl) in enumerate([(avg_py, c_line_py, py_label), (avg_cy, c_line_cy, cy_label)]):
            fig.add_shape(type="line", x0=0, x1=1, y0=avg, y1=avg,
                          xref="paper", yref="y", line=dict(color=clr, dash="dash"))
            y_shift = y_max_val * 0.20 if (too_close and i == 0) else (-y_range_top * 0.03 if too_close else 0)
            fig.add_annotation(x=0.99, y=avg + y_shift, xref="paper", yref="y", xanchor="right",
                              text=f"{lbl}均值: {avg:.1%}", showarrow=False,
                              bgcolor="rgba(255,255,255,0.15)", bordercolor=clr,
                              borderwidth=1, borderpad=2, font=dict(color=clr, size=11))
        
        if hl_co in [str(c).strip() for c in cos]:
            idx = [str(c).strip() for c in cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper",
                          x0=idx - 0.46, x1=idx + 0.46, y0=-0.10, y1=1.05,
                          fillcolor=HL_BOX_FILL, line=dict(color=HL_BOX_LINE, width=1.5), layer="above")
        
        fig.update_layout(
            barmode='group', bargroupgap=0, bargap=gap, height=450,
            margin=dict(t=50, b=40, l=40, r=40),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1)
        )
        fig.update_xaxes(showline=False, showgrid=False, zeroline=False,
                         tickvals=x_idx,
                         ticktext=[f"<span style='color:#00338D;'><b>{c}</b></span>" for c in cos],
                         ticks="", ticklen=0)
        fig.update_yaxes(showgrid=False, tickformat='.0%', zeroline=True,
                         zerolinecolor='lightgray', range=[y_range_bot, max(y_range_top, placeholder_h * 1.3)])
        return fig
# --- 18. CSM概览表 (升级为纯HTML渲染) ---
    def show_csm_summary_table(df, period, selected_cos, highlight_co="无"):
        f_map = {"CSM期初余额": "CSM余额", "新业务CSM（集团口径）": "新业务CSM", "CSM计息": "CSM计息", "CSM调整": "CSM调整", "CSM摊销": "CSM摊销", "CSM其他": "其他变动", "CSM期末余额": "CSM期末余额"}
        f_keys, f_names = list(f_map.keys()), list(f_map.values())
        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        y_str = str(t_year).replace(".0", "")

        msk = (df['报告年份'].astype(str).str.contains(y_str)) & (df['字段名'].isin(f_keys))
        if t_month is not None and '报告月份' in df.columns:
            msk = msk & (df['报告月份'].astype(str) == str(t_month))
        d_sub = df[msk]
        if d_sub.empty: return ""
        
        hl = str(highlight_co).strip()
        # 🌟 字体缩小至 11px，间距压缩
        html = "<table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:11px; margin-bottom:10px; text-align:center;'><tr style='background-color:#00338D; color:white; font-weight:bold;'><th style='padding:4px; border:1px solid white; text-align:left;'>公司</th>"
        for fn in f_names: html += f"<th style='padding:4px; border:1px solid white;'>{fn}</th>"
        html += "</tr>"
        
        for i, co in enumerate(selected_cos):
            is_hl = (str(co).strip() == hl)
            bg = "rgba(0,51,141,0.08)" if is_hl else ("white" if i % 2 == 0 else "#F8F9FA")
            html += f"<tr style='background-color:{bg}; color:{'#00338D' if is_hl else '#333'}; font-weight:{'bold' if is_hl else 'normal'};'><td style='padding:4px; border:1px solid #EAEAEA; text-align:left; font-weight:bold;'>{co}</td>"
            
            for fk in f_keys:
                vs = d_sub[(d_sub['公司'] == co) & (d_sub['字段名'] == fk)]['(百万)人民币']
                v = vs.iloc[0] if not vs.empty else 0
                
                # 🌟 核心拦截：缺失或为 0 则变灰写“未披露”
                if pd.isna(v):
                    html += "<td style='padding:4px; border:1px solid #EAEAEA; background-color:#CDCDCD; color:white;'>未披露</td>"
                else:
                    v_div = v / divisor
                    v_str = f"({abs(v_div):.1f})" if v_div < 0 else f"{v_div:.1f}"
                    html += f"<td style='padding:4px; border:1px solid #EAEAEA;'>{v_str}</td>"
            html += "</tr>"
            
        return html + "</table>"

    # --- 19. CSM过渡期拆 ---
    def create_csm_transition_chart(df, selected_cos, show_labels, bar_width, highlight_co="无",
                                    current_period=None, comparison_period=None):
        """CSM过渡期计量方法拆分图：从上到下 本期 → 对比期 → 上上期（按你选的报告期年+月，
        上上期按本期与对比期的间隔再往前推一期）。无论间隔多大、有没有数据，固定渲染3根条形，
        没有数据的用灰条占位，绝不会漏行。"""
        cols, m = 3, [
            ("采用公允价值法计量的合同", "rgb(0, 51, 141)", "采用公允价值法计量的合同"),
            ("采用修正追溯法计量的合同", "rgb(1, 176, 234)", "采用修正追溯调整法计量的合同"),
            ("其他保险合同", "#7213Ea", "其他合同"),
        ]
        rows = (len(selected_cos) + cols - 1) // cols
        titles = [f"<b><span style='color:#00338D;'>{co}</span></b>" for co in selected_cos]
        safe_v_spacing = 0 if rows <= 1 else min(0.15, 0.8 / rows)

        # 三列子图的纵轴时点标签较长，增加列间留白避免第二、三列标签压到前一列柱子。
        fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                            horizontal_spacing=0.15, vertical_spacing=safe_v_spacing)
        hl_co = str(highlight_co).strip()

        # ---- 确定三个时点：本期 / 对比期 / 上上期（本期、对比期取自你在页面上的选择） ----
        if current_period is None or comparison_period is None:
            years = sorted(df['报告年份'].dropna().astype(str).str.replace('.0', '', regex=False).unique())
            cy_year = int(years[-1]) if years else 2025
            py_year = int(years[-2]) if len(years) >= 2 else cy_year - 1
            cy_month = py_month = 12
        else:
            cy_year, cy_month = current_period
            py_year, py_month = comparison_period

        def _to_months(y, mn):
            return int(y) * 12 + (int(mn) - 1)

        cy_m = _to_months(cy_year, cy_month)
        py_m = _to_months(py_year, py_month)
        interval = cy_m - py_m          # 本期 - 对比期（月数）
        pp_period = None
        if interval > 0:                # ⭐ 不再限制间隔≤12个月：不管差多少个月，都按同样的间隔再往前推一期
            pp_m = py_m - interval
            pp_period = (pp_m // 12, pp_m % 12 + 1)

        cy_label = f"{format_period_label(cy_year, cy_month)}"
        py_label = f"{format_period_label(py_year, py_month)}"
        pp_label = f"{format_period_label(pp_period[0], pp_period[1])}" if pp_period else "上上期"

        # 三个估值时点（从上到下）：
        # 本期标签取本期期末；对比期标签取本期期初；上上期标签取对比期期初。
        # 例如本期 2025.12、对比期 2024.12：
        # 2025.12 -> 2025.12 期末，2024.12 -> 2025.12 期初，2023.12 -> 2024.12 期初。
        periods = [
            (cy_label, cy_year, cy_month, "期末负债"),
            (py_label, cy_year, cy_month, "期初负债"),
            (pp_label, py_year, py_month, "期初负债"),
        ]
        # categoryarray 第 1 个元素在底部 → 倒序排列，让“本期”置顶
        y_labels = [periods[2][0], periods[1][0], periods[0][0]]

        # 用隐形散点锁定全局图例
        for name, clr, _ in m:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                           marker=dict(symbol="square", size=10, color=clr), name=name, showlegend=True))

        for i, co in enumerate(selected_cos):
            r, c, df_c = (i // cols) + 1, (i % cols) + 1, df[df['公司'] == co]
            for label, yr, mn, balance_suffix in periods:
                # ⭐ 关键：不管查不查得到数据，这个 for 循环里每个时点都恰好执行一次、加一条 trace，
                # 保证3个时点永远各占一行，不会因为数据缺失而整行消失
                tot, vs = 0, [0, 0, 0]
                if yr is not None:
                    df_y = df_c[df_c['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(yr).replace('.0', '')]
                    if '报告月份' in df_y.columns:
                        df_y = df_y[df_y['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(mn).replace('.0', '')]
                    vs = [df_y.loc[df_y['字段名'] == f"{f}{balance_suffix}", '(百万)人民币'].sum() for _, _, f in m]
                    tot = sum(vs)

                if tot <= 0:
                    fig.add_trace(go.Bar(x=[100], textangle=0, constraintext='none', y=[label],
                                         orientation='h', marker_color='#CDCDCD', width=bar_width,
                                         showlegend=False, text=["未披露"], textposition='inside',
                                         insidetextanchor='middle', textfont=dict(size=11, color="white")), row=r, col=c)
                else:
                    for j, (name, clr, _) in enumerate(m):
                        pct = vs[j] / tot * 100
                        fig.add_trace(go.Bar(x=[pct], textangle=0, constraintext='none', y=[label],
                                             orientation='h', name=name, marker_color=clr, width=bar_width,
                                             showlegend=False, text=[f"{pct:.0f}%" if show_labels and pct > 0 else ""],
                                             textposition='inside', insidetextanchor='middle',
                                             textfont=dict(size=11, color="white")), row=r, col=c)

            is_hl = (str(co).strip() == hl_co)
            bg_fill = HL_BOX_FILL if is_hl else "rgba(0,0,0,0)"
            line_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="rgba(0,0,0,0)", width=0)
            fig.add_shape(type="rect", xref="x domain", yref="y domain", x0=-0.08, x1=1.08, y0=-0.10, y1=1.33,
                          fillcolor=bg_fill, line=line_dict, layer="above", row=r, col=c)
            fig.update_yaxes(type='category', categoryorder='array', categoryarray=y_labels,
                             showgrid=False, ticks="", ticklen=0, tickcolor="rgba(0,0,0,0)",
                             tickfont=dict(size=11, color="#7D8699"), automargin=True,
                             row=r, col=c)
            fig.update_xaxes(range=[0, 100], tickvals=[0, 20, 40, 60, 80, 100], ticksuffix="%",
                             showgrid=False, row=r, col=c)

        fig.update_layout(barmode='stack', height=300 * rows, paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=80, l=50, r=20),
                          legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.08))
        fig.update_annotations(yshift=5, font_size=12)
        return fig

    def create_csm_composition_chart(df, selected_cos, period, show_labels, label_size, bar_width, highlight_co="无", title_text=""):
        field_map = {"新业务CSM（集团口径）": "新业务 CSM", "CSM计息": "CSM 计息", "CSM调整": "CSM 调整"}
        color_map = {"新业务CSM（集团口径）": "rgb(0, 51, 140)", "CSM计息": "rgb(147, 157, 253)", "CSM调整": "rgb(253, 52, 156)"}
        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        fields, year_str = list(field_map.keys()), str(t_year).replace(".0", "")
        d_sub = df[(df['报告年份'].astype(str).str.contains(year_str)) & (df['公司'].isin(selected_cos)) & (df['字段名'].isin(fields))]
        if t_month is not None and '报告月份' in d_sub.columns:
            d_sub = d_sub[d_sub['报告月份'].astype(str) == str(t_month)]
        d_sub = d_sub.copy()
        if d_sub.empty: return None
        d_pivot = d_sub.pivot(index='公司', columns='字段名', values='(百万)人民币')
        for f in fields:
            if f not in d_pivot.columns: d_pivot[f] = 0
        d_pivot = d_pivot.reindex(selected_cos).fillna(0)
        d_pivot['Total'] = d_pivot[fields].abs().sum(axis=1).replace(0, 1)
        no_data_cos = d_pivot[d_pivot[fields].abs().sum(axis=1) == 0].index.tolist()
        fig, hl_co = go.Figure(), str(highlight_co).strip()
        x_idx = list(range(len(selected_cos)))
        no_data_x = [i for i, co in enumerate(selected_cos) if co in no_data_cos]
        if no_data_x:
            fig.add_trace(go.Bar(
                x=no_data_x, y=[100] * len(no_data_x),
                width=bar_width,
                marker_color="#D9D9D9",
                showlegend=False,
                text=["未披露"] * len(no_data_x),
                textposition='inside',
                insidetextanchor='middle',
                textfont=dict(size=label_size, color="white"),
                hoverinfo='skip'
            ))
        
        for f_name in fields:
            vals_pct = (d_pivot[f_name] / d_pivot['Total']) * 100
            # ✅ 有数据的公司正常显示，无数据的公司值设为0不显示
            vals_pct = [0 if co in no_data_cos else v for co, v in zip(selected_cos, vals_pct)]
            t_color = "white" if f_name == "新业务CSM（集团口径）" else "black"
            fig.add_trace(go.Bar(
                name=field_map[f_name], x=x_idx, y=vals_pct,
                width=bar_width, marker_color=color_map[f_name],
                text=[f"{v:.0f}%" if abs(v) >= 1 else "" for v in vals_pct] if show_labels else None,
                textposition='inside', insidetextanchor='middle',
                textfont=dict(size=label_size, color=t_color),
                constraintext='none'
            ))  
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.12, y1=1.05, fillcolor=HL_BOX_FILL  , line=dict(color=HL_BOX_LINE, width=1.5), layer="above")

        tick_txt = [f"<span style='font-size:14px; color:#00338D;'><b>{co}</b></span>" for co in selected_cos]
        
        # 🌟 修复点：动态判断是否传入了 title_text
        layout_args = dict(barmode='relative', height=500, margin=dict(t=80 if title_text else 40, b=100, l=60, r=40), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
        if title_text:
            layout_args['title'] = dict(text=f"<b>{title_text}</b>", x=0.5, y=0.95, xanchor='center', font=COMMON_TITLE_FONT)
            
        fig.update_layout(**layout_args)
        fig.update_xaxes(showgrid=False, zeroline=False, ticktext=tick_txt, tickvals=x_idx, ticks="", ticklen=0)
        fig.update_yaxes(showgrid=False, range=[-25, 105], tickvals=[-20, 0, 20, 40, 60, 80, 100], ticktext=["-20%", "0%", "20%", "40%", "60%", "80%", "100%"], zeroline=True, zerolinecolor='#FFB07C', zerolinewidth=1.5)
        return fig

    # --- 21. CSM 比率折线图 ---  
    def get_company_color_mapping(companies, key_prefix="cp"):
        PRESET_COLORS_FIXED = ["#C00000", "#0865EE", "#FEAED7", "#92D050", "#7030A0", "#EF9867", "#61CBF4", "#C7A0F7"]
        cols = st.columns(len(companies))
        mapping = {}
        for i, co in enumerate(companies):
            with cols[i]:
                st.caption(f"**{co}**")
                mapping[co] = st.color_picker(label=co, value=PRESET_COLORS_FIXED[i % len(PRESET_COLORS_FIXED)], key=f"{key_prefix}_{co}", label_visibility="collapsed")
        return mapping

    #22.CSM摊销、持续比例图
    def render_shared_legend(selected_cos, color_map, highlight_co="无"):
            items = "".join([f'<div style="display:flex;align-items:center;"><div style="width:10px;height:10px;border-radius:50%;background:{HIGHLIGHT_COLOR if co == highlight_co else color_map.get(co, "#333")};margin-right:5px;flex-shrink:0;"></div><span>{co}</span></div>' for co in selected_cos])
            st.markdown(f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin-bottom:6px;padding-left:6px;font-size:12px;">{items}</div>', unsafe_allow_html=True)
    
    def create_ratio_line_chart_v3(df_plot, title, color_map, show_labels, marker_size, y_axis_format, selected_cos, highlight_co="无", print_mode=False):
            fig = go.Figure()
            latest_yr = df_plot['报告年份'].max()
            df_latest = df_plot[df_plot['报告年份'] == latest_yr].dropna(subset=['value'])
            
            max_co = df_latest.loc[df_latest['value'].idxmax(), '公司'] if not df_latest.empty else None
            min_co = df_latest.loc[df_latest['value'].idxmin(), '公司'] if not df_latest.empty else None
    
            for co in selected_cos:
                d_co = df_plot[df_plot['公司'] == co].sort_values('报告年份')
                if d_co.empty: continue
                
                is_hl, is_ext = (co == highlight_co), (co in [max_co, min_co])
                fig.add_trace(go.Scatter(
                    x=d_co['报告年份'], y=d_co['value'], name=co,
                    mode='lines+markers+text' if show_labels else 'lines+markers',
                    line=dict(color=HIGHLIGHT_COLOR if is_hl else color_map.get(co, "#333"), width=4 if is_hl else (2.5 if is_ext else 2), dash="solid" if (is_hl or is_ext) else "dot"),
                    marker=dict(size=marker_size * 1.5 if is_hl else marker_size, symbol='circle'),
                    text=[f"{v*100:.1f}%" if (not print_mode or i == len(d_co)-1) else "" for i, v in enumerate(d_co['value'])],
                    textposition="middle right", cliponaxis=False
                ))
    
            fig.update_layout(title=dict(text=title, x=0, font=dict(size=12)), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=160, margin=dict(t=25, b=0, l=0, r=0), showlegend=False)
            fig.update_xaxes(showgrid=False, showline=False, zeroline=False)
            fig.update_yaxes(showgrid=False, zeroline=False, tickformat=y_axis_format)
            
            return fig

    # --- 22.综合净资产指标 --- 
    def create_csm_equity_analysis(df, selected_cos, show_labels, label_size, bar_width, co_font_size, pct_height_adjust, highlight_co="无", title_text="", current_period=None, comparison_period=None):
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label_ml(cy, cy_month), format_period_label_ml(py, py_month)

        def _mask(df_in, y, m):
            msk = (df_in['报告年份'].astype(str) == str(y)) & (df_in['公司'].isin(selected_cos)) & (df_in['字段名'].isin(["CSM期末余额", "期末股东权益"]))
            if m is not None and '报告月份' in df_in.columns:
                msk = msk & (df_in['报告月份'].astype(str) == str(m))
            return msk

        d_sub = df[_mask(df, cy, cy_month) | _mask(df, py, py_month)].copy()
        d_sub['value'] = d_sub['(百万)人民币'] / divisor

        def _tot(co, y, m):
            msk = (d_sub['公司'] == co) & (d_sub['报告年份'].astype(str) == str(y))
            if m is not None and '报告月份' in d_sub.columns:
                msk = msk & (d_sub['报告月份'].astype(str) == str(m))
            return d_sub[msk]['value'].sum()

        # 获取全局最大值，用于设置 Y 轴高度和占位柱高度
        _all_totals = [_tot(_co, _y, _m) for _co in selected_cos for _y, _m in [(py, py_month), (cy, cy_month)]]
        global_max_bar = max(_all_totals + [1.0])
        global_base_y, global_y_top = global_max_bar * 1.03, global_max_bar * 1.12
        placeholder_h = global_max_bar * 0.4  # 🌟 占位灰柱高度
        
        hl_co = str(highlight_co).strip()
        n = len(selected_cos)
        titles = [f"<span style='color:#00338D; font-size:{co_font_size}px;'><b>{co}</b></span>" for co in selected_cos]
        fig = make_subplots(rows=1, cols=n, horizontal_spacing=0.015 if n<=1 else min(0.015, 0.8/(n-1)), subplot_titles=titles)            
        
        # 隐形散点锁定全局图例
        for leg_name, leg_color in [("再保前净CSM", "rgb(0, 184, 245)"), ("净资产", "rgb(30, 73, 226)"), ("再保前税后CSM/净资产", "rgb(114, 19, 214)")]:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color=leg_color), name=leg_name, showlegend=True), row=1, col=1)                
        
        for i, co in enumerate(selected_cos):
            col_idx, cd = i + 1, d_sub[d_sub['公司'] == co]
            def gv(y, m, f):
                msk = (cd['报告年份'].astype(str)==str(y)) & (cd['字段名']==f)
                if m is not None and '报告月份' in cd.columns:
                    msk = msk & (cd['报告月份'].astype(str)==str(m))
                return cd[msk]['value'].sum()
            v24b, v25b, v24e, v25e = gv(py, py_month, "CSM期末余额"), gv(cy, cy_month, "CSM期末余额"), gv(py, py_month, "期末股东权益"), gv(cy, cy_month, "期末股东权益")
            
            # 🌟 核心拦截逻辑：判断该年是否完全没数据
            m24, m25 = (v24b==0 and v24e==0), (v25b==0 and v25e==0)
            
            v24c, v25c = (0 if m24 else v24b*0.75), (0 if m25 else v25b*0.75)
            v24e, v25e = (0 if m24 else v24e), (0 if m25 else v25e)
            
            p24 = (v24c / v24e * 100) if v24e != 0 and not m24 else 0
            p25 = (v25c / v25e * 100) if v25e != 0 and not m25 else 0
            x_axis = [py_label, cy_label]
            
            # 画真实数据柱子（如果是未披露，传进去的是 0，自动隐
            lbl = lambda v, m: f"{v:.0f}" if show_labels and pd.notna(v) and v!=0 and not m else ""
            fig.add_trace(go.Bar(x=x_axis, y=[v24c, v25c], marker_color="rgb(0, 184, 245)", width=bar_width, showlegend=False, text=[lbl(v24c,m24), lbl(v25c,m25)], textposition='inside', textangle=0, textfont=dict(size=label_size, color="white"), constraintext='none'), row=1, col=col_idx)                
            fig.add_trace(go.Bar(x=x_axis, y=[v24e, v25e], marker_color="rgb(30, 73, 226)", width=bar_width, showlegend=False, text=[lbl(v24e,m24), lbl(v25e,m25)], textposition='inside', textangle=0, textfont=dict(size=label_size, color="white"), constraintext='none'), row=1, col=col_idx)                
            
            # 🌟 画专门的灰色占位柱子
            fig.add_trace(go.Bar(x=x_axis, y=[placeholder_h if m24 else 0, placeholder_h if m25 else 0], marker_color="#CDCDCD", width=bar_width, showlegend=False, text=["未披露" if m24 else "", "未披露" if m25 else ""], textposition='inside', insidetextanchor='middle', textfont=dict(size=12, color="white"), constraintext='none', cliponaxis=False), row=1, col=col_idx)
            
            # 折线图与比例标签逻辑：只有在真实数据存在时才绘制
            pct_max, delta = max(abs(p24), abs(p25), 1.0), global_max_bar * 0.04
            y24_line = global_base_y + (p24 / pct_max) * delta * 0.5 if not m24 else None
            y25_line = global_base_y + (p25 / pct_max) * delta * 0.5 if not m25 else None
            
            fig.add_trace(go.Scatter(x=x_axis, y=[y24_line, y25_line], mode="lines", line=dict(color="rgb(114, 19, 214)", width=1.2), showlegend=False, hoverinfo="skip"), row=1, col=col_idx)
            # 对于散点和文本，如果是未披露，把文本设为空字符串
            fig.add_trace(go.Scatter(x=x_axis, y=[y24_line, y25_line], mode="markers+text", marker=dict(symbol="triangle-up", size=7, color="rgb(114, 19, 214)"), text=[f"{p24:.0f}%" if not m24 else "", f"{p25:.0f}%" if not m25 else ""], textposition="top center", textfont=dict(color="rgb(114, 19, 214)", size=label_size), showlegend=False, hoverinfo="skip"), row=1, col=col_idx)                
            
            fig.update_yaxes(range=[0, global_y_top], showticklabels=False, showgrid=False, zeroline=False, row=1, col=col_idx)                
            
            # 🌟 恢复高亮逻辑：高亮公司带深色框和浅蓝蒙版（layer="above"），普通公司透明/交替浅灰
            is_hl = (str(co).strip() == hl_co)
            bg_fill = HL_BOX_FILL   if is_hl else ("rgba(200, 200, 200, 0.12)" if i % 2 == 1 else "rgba(255,255,255,0)")
            border_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="#EAEAEA", width=1)
            xref_str = f"x{col_idx} domain" if col_idx > 1 else "x domain"
            fig.add_shape(type="rect", xref=xref_str, yref="paper", x0=-0.04, x1=1.04, y0=-0.12, y1=1.12, line=border_dict, fillcolor=bg_fill, layer="above" if is_hl else "below")

        fig.update_layout(barmode='stack', height=550, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=50, b=100, l=20, r=20), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, font=dict(size=12), itemsizing="constant"))                
        
        for ann in fig.layout.annotations:
            if "span" in str(ann.text): ann.update(y=1.03)
                
        for i in range(1, n + 1):
            fig.update_xaxes(type="category", showgrid=False, zeroline=False, ticks="", ticklen=0, row=1, col=i)
        return fig

# --- 23.新业务盈利合同 ---   
    def create_new_biz_csm_chart(df_source, field_name, title, show_labels, p_size, g_gap, highlight_co="无", current_period=None, comparison_period=None):
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'], d['value'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False), d['value'] / divisor
        if current_period is None or comparison_period is None:
            y_new, y_new_month, y_old, y_old_month = latest_year, None, prev_year, None
        else:
            y_new, y_new_month = current_period
            y_old, y_old_month = comparison_period
        y_new_label, y_old_label = format_period_label(y_new, y_new_month), format_period_label(y_old, y_old_month)
        hl_co = str(highlight_co).strip()
        fig, x_idx = go.Figure(), list(range(len(selected_cos)))

        all_vals = d['value'].dropna()
        all_vals = all_vals[all_vals != 0]
        y_max, y_min = (all_vals.max(), all_vals.min()) if not all_vals.empty else (100, 0)
        off = (y_max - y_min) * 0.11 if not all_vals.empty else 12
        placeholder_h = y_max * 0.2 if y_max > 0 else 10  # 未披露灰色柱子的高度

        def _filt(sub, y, m):
            msk = sub['报告年份'] == str(y)
            if m is not None and '报告月份' in sub.columns:
                msk = msk & (sub['报告月份'].astype(str) == str(m))
            return sub[msk].set_index('公司')
        df_old = _filt(d, y_old, y_old_month)
        df_new = _filt(d, y_new, y_new_month)
        vals_old, vals_new, txt_old, txt_new = [], [], [], []
        col_old, col_new, pos_old, pos_new, fc_old, fc_new = [], [], [], [], [], []

        for i, co in enumerate(selected_cos):
            v0 = df_old.loc[co, 'value'] if co in df_old.index else np.nan
            v1 = df_new.loc[co, 'value'] if co in df_new.index else np.nan
            m0, m1 = pd.isna(v0), pd.isna(v1)

            # 情况1：两年都未披露 -> 双倍宽灰柱，文字居中悬浮
            if m0 and m1:
                vals_old.append(placeholder_h); vals_new.append(placeholder_h)
                txt_old.append(""); txt_new.append("")
                col_old.append("#CDCDCD"); col_new.append("#CDCDCD")
                pos_old.append("inside"); pos_new.append("inside")
                fc_old.append("white"); fc_new.append("white")
                fig.add_annotation(x=i, y=placeholder_h/2, text="未披露", showarrow=False, font=dict(color="white", size=11), xanchor="center", yanchor="middle")
            
            # 情况2：只有往年未披露 -> 往年灰柱(字在内)，最新年蓝柱(字在外)
            elif m0 and not m1:
                vals_old.append(placeholder_h); vals_new.append(v1)
                txt_old.append("未披露"); txt_new.append(f"{v1:.1f}" if show_labels else "")
                col_old.append("#CDCDCD"); col_new.append("rgb(0, 51, 141)")
                pos_old.append("inside"); pos_new.append("outside")
                fc_old.append("white"); fc_new.append("#333")
                
            # 情况3：只有最新年未披露 -> 往年蓝柱(字在外)，最新年灰柱(字在内)
            elif not m0 and m1:
                vals_old.append(v0); vals_new.append(placeholder_h)
                txt_old.append(f"{v0:.1f}" if show_labels else ""); txt_new.append("未披露")
                col_old.append("rgb(15, 101, 253)"); col_new.append("#CDCDCD")
                pos_old.append("outside"); pos_new.append("inside")
                fc_old.append("#333"); fc_new.append("white")
                
            # 情况4：两年都有数据 -> 正常蓝柱，计算百分比箭头
            else:
                vals_old.append(v0); vals_new.append(v1)
                txt_old.append(f"{v0:.1f}" if show_labels else ""); txt_new.append(f"{v1:.1f}" if show_labels else "")
                col_old.append("rgb(15, 101, 253)"); col_new.append("rgb(0, 51, 141)")
                pos_old.append("outside"); pos_new.append("outside")
                fc_old.append("#333"); fc_new.append("#333")
                
                # 🌟 修复：只有当分母 (v0) 不等于 0 时，才计算和绘制百分比箭头
                if v0 != 0:
                    pct = (v1 - v0) / abs(v0)
                    arr_color, arr_symbol = ("#FD349C", "↗") if pct >= 0 else ("#269924", "↘")
                    y_pos, v_align = (max(v0, v1) + off, "bottom") if v1 >= 0 else (min(v0, v1) - off, "top")
                    fig.add_annotation(x=i, y=y_pos, text=f"<b>{arr_symbol} {pct:.1%}</b>", showarrow=False, font=dict(color=arr_color, size=p_size), xshift=8, valign=v_align)
        # 🌟 增加隐形散点图例，锁定为方形和标准蓝
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color="rgb(15, 101, 253)"), name=f"{y_old_label}新业务盈利合同（CSM）"))
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color="rgb(0, 51, 141)"), name=f"{y_new_label}新业务盈利合同（CSM）"))

        # 🌟 真实柱子，关闭自身图例
        fig.add_trace(go.Bar(name=f"{y_old_label}新业务盈利合同（CSM）", x=x_idx, y=vals_old, marker_color=col_old, text=txt_old, textposition=pos_old, insidetextanchor="middle",textfont=dict(size=12, color=fc_old), textangle=0, cliponaxis=False, showlegend=False))
        fig.add_trace(go.Bar(name=f"{y_new_label}新业务盈利合同（CSM）", x=x_idx, y=vals_new, marker_color=col_new, text=txt_new, textposition=pos_new, insidetextanchor="middle",textfont=dict(size=12, color=fc_new), textangle=0, cliponaxis=False, showlegend=False))
            
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.12, y1=1.05, fillcolor=HL_BOX_FILL  , line=dict(color=HL_BOX_LINE, width=1.5), layer="above")

        fig.update_layout(barmode='group', bargroupgap=0, bargap=g_gap, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=60, l=40, r=40), height=500, legend=dict(orientation="v", yanchor="top", y=1.1, xanchor="right", x=1.0))
        r_top, r_bot = y_max + (y_max - y_min) * 0.18, y_min - (y_max - y_min) * 0.15 if y_min < 0 else 0
        r_top = max(r_top, placeholder_h * 1.3) # 保证未披露柱子不会顶破天花板
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02, range=[r_bot, r_top])
        fig.update_xaxes(showline=False, showgrid=False, zeroline=False, tickvals=x_idx, ticktext=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos], ticks="", ticklen=0)
        return fig



# --- 24.新业务亏损 ---   
    def create_new_lost_csm_chart(df_source, field_name, title, show_labels, p_size, g_gap, highlight_co="无", current_period=None, comparison_period=None):
        d = df_source[df_source['指标名称'] == field_name].copy()
        d['报告年份'], d['value'] = d['报告年份'].astype(str).str.replace(".0", "", regex=False), d['value'] / divisor
        if current_period is None or comparison_period is None:
            y_new, y_new_month, y_old, y_old_month = latest_year, None, prev_year, None
        else:
            y_new, y_new_month = current_period
            y_old, y_old_month = comparison_period
        y_new_label, y_old_label = format_period_label(y_new, y_new_month), format_period_label(y_old, y_old_month)
        hl_co = str(highlight_co).strip()
        fig, x_idx = go.Figure(), list(range(len(selected_cos)))
        
        all_vals = d['value'].dropna()
        all_vals = all_vals[all_vals != 0]
        if not all_vals.empty:
            y_max, y_min = all_vals.max(), all_vals.min()
            off = (y_max - y_min) * 0.15
            
            # 判断整体方向：如果极小值的绝对值 > 极大值的绝对值，说明主要是负数（向下画）
            if abs(y_min) > abs(y_max):
                placeholder_h = y_min * 0.5  # 取最深的一半
            else:
                placeholder_h = y_max * 0.5  # 取最高的一半
                
        else:
            # 如果全军覆没都没数据，给个默认的向下占位
            y_max, y_min = 0, -100
            off = 12
            placeholder_h = -50 
            
        def _filt(sub, y, m):
            msk = sub['报告年份'] == str(y)
            if m is not None and '报告月份' in sub.columns:
                msk = msk & (sub['报告月份'].astype(str) == str(m))
            return sub[msk].set_index('公司')
        df_old = _filt(d, y_old, y_old_month)
        df_new = _filt(d, y_new, y_new_month)
        vals_old, vals_new, txt_old, txt_new = [], [], [], []
        col_old, col_new, pos_old, pos_new, fc_old, fc_new = [], [], [], [], [], []

        for i, co in enumerate(selected_cos):
            v0 = df_old.loc[co, 'value'] if co in df_old.index else np.nan
            v1 = df_new.loc[co, 'value'] if co in df_new.index else np.nan
            m0, m1 = pd.isna(v0), pd.isna(v1)

            # 🌟 修复了文字居中：如果两年都未披露，只在居中位置打一个标签
            if m0 and m1:
                vals_old.append(placeholder_h); vals_new.append(placeholder_h)
                txt_old.append(""); txt_new.append("")
                col_old.append("#CDCDCD"); col_new.append("#CDCDCD")
                pos_old.append("inside"); pos_new.append("inside")
                fc_old.append("white"); fc_new.append("white")
                fig.add_annotation(x=i, y=placeholder_h/2, text="未披露", showarrow=False, font=dict(color="white", size=11), xanchor="center", yanchor="middle")
            
            elif m0 and not m1:
                vals_old.append(placeholder_h); vals_new.append(v1)
                txt_old.append("未披露"); txt_new.append(f"{v1:.1f}" if show_labels else "")
                col_old.append("#CDCDCD"); col_new.append("rgb(0, 51, 141)")
                pos_old.append("inside"); pos_new.append("outside")
                fc_old.append("white"); fc_new.append("#333")
                
            elif not m0 and m1:
                vals_old.append(v0); vals_new.append(placeholder_h)
                txt_old.append(f"{v0:.1f}" if show_labels else ""); txt_new.append("未披露")
                col_old.append("rgb(15, 101, 253)"); col_new.append("#CDCDCD")
                pos_old.append("outside"); pos_new.append("inside")
                fc_old.append("#333"); fc_new.append("white")
                
            else:
                vals_old.append(v0); vals_new.append(v1)
                txt_old.append(f"{v0:.1f}" if show_labels else ""); txt_new.append(f"{v1:.1f}" if show_labels else "")
                col_old.append("rgb(15, 101, 253)"); col_new.append("rgb(0, 51, 141)")
                pos_old.append("outside"); pos_new.append("outside")
                fc_old.append("#333"); fc_new.append("#333")
                
                # 🌟 修复：如果基数 v0 为 0，跳过百分比计算，防止 ZeroDivisionError
                if v0 != 0:
                    pct = (v1 - v0) / abs(v0)
                    arr_color, arr_symbol = ("#FD349C", "↗") if pct >= 0 else ("#269924", "↘")
                    y_pos, v_align = (max(v0, v1) + off, "bottom") if v1 >= 0 else (min(v0, v1) - off, "top")
                    fig.add_annotation(x=i, y=y_pos, text=f"<b>{arr_symbol} {pct:.1%}</b>", showarrow=False, font=dict(color=arr_color, size=p_size), xshift=10, valign=v_align)
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color="rgb(15, 101, 253)"), name=f"{y_old_label}新业务亏损（LC）"))
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color="rgb(0, 51, 141)"), name=f"{y_new_label}新业务亏损（LC）"))

        fig.add_trace(go.Bar(name=f"{y_old_label}新业务亏损（LC）", x=x_idx, y=vals_old, marker_color=col_old, text=txt_old, textposition=pos_old, textfont=dict(size=12, color=fc_old), textangle=0, cliponaxis=False, showlegend=False))
        fig.add_trace(go.Bar(name=f"{y_new_label}新业务亏损（LC）", x=x_idx, y=vals_new, marker_color=col_new, text=txt_new, textposition=pos_new, textfont=dict(size=12, color=fc_new), textangle=0, cliponaxis=False, showlegend=False))
            
        if hl_co in [str(c).strip() for c in selected_cos]:
            idx = [str(c).strip() for c in selected_cos].index(hl_co)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.12, y1=1.05, fillcolor=HL_BOX_FILL  , line=dict(color=HL_BOX_LINE, width=1.5), layer="above")

        fig.update_layout(barmode='group', bargroupgap=0, bargap=g_gap, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=60, l=40, r=40), height=500, legend=dict(orientation="v", yanchor="top", y=1.15, xanchor="right", x=1.0))
        
        # 🌟 修复 Y 轴范围保护，同时适应正数和负数的扩展
        r_top = y_max + (y_max - y_min) * 0.18
        r_bot = y_min - (y_max - y_min) * 0.15 if y_min < 0 else 0
        if placeholder_h > 0: r_top = max(r_top, placeholder_h * 1.3)
        if placeholder_h < 0: r_bot = min(r_bot, placeholder_h * 1.3)
            
        fig.update_yaxes(showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02, range=[r_bot, r_top])
        fig.update_xaxes(showline=False, showgrid=False, zeroline=False, tickvals=x_idx, ticktext=[f"<span style='color:#00338D;'><b>{co}</b></span>" for co in selected_cos], ticks="", ticklen=0)
        return fig
    
# 24.新业务占比 (终极完美版：修正了图例大小与亏损占位柱方向)
    def create_new_business_metrics_charts(df_raw, selected_cos, show_lab, lab_sz, bar_width, co_sz, highlight_co="无", is_print_mode=False, current_period=None, comparison_period=None):
        if current_period is None or comparison_period is None:
            cy, cy_month, py, py_month = latest_year, None, prev_year, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)

        df_clean = df_raw.copy()
        df_clean['报告年份'] = df_clean['报告年份'].astype(str).str.replace('.0', '', regex=False)
        val_col = "(百万)人民币" if "(百万)人民币" in df_clean.columns else df_clean.columns[-1]
        req_f = ["新业务RA", "新业务亏损合同（LC）——非PAA", "新业务未来现金流入现值", "新业务未来现金流入现值（盈利）", "新业务未来现金流入现值（亏损）", "新业务CSM（集团口径）"]

        idx_cols = ['公司', '报告年份']
        if '报告月份' in df_clean.columns:
            idx_cols.append('报告月份')
        df_pivot = df_clean[df_clean['字段名'].isin(req_f)].pivot_table(index=idx_cols, columns='字段名', values=val_col, aggfunc='sum').reset_index()
        if selected_cos: df_pivot = df_pivot[df_pivot['公司'].isin(selected_cos)]
        if df_pivot.empty: return None, None, None

        # 只补齐列名，不强填 0，保留 np.nan 以区分真实 0 和未披露
        for c in req_f: 
            if c not in df_pivot.columns: 
                df_pivot[c] = np.nan
                
# 🌟 终极修复：使用 np.where。只要分母是 0，直接让结果等于 np.nan（空值，触发未披露）
        num1 = df_pivot['新业务CSM（集团口径）'].astype(float)
        den1 = df_pivot['新业务未来现金流入现值（盈利）'].astype(float).abs() # 👈 加上 .abs() 取绝对值
        df_pivot['新业务CSM利润率'] = np.where(den1 == 0, np.nan, num1 / den1)
        
        num2 = df_pivot['新业务亏损合同（LC）——非PAA'].astype(float)
        den2 = df_pivot['新业务未来现金流入现值（亏损）'].astype(float).abs() # 👈 加上 .abs() 取绝对值
        df_pivot['新业务LC亏损率'] = np.where(den2 == 0, np.nan, num2 / den2)
        
        num3 = df_pivot['新业务RA'].astype(float)
        den3 = df_pivot['新业务未来现金流入现值'].astype(float).abs() # 👈 加上 .abs() 取绝对值
        df_pivot['新业务RA率'] = np.where(den3 == 0, np.nan, num3 / den3)
        
        # 兜底：防止任何意外产生的无穷大 (inf) 破坏图表
        df_pivot.replace([np.inf, -np.inf], 0.0, inplace=True)

        configs = [("新业务CSM利润率", "rgb(30, 73, 225)", "rgb(149, 229, 255)"), ("新业务LC亏损率", "rgb(253, 52, 156)", "rgb(255, 214, 235)"), ("新业务RA率", "rgb(114, 19, 234)", "rgb(227, 207, 251)")]
        figs, hl_co, x_idx = [], str(highlight_co).strip(), list(range(len(selected_cos)))

        for m, c_lat, c_pre in configs:
            def _sub(y, m):
                msk = df_pivot['报告年份'] == str(y)
                if m is not None and '报告月份' in df_pivot.columns:
                    msk = msk & (df_pivot['报告月份'].astype(str) == str(m))
                return df_pivot[msk].set_index('公司').reindex(selected_cos)
            df_lat, df_pre = _sub(cy, cy_month), _sub(py, py_month)
            fig = go.Figure()
            
            val_valid = pd.concat([df_lat[m], df_pre[m]]).dropna()
            val_valid = val_valid[val_valid != 0]
            ph = val_valid.abs().max() * 0.3 if not val_valid.empty else 0.05
            
            if m == "新业务LC亏损率": ph = -ph
            
            yp, yl, tp, tl, cp, cl, pp, pl, fp, fl = [],[],[],[],[],[],[],[],[],[]

            for i, co in enumerate(selected_cos):
                vp, vl = df_pre.loc[co, m] if co in df_pre.index else np.nan, df_lat.loc[co, m] if co in df_lat.index else np.nan
                
                # 判断依据严格变为 pd.isna()，彻底没数(NaN)才算未披露
                mp, ml = pd.isna(vp), pd.isna(vl)
                
                if mp and ml:
                    yp.append(ph); yl.append(ph); tp.append(""); tl.append(""); cp.append("#CDCDCD"); cl.append("#CDCDCD"); pp.append("inside"); pl.append("inside"); fp.append("white"); fl.append("white")
                    fig.add_annotation(x=i, y=ph/2, text="未披露", showarrow=False, font=dict(color="white", size=11))
                elif mp and not ml:
                    yp.append(ph); yl.append(vl); tp.append("未披露"); tl.append(f"{vl*100:.1f}%" if show_lab else ""); cp.append("#CDCDCD"); cl.append(c_lat); pp.append("inside"); pl.append("outside"); fp.append("white"); fl.append("#333")
                elif not mp and ml:
                    yp.append(vp); yl.append(ph); tp.append(f"{vp*100:.1f}%" if show_lab else ""); tl.append("未披露"); cp.append(c_pre); cl.append("#CDCDCD"); pp.append("outside"); pl.append("inside"); fp.append("#333"); fl.append("white")
                else:
                    yp.append(vp); yl.append(vl); tp.append(f"{vp*100:.1f}%" if show_lab else ""); tl.append(f"{vl*100:.1f}%" if show_lab else ""); cp.append(c_pre); cl.append(c_lat); pp.append("outside"); pl.append("outside"); fp.append("#333"); fl.append("#333")

            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color=c_pre), name=py_label))
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color=c_lat), name=cy_label))
            
            fig.add_trace(go.Bar(x=x_idx, y=yp, marker_color=cp, text=tp, textposition=pp, textfont=dict(size=lab_sz, color=fp), showlegend=False, cliponaxis=False, constraintext='none'))
            fig.add_trace(go.Bar(x=x_idx, y=yl, marker_color=cl, text=tl, textposition=pl, textfont=dict(size=lab_sz, color=fl), showlegend=False, cliponaxis=False, constraintext='none'))

            if hl_co in [str(c).strip() for c in selected_cos]:
                idx = [str(c).strip() for c in selected_cos].index(hl_co)
                fig.add_shape(type="rect", xref="x", yref="paper", x0=idx-0.46, x1=idx+0.46, y0=-0.40, y1=1.15, fillcolor="rgba(0, 51, 141, 0.05)", line=dict(color="rgba(0, 51, 141, 0.85)", width=1.5), layer="above")

            mb, leg_y, leg_a = 17, 1.02, "bottom"
            if not df_lat[m].dropna().empty:
                avg, y_r = df_lat[m].mean(), (max(val_valid) - min(val_valid)) if not val_valid.empty else 1
                if avg < 0: mb, leg_y, leg_a = 60, -0.15, "top"
                
                if m == "新业务LC亏损率" and avg < 0: leg_y -= 0.11; mb += 17
                
                fig.add_hline(y=avg, line_dash="dash", line_color=c_lat, line_width=1.5)
                l_m = max((df_pre[m].iloc[-1] if not pd.isna(df_pre[m].iloc[-1]) else 0), (df_lat[m].iloc[-1] if not pd.isna(df_lat[m].iloc[-1]) else 0))
                dyn_a, dyn_y = ("bottom", 2) if abs(avg - l_m) >= (y_r * 0.15) else (("bottom", 15) if avg >= l_m else ("top", -15))
                fig.add_annotation(x=0.98, xref="paper", y=avg, yref="y", xanchor="right", yanchor=dyn_a, yshift=dyn_y, text=f"{cy_label}均值 {avg*100:.1f}%", showarrow=False, bgcolor="rgba(255,255,255,0.85)", bordercolor=c_lat, borderwidth=1, borderpad=2, font=dict(color=c_lat, size=max(lab_sz-3, 8)))

            fig.update_layout(title=dict(text=f"<b>{m}</b>", x=0.5, xanchor='center', y=0.98 if is_print_mode else 0.95, font=dict(size=11, color="#00338D", family="Microsoft YaHei")), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", barmode='group', bargroupgap=0, bargap=max(0, 1.0 - bar_width), margin=dict(t=30 if is_print_mode else 50, b=0 if is_print_mode else mb, l=20, r=40),height=210 if is_print_mode else 360, yaxis=dict(tickformat=".0%", showgrid=False, zeroline=True, zerolinecolor="#E0E0E0", zerolinewidth=1.02), legend=dict(orientation="h", yanchor=leg_a, y=leg_y-0.15, xanchor="right", x=1,font=dict(size=11) ))
            fig.update_xaxes(showgrid=False, zeroline=False, ticktext=[f"<span style='font-size:{co_sz}px; color:#00338D;'><b>{c}</b></span>" for c in selected_cos], tickvals=x_idx, ticks="", ticklen=0)
            figs.append(fig)

        return figs[0], figs[1], figs[2]

    # --- 25.新业务利润率指标趋势 ---   
    def create_nb_margin_trend_chart(df, cos, title, color_map, show_labels, marker_size, legend_font_size, highlight_co="无",
                                     current_period=None, comparison_period=None):
        # ⭐ 只保留本期 + 对比期这两个报告期，不再画全历史趋势线
        if current_period is not None and comparison_period is not None:
            _periods = sorted({(int(current_period[0]), int(current_period[1])),
                               (int(comparison_period[0]), int(comparison_period[1]))})
        else:
            # 兼容层：没传报告期时退回旧逻辑，取数据里全部时点
            _period_rows = df[['报告年份', '报告月份']].drop_duplicates()
            _periods = []
            for _, r in _period_rows.iterrows():
                _y = str(r['报告年份']).replace('.0', '')
                _m = str(r['报告月份']).replace('.0', '')
                if _y.isdigit():
                    _periods.append((int(_y), int(_m) if _m.isdigit() else 12))
            _periods = sorted(set(_periods))
        x_categories = [format_period_label(y, m) for y, m in _periods]
        plot_data = []
        for co in cos:
            for (y, m) in _periods:
                df_curr = df[(df['公司'] == co) &
                             (df['报告年份'].astype(str).str.replace('.0', '', regex=False) == str(y)) &
                             (df['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(m))]
                v = lambda k: df_curr[df_curr['字段名'].str.contains(k, regex=False, na=False)]['(百万)人民币'].sum()
                csm, lc, pv = v('新业务CSM'), v('新业务亏损合同'), v('新业务未来现金流入')
                if pv != 0: plot_data.append({'公司': co, '报告期': format_period_label(y, m), 'sort_num': y * 100 + m, 'value': (csm + lc) / abs(pv)})

        df_plot = pd.DataFrame(plot_data, columns=['公司', '报告期', 'sort_num', 'value'])
        fig = go.Figure()
        max_co, min_co = None, None
        if not df_plot.empty:
            latest_sort = df_plot['sort_num'].max()
            df_latest = df_plot[df_plot['sort_num'] == latest_sort].dropna(subset=['value'])
            if not df_latest.empty:
                max_co = df_latest.loc[df_latest['value'].idxmax(), '公司']
                min_co = df_latest.loc[df_latest['value'].idxmin(), '公司']

        for co in cos:
            d_co = df_plot[df_plot['公司'] == co].sort_values('sort_num')
            is_missing = d_co.empty or d_co['value'].isna().all()
            
            if is_missing:
                fig.add_trace(go.Scatter(
                    x=x_categories, y=[None]*len(x_categories), 
                    name=f"<span style='color:#999999'>{co} (未披露)</span>", 
                    mode='lines+markers', 
                    line=dict(color="#CDCDCD", width=2, dash="dot"), 
                    marker=dict(size=marker_size, symbol='circle'),
                    showlegend=True
                ))
            else:
                is_highlight = (co == highlight_co)
                is_ext = (co in [max_co, min_co]) # 🌟 判断当前公司是否是最高或最低
                
                # 标签显示逻辑：如果是高亮、最高、最低，或者头尾端点，就显示标签
                text_labels = [f"{v:.1%}" if (is_highlight or is_ext or i==0 or i==len(d_co)-1) else "" for i, v in enumerate(d_co['value'])]
                
                fig.add_trace(go.Scatter(
                    x=d_co['报告期'], y=d_co['value'],
                    name=co,
                    mode='lines+markers+text' if show_labels else 'lines+markers', 
                    line=dict(
                        color=HIGHLIGHT_COLOR if is_highlight else color_map.get(co, "#333"), 
                        width=4 if is_highlight else (2.5 if is_ext else 2), # 🌟 极值稍微加粗到 2.5
                        dash="solid" if (is_highlight or is_ext) else "dot"  # 🌟 极值变成实线 (solid)
                    ), 
                    marker=dict(size=marker_size*1.5 if is_highlight else marker_size, symbol='circle'), 
                    text=text_labels if show_labels else None, 
                    textposition="top center", 
                    cliponaxis=False,
                    showlegend=True
                ))
                
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=40, l=70, r=70), height=450, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=legend_font_size)), width=600,  xaxis=dict(showgrid=False, showline=False, zeroline=False), yaxis=dict(showgrid=False, zeroline=False, tickformat=".1%"))
        fig.update_xaxes(type='category', categoryorder='array', categoryarray=x_categories)
        
        valid_vals = df_plot['value'].dropna()
        if not valid_vals.empty:
            y_max, y_min = valid_vals.max(), valid_vals.min()
            bottom_range = y_min * 0.8 if y_min >= 0 else y_min * 1.2
            fig.update_yaxes(range=[bottom_range, y_max + abs(y_max) * 0.15])
            
        return fig

# --- 26. 费用结构 --- 
    def create_expense_breakdown_chart(df, selected_cos, show_labels, label_size, bar_width, co_font_size, highlight_co="无", current_period=None, comparison_period=None):
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label_ml(cy, cy_month), format_period_label_ml(py, py_month)
        f = ["获取费用", "维持费用", "非履约费用"]

        def _period_mask(d, y, m):
            msk = d['报告年份'].astype(str) == str(y)
            if m is not None and '报告月份' in d.columns:
                msk = msk & (d['报告月份'].astype(str) == str(m))
            return msk

        d_cy = df[_period_mask(df, cy, cy_month) & df['公司'].isin(selected_cos) & df['字段名'].isin(f)]
        d_py = df[_period_mask(df, py, py_month) & df['公司'].isin(selected_cos) & df['字段名'].isin(f)]
        d_sub = pd.concat([d_cy, d_py], ignore_index=True).copy()
        d_sub['value'] = d_sub['(百万)人民币'] / divisor

        avg_acq, avg_maint, avg_non = d_sub[d_sub['字段名'] == "获取费用"]['value'].sum(), d_sub[d_sub['字段名'] == "维持费用"]['value'].sum(), d_sub[d_sub['字段名'] == "非履约费用"]['value'].sum()
        avg_total = avg_acq + avg_maint + avg_non
        p_acq, p_maint, p_non = (avg_acq/avg_total*100) if avg_total>0 else 0, (avg_maint/avg_total*100) if avg_total>0 else 0, (avg_non/avg_total*100) if avg_total>0 else 0
        # 计算全局最高柱子高度，用来兜底
        global_max = max([d_sub[_period_mask(d_sub, yr, mo) & (d_sub['公司']==co)]['value'].sum() for co in selected_cos for (yr, mo) in [(py, py_month), (cy, cy_month)]] + [1.0])
        hl_co = str(highlight_co).strip()
        
        # 🌟 设置灰色占位柱的高度：全局最高的一半
        placeholder_h = global_max * 0.5
        
        titles = [f"<span style='color:#00338D; font-size:{co_font_size}px;'><b>{co}</b></span>" for co in selected_cos]
        fig = make_subplots(rows=1, cols=len(selected_cos), horizontal_spacing=0.02, subplot_titles=titles)
        
        # 统一设置图例
        for leg_name, leg_color in [("获取费用", "rgb(30, 73, 226)"), ("维持费用", "rgb(118, 210, 255)"), ("非履约费用", "rgb(114, 19, 234)")]:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color=leg_color), name=leg_name, showlegend=True), row=1, col=1)
            
        for i, co in enumerate(selected_cos):
            col_idx = i + 1
            xref_key, yref_key, xref_d, yref_d = f"x{col_idx}" if col_idx>1 else "x", f"y{col_idx}" if col_idx>1 else "y", f"x{col_idx} domain" if col_idx>1 else "x domain", f"y{col_idx} domain" if col_idx>1 else "y domain"
            cd = d_sub[d_sub['公司'] == co]
            gv = lambda y, m, field: cd[_period_mask(cd, y, m) & (cd['字段名']==field)]['value'].sum()
            v24a, v25a, v24m, v25m, v24n, v25n = gv(py, py_month, "获取费用"), gv(cy, cy_month, "获取费用"), gv(py, py_month, "维持费用"), gv(cy, cy_month, "维持费用"), gv(py, py_month, "非履约费用"), gv(cy, cy_month, "非履约费用")

            t24, t25 = v24a+v24m+v24n, v25a+v25m+v25n
            m24, m25 = (t24 == 0), (t25 == 0) # 🌟 标记这两个报告期是不是全空（未披露）

            lbl = lambda v, t: f"{v/t*100:.0f}%" if t>0 and v>0 else ""
            x_axis = [py_label, cy_label]
            
            # 🌟 画真实数据柱子（如果是未披露，传进去的是 0，在堆叠图里会自动隐形）
            fig.add_trace(go.Bar(x=x_axis, y=[v24a, v25a], marker_color="rgb(30, 73, 226)", width=bar_width, showlegend=False, text=[lbl(v24a,t24), lbl(v25a,t25)] if show_labels else None, textposition='inside', textangle=0, textfont=dict(size=label_size, color="white"), constraintext='none'), row=1, col=col_idx)
            fig.add_trace(go.Bar(x=x_axis, y=[v24m, v25m], marker_color="rgb(118, 210, 255)", width=bar_width, showlegend=False, text=[lbl(v24m,t24), lbl(v25m,t25)] if show_labels else None, textposition='inside', textangle=0, textfont=dict(size=label_size, color="#1a1a2e"), constraintext='none'), row=1, col=col_idx)
            fig.add_trace(go.Bar(x=x_axis, y=[v24n, v25n], marker_color="rgb(114, 19, 234)", width=bar_width, showlegend=False, text=[lbl(v24n,t24), lbl(v25n,t25)] if show_labels else None, textposition='inside', textangle=0, textfont=dict(size=label_size, color="white"), constraintext='none'), row=1, col=col_idx)                        
            
            # 🌟 专门画一层隐形的灰色占位柱子
            fig.add_trace(go.Bar(
                x=x_axis, 
                y=[placeholder_h if m24 else 0, placeholder_h if m25 else 0], 
                marker_color="#CDCDCD", width=bar_width, showlegend=False, 
                text=["未披露" if m24 else "", "未披露" if m25 else ""], 
                textposition='inside', insidetextanchor='middle', textangle=0,textfont=dict(size=12, color="white"), constraintext='none', cliponaxis=False
            ), row=1, col=col_idx)

            # 🌟 连线逻辑：只有当两年都有真实数据时，才画段之间的连接线
            if not m24 and not m25:
                for y0, y1 in [(v24a, v25a), (v24a+v24m, v25a+v25m), (t24, t25)]:
                    fig.add_shape(type="line", xref=xref_key, yref=yref_key, x0=bar_width/2, y0=y0, x1=1-bar_width/2, y1=y1, line=dict(color="rgba(170,170,170,0.85)", width=0.9), layer="above")
            
            # 顶部总额标签（未披露时不画顶部数字）
            for x_cat, total_v, is_missing in [(py_label, t24, m24), (cy_label, t25, m25)]:
                if not is_missing:
                    fig.add_annotation(x=x_cat, y=total_v+global_max*0.02, xref=xref_key, yref=yref_key, text=f"<b>{total_v:.0f}</b>", showarrow=False, font=dict(size=label_size, color="#222"), bgcolor="white", bordercolor="#BBB", borderwidth=1, xanchor="center", yanchor="bottom")
            
            # 🌟 涨幅箭头逻辑：只有当两年都有数据时，才计算和绘制增幅箭头
            if not m24 and not m25:
                pct = ((t25-t24)/t24*100) if t24>0 else 0
                base_arrow_y, slope = max(t24, t25) + global_max*0.12, global_max*0.01
                if pct > 0: y_start, y_end, arr_clr, sign = base_arrow_y-slope, base_arrow_y+slope, "rgb(253, 52, 155)", "+"
                elif pct < 0: y_start, y_end, arr_clr, sign = base_arrow_y+slope, base_arrow_y-slope, "rgb(0, 180, 100)", ""
                else: y_start, y_end, arr_clr, sign = base_arrow_y, base_arrow_y, "rgb(253, 52, 155)", ""
                fig.add_annotation(x=0.65, y=y_end, ax=0.35, ay=y_start, xref=xref_key, yref=yref_key, axref=xref_key, ayref=yref_key, text="", showarrow=True, arrowhead=2, arrowsize=0.7, arrowwidth=1.5, arrowcolor=arr_clr)
                fig.add_annotation(x=0.5, xref=xref_d, y=max(y_start, y_end)+global_max*0.02, yref=yref_key, text=f"<b>{sign}{pct:.0f}%</b>", showarrow=False, font=dict(size=label_size+1, color=arr_clr), xanchor="center", yanchor="bottom")
            
            # 框线与背景
            is_hl = (str(co).strip() == hl_co)
            bg_fill = HL_BOX_FILL   if is_hl else ("rgba(200, 200, 200, 0.18)" if i % 2 == 1 else "rgba(255,255,255,0)")
            border_dict = dict(color=HL_BOX_LINE, width=1.5) if is_hl else dict(color="#CCCCCC", width=1)
            fig.add_shape(type="rect", xref=xref_d, yref=yref_d, x0=0, x1=1, y0=-0.1, y1=1.13, line=border_dict, fillcolor=bg_fill, layer="above" if is_hl else "below", row=1, col=col_idx)

            fig.update_yaxes(range=[0, global_max*1.3], showticklabels=False, showgrid=False, zeroline=False, row=1, col=col_idx)
            fig.update_xaxes(type="category", showgrid=False, zeroline=False, ticks="", ticklen=0, row=1, col=col_idx)
            
        fig.update_layout(barmode='stack', height=550, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=80, l=10, r=10), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, font=dict(size=12), itemsizing="constant"))
        for ann in fig.layout.annotations:
            if "span" in str(ann.text): ann.update(y=1.03)

        return fig, (p_acq, p_maint, p_non)

# --- 27. 折现率假设表 (纯HTML生成不变) ---
    def create_discount_rate_table(df_raw, cos, current_period=None, comparison_period=None, highlight_co="无"):
        df = df_raw.copy()
        for c in ['报告年份','公司','字段名']:
            df[c] = df[c].astype(str).str.replace('.0','',regex=False).str.strip()
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)
        val_col = "(百万)人民币" if "(百万)人民币" in df.columns else df.columns[-1]

        def build_map(field, y, m):
            msk = df['公司'].isin(cos) & (df['报告年份'] == str(y)) & (df['字段名'] == field)
            if m is not None and '报告月份' in df.columns:
                msk = msk & (df['报告月份'].astype(str) == str(m))
            d = df[msk].copy()
            mp = {}
            for _, r in d.iterrows():
                k, v = r['公司'], r.get(val_col, "")
                if k not in mp and pd.notna(v) and str(v).strip().lower() not in ["", "nan", "none", "null", "-"]:
                    mp[k] = str(v).strip()
            return mp

        # 只保留基本的折现率提取
        disc_map_cy = build_map("折现率假设", cy, cy_month)
        disc_map_py = build_map("折现率假设", py, py_month)
    
        def fmt(v):
            if pd.isna(v) or str(v).strip().lower() in ["", "nan", "none", "null", "-"]:
                return "未披露", True
            # 保留换行符替换机制，防止长文本撑爆表格
            v_str = str(v).strip().replace('\n', '<br>').replace('\r', '')
            return v_str, False
    
        hl = str(highlight_co).strip()
        
        # 调整表头：去掉第四列，宽度重新分配为 30% / 35% / 35%
        html = "<table style='width:100%; border-collapse:collapse; font-family:sans-serif; margin-bottom:20px; font-size:13px;'>"
        html += f"<tr style='background-color:#00338D; color:white; font-size:14px; text-align:center; font-weight:bold;'><th style='padding:10px; text-align:left; border:1px solid white; width:30%;'>公司名称</th><th style='padding:10px; text-align:center; border:1px solid white; width:35%;'>{cy_label}</th><th style='padding:10px; text-align:center; border:1px solid white; width:35%;'>{py_label}</th></tr>"
    
        for i, co in enumerate(cos):
            v_c, m_c = fmt(disc_map_cy.get(co, "-"))
            v_p, m_p = fmt(disc_map_py.get(co, "-"))
            
            is_hl = str(co).strip() == hl
            row_bg = "rgba(0,51,141,0.08)" if is_hl else ("#F8F9FA" if i % 2 == 0 else "white")
            tc, fw = ("#00338D", "bold") if is_hl else ("#333", "normal")
            bd = "border-top:2px solid #00338D; border-bottom:2px solid #00338D; border-left:1px solid #EAEAEA; border-right:1px solid #EAEAEA;" if is_hl else "border:1px solid #EAEAEA;"
            
            sc = "background-color:#CDCDCD; color:white;" if m_c else f"color:{tc};"
            sp = "background-color:#CDCDCD; color:white;" if m_p else f"color:{tc};"
            
            # 调整数据行：去掉第四个 <td> 单元格
            html += f"<tr style='background-color:{row_bg}; font-weight:{fw};'><td style='padding:12px 10px; text-align:left; {bd} font-weight:bold; color:{tc};'>{co}</td><td style='padding:12px 10px; text-align:center; {bd} {sc}'>{v_c}</td><td style='padding:12px 10px; text-align:center; {bd} {sp}'>{v_p}</td></tr>"
            
        return html + "</table>"
    
# --- 28. 非金融风险置信水平表 (纯HTML生成不变) ---
    def create_confidence_level_table(df_raw, cos, current_period=None, comparison_period=None, highlight_co="无"):
        df = df_raw.copy()
        df['报告年份'] = df['报告年份'].astype(str).str.replace('.0', '', regex=False)
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)

        def _mask(y, m):
            msk = (df['报告年份'] == str(y)) & (df['公司'].isin(cos)) & (df['字段名'].str.contains("非金融风险的置信水平", na=False))
            if m is not None and '报告月份' in df.columns:
                msk = msk & (df['报告月份'].astype(str) == str(m))
            return msk

        val_col = "(百万)人民币" if "(百万)人民币" in df.columns else df.columns[-1]
        cy_map = df[_mask(cy, cy_month)].drop_duplicates(['公司'], keep='first').set_index('公司')[val_col].to_dict()
        py_map = df[_mask(py, py_month)].drop_duplicates(['公司'], keep='first').set_index('公司')[val_col].to_dict()

        current_hl = str(highlight_co).strip()
        
        def format_conf_val(val):
            if pd.isna(val):
                return "未披露", True
        
            s = str(val).strip()
            s_norm = s.replace("％", "%").replace("－", "-").replace("—", "-").replace("–", "-").replace("～", "~")
        
            # 只有真正空白/无内容才算未披露
            if s_norm.lower() in ["", "nan", "none", "null", "无", "-"]:
                return "未披露", True
        
            # 只要有 % 或区间符号，直接展示文本
            if "%" in s_norm or "~" in s_norm or "-" in s_norm or "至" in s_norm or "到" in s_norm:
                return s_norm, False
        
            # 纯数字：0.75 -> 75%，75 -> 75%
            try:
                num = float(s_norm.replace(",", ""))
                if num == 0:
                    return "未披露", True
                return (f"{num * 100:.0f}%" if 0 < abs(num) <= 1 else f"{num:.0f}%"), False
            except:
                # 只要单元格有文本，就展示，不判未披露
                return s_norm, False

        html = "<table style='width:100%; border-collapse: collapse; font-family: sans-serif; margin-bottom: 20px; font-size: 13px;'>"
        html += f"<tr style='background-color: #00338D; color: white; font-size: 14px; text-align: center; font-weight: bold;'><th style='padding: 10px; text-align: left; border: 1px solid white; width: 30%;'>公司名称</th><th style='padding: 10px; text-align: center; border: 1px solid white; width: 35%;'>{cy_label}</th><th style='padding: 10px; text-align: center; border: 1px solid white; width: 35%;'>{py_label}</th></tr>"

        for row_idx, co in enumerate(cos):
            v_c, m_c = format_conf_val(cy_map.get(co, "-"))
            v_p, m_p = format_conf_val(py_map.get(co, "-"))
            is_hl = (str(co).strip() == current_hl)
            
            row_bg, text_color, font_weight, borders = ("#F8F9FA" if row_idx % 2 == 0 else "white"), "#333", "normal", "border: 1px solid #EAEAEA;"
            if is_hl: 
                row_bg, text_color, font_weight, borders = "rgba(0, 51, 141, 0.08)", "#00338D", "bold", "border-top: 2px solid #00338D; border-bottom: 2px solid #00338D; border-left: 1px solid #EAEAEA; border-right: 1px solid #EAEAEA;"
            
            style_c = f"background-color: #CDCDCD; color: white;" if m_c else f"color: {text_color};"
            style_p = f"background-color: #CDCDCD; color: white;" if m_p else f"color: {text_color};"
            
            html += f"<tr style='background-color: {row_bg}; font-weight: {font_weight};'><td style='padding: 12px 10px; text-align: left; {borders} font-weight: bold; color: {text_color};'>{co}</td><td style='padding: 12px 10px; text-align: center; {borders} {style_c}'>{v_c}</td><td style='padding: 12px 10px; text-align: center; {borders} {style_p}'>{v_p}</td></tr>"
            
        return html + "</table>"


# --- 28. 合同服务边际CSM 预期摊销速度折线图 ---
    def create_csm_maturity_table(df_raw, period, selected_cos, color_map, show_labels, marker_size, highlight_co="无", title_text=""):
        COMMON_TITLE_FONT = dict(size=18, color="#00338D", family="Microsoft YaHei")

        df = df_raw.copy()
        df['报告年份'] = df['报告年份'].astype(str).str.replace('.0', '', regex=False)
        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        curr_year_str = str(t_year).replace('.0', '')

        fields = [
            "1年及1年以内合同服务边际", "1-5年合同服务边际",
            "5-10年合同服务边际", "10-20年合同服务边际", "20年合同服务边际"
        ]

        df_target = df[(df['报告年份'] == curr_year_str) & (df['公司'].isin(selected_cos)) & (df['字段名'].isin(fields))]
        if t_month is not None and '报告月份' in df_target.columns:
            df_target = df_target[df_target['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(t_month).replace('.0', '')]
        df_target = df_target.copy()
        
        preferred_cols = ["(%)原币", "(%)", "百分比", "比例", "占比", "数值", "值", "(百万)原币"]
        val_col = next((c for c in preferred_cols if c in df_target.columns), None)
        if not val_col:
            non_dim_cols = [c for c in df_target.columns if c not in ['报告年份', '公司', '字段名']]
            val_col = non_dim_cols[-1] if non_dim_cols else None
            
        if not val_col: return go.Figure()

        data_map = df_target.set_index(['公司', '字段名'])[val_col].to_dict()
        
        def parse_pct(v):
            if pd.isna(v): return None
            s = str(v).strip()
            if s in ["", "nan", "-"]: return None
            try:
                if "%" in s: return float(s.replace("%", "").replace(",", ""))
                num = float(s.replace(",", ""))
                if abs(num) <= 1.0: return num * 100
                return num
            except:
                return None

        fig = go.Figure()
        hl_co = str(highlight_co).strip()

        # 🌟 第一步：遍历计算数据，并标记哪些公司是“未披露/数据为0”
        plot_info = {}
        valid_cos = []  # 专门存放有真实有效数据的公司名单
        for co in selected_cos:
            f1 = parse_pct(data_map.get((co, "1年及1年以内合同服务边际")))
            f5 = parse_pct(data_map.get((co, "1-5年合同服务边际")))
            f10 = parse_pct(data_map.get((co, "5-10年合同服务边际")))
            f20 = parse_pct(data_map.get((co, "10-20年合同服务边际")))
            f20p = parse_pct(data_map.get((co, "20年合同服务边际")))
            
            has_0_5 = (f1 is not None and f1 > 0) or (f5 is not None and f5 > 0)
            
            v1  = f1  if f1  is not None else 0
            v5  = f5  if f5  is not None else 0
            v10 = f10 if f10 is not None else 0
            v20 = f20 if f20 is not None else 0
            v20p = f20p if f20p is not None else 0
            
            actual_v10 = ((v20 + v20p) / 2) if (f10 is None or v10 == 0) else v10
            x_vals = [0, 5, 10]
            
            if has_0_5:
                y5  = v1 + v5
                y10 = y5 + actual_v10
            else:
                y10 = actual_v10
                y5  = y10 / 2.0
            
            # 🌟 拦截：如果10年累计依然是0，判定为无数据/未披露
            is_missing = (y10 == 0)
            if not is_missing:
                valid_cos.append(co)
                
            plot_info[co] = {'x_vals': x_vals, 'y_vals': [0, y5, y10], 'y5': y5, 'y10': y10, 'is_missing': is_missing}

        # 🌟 找出 X=10 时最高和最低的公司（只在有效公司里找！）
        max_co = max(valid_cos, key=lambda k: plot_info[k]['y10']) if valid_cos else None
        min_co = min(valid_cos, key=lambda k: plot_info[k]['y10']) if valid_cos else None

        # 🌟 第二步：正式画图并分配虚实线
        for co in selected_cos:
            p_data = plot_info[co]
            
            if p_data['is_missing']:
                # 🌟 生成“隐形图例”：不画真实的线，名字标灰并加(未披露)
                fig.add_trace(go.Scatter(
                    x=[None], y=[None], 
                    name=f"<span style='color:#999999'>{co} (未披露)</span>", 
                    mode='lines+markers', 
                    line=dict(color="#CDCDCD", width=2, dash="dot"), 
                    marker=dict(size=marker_size, symbol='circle'),
                    showlegend=True
                ))
            else:
                # 🌟 正常绘制有数据的公司
                y5, y10 = p_data['y5'], p_data['y10']
                is_hl = (co == hl_co)
                is_ext = (co in [max_co, min_co])
                
                default_color = f"hsl({hash(co) % 360}, 70%, 50%)" 
                line_color = "#00338D" if is_hl else color_map.get(co, default_color)
                
                # 高亮和极值线稍微加粗，高亮为4，极值为2.5
                line_width = 4 if is_hl else (2.5 if is_ext else 2) 
                
                # 🌟 判断线型：最高、最低以及高亮的公司用实线，其余全部用虚线
                line_dash = "solid" if (is_ext or is_hl) else "dash"
                
                fig.add_trace(go.Scatter(
                    x=p_data['x_vals'],
                    y=p_data['y_vals'],
                    name=co,
                    mode='lines+markers+text' if show_labels else 'lines+markers',
                    text=["", f"{y5:.1f}%", f"{y10:.1f}%"], # 起点 0 不显示文字，显得干净
                    textposition="top center",
                    line=dict(color=line_color, width=line_width, dash=line_dash), 
                    marker=dict(size=marker_size * 1.5 if is_hl else marker_size, color=line_color),
                    cliponaxis=False
                ))
                
        layout_args = dict(
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)', 
            margin=dict(t=80 if title_text else 50, b=40, l=40, r=40), 
            height=450,
            # 将图例移到顶部并换行展示，防止重叠
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=11), itemwidth=30)
        )
        if title_text:
            layout_args['title'] = dict(text=f"<b>{title_text}</b>", x=0.5, y=0.95, xanchor='center', font=COMMON_TITLE_FONT)
            
        fig.update_layout(**layout_args)
        
        # 强制格式化 X 轴和 Y 轴
        fig.update_xaxes(
            tickvals=[0, 5, 10], 
            ticktext=["0", "5年", "10年"], 
            showgrid=True, gridcolor="rgba(200,200,200,0.3)", zeroline=False
        )
        fig.update_yaxes(
            showgrid=True, gridcolor="rgba(200,200,200,0.3)", 
            zeroline=True, zerolinecolor="#E0E0E0", 
            tickformat=".0f", ticksuffix="%"
        )
        
        return fig



# --- 29. 散点图 ---
    # 通用比率/增长率散点图
    def _scatter_field_getter(df_raw, period, cos):
        """period: (年份, 月份) 二元组，同时按年份+月份过滤，避免同一年份多个月份的数据互相冲突"""
        year, month = period
        df = df_raw.copy()
        df[["字段名", "公司", "报告年份", "报告月份"]] = df[["字段名", "公司", "报告年份", "报告月份"]].astype(str).apply(lambda x: x.str.strip().str.replace(".0", "", regex=False))
        df_year = df[(df["报告年份"] == str(year)) & (df["报告月份"] == str(month)) & df["公司"].isin(cos)]
        def _get(co, field):
            rows = df_year[(df_year["公司"] == co) & (df_year["字段名"] == field)]
            if rows.empty: return float("nan")
            val_col = "(百万)人民币" if "(百万)人民币" in rows.columns else rows.columns[-1]
            return pd.to_numeric(rows[val_col].iloc[0], errors="coerce")
        return _get

    REF_LINE_STYLE = dict(color="black", width=1, dash="dash")

    def _add_ref_line(fig, records, ref_line, diagonal_note):
        """按 ref_line 画参考虚线并在右下角加说明。ref_line: None/"median"/"zero"/"diag_neg1"/"diag_pos1" """
        if not ref_line:
            return
        xs, ys = [r["x"] for r in records], [r["y"] for r in records]
        if ref_line == "median":
            fig.add_vline(x=float(np.median(xs)), line=REF_LINE_STYLE, layer="below")
            fig.add_hline(y=float(np.median(ys)), line=REF_LINE_STYLE, layer="below")
            note = "虚线：样本中位数"
        elif ref_line == "zero":
            fig.add_vline(x=0, line=REF_LINE_STYLE, layer="below")
            fig.add_hline(y=0, line=REF_LINE_STYLE, layer="below")
            note = "虚线：零轴"
        elif ref_line in ("diag_neg1", "diag_pos1"):
            sign = -1 if ref_line == "diag_neg1" else 1
            x_lo, x_hi = min(xs), max(xs)
            if np.isclose(x_lo, x_hi):
                pad = max(abs(x_lo) * 0.1, 1.0)
                x_lo, x_hi = x_lo - pad, x_hi + pad
            fig.add_shape(type="line", xref="x", yref="y", x0=x_lo, y0=sign * x_lo, x1=x_hi, y1=sign * x_hi,
                          line=dict(color="black", width=1, dash="dash"), layer="below")
            note = diagonal_note if ref_line == "diag_neg1" else "虚线：Y=X"
        else:
            return
        fig.add_annotation(text=f"<b>{note}</b>", xref="paper", yref="paper", x=1, y=-0.02, xanchor="right", yanchor="bottom",
                            showarrow=False, font=dict(size=11, color="#333333"))

    def create_ratio_scatter_chart(df_raw, cy, py, cos, title, x_label, x_calc, y_label, y_calc,
                                    highlight_co="无", label_size=11, show_labels=False, dot_size=11,
                                    x_pct=True, y_pct=True, size_calc=None, size_label="",
                                    min_bubble=8, max_bubble=30, ref_line=None, diagonal_note="虚线：Y＝－X"):
        """通用双轴气泡散点图。x_calc/y_calc/size_calc 签名均为 (get_cy, get_py, 公司) -> float|None。"""
        get_cy, get_py = _scatter_field_getter(df_raw, cy, cos), _scatter_field_getter(df_raw, py, cos)

        records = []
        for co in cos:
            try:
                x_val, y_val = x_calc(get_cy, get_py, co), y_calc(get_cy, get_py, co)
            except Exception:
                continue
            if x_val is None or y_val is None or pd.isna(x_val) or pd.isna(y_val):
                continue
            size_val = None
            if size_calc is not None:
                try:
                    size_val = size_calc(get_cy, get_py, co)
                except Exception:
                    size_val = None
                if size_val is not None and pd.isna(size_val):
                    size_val = None
            records.append({"公司": co, "x": x_val, "y": y_val, "size": size_val})

        fig = go.Figure()
        if not records:
            fig.update_layout(height=500, xaxis_title=x_label, yaxis_title=y_label,
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            return fig

        cmap, hl = get_color_map(cos), str(highlight_co).strip()
        size_vals = [np.log1p(r["size"]) for r in records if r["size"] is not None and r["size"] > 0]

        def _bubble_px(v):
            if v is None or v <= 0 or not size_vals:
                return dot_size
            v, lo, hi = np.log1p(v), min(size_vals), max(size_vals)
            if hi <= lo:
                return (min_bubble + max_bubble) / 2
            frac = (v - lo) / (hi - lo)
            area_lo, area_hi = min_bubble ** 2, max_bubble ** 2
            return (area_lo + frac * (area_hi - area_lo)) ** 0.5

        _add_ref_line(fig, records, ref_line, diagonal_note)

        for r in records:
            co, is_hl = r["公司"], (r["公司"] == hl)
            px = _bubble_px(r["size"]) if size_calc is not None else (dot_size * 1.45 if is_hl else dot_size)
            size_hover = f"<br>{size_label}: {r['size']:.0f}" if (size_calc is not None and r["size"] is not None) else ""
            fig.add_trace(go.Scatter(
                x=[r["x"]], y=[r["y"]], mode="markers+text" if show_labels else "markers", name=co,
                text=[co] if show_labels else None, textposition="top center", textfont=dict(size=label_size, color="#333"),
                marker=dict(size=px, color=cmap.get(co, "#1f77b4"), line=dict(color="white", width=1.8 if is_hl else 1.2), opacity=0.95),
                customdata=[[f"{r['x']:.1f}", f"{r['y']:.1f}"]],
                hovertemplate=f"<b>{co}</b><br>{x_label}: %{{customdata[0]}}{'%' if x_pct else ''}<br>{y_label}: %{{customdata[1]}}{'%' if y_pct else ''}{size_hover}<extra></extra>"
            ))

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=460, margin=dict(t=70, b=60, l=70, r=40), hovermode="closest",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
                        font=dict(size=11), itemwidth=40, tracegroupgap=8, itemsizing="constant")
        )
        axis_frame = dict(showline=True, mirror="allticks", linecolor="black", linewidth=1.6,
                           ticks="outside", ticklen=4, tickwidth=1.6)
        fig.update_xaxes(title=dict(text=x_label, font=dict(size=12, color="#333333")), showgrid=True,
                          gridcolor="rgba(120,120,120,0.6)", gridwidth=1, zeroline=True, zerolinecolor="rgba(80,80,80,0.7)",
                          ticksuffix="%" if x_pct else "", **axis_frame)
        fig.update_yaxes(title=dict(text=y_label, font=dict(size=12, color="#333333")), showgrid=True,
                          gridcolor="rgba(120,120,120,0.6)", gridwidth=1, zeroline=True, zerolinecolor="rgba(80,80,80,0.7)",
                          ticksuffix="%" if y_pct else "", **axis_frame)
        return fig

    # ---- 公用公式（供下方各图 x_calc/y_calc 复用）----

    def _margin_ratio(g, co):
        """保险服务利润率 = (保险服务收入合计-保险服务费用合计) / 保险服务收入合计 × 100"""
        inc, exp = g(co, "保险服务收入合计"), g(co, "保险服务费用合计")
        return None if pd.isna(inc) or inc == 0 else (inc - (exp if pd.notna(exp) else 0)) / inc * 100

    def _growth_rate(g_cy, g_py, co, field):
        """(本期字段值/对比期字段值 - 1) × 100"""
        cy_v, py_v = g_cy(co, field), g_py(co, field)
        return None if pd.isna(cy_v) or pd.isna(py_v) or py_v == 0 else (cy_v / py_v - 1) * 100

    def _growth_of(calc, g_cy, g_py, co):
        """(本期calc值/对比期calc值 - 1) × 100，calc为_comp_equity等衍生指标函数（非原始字段）"""
        cy_v, py_v = calc(g_cy, co), calc(g_py, co)
        return None if cy_v is None or py_v is None or py_v == 0 else (cy_v / py_v - 1) * 100

    def _diff(calc, g_cy, g_py, co):
        """两期同一衍生指标的差值：calc(本期)-calc(对比期)"""
        v_cy, v_py = calc(g_cy, co), calc(g_py, co)
        return None if v_cy is None or v_py is None else v_cy - v_py

    def _comp_equity(g, co):
        """综合净资产 = 期末股东权益 + CSM期末余额 × 0.75"""
        eq, csm = g(co, "期末股东权益"), g(co, "CSM期末余额")
        return None if pd.isna(eq) else eq + (csm if pd.notna(csm) else 0) * 0.75

    def _avg_eq(g_cy, g_py, co):
        """平均净资产 = (期末股东权益_本期 + 期末股东权益_对比期) / 2，缺失或为0返回None"""
        eq_cy, eq_py = g_cy(co, "期末股东权益"), g_py(co, "期末股东权益")
        if pd.isna(eq_cy) or pd.isna(eq_py):
            return None
        avg = (eq_cy + eq_py) / 2
        return None if avg == 0 else avg

    def _nb_ifrs_margin(g, co):
        """新业务IFRS利润率 = (新业务CSM + 新业务LC) / 新业务未来现金流入现值 × 100"""
        nb_csm, lc, pv = g(co, "新业务CSM（集团口径）"), g(co, "新业务亏损合同（LC）——非PAA"), g(co, "新业务未来现金流入现值")
        return None if pd.isna(pv) or pv == 0 else (nb_csm + (lc if pd.notna(lc) else 0)) / pv * 100

    def _scaled(g, co, field, divisor):
        """按 divisor 缩放的取值，供各图 x_calc/size_calc 里"取一个字段直接除以单位换算系数"的场景复用"""
        v = g(co, field)
        return None if pd.isna(v) else v / divisor

    # ---- 8 张散点图：x_calc/y_calc 多为一行lambda直传 + 调一次 create_ratio_scatter_chart ----

    def create_sc_profit_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """1. 保险规模与盈利：X=保险服务收入，Y=保险服务利润率，气泡=总资产"""
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "保险规模与盈利",
            "保险服务收入", lambda g, p, co: _scaled(g, co, "保险服务收入合计", divisor),
            "保险服务利润率", lambda g, p, co: _margin_ratio(g, co),
            highlight_co, label_size, show_labels, dot_size, x_pct=False, y_pct=True,
            size_calc=lambda g, p, co: _scaled(g, co, "总资产", divisor), size_label=f"总资产({unit_label})", ref_line="median")

    def create_gr_qual_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """2. 保险增长质量：X=保险服务收入增长率，Y=保险服务利润率变动(百分点)，气泡=保险服务收入"""
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "保险增长质量",
            "保险服务收入增长率", lambda g_cy, g_py, co: _growth_rate(g_cy, g_py, co, "保险服务收入合计"),
            "保险服务利润率变动（百分点）", lambda g_cy, g_py, co: _diff(_margin_ratio, g_cy, g_py, co),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g_cy, g_py, co: _scaled(g_cy, co, "保险服务收入合计", divisor), size_label=f"保险服务收入({unit_label})", ref_line="zero")

    def create_dual_engine_profit_chart(df_raw, target_period, cos, highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """3. 双引擎盈利：X=保险服务利润率，Y=投资服务利润率，气泡=总资产"""
        x_calc = _margin_ratio
        def y_calc(g, co):
            nr, uw, re_uw = g(co, "净投资回报"), g(co, "承保财务损益"), g(co, "分出再保险财务损益")
            return None if pd.isna(nr) or nr == 0 else (nr + (uw if pd.notna(uw) else 0) + (re_uw if pd.notna(re_uw) else 0)) / nr * 100
        g = _scatter_field_getter(df_raw, target_period, cos)
        records = [{'公司': co, '保险服务利润率': x, '投资服务利润率': y}
                   for co in cos if (x := x_calc(g, co)) is not None and pd.notna(x) and (y := y_calc(g, co)) is not None and pd.notna(y)]
        df_data = pd.DataFrame(records) if records else pd.DataFrame()
        fig = create_ratio_scatter_chart(df_raw, target_period, target_period, cos, "双引擎盈利",
            "保险服务利润率", lambda g, p, co: x_calc(g, co), "投资服务利润率", lambda g, p, co: y_calc(g, co),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g, p, co: _scaled(g, co, "总资产", 1), size_label="总资产（百万元人民币）", ref_line="median")
        return fig, df_data

    def create_alm_chart(df_raw, cy, py, cos, highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """4. 资产负债匹配：X=本期可转损益的负债OCI/平均净资产，Y=本期FVOCI债券/平均净资产，气泡=净资产；参考线 Y=-X"""
        def _ratio(field):
            def calc(g_cy, g_py, co):
                a, v = _avg_eq(g_cy, g_py, co), g_cy(co, field)
                return None if a is None or pd.isna(v) else v / a * 100
            return calc
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "资产负债匹配",
            "可转损益的负债OCI / 平均净资产", _ratio("可转损益的负债OCI"), "FVOCI债券 / 平均净资产", _ratio("FVOCI债券公允价值"),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g_cy, g_py, co: _scaled(g_cy, co, "期末股东权益", 1),
            size_label="净资产（百万元人民币）", ref_line="diag_neg1", diagonal_note="虚线：Y＝－X")

    def create_nas_sv_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """5. 综合净资产-规模与价值：X=总资产增长率，Y=综合净资产增长率，气泡=综合净资产；参考线 Y=X"""
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "综合净资产-规模与价值",
            "总资产增长率", lambda g_cy, g_py, co: _growth_rate(g_cy, g_py, co, "总资产"),
            "综合净资产增长率", lambda g_cy, g_py, co: _growth_of(_comp_equity, g_cy, g_py, co),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g_cy, g_py, co: None if _comp_equity(g_cy, co) is None else _comp_equity(g_cy, co) / divisor,
            size_label=f"综合净资产({unit_label})", ref_line="diag_pos1")

    def create_nas_pf_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """6. 综合净资产-资本积累与未赚利润储备：X=净资产增长率，Y=CSM增长率，气泡=CSM期末余额"""
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "综合净资产-过去利润与未来利润",
            "净资产增长率", lambda g_cy, g_py, co: _growth_rate(g_cy, g_py, co, "期末股东权益"),
            "CSM增长率", lambda g_cy, g_py, co: _growth_rate(g_cy, g_py, co, "CSM期末余额"),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g_cy, g_py, co: _scaled(g_cy, co, "CSM期末余额", divisor), size_label=f"CSM期末余额({unit_label})", ref_line="median")

    def create_shr_ret_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """7. 股东回报：X=净资产(绝对额)，Y=ROE净资产收益率，气泡=税后利润"""
        def y_calc(g_cy, g_py, co):
            a, p = _avg_eq(g_cy, g_py, co), g_cy(co, "净利润")
            return None if a is None or pd.isna(p) else p / a * 100
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "股东回报",
            "净资产", lambda g_cy, g_py, co: _scaled(g_cy, co, "期末股东权益", divisor), "ROE净资产收益率", y_calc,
            highlight_co, label_size, show_labels, dot_size, x_pct=False, y_pct=True,
            size_calc=lambda g_cy, g_py, co: _scaled(g_cy, co, "净利润", divisor), size_label=f"税后利润({unit_label})", ref_line="median")

    def create_nb_qual_chart(df_raw, cy, py, cos, divisor=1, unit_label="百万元", highlight_co="无", label_size=11, show_labels=False, dot_size=11):
        """8. 新业务质量：X=新业务CSM增长率，Y=新业务IFRS利润率变动率，气泡=新业务未来现金流入现值"""
        return create_ratio_scatter_chart(df_raw, cy, py, cos, "新业务质量",
            "新业务CSM增长率", lambda g_cy, g_py, co: _growth_rate(g_cy, g_py, co, "新业务CSM（集团口径）"),
            "新业务IFRS利润率变动率", lambda g_cy, g_py, co: _diff(_nb_ifrs_margin, g_cy, g_py, co),
            highlight_co, label_size, show_labels, dot_size, x_pct=True, y_pct=True,
            size_calc=lambda g_cy, g_py, co: _scaled(g_cy, co, "新业务未来现金流入现值", divisor),
            size_label=f"新业务未来现金流入现值({unit_label})", ref_line="zero")

    # 每张散点图的气泡大小对应字段说明，供 display_notes 生成注释文字；新增图表时在此加一行即可
    SCATTER_SIZE_FIELD = {
        "sc_profit_ratio": "总资产规模",
        "gr_qual_ratio": "保险服务收入",
        "uw_inv_comboratio": "总资产规模",
        "alm_ratio": "净资产规模",
        "nas_sv_ratio": "综合净资产规模",
        "nas_pf_ratio": "CSM期末余额",
        "shr_ret_ratio": "税后利润",
        "nb_qual_ratio": "新业务未来现金流入现值",
    }

    def display_notes(module_id, ai_df=None, ai_field=None, is_pct=False):
        md = notes_dict.get(module_id, {})
        an_default = md.get('analysis_default', "")
        an_custom  = md.get('analysis_custom', "")
        nt         = md.get('note', "")
        ai_txt     = generate_ai_insight(ai_df, ai_field, is_pct)

        # 核心：只要该模块的自定义列为空，就自动生成（不再区分默认表/上传表）
        if not an_custom:
            an_custom = generate_custom_analysis(
                module_id, df_filtered, selected_cos, current_period, comparison_period
            )

        if module_id in SCATTER_SIZE_FIELD:
            if nt:
                nt = re.sub(r"[；;，,。．.]*\s*（?虚线.*?）?\s*", "", nt)
            size_field = SCATTER_SIZE_FIELD[module_id]
            if size_field:
                nt = join_note_parts(f"气泡大小由{size_field}决定（log1p缩放，仅表达相对规模）。", nt)

        elif module_id == "summary_table":
            cy_label = format_period_label(current_period[0], current_period[1])
            py_label = format_period_label(comparison_period[0], comparison_period[1])
            formula_note = (
                f"%变化 = 本期/对比期-1，即 {cy_label}/{py_label}-1；"
                "CSM摊销比例 = CSM摊销/(摊销前的期末CSM)；"
                "CSM持续率 = 新业务CSM/CSM摊销"
            )
            nt = join_note_parts(formula_note, nt)

        def _remove_break_before_second_point(value):
            """确保编号①和②连续显示，不在②前插入强制换行。"""
            if not value:
                return value
            return re.sub(r"(?:<br\s*/?>|\r?\n|\r)\s*(?=②)", "", str(value))

        an_default = _remove_break_before_second_point(an_default)
        an_custom = _remove_break_before_second_point(an_custom)
        ai_txt = _remove_break_before_second_point(ai_txt)

        if an_default or an_custom or ai_txt:
            html = '<div style="text-align:left; background:#F0F4FA; border-left:4px solid #00338D; padding:3px 10px; margin-bottom:6px; border-radius:4px; font-family:Microsoft YaHei, 微软雅黑, sans-serif;">'
            if an_default:
                html += f'<p style="margin:2px 0; color:#0A1F5C; font-size:14px; line-height:1.4;">{an_default}</p>'
            if an_custom:
                html += f'<p style="margin:2px 0; color:#7A9CC5; font-size:14px; line-height:1.4;">{an_custom}</p>'
            if ai_txt:
                html += f'<p style="margin:2px 0; color:#D84315; font-size:12px; line-height:1.4;">{ai_txt}</p>'
            st.markdown(html + "</div>", unsafe_allow_html=True)

        return (an_default or an_custom), nt

# --- 29. 业绩明细表 (纯HTML生成不变) ---
    def create_financial_report_table(df_raw, period, cos, div, unit_str, highlight_co="无"):
        df = df_raw.copy()
        df['报告年份'] = df['报告年份'].astype(str).str.replace('.0', '', regex=False)
        if isinstance(period, tuple):
            t_year, t_month = period
        else:
            t_year, t_month = period, None
        df_year = df[(df['报告年份'] == str(t_year).replace('.0', '')) & (df['公司'].isin(cos))]
        if t_month is not None and '报告月份' in df_year.columns:
            df_year = df_year[df_year['报告月份'].astype(str).str.replace('.0', '', regex=False) == str(t_month).replace('.0', '')]
        val_col = "(百万)人民币" if "(百万)人民币" in df.columns else df.columns[-1]
        data_map = df_year.set_index(['公司', '字段名'])[val_col].to_dict()
        get_val = lambda co, field: data_map.get((co, field), None) # 🌟 找不到时返回 None 而不是 0，用来判定是否未披露

        rows_config = [("未采用保费分配法的保险合同", None, "header"), ("保险服务收入", "未采用保费分配法计量的保险合同保险服务收入", "data"), ("合同服务边际的释放", "合同服务边际的摊销", "data"), ("非金融风险调整的变动", "非金融风险调整的变动", "data"), ("预期当期发生的保险服务费用", "预计当期发生的保险服务费用", "data"), ("保险获取现金流的摊销", "保险获取现金流的摊销（保险服务收入）", "data"), ("其他", "其他收入调整", "data"), ("保险服务费用", "未采用保费分配法计量的保险合同保险服务费用", "neg_data"), ("保险获取现金流的摊销 ", "保险获取现金流的摊销（保险服务费用）", "neg_data"), ("亏损部分的确认及转回", "亏损部分的确认及转回", "neg_data"), ("当期发生的赔款及其他相关费用", "当期发生的赔款及其他相关费用", "neg_data"), ("已发生赔款负债相关的履约现金流量变动", "已发生赔款负债相关的履约现金流量变动", "neg_data"), ("其他项", "FIXED_ZERO", "data"), ("保险服务业绩", "FORMULA_KPI_1", "subtotal"), ("采用保费分配法的保险合同", None, "header"), ("保险服务收入 ", "采用保费分配法计量的保险合同保险服务收入", "data"), ("保险服务费用 ", "采用保费分配法计量的保险合同保险服务费用", "neg_data"), ("保险服务业绩 ", "采用保费分配法计量的保险合同保险业绩", "data"), ("集团/业务条线-汇总", None, "header"), ("保险服务收入  ", "保险服务收入合计", "data"), ("保险服务费用  ", "保险服务费用合计", "neg_data"), ("保险服务业绩（不含再保收支净额）", "FORMULA_TOTAL_KPI", "total"), ("CSM释放在保险服务业绩中占比", "FORMULA_CSM_RATIO", "percent")]
        current_hl = str(highlight_co).strip()
        html = "<table style='width:96%; border-collapse: collapse; font-family: sans-serif; margin-bottom: 10px; font-size: 10.5px;'><thead>"
        html += f"<tr style='background-color: #00338D; color: white; font-size: 11px; text-align: center; font-weight: bold;'><th style='padding: 3px 2px; text-align: left; border: 1.5px solid white;'>项目名称 (单位: {unit_str}人民币)</th>"
        for co in cos:
            is_hl = (str(co).strip() == current_hl)
            html += f"<th style='padding: 3px 2px; text-align: center; background-color: {'#001A4D' if is_hl else '#00338D'}; border-top: 1px solid {'#00338D' if is_hl else 'white'}; border-left: 1px solid {'#00338D' if is_hl else 'white'}; border-right: 1px solid {'#00338D' if is_hl else 'white'}; border-bottom: none;'>{co}</th>"
        html += "</tr></thead><tbody>"

        total_rows = len(rows_config)
        for row_idx, (row_name, field, r_type) in enumerate(rows_config):
            is_header, is_total = (r_type == "header"), (r_type in ["subtotal", "total"])
            row_bg = "#E8EDF4" if is_header else ("white" if row_idx % 2 == 0 else "#F8F9FA")
            n_weight, n_indent = ("bold" if (is_header or is_total) else "normal"), ("0px" if is_header else "10px")
            html += f"<tr><td style='padding: 2px 3px; padding-left: {n_indent}; text-align: left; font-weight: {n_weight}; background-color: {row_bg}; border: 1px solid #EAEAEA; color: #333333;'>{row_name}</td>"
            
            for co in cos:
                is_hl = (str(co).strip() == current_hl)
                val_str, is_missing = "", False
                if not is_header:
                    if r_type == "data": val = (get_val(co, field) / div) if field != "FIXED_ZERO" and get_val(co, field) is not None else (0 if field == "FIXED_ZERO" else None)
                    elif r_type == "neg_data": val = -(get_val(co, field) / div) if get_val(co, field) is not None else None
                    elif r_type in ["subtotal", "total", "percent"]:
                        v1, v2 = get_val(co, "未采用保费分配法计量的保险合同保险服务收入"), get_val(co, "未采用保费分配法计量的保险合同保险服务费用")
                        if r_type == "subtotal": val = (v1/div - v2/div) if v1 is not None and v2 is not None else None
                        elif r_type == "total": 
                            t1, t2 = get_val(co, "保险服务收入合计"), get_val(co, "保险服务费用合计")
                            val = (t1/div - t2/div) if t1 is not None and t2 is not None else None
                        elif r_type == "percent":
                            csm_rel = get_val(co, "合同服务边际的摊销")
                            denom = (v1 - v2) if v1 is not None and v2 is not None else None
                            val = (csm_rel / denom) if csm_rel is not None and denom is not None and denom != 0 else None
                    
                    if pd.isna(val) or val is None: is_missing = True; val_str = "未披露"
                    elif r_type == "percent": val_str = f"{val*100:.0f}%"
                    elif val < 0: val_str = f"({abs(val):,.0f})"
                    elif val == 0: val_str = "0"
                    else: val_str = f"{val:,.0f}"

                c_bg = "#CDCDCD" if is_missing else (HL_BOX_FILL   if is_hl else row_bg)
                c_color = "white" if is_missing else ("#00338D" if is_hl else ("#333333" if n_weight == "bold" else "#444444"))
                c_weight = "bold" if (is_hl or is_total) and not is_missing else "normal"
                borders = f"border-left: 2.5px solid #00338D; border-right: 1.5px solid #00338D; border-top: none; border-bottom: {'1.5px solid #00338D' if row_idx == total_rows - 1 else 'none'};" if is_hl else "border: 1px solid #EAEAEA;"
                
                html += f"<td style='padding: 2px 3px; text-align: center; background-color: {c_bg}; {borders} color: {c_color}; font-weight: {c_weight};'>{val_str}</td>"
            html += "</tr>"
            
        return html + "</tbody></table>"
    
# --- 30.新业务价值及增长分析表 (纯HTML生成不变) ---
    def create_nbv_summary_table(df, cos, div, unit_str, current_period=None, comparison_period=None, highlight_co="无"):
        if current_period is None or comparison_period is None:
            cy, py, cy_month, py_month = latest_year, prev_year, None, None
        else:
            cy, cy_month = current_period
            py, py_month = comparison_period
        cy_label, py_label = format_period_label(cy, cy_month), format_period_label(py, py_month)

        # 🌟 修复 1：动态构建分析指标列表
        metrics = ["新业务盈利合同(CSM)"]
        metrics.append(f"新业务CSM增长率 ({cy_label}/{py_label}-1)")
        metrics.extend(["新业务亏损合同(LC)", "新业务未来现金流入现值", "新业务IFRS利润率", "CSM持续率 (新业务CSM/CSM摊销)"])

        col_data = {}
        for co in cos:
            df_co = df[df['公司'] == co]

            def get_val(y, m, kw):
                msk = (df_co['报告年份'].astype(str) == str(y)) & (df_co['字段名'] == kw)
                dedup = ['公司', '报告年份', '字段名']
                if m is not None and '报告月份' in df_co.columns:
                    msk = msk & (df_co['报告月份'].astype(str) == str(m))
                    dedup = ['公司', '报告年份', '报告月份', '字段名']
                s = df_co[msk].drop_duplicates(subset=dedup)['(百万)人民币']
                return s.sum() if not s.empty else 0

            nb_csm_cy = get_val(cy, cy_month, '新业务CSM（集团口径）')
            nb_csm_py = get_val(py, py_month, '新业务CSM（集团口径）')
            lc_cy = get_val(cy, cy_month, '新业务亏损合同（LC）——非PAA')
            pv_in_cy = get_val(cy, cy_month, '新业务未来现金流入现值')
            amort_cy = get_val(cy, cy_month, 'CSM摊销')

            # 🌟 修复 2：将缺失值统一标记为 "未披露"
            fmt_num = lambda x: "未披露" if pd.isna(x) or x == 0 else f"{x / div:.1f}"
            fmt_pct = lambda x: "未披露" if pd.isna(x) or x == 0 else f"{x:.0%}"

            v1, v3, v4 = fmt_num(nb_csm_cy), fmt_num(lc_cy), fmt_num(pv_in_cy)
            v2 = "未披露" if nb_csm_py == 0 or nb_csm_cy == 0 else fmt_pct((nb_csm_cy / nb_csm_py) - 1)
            v5 = "未披露" if pv_in_cy == 0 else fmt_pct((nb_csm_cy - lc_cy) / pv_in_cy)
            v6 = fmt_pct(nb_csm_cy / (-amort_cy)) if amort_cy != 0 else "未披露"

            col_data[co] = {
                "新业务盈利合同(CSM)": v1, f"新业务CSM增长率 ({cy_label}/{py_label}-1)": v2,
                "新业务亏损合同(LC)": v3, "新业务未来现金流入现值": v4,
                "新业务IFRS利润率": v5, "CSM持续率 (新业务CSM/CSM摊销)": v6
            }
            
        current_hl = str(highlight_co).strip()
        html = "<table style='width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 12px; margin-bottom: 15px;'><tr style='background-color: #00338D; color: white; text-align: center; font-weight: bold;'><th style='padding: 6px 4px; border: 1px solid #EAEAEA; width: 22%; text-align: left;'>分析指标</th>"
        for co in cos:
            is_hl = (co == current_hl)
            html += f"<th style='padding: 6px 4px; background-color: {'#001A4D' if is_hl else '#00338D'}; border: 1px solid #EAEAEA;'>{co}</th>"
        html += "</tr>"
        
        for i, metric in enumerate(metrics):
            html += f"<tr style='background-color: {'white' if i % 2 == 0 else '#F9F9F9'};'><td style='padding: 6px 4px; text-align: left; font-weight: bold; color: #333333; border: 1px solid #EAEAEA;'>{metric}</td>"
            for co in cos:
                val, is_hl = col_data[co].get(metric, "未披露"), (co == current_hl)
                # 🌟 修复 3：HTML 渲染时，如果拿到 "未披露"，直接置灰并写白色字
                if val == "未披露":
                    html += "<td style='padding: 6px 4px; text-align: center; background-color: #CDCDCD; color: white; border: 1px solid #EAEAEA;'>未披露</td>"
                else:
                    html += f"<td style='padding: 6px 4px; text-align: center; background-color: {'rgba(0, 51, 141, 0.08)' if is_hl else 'transparent'}; font-weight: {'bold' if is_hl else 'normal'}; color: {'#00338D' if is_hl else '#444444'}; border: 1px solid #EAEAEA;'>{val}</td>"
            html += "</tr>"
        return html + "</table>"


    # ==========================================
    # 🎛️ 终极模块路由引擎：绑定专属 UI 控件并出图
    # ==========================================
    def render_pure_chart_entity(m_id, print_mode):
        current_hl = highlight_co if highlight_co else "无"
        
        # 1. 关键数据概览表
        if m_id == "summary_table":
            html_table = create_financial_summary_table(df_filtered, selected_cos, current_hl, current_period, comparison_period)
            if html_table: st.markdown(html_table, unsafe_allow_html=True)

        # 2. 利润贡献与保险和投资利润占比
        elif m_id == "prof_mix":
            if not print_mode:
                c1, c2 = st.columns([1, 2])
                with c1: lab = st.toggle("显示数据标签", value=True, key=f"lab_{m_id}")
                with c2: gap = st.slider("柱子间距", 0.2, 0.7, 0.4, key=f"gap_{m_id}")
            else:
                lab, gap = True,0.4 
            fig = create_profit_mixed_chart(df_filtered, selected_cos, "", lab, gap, divisor, unit_label, current_hl, current_period, comparison_period, selected_cos)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 3. 单一指标趋势 (保险收入/费用/业绩)
        elif m_id in ["inc_total", "exp_total", "perf_total"]:
            field_map = {"inc_total": "保险服务收入合计", "exp_total": "保险服务费用合计", "perf_total": "保险服务业绩"}
            if not print_mode:
                c1, c2, c3 = st.columns([1.5, 2, 3])
                with c1: lab = st.toggle("显示柱状图数据标签", value=True, key=f"lab_{m_id}")
                with c2: psz = st.slider("涨幅文字大小", 8, 24, 12, key=f"psz_{m_id}")
                with c3: gap = st.slider("调整公司间距与柱子粗细", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab, psz, gap=True, 13, 0.3
            fig = create_kpmg_chart(df_filtered, field_map[m_id], "", lab, psz, gap, current_hl, current_period, comparison_period, divisor, selected_cos)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 4. 收入结构分析 1/2
        elif m_id == "comp_1":
            if not print_mode:
                c1, c2, c3, c4 = st.columns(4)
                with c1: lab = st.toggle("显示数据标签", value=True, key=f"lab_{m_id}")
                with c2: lsz = st.slider("标签大小", 5, 20, 12, key=f"lsz_{m_id}")
                with c3: wid = st.slider("柱子宽度", 0.1, 1.0, 0.6, 0.05, key=f"wid_{m_id}")
                with c4: cfs = st.slider("公司名称大小", 10, 20, 12, key=f"cfs_{m_id}")
            else:
                # 使用 .get() 从缓存中读取用户在网页上调整过的值，如果没有就用默认值
                lab = st.session_state.get(f"lab_{m_id}", True)
                lsz = st.session_state.get(f"lsz_{m_id}", 12)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                cfs = st.session_state.get(f"cfs_{m_id}", 12)
            comp_fields = ["采用保费分配法计量的保险合同保险服务收入", "未采用保费分配法计量的保险合同保险服务收入"]
            fig = create_kpmg_composition_chart(df_filtered, comp_fields, "", lab, lsz, wid, cfs, current_hl, current_period, comparison_period, divisor, selected_cos)
            show_chart(fig, print_mode,m_id=m_id)
            
# 5. 收入结构分析 2/2 (多组成带表格)
        elif m_id == "comp_2":
            if not print_mode:
                c1, c2, c3, c4 = st.columns(4)
                with c1: lab = st.toggle("显示数据标签", value=True, key=f"lab_{m_id}")
                with c2: lsz = st.slider("标签大小", 5, 20, 10, key=f"lsz_{m_id}") # 🌟 默认值调到10
                with c3: wid = st.slider("柱子宽度", 0.1, 1.0, 0.6, 0.05, key=f"wid_{m_id}")
                with c4: cfs = st.slider("公司名称大小", 10, 20, 11, key=f"cfs_{m_id}") # 🌟 默认值调到11
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                lsz = st.session_state.get(f"lsz_{m_id}", 10)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                cfs = st.session_state.get(f"cfs_{m_id}", 11)
                
            f_m2 = {"合同服务边际的摊销":"合同服务边际的释放", "非金融风险调整的变动":"非金融风险调整的变动", "预计当期发生的保险服务费用":"预期当期发生的保险服务费用", "保险获取现金流的摊销（保险服务收入）":"保险获取现金流的摊销", "与当期服务或过去服务相关得保费经验调整":"与当期服务或过去服务相关的保费经验调整", "其他收入调整":"其他"}
            c_m2 = {"合同服务边际的摊销":"rgb(30, 73, 226)", "非金融风险调整的变动":"rgb(254, 174, 215)", "预计当期发生的保险服务费用":"rgb(0, 163, 161)", "保险获取现金流的摊销（保险服务收入）":"rgb(1, 184, 245)", "与当期服务或过去服务相关得保费经验调整":"rgb(0, 219, 214)", "其他收入调整":"rgb(114, 19, 234)"}
            
            fig, df_avg = create_kpmg_multi_composition_chart(df_filtered, f_m2, c_m2, "", lab, lsz, wid, cfs, current_hl, current_period, comparison_period, selected_cos, divisor)
            
            # 🌟 修复：极致压缩表格体积，防止 PDF 换页
            if fig and not df_avg.empty:
                st.markdown("<div style='margin-bottom: 2px;'><div style='font-size: 12px; font-weight: bold; margin-bottom: 4px; color:#333;'>各公司平均占比情况 </div>", unsafe_allow_html=True)
                html = "<table style='width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 10px; margin-bottom: 4px;'><tr style='background-color: #00338D; color: white; text-align: center; font-weight: bold;'><th style='padding: 2px 4px; border: 1px solid white;'>报告年份</th>"
                for orig_k, display_name in f_m2.items(): 
                    html += f"<th style='padding: 2px 4px; background-color: {c_m2[orig_k]}; color: white; border: 1px solid white;'>{display_name}</th>"
                html += "</tr>"
                for yr, row in df_avg.iterrows():
                    html += f"<tr><td style='padding: 2px 4px; font-weight: bold; background-color: #F8F9FA; border: 1px solid #EAEAEA;'>{yr}</td>"
                    for orig_k, display_name in f_m2.items(): 
                        html += f"<td style='padding: 2px 4px; text-align: center; background-color: white; border: 1px solid #EAEAEA;'>{row[display_name]:.1f}%</td>"
                    html += "</tr>"
                html += "</table></div>"
                st.markdown(html, unsafe_allow_html=True)
                
            show_chart(fig, print_mode,m_id=m_id)


# 6.新加费用的图
        elif m_id == "exp_1":
            if not print_mode:
                c1, c2, c3, c4 = st.columns(4)
                with c1: lab = st.toggle("显示数据标签", value=True, key=f"lab_{m_id}")
                with c2: lsz = st.slider("标签大小", 5, 20, 10, key=f"lsz_{m_id}") # 默认值调小点
                with c3: wid = st.slider("柱子宽度", 0.1, 1.0, 0.6, 0.05, key=f"wid_{m_id}")
                with c4: cfs = st.slider("公司名称大小", 10, 20, 11, key=f"cfs_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                lsz = st.session_state.get(f"lsz_{m_id}", 10)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                cfs = st.session_state.get(f"cfs_{m_id}", 11)
        
            f_m2 = {
                "保险获取现金流的摊销（保险服务费用）": "保险获取现金流的摊销",
                "亏损部分的确认及转回": "亏损部分的确认及转回",
                "当期发生的赔款及其他相关费用": "当期发生的赔款及费用",
                "已发生赔款负债相关的履约现金流量变动": "已发生赔款负债变动",
            }
            c_m2 = {
                "保险获取现金流的摊销（保险服务费用）": "rgb(30, 73, 226)",
                "亏损部分的确认及转回":               "rgb(254, 174, 215)",
                "当期发生的赔款及其他相关费用":        "rgb(0, 163, 161)",
                "已发生赔款负债相关的履约现金流量变动": "rgb(1, 184, 245)",
            }
        
            fig, df_avg = create_kpmg_exp_chart(df_filtered, f_m2, c_m2, "", lab, lsz, wid, cfs, current_hl, current_period, comparison_period, selected_cos, divisor)
            
            # 🌟 修复：将表格包裹在一个 div 中，防止 margin 溢出导致打印换页。同时极大地压缩表格字体和 padding
            if fig and not df_avg.empty:
                st.markdown("<div style='margin-bottom: 2px;'><div style='font-size:12px; font-weight:bold; margin-bottom:4px; color:#333;'>各公司平均占比情况 </div>", unsafe_allow_html=True)
                html = "<table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:10px; margin-bottom:4px;'><tr style='background-color:#00338D; color:white; text-align:center; font-weight:bold;'><th style='padding:2px 4px; border:1px solid white;'>报告年份</th>"
                for orig_k, display_name in f_m2.items():
                    html += f"<th style='padding:2px 4px; background-color:{c_m2[orig_k]}; color:white; border:1px solid white;'>{display_name}</th>"
                html += "</tr>"
                for yr, row in df_avg.iterrows():
                    html += f"<tr><td style='padding:2px 4px; font-weight:bold; background-color:#F8F9FA; border:1px solid #EAEAEA;'>{yr}</td>"
                    for orig_k, display_name in f_m2.items():
                        html += f"<td style='padding:2px 4px; text-align:center; background-color:white; border:1px solid #EAEAEA;'>{row[display_name]:.1f}%</td>"
                    html += "</tr>"
                html += "</table></div>"
                st.markdown(html, unsafe_allow_html=True)
                
            show_chart(fig, print_mode, m_id=m_id)
            
            
        # 6. 利润构成拆解
        elif m_id in ["prof_2025", "prof_2024"]:
            if not print_mode:
                c1, c2, c3, c4 = st.columns(4)
                with c1: lab = st.toggle("显示利润标签", value=True, key=f"lab_{m_id}")
                with c2: psz = st.slider("标签字号", 8, 16, 11, key=f"psz_{m_id}")
                with c3: wid = st.slider("柱宽", 0.2, 0.8, 0.4, key=f"wid_{m_id}")
                with c4: cfs = st.slider("公司字号", 10, 20, 11, key=f"cfs_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                psz = st.session_state.get(f"psz_{m_id}", 11)
                wid = st.session_state.get(f"wid_{m_id}", 0.5)
                cfs = st.session_state.get(f"cfs_{m_id}", 11)
            fig, df_p = create_profit_composition_chart(df_filtered, selected_cos, current_period if m_id == "prof_2025" else comparison_period, lab, psz, wid, cfs, current_hl, divisor)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 7. 投资相关简单柱图
        elif m_id in ["inv_return", "uw_profit", "inv_profit"]:
            field_map = {"inv_return": "净投资回报", "uw_profit": "承保财务净损益", "inv_profit": "投资利润"}
            if not print_mode:
                c1, c2, c3 = st.columns([2, 2, 3])
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: psz = st.slider("文字大小", 8, 20, 14, key=f"psz_{m_id}")
                with c3: gap = st.slider("柱子间距", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                psz = st.session_state.get(f"psz_{m_id}", 13)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
            fig = create_simple_kpmg_chart(df_plot_final, field_map[m_id], "", lab, psz, gap, current_hl, current_period, comparison_period, selected_cos, divisor)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 8. 税前利润
        elif m_id == "tax_profit":
            if not print_mode:
                c1, c2, c3, c4, c5 = st.columns(5)
                with c1: lab = st.toggle("显示标签", value=True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.1, 0.8, 0.4, key=f"wid_{m_id}")
                with c3: f_sz = st.slider("字号", 8, 16, 10, key=f"fs_{m_id}")
                with c4: cfs = st.slider("公司名字号", 10, 24, 13, key=f"cfs_{m_id}")
                with c5: hoy = st.slider("高度比例", 1.0, 1.2, 1.02, step=0.01, key=f"hoy_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.4)
                f_sz = st.session_state.get(f"fs_{m_id}", 10)
                cfs = st.session_state.get(f"cfs_{m_id}", 13)
                hoy = st.session_state.get(f"hoy_{m_id}", 1.02)
            fig = create_tax_subplot_chart(df_tax_pivot, selected_cos, lab, wid, f_sz, cfs, hoy, current_hl)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 9. 综合收益变动趋势
        elif m_id in ["net_profit", "oci_profit", "total_profit"]:
            field_map = {"net_profit": "净利润", "oci_profit": "其他综合收益", "total_profit": "综合收益总额"}
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: psz = st.slider("文字大小", 8, 20, 12, key=f"psz_{m_id}")
                with c3: gap = st.slider("柱宽", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                psz = st.session_state.get(f"psz_{m_id}", 12)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
            fig = create_financial_trend_chart_v5(df_fin_raw, field_map[m_id], "", lab, psz, gap, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 10. 资产端分类
        elif m_id == "asset_struct":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.1, 1.0, 0.6, key=f"wid_{m_id}")
                with c3: sz = st.slider("字号", 8, 20, 12, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            f_map = {"AC": "债权投资<br>（以摊余成本法计量）", "FVOCI": "其他债权投资<br>（以公允价值计量入其他综合收益）", "FVTPL": "交易性金融资产<br>（以公允价值计量入损益）", "指定FVOCI": "其他权益工具投资<br>（以公允价值计量入其他综合收益）"}
            c_map = {"AC": "rgb(0, 184, 245)", "FVOCI": "rgb(114, 19, 234)", "FVTPL": "rgb(253, 52, 156)", "指定FVOCI": "rgb(181, 2, 95)"}
            fig = create_asset_composition_chart(df_filtered, selected_cos, f_map, c_map, "", lab, sz, wid, 12, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 11. 两年的 OCI 变动分析
        elif m_id in ["oci_year_lat", "oci_year_pre"]:
            period = current_period if m_id == "oci_year_lat" else comparison_period
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: gap = st.slider("间距", 0.05, 0.5, 0.15, key=f"gap_{m_id}")
                with c3: sz = st.slider("公司字号", 8, 20, 12, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.15)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_oci_chart(df_filtered, period, "", lab, sz, gap, selected_cos, current_hl)
            show_chart(fig, print_mode,m_id=m_id)
            
        # 12. 资负 OCI
        elif m_id == "oci_deep":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: gap = st.slider("间距", 0.05, 0.5, 0.15, key=f"gap_{m_id}")
                with c3: sz = st.slider("公司字号", 8, 20, 12, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.15)
                sz = st.session_state.get(f"sz_{m_id}", 12)
                
            fig = create_asset_liab_oci_chart(df_filtered, selected_cos, gap, sz, lab, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode, m_id=m_id)
            
            # 🌟 直接接收并渲染已经在函数内排版好的精美 HTML 表格，下面一堆旧的拼表代码全删了！
            html_table, c_y, p_y = calculate_oci_analysis_table(df_filtered, selected_cos, current_hl, current_period, comparison_period)
            if html_table:
                st.markdown(f"<p style='font-size:13px; font-weight:bold; color:#00338D; margin-top:-30px; margin-bottom:6px;'>资负 OCI 变动分析表 ({p_y} - {c_y})</p>", unsafe_allow_html=True)
                st.markdown(html_table, unsafe_allow_html=True)

# 13. 净资产变动与总资产变动
        elif m_id in ["equity_trend", "asset_trend"]:
            field_map = {"equity_trend": "期末股东权益", "asset_trend": "总资产"}
            df_asset_raw = df_filtered[df_filtered['字段名'].isin(['期末股东权益', '总资产']) & df_filtered['公司'].isin(selected_cos)].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名']).copy()
            df_asset_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: sz = st.slider("字号", 8, 24, 11, key=f"sz_{m_id}")
                with c3: gap = st.slider("间距", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_asset_trend_chart(df_asset_raw, field_map[m_id], "", lab, sz, gap, current_hl, current_period, comparison_period, selected_cos, divisor)
            show_chart(fig, print_mode,m_id=m_id)

            # 净资产趋势图下面，增加净资产变动明细表
            if m_id == "equity_trend":
                equity_detail_html = create_equity_change_detail_table(
                    df_filtered,
                    current_period,
                    selected_cos,
                    divisor=divisor,
                    unit_label=unit_label,
                    highlight_co=current_hl
                )
                st.markdown(equity_detail_html, unsafe_allow_html=True)            
        # 14. CSM余额变动趋势
        elif m_id == "csm_bal":
            df_csm_raw = df_filtered[(df_filtered['字段名'] == 'CSM期末余额') & df_filtered['公司'].isin(selected_cos)].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名']).copy()
            df_csm_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)    
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: sz = st.slider("字号", 8, 24, 12, key=f"sz_{m_id}")
                with c3: gap = st.slider("柱宽", 0.1, 0.8, 0.35, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.35)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_csm_trend_chart(df_csm_raw, 'CSM期末余额', "", lab, sz, gap, current_hl, current_period, comparison_period, selected_cos, divisor)
            show_chart(fig, print_mode,m_id=m_id)

        # 15. CSM期初余额占比分析
        elif m_id == "csm_ratio":
            if not print_mode:
                c1, c2 = st.columns(2)
                with c1: lab = st.toggle("显示占比百分比标签", True, key=f"lab_{m_id}") 
                with c2: gap = st.slider("柱距调节 (越小柱子越粗)", 0.1, 0.8, 0.3, key=f"gap_{m_id}")   
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
            fig = create_csm_ratio_chart(df_filtered, selected_cos, lab, gap, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode,m_id=m_id)

        # 16. CSM 概览明细表
        elif m_id == "csm_table":
            # 🌟 核心修改：现在函数直接返回排版好的 HTML 文本
            html_table = show_csm_summary_table(df_filtered, current_period, selected_cos, current_hl)
            
            # 如果成功生成了 HTML，就直接用 st.markdown 渲染它，原先那堆拼接逻辑全删了！
            if html_table:
                st.markdown(html_table, unsafe_allow_html=True)

        # 17. CSM过渡期拆分
        elif m_id == "csm_trans":
            if not print_mode:
                c1,c2=st.columns(2)
                with c1: lab=st.toggle("显示标签",True,key=f"lab_{m_id}")
                with c2: wid=st.slider("柱宽",0.1,0.8,0.4,key=f"wid_{m_id}")
            else:
                lab=st.session_state.get(f"lab_{m_id}",True)
                wid=st.session_state.get(f"wid_{m_id}",0.4)
            fig=create_csm_transition_chart(df_filtered,selected_cos,lab,wid,current_hl,current_period,comparison_period)
            show_chart(fig,print_mode,m_id=m_id)

        # 18. 两年的摊销前CSM占比
        elif m_id in ["csm_comp_lat", "csm_comp_pre"]:
            period = current_period if m_id == "csm_comp_lat" else comparison_period
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.1, 1.0, 0.5, key=f"wid_{m_id}")
                with c3: sz = st.slider("字号", 8, 20, 11, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.5)
                sz = st.session_state.get(f"sz_{m_id}", 11)
            fig = create_csm_composition_chart(df_filtered, selected_cos, period, lab, sz, wid, current_hl, title_text="")
            show_chart(fig, print_mode,m_id=m_id)

        # 19. CSM比率折线图 (摊销比率 + 持续率双图并行)
        elif m_id == "csm_ratio_trend":
            if not print_mode:
                c1, c2 = st.columns(2)
                with c1: lab = st.toggle("显示数值", True, key=f"lab_{m_id}")
                with c2: sz = st.slider("点大小", 4, 15, 6, key=f"sz_{m_id}")
            else:
                lab, sz = st.session_state.get(f"lab_{m_id}", True), st.session_state.get(f"sz_{m_id}", 6)
        
            color_map = get_color_map(selected_cos)
            # ⭐ 只保留本期 + 对比期这两个报告期，不再画全历史趋势线
            _cy_y, _cy_m = current_period
            _py_y, _py_m = comparison_period
            _keep_periods = {(str(_cy_y), str(_cy_m)), (str(_py_y), str(_py_m))}
            _yr_s = df_filtered['报告年份'].astype(str).str.replace('.0', '', regex=False)
            _mo_s = df_filtered['报告月份'].astype(str).str.replace('.0', '', regex=False)
            _period_mask = pd.Series(list(zip(_yr_s, _mo_s)), index=df_filtered.index).isin(_keep_periods)
            df_ratio_src = df_filtered[_period_mask]

            df_c_sub = df_ratio_src[df_ratio_src['字段名'].isin(['CSM摊销', 'CSM期末余额', '新业务CSM（集团口径）'])].pivot_table(
                index=['公司', '报告年份', '报告月份'], columns='字段名', values='(百万)人民币').reset_index().fillna(0)
            denom1 = (df_c_sub['CSM期末余额'] - df_c_sub['CSM摊销']).replace(0, np.nan)
            denom2 = df_c_sub['CSM摊销'].replace(0, np.nan)

            df_c_sub['摊销比率'] = -df_c_sub['CSM摊销'] / denom1
            df_c_sub['持续率'] = -df_c_sub['新业务CSM（集团口径）'] / denom2

            df_c_sub.replace([np.inf, -np.inf], np.nan, inplace=True)
            df_c_sub.replace([np.inf, -np.inf], np.nan, inplace=True)
            # 🌟 报告期改造：按"年+月"区分时点，标签用"年+月"，排序用数值键
            df_c_sub['报告年份'] = df_c_sub['报告年份'].astype(str).str.replace(".0", "", regex=False)
            df_c_sub['报告月份'] = df_c_sub['报告月份'].astype(str).str.replace(".0", "", regex=False)
            df_c_sub['__period'] = df_c_sub['报告年份'] + "年" + df_c_sub['报告月份'] + "月"
            df_c_sub['__sort'] = pd.to_numeric(df_c_sub['报告年份'], errors='coerce') * 100 + pd.to_numeric(df_c_sub['报告月份'], errors='coerce').fillna(12)
        
# ✅ 自定义圆点图例（HTML），两个子图共用：自动侦测缺失/为0的数据并标注(未披露)
            legend_items = []
            for co in selected_cos:
                # 1. 抓取该公司的全部数据
                d_co = df_c_sub[df_c_sub['公司'] == co]
                
                # 2. 判断是否未披露（没查到数据，或者摊销/持续率全为 0 或 NaN）
                is_missing = False
                if d_co.empty:
                    is_missing = True
                else:
                    v_tanxiao = d_co['摊销比率'].fillna(0)
                    v_chixu = d_co['持续率'].fillna(0)
                    if (v_tanxiao == 0).all() and (v_chixu == 0).all():
                        is_missing = True
                
                # 3. 如果未披露，加上后缀，顺便把字变成浅灰色，视觉上更直观
                display_name = f"{co} (未披露)" if is_missing else co
                text_color = "#999999" if is_missing else "#333333"
                bg_color = HIGHLIGHT_COLOR if co == current_hl else color_map.get(co, "#333")
                
                # 4. 组装单个图例项
                legend_items.append(
                    f'<div style="display:flex;align-items:center;gap:4px;">'
                    f'<div style="width:9px;height:9px;border-radius:50%;background:{bg_color};flex-shrink:0;"></div>'
                    f'<span style="color:{text_color};">{display_name}</span></div>'
                )

            st.markdown(
                f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px;font-size:11px;font-family:Microsoft YaHei,sans-serif;">{"".join(legend_items)}</div>',
                unsafe_allow_html=True
            )
        
            # ✅ 合并成一个 subplot，打印网页都稳定
            from plotly.subplots import make_subplots
            fig = make_subplots(rows=1, cols=2,
                                subplot_titles=["CSM摊销比率趋势", "CSM持续率趋势"],
                                horizontal_spacing=0.08)
        
            for col_idx, metric in enumerate(['摊销比率', '持续率'], 1):
                df_m = df_c_sub[['公司', '__period', '__sort', metric]].rename(columns={metric: 'value'})
                latest_sort = df_m['__sort'].max()
                # ✅ 改成：只从有效（非0非NaN）的数据里找最大最小
                df_latest = df_m[df_m['__sort'] == latest_sort].dropna(subset=['value'])
                df_latest_valid = df_latest[df_latest['value'] != 0]  # 👈 排除0值
                max_co = df_latest_valid.loc[df_latest_valid['value'].idxmax(), '公司'] if not df_latest_valid.empty else None
                min_co = df_latest_valid.loc[df_latest_valid['value'].idxmin(), '公司'] if not df_latest_valid.empty else None

                for co in selected_cos:
                    d_co = df_m[df_m['公司'] == co].sort_values('__sort')

                    # 🌟 核心拦截逻辑：检查数据是否真实有效
                    if d_co.empty:
                        continue

                    # 取出所有的非空数值
                    valid_values = d_co['value'].dropna()

                    # 如果全是 NaN，或者所有算出来的值都是 0，就不画这条线
                    if valid_values.empty or (valid_values == 0).all():
                        continue
                    is_hl  = (co == current_hl)
                    is_ext = (co in [max_co, min_co])
                    fig.add_trace(go.Scatter(
                        x=d_co['__period'], y=d_co['value'], name=co,
                        mode='lines+markers+text' if lab else 'lines+markers',
                        line=dict(
                            color=HIGHLIGHT_COLOR if is_hl else color_map.get(co, "#333"),
                            width=4 if is_hl else (2.5 if is_ext else 2),
                            dash="solid" if (is_hl or is_ext) else "dot"
                        ),
                        marker=dict(size=sz * 1.5 if is_hl else sz, symbol='circle'),
                        text=[f"{v*100:.1f}%" for v in d_co['value']] if lab else None,
                        textposition="top center", cliponaxis=False,
                        showlegend=False  # ✅ 关掉Plotly自带图例，用上面HTML圆点图例
                    ), row=1, col=col_idx)
        
                fig.update_yaxes(tickformat=".1%", showgrid=False, zeroline=False, row=1, col=col_idx)
                fig.update_xaxes(showgrid=False, showline=False, zeroline=False, row=1, col=col_idx)
        
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                height=380 if print_mode else 430,
                margin=dict(t=40, b=20, l=30, r=30),
            )
        
            show_chart(fig, print_mode, m_id=m_id)

        # 20. 综合净资产指标
        elif m_id == "csm_equity":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.1, 1.0, 0.5, key=f"wid_{m_id}")
                with c3: sz = st.slider("字号", 8, 20, 12, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.5)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_csm_equity_analysis(df_filtered, selected_cos, lab, sz, wid, 12, 20, current_hl, title_text="", current_period=current_period, comparison_period=comparison_period)
            show_chart(fig, print_mode,m_id=m_id)
            def create_csm_equity_ratio_table(df, cos, current_period, comparison_period, div, highlight_co="无"):
                hl = str(highlight_co).strip()
                if isinstance(current_period, tuple):
                    cy, cy_month = current_period
                else:
                    cy, cy_month = current_period, None
                if isinstance(comparison_period, tuple):
                    py, py_month = comparison_period
                else:
                    py, py_month = comparison_period, None
                cy_str, py_str = str(cy).replace('.0', ''), str(py).replace('.0', '')
                cy_label = format_period_label(cy, cy_month)
                py_label = format_period_label(py, py_month)

                def get_val(co, year, month, field):
                    msk = (df['公司']==co) & \
                           (df['报告年份'].astype(str).str.replace('.0','',regex=False)==year) & \
                           (df['字段名']==field)
                    if month is not None and '报告月份' in df.columns:
                        msk = msk & (df['报告月份'].astype(str).str.replace('.0','',regex=False)==str(month).replace('.0',''))
                    s = df[msk]['(百万)人民币']
                    return s.iloc[0] if not s.empty and pd.notna(s.iloc[0]) else None

                def calc_ratio(co, year, month):
                    nav = get_val(co, year, month, "综合净资产")
                    ta  = get_val(co, year, month, "总资产")
                    if nav is None or ta is None or ta == 0:
                        return "未披露", True
                    return f"{nav / ta * 100:.1f}%", False

                # ✅ 表头：第一列报告期，后面每列一个公司
                html = ("<table style='width:100%; border-collapse:collapse; font-family:sans-serif; "
                        "font-size:11px; margin-top:8px; margin-bottom:15px;'>")
                html += "<tr style='background-color:#00338D; color:white; font-weight:bold; text-align:center;'>"
                html += "<th style='padding:6px 8px; border:1px solid white; text-align:left;'>报告期</th>"
                for co in cos:
                    is_hl = (str(co).strip() == hl)
                    bg = "rgba(0,184,245,0.3)" if is_hl else ""
                    html += f"<th style='padding:6px 8px; border:1px solid white; {bg}'>{co}</th>"
                html += "</tr>"

                # ✅ 每行是一个报告期
                for row_idx, (year_str, month_val, period_label) in enumerate([(py_str, py_month, py_label), (cy_str, cy_month, cy_label)]):
                    bg = "#F8F9FA" if row_idx % 2 == 0 else "white"
                    html += f"<tr style='background-color:{bg};'>"
                    html += (f"<td style='padding:6px 8px; border:1px solid #EAEAEA; "
                             f"font-weight:bold; color:#00338D;'>{period_label} 综合净资产/总资产</td>")
                    for co in cos:
                        is_hl = (str(co).strip() == hl)
                        borders = ("border-top:1.5px solid #00338D; border-bottom:1.5px solid #00338D; "
                                   "border-left:1px solid #EAEAEA; border-right:1px solid #EAEAEA;"
                                   if is_hl else "border:1px solid #EAEAEA;")
                        v, m = calc_ratio(co, year_str, month_val)
                        cell_style = f"background-color:#CDCDCD; color:white;" if m else (
                            f"color:#00338D; font-weight:bold;" if is_hl else "color:#333;")
                        html += f"<td style='padding:6px 8px; text-align:center; {borders} {cell_style}'>{v}</td>"
                    html += "</tr>"

                return html + "</table>"
            
            ratio_html = create_csm_equity_ratio_table(
                df_filtered, selected_cos, current_period, comparison_period, divisor, current_hl
            )
            st.markdown(ratio_html, unsafe_allow_html=True)
        # 21. 新业务盈利合同(CSM)
        elif m_id == "nb_csm":
            df_nb_csm_raw = df_filtered[(df_filtered['字段名'] == '新业务CSM（集团口径）') & df_filtered['公司'].isin(selected_cos)].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名']).copy()
            df_nb_csm_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: sz = st.slider("字号", 8, 24, 12, key=f"sz_{m_id}")
                with c3: gap = st.slider("间距", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_new_biz_csm_chart(df_nb_csm_raw, '新业务CSM（集团口径）', "", lab, sz, gap, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode,m_id=m_id)


        # 22. 新业务亏损(CSM-非PAA)
        elif m_id == "nb_lost":
            df_nb_csm_raw = df_filtered[(df_filtered['字段名'] == '新业务亏损合同（LC）——非PAA') & df_filtered['公司'].isin(selected_cos)].drop_duplicates(subset=['公司', '报告年份', '报告月份', '字段名']).copy()
            df_nb_csm_raw.rename(columns={'字段名': '指标名称', '(百万)人民币': 'value'}, inplace=True)
            # ✅ 取负数
            df_nb_csm_raw['value'] = -df_nb_csm_raw['value']
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: sz = st.slider("字号", 8, 24, 12, key=f"sz_{m_id}")
                with c3: gap = st.slider("间距", 0.1, 0.8, 0.3, key=f"gap_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                gap = st.session_state.get(f"gap_{m_id}", 0.3)
                sz = st.session_state.get(f"sz_{m_id}", 12)
            fig = create_new_lost_csm_chart(df_nb_csm_raw, '新业务亏损合同（LC）——非PAA', "", lab, sz, gap, current_hl, current_period, comparison_period)
            show_chart(fig, print_mode, m_id=m_id)
            
        # 22. 新业务指标拆解三图
        elif m_id == "nb_struct":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.2, 1.0, 0.6, key=f"wid_{m_id}")
                with c3: sz  = st.slider("字号", 8, 20, 12, key=f"sz_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                sz  = st.session_state.get(f"sz_{m_id}", 11)
        
            f1, f2, f3 = create_new_business_metrics_charts(
                df_filtered, selected_cos, lab, sz, wid, 11, current_hl, is_print_mode=print_mode,
                current_period=current_period, comparison_period=comparison_period
            )
            if f1:
                show_chart(f1, print_mode, m_id=m_id)
                # 👇 第2、3个图前插续标题（只在打印模式）
                # if print_mode: render_continue_title(m_id)
                show_chart(f2, print_mode, m_id=m_id)
                show_chart(f3, print_mode, m_id=m_id)

        # 23. 新业务IFRS利润率趋势
        elif m_id == "nb_margin_trend":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: mk = st.slider("节点大小", 4, 15, 6, key=f"mk_{m_id}")
                with c3: fs = st.slider("图例字号", 8, 16, 12, key=f"fs_{m_id}")
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                mk = st.session_state.get(f"mk_{m_id}", 6)
                fs = st.session_state.get(f"fs_{m_id}", 12)
                
            color_map = get_color_map(selected_cos)
            fig = create_nb_margin_trend_chart(df_filtered, selected_cos, "", color_map, lab, mk, fs, current_hl,
                                               current_period=current_period, comparison_period=comparison_period)
            
            # 🌟 修复：去掉 col_l 和 col_r 的分列，直接渲染，它就会自动居中并撑满页面！
            if fig:
                col_left, col_center, col_right = st.columns([1, 8, 1]) 
                with col_center:
                    show_chart(fig, print_mode, m_id=m_id)

        # 24. 费用结构及HTML统计表
        elif m_id == "exp_struct":
            if not print_mode:
                c1, c2, c3 = st.columns(3)
                with c1: lab = st.toggle("显示标签", True, key=f"lab_{m_id}")
                with c2: wid = st.slider("柱宽", 0.2, 0.8, 0.6, key=f"wid_{m_id}")
                with c3: sz = st.slider("字号", 8, 20, 10, key=f"sz_{m_id}")  
            else:
                lab = st.session_state.get(f"lab_{m_id}", True)
                wid = st.session_state.get(f"wid_{m_id}", 0.6)
                sz = st.session_state.get(f"sz_{m_id}", 11)               
            fig, stats = create_expense_breakdown_chart(df_filtered, selected_cos, lab, sz, wid, 12, current_hl, current_period, comparison_period)
            p_acq, p_maint, p_non = stats      
            st.markdown(f"""
            <table style='width:100%; border-collapse: collapse; font-family: sans-serif; margin-bottom: 15px; font-size: 11px;'>
                <tr style='background-color: #00338D; color: white; font-size: 12px; text-align: center; font-weight: bold;'>
                    <th style='padding: 6px 4px; text-align: left; border: 1px solid white;'>项目</th>
                    <th style='padding: 6px 4px; text-align: center; border: 1px solid white;'>获取费用均值</th>
                    <th style='padding: 6px 4px; text-align: center; border: 1px solid white;'>维持费用均值</th>
                    <th style='padding: 6px 4px; text-align: center; border: 1px solid white;'>非履约费用均值</th>
                </tr>
                <tr>
                    <td style='padding: 4px 4px; text-align: left; font-weight: bold; background-color: #F8F9FA; border: 1px solid #EAEAEA;'>各公司平均占比</td>
                    <td style='padding: 4px 4px; text-align: center; background-color: white; border: 1px solid #EAEAEA; color: rgb(30, 73, 226); font-weight: bold;'>{p_acq:.0f}%</td>
                    <td style='padding: 4px 4px; text-align: center; background-color: white; border: 1px solid #EAEAEA; color: rgb(118, 210, 255); font-weight: bold;'>{p_maint:.0f}%</td>
                    <td style='padding: 4px 4px; text-align: center; background-color: white; border: 1px solid #EAEAEA; color: rgb(114, 19, 234); font-weight: bold;'>{p_non:.0f}%</td>
                </tr>
            </table>
            """, unsafe_allow_html=True)        
            show_chart(fig, print_mode,m_id=m_id)

        # 25. 关键披露：折现率假设与非金融风险置信水平表与摊销比
        elif m_id == "discount_rate":
            html = create_discount_rate_table(df_filtered, selected_cos, current_period, comparison_period, current_hl)
            if html: st.markdown(html, unsafe_allow_html=True)

        elif m_id == "confidence_level":
            html = create_confidence_level_table(df_filtered, selected_cos, current_period, comparison_period, current_hl)
            if html: st.markdown(html, unsafe_allow_html=True)


        elif m_id == "csm_maturity_table":
            if not print_mode:
                c1, c2 = st.columns(2)
                with c1: lab = st.toggle("显示摊销累积比例", True, key=f"lab_{m_id}")
                with c2: mk  = st.slider("数据点大小", 4, 15, 8, key=f"mk_{m_id}")
            else:
                lab, mk = True, 8
        
            PRESET_COLORS = [
                "#C00000", "#0865EE", "#FEAED7", "#92D050", "#7030A0",
                "#EF9867", "#61CBF4", "#C7A0F7", "#FF4500", "#008B8B",
                "#FFD700", "#8B008B"
            ]
        
            # ✅ 每次都根据当前 selected_cos 重建 color_map，避免缓存旧状态导致撞色
            color_map_key = tuple(selected_cos)  # 用公司列表作为缓存 key
            if st.session_state.get('_color_map_key') != color_map_key:
                st.session_state['company_color_map'] = {
                    co: PRESET_COLORS[i % len(PRESET_COLORS)]
                    for i, co in enumerate(selected_cos)
                }
                st.session_state['_color_map_key'] = color_map_key
        
            color_map = st.session_state['company_color_map']
        
            fig = create_csm_maturity_table(
                df_filtered, current_period, selected_cos,
                color_map, lab, mk, current_hl, title_text=""
            )
            if fig:
                show_chart(fig, print_mode,m_id=m_id)
                
# 26. 附录：业绩明细表与新业务明细表 (双表同打)
        elif m_id == "report_detail":
            cy_label = format_period_label(current_period[0], current_period[1])
            py_label = format_period_label(comparison_period[0], comparison_period[1])

            # ====== 第一页：渲染本期 (current_period) ======
            st.markdown(f"<div style='font-size:13px; font-weight:bold; color:#00338D; margin-bottom: 0px;'>▪ {cy_label}分析表</div>", unsafe_allow_html=True)
            html_cy = create_financial_report_table(df_filtered, current_period, selected_cos, divisor, unit_label, current_hl)
            
            if html_cy: 
                # 🌟 核心技巧：只对最新年的表进行“极致压缩”，强行削减 padding 和 行高，防止 PDF 跨页
                html_cy = html_cy.replace("padding: 3px 4px;", "padding: 3px 4px; line-height: 1.1;") # 压扁数据行
                html_cy = html_cy.replace("padding: 4px 3px;", "padding: 4px 3px;") # 压扁表头
                html_cy = html_cy.replace("font-size: 10.5px;", "font-size: 10.5px;") # 字号微缩
                html_cy = html_cy.replace("margin-bottom: 10px;", "margin-bottom: 2px;") # 去掉底部留白
                st.markdown(html_cy, unsafe_allow_html=True)
            
            # ====== 第二页：强制断页，并渲染对比期 (comparison_period) ======
            # 引入专业的 pdf-page-break 强行另起一页
            st.markdown(f"""
            <div class="pdf-page-break"></div>
            <div style='font-size:13px;font-weight:bold;color:#00338D;margin-top:15px;margin-bottom:5px;'>
            ▪ {py_label}分析表
            </div>
            """, unsafe_allow_html=True)

            html_py = create_financial_report_table(df_filtered, comparison_period, selected_cos, divisor, unit_label, current_hl)
            
            if html_py: 
                # 🌟 去年的表不做任何替换，原汁原味渲染，保持原有大小
                st.markdown(html_py, unsafe_allow_html=True)

        elif m_id == "nbv_table":
            cy_label = format_period_label(current_period[0], current_period[1])
            st.markdown(f"<div style='font-size:13px; font-weight:bold; color:#00338D; margin-bottom: 5px;'>▪ {cy_label}分析表</div>", unsafe_allow_html=True)
            html_cy = create_nbv_summary_table(df_filtered, selected_cos, divisor, unit_label, current_period, comparison_period, current_hl)
            if html_cy: st.markdown(html_cy, unsafe_allow_html=True)

        elif m_id == "uw_inv_comboratio":
            fig, df_scatter = create_dual_engine_profit_chart(
                df_raw=df_filtered, target_period=current_period, cos=selected_cos,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "sc_profit_ratio":
            # 保险规模与盈利：X=保险服务收入（绝对额），Y=保险服务利润率
            fig = create_sc_profit_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "gr_qual_ratio":
            # 保险增长质量：X=保险服务收入增长率，Y=保险服务利润率变动（本期-对比期，百分点），气泡=保险服务收入
            fig = create_gr_qual_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "alm_ratio":
            # 资产负债匹配：X=本期可转损益的负债OCI/平均净资产，Y=本期FVOCI债券/平均净资产，气泡=净资产
            fig = create_alm_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "nas_sv_ratio":
            # 综合净资产-规模与价值：X=总资产增长率，Y=综合净资产增长率，气泡=综合净资产
            fig = create_nas_sv_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "nas_pf_ratio":
            # 综合净资产-资本积累与未赚利润储备：X=净资产增长率，Y=CSM增长率，气泡=CSM期末余额
            fig = create_nas_pf_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "shr_ret_ratio":
            # 股东回报：X=净资产（绝对额），Y=ROE净资产收益率
            fig = create_shr_ret_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)

        elif m_id == "nb_qual_ratio":
            # 新业务质量：X=新业务CSM增长率，Y=新业务IFRS利润率变动率，气泡=新业务未来现金流入现值
            fig = create_nb_qual_chart(
                df_raw=df_filtered, cy=current_period, py=comparison_period, cos=selected_cos,
                divisor=divisor, unit_label=unit_label,
                highlight_co=current_hl, label_size=11, show_labels=False, dot_size=11
            )
            show_chart(fig, print_mode, m_id=m_id)
    # ==========================================
    # 🌟 统一调用出口：根据 m_id 自动组装全部零配件
    # ==========================================
    def render_report_module(m_id, print_mode, is_first=False):
        mod_data = notes_dict.get(m_id, {})
    
        full_title = mod_data.get('title', m_id)
        if 'df_notes' in st.session_state and isinstance(st.session_state['df_notes'], pd.DataFrame):
            df_n = st.session_state['df_notes']
            if '模块ID' in df_n.columns:
                match = df_n[df_n['模块ID'] == m_id]
                if not match.empty:
                    r = match.iloc[0]
                    title_parts = []
                    for field in ['一级分类', '二级分类', '对应图表名称']:
                        val = str(r.get(field, '')).strip()
                        if val and val.lower() != 'nan' and val != '全部':
                            title_parts.append(val)
                    if title_parts:
                        full_title = " - ".join(title_parts)
    
        if print_mode:
            st.markdown("<div class='page-break-container' style='margin:0;padding:0;'>", unsafe_allow_html=True)
        if not print_mode:
            st.markdown(
                "<div class='no-print' style='height:2px; background:linear-gradient(...)'></div>",
                unsafe_allow_html=True
            )    
        # ====== 第 1 步：标题 ======（移出else，打印和网页都执行）
        title_cls = "page-break-title" if (print_mode and not is_first) else ""
        mt = "0px" if (print_mode and is_first) else "20px"
        font_size = "35px" if print_mode else "30px"
        st.markdown(
            f"<h3 class='{title_cls}' style='"
            f"text-align:left; color:#00338D; font-size:{font_size}; font-weight:900; "
            f"font-family:Microsoft YaHei, 微软雅黑, sans-serif; "
            f"margin-top:{mt}; margin-bottom:20px; border:none; padding-bottom:0px;'>"
            f"{full_title}</h3>",
            unsafe_allow_html=True
        )
    
        # ====== 第 2 步：手动截图覆盖 ======
        if 'manual_upload_images' in st.session_state and m_id in st.session_state.manual_upload_images:
            if print_mode:
                st.image(st.session_state.manual_upload_images[m_id], use_column_width=True)
            else:
                img_col_left, img_col_center, img_col_right = st.columns([1, 8, 1])
                with img_col_center:
                    st.image(st.session_state.manual_upload_images[m_id], use_column_width=True)
            _, nt = display_notes(m_id)
            display_bottom_note(nt)
            if print_mode:
                st.markdown("</div>", unsafe_allow_html=True)
            return
    
        # ====== 第 3 步：AI / 注释框 ======
        an, nt = display_notes(m_id, ai_df=df_filtered, ai_field=mod_data.get('title', m_id))

        # ====== 第 4 步：图表 ======
        if print_mode:
            if m_id not in ["csm_amortization", "discount_rate", "confidence_level", "csm_maturity_table"]:
                if m_id in ["sc_profit_ratio", "shr_ret_ratio"]:
                    unit_text = f"百分比 (%) ／ {unit_label}人民币"
                else:
                    unit_text = "百分比 (%)" if "comp" in m_id or m_id == "asset_struct" or "ratio" in m_id or "margin" in m_id or "csm_trans"in m_id or "struct" in m_id else f"{unit_label}人民币"
                st.markdown(f"<p style='text-align:right; font-size:11px; margin-bottom:2px; color:#666;'>单位：{unit_text}</p>", unsafe_allow_html=True)
            render_pure_chart_entity(m_id, print_mode)
        else:
            chart_col_left, chart_col_center, chart_col_right = st.columns([1, 10, 1])
            with chart_col_center:
                if m_id not in ["csm_amortization", "discount_rate", "confidence_level", "csm_maturity_table"]:
                    if m_id in ["sc_profit_ratio", "shr_ret_ratio"]:
                        unit_text = f"百分比 (%) ／ {unit_label}人民币"
                    else:
                        unit_text = "百分比 (%)" if "comp" in m_id or m_id == "asset_struct" or "ratio" in m_id or "margin" in m_id or "csm_trans"in m_id or "struct" in m_id else f"{unit_label}人民币"
                    st.markdown(f"<p style='text-align:right; font-size:12px; margin-bottom:2px; color:#666;'>单位：{unit_text}</p>", unsafe_allow_html=True)
                render_pure_chart_entity(m_id, print_mode)
    
        # ====== 第 5 步：底部注释 ======
        display_bottom_note(nt)
    
        if print_mode:
            st.markdown("</div>", unsafe_allow_html=True)
            
#-----------跨页标题重复---------
    def render_continue_title(m_id):
        title = ""
        if 'df_notes' in st.session_state and isinstance(st.session_state['df_notes'], pd.DataFrame):
            df_n = st.session_state['df_notes']
            match = df_n[df_n['模块ID'] == m_id]
            if not match.empty:
                r = match.iloc[0]
                parts = [str(r.get(f,'')).strip() for f in ['一级分类','二级分类','对应图表名称']
                         if str(r.get(f,'')).strip() not in ['','nan','全部']]
                title = " - ".join(parts)
        st.markdown(
            f"<h3 class='print-only page-break-title' style='text-align:left; color:#00338D; font-size:32px; "  # ✅ 加 print-only
            f"font-weight:900; font-family:Microsoft YaHei,微软雅黑,sans-serif; "
            f"margin-top:10px; margin-bottom:0px; border:none;'>"
            f"{title}（续）</h3>",
            unsafe_allow_html=True
        )

    # ==========================================
    # 🌐 网页模式 / 🖨️ 打印模式 的最终执行器
    # ==========================================
    if not print_mode:
        st.markdown(
            "<hr class='no-print' style='border:none;border-top:1px solid #EAEAEA;margin:10px 0;'>",
            unsafe_allow_html=True
        )
    if print_mode:
        if 'ordered_modules' not in locals() or not ordered_modules:
            st.warning("⚠️ 报告顺序由【模块ID】的先后顺序决定，请先在上方传入有模块ID的注释表文件。")
        else:
            type_str = "" if "全部" in selected_types else "、".join(selected_types)
            cy_label = format_period_label(current_period[0], current_period[1])
            py_label = format_period_label(comparison_period[0], comparison_period[1])
            
            cover_url = "https://github.com/lifeact666/-annual-report-tool/raw/main/picture/%E6%A0%87%E9%A2%98%E9%A1%B5.png"
            back_url  = "https://github.com/lifeact666/-annual-report-tool/raw/main/picture/%E5%B0%81%E5%BA%95%E9%A1%B5.png"

            # ✅ 封面：用st.image撑满，components.html叠加绝对定位文字
            st.markdown(f"""
            <div style="position:relative; width:338.67mm;  height:175.5mm;    
                page-break-after:always; overflow:hidden; margin:0; padding:0;
                -webkit-print-color-adjust:exact; print-color-adjust:exact; forced-color-adjust:none;">
                <img src="{cover_url}" style="width:100%; height:100%; object-fit:cover; display:block;"/>
                <div style="position:absolute; top:0; left:0; width:100%; height:100%;
                    display:flex; flex-direction:column; justify-content:center; align-items:flex-start;
                    padding:0 8%; box-sizing:border-box; margin-top:-30px; z-index:10;
                    forced-color-adjust:none; -webkit-print-color-adjust:exact; print-color-adjust:exact;">
                    <div style="font-size:52px; font-weight:900; line-height:1.4; margin-bottom:16px;
                        font-family:Microsoft YaHei,微软雅黑,sans-serif;
                        color:white; -webkit-text-fill-color:white;
                        text-shadow:2px 2px 4px rgba(0,0,0,0.5), 0 0 20px rgba(0,0,0,0.3);
                        forced-color-adjust:none; -webkit-print-color-adjust:exact;">
                        新会计准则业绩表现和洞察<br>{type_str}保险公司<br>
                    </div>
                    <div style="font-size:22px; font-weight:650; margin:0; align-self:flex-end; text-align:right;
                        font-family:Microsoft YaHei,微软雅黑,sans-serif;
                        color:white; -webkit-text-fill-color:white;
                        text-shadow:1px 1px 3px rgba(0,0,0,0.5);
                        forced-color-adjust:none; -webkit-print-color-adjust:exact;">
                        本期报告时点：{cy_label}<br>对比期报告时点：{py_label}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            #--------渲染图表和页码-------
            for i, mod in enumerate(ordered_modules):
                render_report_module(mod, print_mode=True, is_first=(i == 0))
                
            st.markdown(f"""
            <div style="position:relative; width:338.67mm;  height:175.5mm;
                page-break-before:always; overflow:hidden; margin:0; padding:0;
                -webkit-print-color-adjust:exact; print-color-adjust:exact; forced-color-adjust:none;">
                <img src="{back_url}" style="width:100%; height:100%; object-fit:cover; display:block;"/>
            </div>
            """, unsafe_allow_html=True)
    else:
        # 如果是网页查看模式，只渲染侧边栏选中的那一个图表！
        if active_m_id:
            # 网页模式下不需要断页，直接传 is_first=True 就行
            render_report_module(active_m_id, print_mode=False, is_first=True)


