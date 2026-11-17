"""新准则财务报告洞察平台的中英文展示层。

本模块只负责“展示文案”，不改动任何指标编码或底层数据：
- 中文/英文语言状态与切换；
- 公司中文名到英文展示名的映射；
- 指标、图表、模块、期间口径、单位、同业分类的英文名称；
- Altair / Plotly 图表的标题、坐标轴、图例、悬浮提示翻译；
- 表格列名与常见枚举值翻译；
- Excel 默认分析内容的英文对照。

语言状态由页面顶部的“中文 / English”控件写入
st.session_state['platform_language']；没有 Streamlit 运行时（例如单元测试）时
默认返回中文，保证原有行为不变。
"""

from __future__ import annotations

from copy import deepcopy
import html
import json
from numbers import Number
from pathlib import Path
import re
from typing import Any

import pandas as pd

try:  # pragma: no cover - Streamlit is available in the app, not necessarily in tests
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


LANG_ZH = "zh"
LANG_EN = "en"
LANGUAGE_LABELS = {"中文": LANG_ZH, "English": LANG_EN}
LANGUAGE_OPTIONS = ("中文", "English")
LANGUAGE_STATE_KEY = "platform_language"
LANGUAGE_DISPLAY_KEY = "platform_language_display"
AI_TRANSLATION_CACHE_KEY = "i18n_ai_translation_cache"
AI_TRANSLATION_PENDING_KEY = "i18n_ai_translation_pending"
AI_TRANSLATION_MAX_ITEM_CHARS = 2000
AI_TRANSLATION_MAX_ITEMS = 80
AI_TRANSLATION_MAX_BATCH_CHARS = 30000


# ---------------------------------------------------------------------------
# 语言状态
# ---------------------------------------------------------------------------
def get_language() -> str:
    if st is None:
        return LANG_ZH
    try:
        value = st.session_state.get(LANGUAGE_STATE_KEY, LANG_ZH)
    except Exception:
        return LANG_ZH
    return LANG_EN if str(value).lower().startswith("en") else LANG_ZH


def set_language(language: str) -> None:
    if st is None:
        return
    value = LANG_EN if str(language).lower().startswith("en") else LANG_ZH
    st.session_state[LANGUAGE_STATE_KEY] = value


def sync_language_from_display_control() -> None:
    """Apply the persisted display-language control before the page paints.

    Streamlit executes widget callbacks before the next script run, but the
    sidebar in app.py is rendered before show_step_7_solvency(). Syncing at
    the application entry point keeps the sidebar and the report title in the
    same language during that rerun, including English -> Chinese switches.
    """
    if st is None:
        return
    try:
        selected = st.session_state.get(LANGUAGE_DISPLAY_KEY)
    except Exception:
        return
    if selected:
        set_language(LANGUAGE_LABELS.get(str(selected), LANG_ZH))


def is_english(language: str | None = None) -> bool:
    return (language or get_language()) == LANG_EN


def t(zh: str, en: str, language: str | None = None) -> str:
    """Return the English text when English display is active."""
    if not is_english(language):
        return zh
    return _replace_company_names(en)


def language_label(language: str | None = None) -> str:
    return "English" if is_english(language) else "中文"


# ---------------------------------------------------------------------------
# 指标名称
# ---------------------------------------------------------------------------
# 只覆盖 Step7 常用指标；未列出的编码使用编码本身按英文单词展开，避免回退成中文。
ENGLISH_METRIC_NAMES: dict[str, str] = {
    "RECOGNIZED_ASSETS": "Recognised assets",
    "RECOGNIZED_LIABILITIES": "Recognised liabilities",
    "ACTUAL_CAPITAL": "Actual capital",
    "CORE_T1_CAPITAL": "Core tier 1 capital",
    "CORE_T2_CAPITAL": "Core tier 2 capital",
    "ANC_T1_CAPITAL": "Ancillary tier 1 capital",
    "ANC_T2_CAPITAL": "Ancillary tier 2 capital",
    "MINIMUM_CAPITAL": "Minimum capital",
    "QUANT_RISK_CAPITAL": "Quantitative risk minimum capital",
    "CONTROL_RISK_CAPITAL": "Control risk minimum capital",
    "ADDITIONAL_CAPITAL": "Additional capital",
    "CORE_SOLVENCY_SURPLUS": "Core solvency surplus",
    "COMBINED_SOLVENCY_SURPLUS": "Combined solvency surplus",
    "CORE_SOLVENCY_RATIO": "Core solvency ratio",
    "COMBINED_SOLVENCY_RATIO": "Combined solvency ratio",
    "NET_PROFIT": "Net profit",
    "NET_ASSETS": "Net assets",
    "TOTAL_ASSETS": "Total assets",
    "ROE": "Return on equity (ROE)",
    "ROA": "Return on assets (ROA)",
    "PREMIUM_GROWTH": "Gross premium growth",
    "SIGNED_PREMIUM": "Signed premium",
    "SIGNED_PREMIUM_MOTOR": "Motor signed premium",
    "SIGNED_PREMIUM_NON_MOTOR_TOP5": "Top 5 non-motor signed premium",
    "INSURANCE_REVENUE": "Insurance revenue",
    "COMBINED_RATIO": "Combined ratio",
    "EXPENSE_RATIO": "Expense ratio",
    "LOSS_RATIO": "Loss ratio",
    "REGISTERED_CAPITAL": "Registered capital",
    "INSURANCE_RISK_CAPITAL": "Life insurance risk minimum capital",
    "NON_LIFE_INSURANCE_RISK_CAPITAL": "Non-life insurance risk minimum capital",
    "MARKET_RISK_CAPITAL": "Market risk minimum capital",
    "CREDIT_RISK_CAPITAL": "Credit risk minimum capital",
    "SPREAD_RISK_CAPITAL": "Spread risk minimum capital",
    "COUNTERPARTY_RISK_CAPITAL": "Counterparty default risk minimum capital",
    "SURRENDER_RISK_CAPITAL": "Surrender risk minimum capital",
    "LOSS_OCCURRENCE_RISK_CAPITAL": "Loss occurrence risk minimum capital",
    "EXPENSE_RISK_CAPITAL": "Expense risk minimum capital",
    "LIFE_INSURANCE_RISK_DIVERSIFICATION_EFFECT": "Life insurance risk diversification effect",
    "QUANT_RISK_DIVERSIFICATION_EFFECT": "Quantitative risk diversification effect",
    "CONTRACT_LOSS_ABSORPTION_EFFECT": "Contractual loss absorption effect",
    "REAL_ESTATE_RISK_CAPITAL": "Real estate price risk minimum capital",
    "OVERSEAS_FIXED_INCOME_RISK_CAPITAL": "Overseas fixed-income price risk minimum capital",
    "OVERSEAS_EQUITY_RISK_CAPITAL": "Overseas equity price risk minimum capital",
    "FOREIGN_EXCHANGE_RISK_CAPITAL": "Foreign exchange risk minimum capital",
    "MARKET_RISK_DIVERSIFICATION_EFFECT": "Market risk diversification effect",
    "CREDIT_RISK_DIVERSIFICATION_EFFECT": "Credit risk diversification effect",
    "INTEREST_RATE_RISK_CAPITAL": "Interest rate risk minimum capital",
    "EQUITY_RISK_CAPITAL": "Equity price risk minimum capital",
    "POLICY_SURPLUS_CORE_T1": "Policy future surplus included in core tier 1 capital",
    "POLICY_SURPLUS_CORE_T2": "Policy future surplus included in core tier 2 capital",
    "POLICY_SURPLUS_ANC_T1": "Policy future surplus included in ancillary tier 1 capital",
    "POLICY_SURPLUS_ANC_T2": "Policy future surplus included in ancillary tier 2 capital",
    "POLICY_SURPLUS_CORE_TO_CORE_CAPITAL": "Policy future surplus / core capital",
    "ACTUAL_CAPITAL_TO_RECOGNIZED_ASSETS": "Actual capital / recognised assets",
    "CORE_CAPITAL_TO_REGISTERED_CAPITAL": "Core capital / registered capital",
    "LIFE_INSURANCE_RISK_TO_QUANT_CAPITAL": "Life insurance risk / quantitative risk capital",
    "NON_LIFE_INSURANCE_RISK_TO_QUANT_CAPITAL": "Non-life insurance risk / quantitative risk capital",
    "MARKET_RISK_TO_QUANT_CAPITAL": "Market risk / quantitative risk capital",
    "CREDIT_RISK_TO_QUANT_CAPITAL": "Credit risk / quantitative risk capital",
    "DIVERSIFICATION_EFFECT_TO_QUANT_CAPITAL": "Diversification effect / quantitative risk capital",
    "LOSS_ABSORPTION_TO_QUANT_CAPITAL": "Loss absorption / quantitative risk capital",
    "LIFE_INSURANCE_RISK_TO_LIABILITIES": "Life insurance risk / recognised liabilities",
    "NON_LIFE_INSURANCE_RISK_TO_LIABILITIES": "Non-life insurance risk / recognised liabilities",
    "INTEREST_RATE_RISK_TO_ASSETS": "Interest rate risk / recognised assets",
    "EQUITY_RISK_TO_ASSETS": "Equity price risk / recognised assets",
    "SPREAD_RISK_TO_ASSETS": "Spread risk / recognised assets",
    "COUNTERPARTY_RISK_TO_ASSETS": "Counterparty risk / recognised assets",
    "PREMIUM_INCOME": "Premium income",
    "UNDERWRITING_PROFIT": "Underwriting profit",
    "UNDERWRITING_PROFIT_AMOUNT": "Underwriting profit",
}

# 同一中文指标名在不同来源中的兜底对照。
ENGLISH_METRIC_NAME_BY_ZH: dict[str, str] = {
    "认可资产": "Recognised assets",
    "认可负债": "Recognised liabilities",
    "实际资本": "Actual capital",
    "最低资本": "Minimum capital",
    "核心一级资本": "Core tier 1 capital",
    "核心二级资本": "Core tier 2 capital",
    "附属一级资本": "Ancillary tier 1 capital",
    "附属二级资本": "Ancillary tier 2 capital",
    "核心偿付能力充足率": "Core solvency ratio",
    "综合偿付能力充足率": "Combined solvency ratio",
    "净利润": "Net profit",
    "总资产": "Total assets",
    "净资产": "Net assets",
    "签单保费": "Signed premium",
    "车险签单保费": "Motor signed premium",
    "综合成本率": "Combined ratio",
    "注册资本": "Registered capital",
    "保费增速": "Premium growth",
    "保费收入": "Premium income",
    "收入": "Revenue",
    "利润": "Profit",
    "净利润率": "Net profit margin",
    "核心资本": "Core capital",
    "附属资本": "Ancillary capital",
}


def english_from_code(code: str) -> str:
    """Build a readable English label from a metric code."""
    words = [word for word in str(code or "").split("_") if word]
    if not words:
        return ""
    acronyms = {"ROE", "ROA", "EPS", "LCR"}
    rendered = []
    for word in words:
        if word in acronyms:
            rendered.append(word)
        elif word.isdigit():
            rendered.append(word)
        else:
            rendered.append(word.capitalize())
    return " ".join(rendered)


def metric_name(code: str, zh_name: str = "", language: str | None = None) -> str:
    if not is_english(language):
        return str(zh_name or code)
    key = str(code or "").strip()
    if key in ENGLISH_METRIC_NAMES:
        return ENGLISH_METRIC_NAMES[key]
    name = str(zh_name or "").strip()
    if name in ENGLISH_METRIC_NAME_BY_ZH:
        return ENGLISH_METRIC_NAME_BY_ZH[name]
    if key:
        return english_from_code(key)
    return name


def translate_metric_frame(frame: pd.DataFrame, language: str | None = None) -> pd.DataFrame:
    """Return a copy of the analysis frame with English metric names for display."""
    if not is_english(language) or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    result = frame.copy()
    if "指标名称" not in result.columns:
        return result
    if "指标编码" in result.columns:
        result["指标名称"] = [
            metric_name(code, name, language)
            for code, name in zip(result["指标编码"], result["指标名称"])
        ]
    else:
        result["指标名称"] = [
            ENGLISH_METRIC_NAME_BY_ZH.get(str(name).strip(), str(name))
            for name in result["指标名称"]
        ]
    return result


# ---------------------------------------------------------------------------
# 图表、模块、分类名称
# ---------------------------------------------------------------------------
# 公司中文名 -> 英文展示名。
# 英文模式优先使用市场通用品牌简称（例如 PICC P&C、CPIC P&C、Ping An P&C），
# 未收录的名称回退为原始名称，保证不会因为映射缺失而隐藏公司。
COMPANY_NAMES_EN: dict[str, str] = {
    "三井住友海上": "Mitsui Sumitomo",
    "三星财险": "Samsung F&C",
    "东京海上日动": "Tokio Marine & Nichido",
    "东吴财险": "Soochow",
    "东海航运": "Donghai Shipping",
    "中华财险": "China United",
    "中原农险": "Zhongyuan Agricultural",
    "中国渔业互保": "China Fisheries Mutual",
    "中意财险": "Generali China",
    "中煤财险": "China Coal",
    "中石油自保": "CNPC Captive",
    "中路财险": "China Road",
    "中远海自保": "COSCO Shipping Captive",
    "中银保险": "BOC Insurance",
    "久隆财险": "Jiulong",
    "亚太财险": "Asia-Pacific",
    "京东安联": "JD Allianz",
    "人保财险": "PICC P&C",
    "众安保险": "ZhongAn",
    "众惠相互": "Zhonghui Mutual",
    "众诚保险": "Zhongcheng",
    "凯本财险": "KB Insurance",
    "利宝保险": "Liberty",
    "前海财险": "Qianhai",
    "劳合社": "Lloyd's",
    "北部湾财险": "Beibu Gulf",
    "华农财险": "Huanong",
    "华安财险": "Sinosafe",
    "华泰财险": "Huatai P&C",
    "华海财险": "Huahai",
    "史带财险": "Starr",
    "合众财险": "Hezhong",
    "国任财险": "Guoren",
    "国元农险": "Guoyuan Agricultural",
    "国寿财险": "China Life P&C",
    "国泰财险": "Cathay",
    "大地财险": "China Continent",
    "大家财险": "Dajia",
    "太保产险": "CPIC P&C",
    "太平科技": "Taiping Technology",
    "太平财险": "Taiping P&C",
    "安信农险": "Anxin Agricultural",
    "安华农险": "Anhua Agricultural",
    "安心财险": "Anxin",
    "安盛天平": "AXA Tianping",
    "安盟财险": "Allianz P&C",
    "安诚财险": "Ancheng",
    "富德财险": "Fude",
    "富邦财险": "Fubon",
    "平安产险": "Ping An P&C",
    "广东能源自保": "Guangdong Energy Captive",
    "建信财险": "CCB Insurance",
    "恒邦财险": "Hengbang",
    "日本兴亚": "Sompo Japan",
    "日本财险": "Sompo Japan",
    "比亚迪财险": "BYD Insurance",
    "永安财险": "Yong'an",
    "永诚财险": "Yongcheng",
    "汇友相互": "Huiyou Mutual",
    "法巴天星": "BNP Paribas Tianxing",
    "泰山财险": "Taishan",
    "泰康在线": "Taikang Online",
    "浙商财险": "Zheshang",
    "海峡金桥": "Haixia Jinqiao",
    "渤海财险": "Bohai",
    "燕赵财险": "Yanzhao",
    "爱和谊日生同和": "Aioi Nissay Dowa",
    "现代财险": "Hyundai",
    "珠峰财险": "Everest",
    "瑞再企商": "Swiss Re Corporate Solutions",
    "申能财险": "Shenergy",
    "紫金财险": "Zijin",
    "美亚财险": "AIG",
    "苏黎世财险": "Zurich",
    "英大财险": "Yingda",
    "融盛财险": "Rongsheng",
    "融通财险": "Rongtong",
    "诚泰财险": "Chengtai",
    "都邦财险": "Dubon",
    "鑫安汽车": "Xin'an Auto",
    "铁路自保": "Railway Captive",
    "锦泰财险": "Jintai",
    "长安责任保险": "Chang'an",
    "长江财险": "Changjiang",
    "阳光信保": "Sunshine Credit",
    "阳光农业相互": "Sunshine Agricultural Mutual",
    "阳光财险": "Sunshine P&C",
    "黄河财险": "Yellow River",
    "鼎和财险": "Dinghe",
}


def company_name(name: Any, language: str | None = None) -> Any:
    """Return the English display name for a company when English is active."""
    if not is_english(language) or not isinstance(name, str):
        return name
    value = name.strip()
    if value in COMPANY_NAMES_EN:
        return COMPANY_NAMES_EN[value]
    # 兼容历史数据中的“平安产险（偿付能力）”等带后缀写法。
    base = re.sub(r"[（(][^）)]*[）)]\s*$", "", value).strip()
    return COMPANY_NAMES_EN.get(base, name)


def _replace_company_names(text: str) -> str:
    """Replace known Chinese company names inside an English display string."""
    if not isinstance(text, str) or not text:
        return text
    result = text
    for source in sorted(COMPANY_NAMES_EN, key=len, reverse=True):
        if source and source in result:
            result = result.replace(source, COMPANY_NAMES_EN[source])
    return result

CHART_NAMES_EN: dict[str, str] = {
    "行业整体保费规模与结构": "Industry premium scale and structure",
    "分险种保费收入": "Premium by line of business",
    "行业市场份额": "Industry market share",
    "承保效益": "Underwriting efficiency",
    "偿付能力披露整体情况": "Solvency disclosure overview",
    "能力五边形": "Capability pentagon",
    "公司业绩展示": "Company performance",
    "综合偿付能力充足率": "Combined solvency ratio",
    "核心偿付能力充足率": "Core solvency ratio",
    "核心资本占比": "Core capital share",
    "保费增速": "Premium growth",
    "关键偿付数据概览": "Key solvency data overview",
    "承保规模": "Underwriting scale",
    "经营效益": "Operating efficiency",
    "资本规模": "Capital scale",
    "资本规模与结构": "Capital scale and structure",
    "核心资本明细占比": "Core capital composition",
    "附属资本明细占比": "Ancillary capital composition",
    "量化风险最低资本构成": "Quantitative risk minimum capital composition",
    "保险风险（非寿）/认可负债率": "Non-life insurance risk / recognised liabilities",
    "各类市场风险占比": "Market risk composition",
    "利率风险/认可资产率": "Interest rate risk / recognised assets",
    "权益价格风险/认可资产率": "Equity price risk / recognised assets",
    "各类信用风险占比": "Credit risk composition",
    "利差风险/认可资产率": "Spread risk / recognised assets",
    "对手违约风险/认可资产率": "Counterparty risk / recognised assets",
    "增资发债信息统计": "Capital raising and bond issuance",
    "资本使用效率与核心资本占比气泡图": "Capital efficiency and core capital share bubble chart",
    "核心资本/注册资本": "Core capital / registered capital",
    "实际资本/认可资产率": "Actual capital / recognised assets",
    "核心及综合充足率": "Core and combined solvency ratios",
    "综合充足率变化": "Combined solvency ratio change",
    "核心充足率变化": "Core solvency ratio change",
    "资本使用效率": "Capital efficiency",
    "行业资本分级": "Industry capital tiers",
    "核心资本": "Core capital",
    "附属资本": "Ancillary capital",
    "风险构成情况": "Risk composition",
    "保险风险": "Insurance risk",
    "保险风险构成": "Insurance risk composition",
    "保险风险/认可负债率": "Insurance risk / recognised liabilities",
    "保险风险／认可负债率": "Insurance risk / recognised liabilities",
    "资本金额堆叠": "Capital amount stack",
    "赔付率与费用率": "Loss ratio and expense ratio",
    "投资收益率": "Investment return",
    "市场风险": "Market risk",
    "信用风险": "Credit risk",
    "重大融资信息": "Major financing",
    "公司分期柱": "Company period bars",
    "效应发散": "Effect divergence",
    "市场信用矩阵": "Market–credit matrix",
    "自定义风险散点": "Custom risk scatter",
    "核心资本明细占比-待定": "Core capital composition – to be defined",
    "附属资本明细占比-待定": "Ancillary capital composition – to be defined",
    "利率与权益价格风险占认可资产率气泡图": "Interest rate and equity price risk / recognised assets bubble chart",
    "利差与对手违约风险占认可资产率气泡图": "Spread and counterparty risk / recognised assets bubble chart",
    "寿险与非寿险保险风险占认可负债率气泡图": "Life and non-life insurance risk / recognised liabilities bubble chart",
    "综合偿付能力充足率变化": "Combined solvency ratio change",
    "核心偿付能力充足率变化": "Core solvency ratio change",
}

LEVEL_NAMES_EN: dict[str, str] = {
    "行业概览": "Industry overview",
    "行业对标与趋势研判": "Peer benchmarking and trends",
    "偿付能力水平深度拆解": "Solvency deep dive",
    "经营与偿付能力联动分析": "Operating and solvency linkage",
    "公司规模与结构": "Company scale and structure",
    "行业画像": "Industry profile",
    "附录": "Appendix",
    "规模与发展": "Scale and development",
    "分险种保费收入": "Premium by line of business",
    "市场份额": "Market share",
    "承保效益": "Underwriting efficiency",
    "偿付能力披露整体情况": "Solvency disclosure overview",
    "能力框架-横向对标": "Capability framework – peer benchmarking",
    "经营表现-横向对标": "Operating performance – peer benchmarking",
    "核心指标速览": "Key metrics at a glance",
    "实际资本变动": "Actual capital movement",
    "实际资本/认可资产率": "Actual capital / recognised assets",
    "最低资本变动": "Minimum capital movement",
    "保费增速": "Premium growth",
    "投资利润": "Investment profit",
    "关键偿付数据概览": "Key solvency data overview",
    "实际资本数据对比-行业资本分级": "Actual capital comparison – industry capital tiers",
    "实际资本数据对比-核心资本": "Actual capital comparison – core capital",
    "实际资本数据对比-附属资本": "Actual capital comparison – ancillary capital",
    "最低资本数据对比-风险构成情况": "Minimum capital comparison – risk composition",
    "实际资本数据对比-保险风险": "Actual capital comparison – insurance risk",
    "实际资本数据对比-市场风险": "Actual capital comparison – market risk",
    "实际资本数据对比-信用风险": "Actual capital comparison – credit risk",
    "重大融资信息": "Major financing",
    "全部": "All",
    "一键显示全部（打印/导出）": "Show all (print/export)",
    "行业整体偿付能力概览": "Industry solvency overview",
    "实际资本数据对比": "Actual capital comparison",
    "最低资本数据对比": "Minimum capital comparison",
    "附录": "Appendix",
}

CHART_KIND_NAMES_EN: dict[str, str] = {
    "行业保费规模与结构图": "Industry premium scale and structure",
    "分险种保费收入图": "Premium by line of business",
    "分险种保费收入组合图": "Premium by line of business",
    "行业市场份额图": "Industry market share",
    "承保效益散点图": "Underwriting efficiency scatter",
    "偿付能力整体情况卡片": "Solvency overview cards",
    "能力雷达图": "Capability radar",
    "业绩模式分列图": "Performance pattern grid",
    "资本充足率组合图": "Capital adequacy combination",
    "资本结构组合图": "Capital structure combination",
    "公司折线趋势图": "Company line trend",
    "保费增速结构图": "Premium growth structure",
    "关键指标表": "Key metrics table",
    "结构变化组合图": "Structural change combination",
    "资本金额堆叠": "Capital amount stack",
    "构成堆叠图": "Composition stack",
    "单指标趋势图": "Single metric trend",
    "重大融资表": "Major financing table",
    "资本效率气泡图": "Capital efficiency bubble",
    "公司柱状图": "Company bar chart",
    "趋势+公司柱状": "Trend + company bars",
    "偿付能力组合图": "Solvency combination",
    "市场信用矩阵": "Market–credit matrix",
    "风险散点图": "Risk scatter",
    "效应发散图": "Effect divergence",
    "公司分期柱": "Company period bars",
    "待定": "To be defined",
}

CATEGORY_NAMES_EN: dict[str, str] = {
    "全部": "All",
    "前十大": "Top 10",
    "前三大": "Top 3",
    "前4-10": "Top 4–10",
    "大型公司": "Large companies",
    "中型公司": "Medium companies",
    "小型公司": "Small companies",
    "农业保险": "Agricultural insurance",
    "机动车辆保险": "Motor vehicle insurance",
    "责任险": "Liability insurance",
    "健康险": "Health insurance",
    "意外险": "Accident insurance",
    "企业财产保险": "Commercial property insurance",
    "家庭财产保险": "Home property insurance",
    "工程保险": "Engineering insurance",
    "保证保险": "Guarantee insurance",
    "外资系": "Foreign-invested",
    "自保公司": "Captive insurers",
    "其他": "Other",
    "未分类": "Unclassified",
    "行业合计": "Industry total",
    "头部": "Top tier",
    "中小": "Small and medium",
    "大型": "Large",
    "中型": "Medium",
    "小型": "Small",
}

PERFORMANCE_NAMES_EN: dict[str, str] = {
    "逐年提升": "Consistent improvement",
    "稳健经营": "Steady performance",
    "V形反转": "V-shaped recovery",
    "大起大落": "Highly volatile",
    "持续恶化": "Continuous deterioration",
    "倒V形反转": "Inverted V-shaped reversal",
    "其他": "Other",
}

DISCLOSURE_NAMES_EN: dict[str, str] = {
    "已披露": "Disclosed",
    "未披露": "Not disclosed",
    "有": "Yes",
    "无": "No",
    "完整": "Complete",
    "异常数": "Anomalies",
    "合计": "Total",
    "车险": "Motor",
    "非车险": "Non-motor",
    "未拆分": "Unallocated",
    "保费": "Premium",
    "净利润": "Net profit",
    "承保利润": "Underwriting profit",
    "年度": "Year",
    "来源": "Source",
    "公司类别": "Company category",
    "盈亏": "Profit / loss",
    "盈亏平衡": "Break-even",
    "盈利": "Profit",
    "亏损": "Loss",
    "固定行业数据": "Built-in industry data",
    "上传数据": "Uploaded data",
    "本年累计数": "Year-to-date",
    "本季度数": "Quarterly",
    "本季度末数": "Quarter-end",
    "上季度末数": "Prior quarter-end",
    "期末数": "Period-end",
    "期初数": "Period-start",
    "合并": "Merged",
    "拆分": "Split",
    "核心一级资本": "Core tier 1 capital",
    "核心二级资本": "Core tier 2 capital",
    "附属一级资本": "Ancillary tier 1 capital",
    "附属二级资本": "Ancillary tier 2 capital",
    "计入核心一级资本": "Included in core tier 1 capital",
    "计入核心二级资本": "Included in core tier 2 capital",
    "计入附属一级资本": "Included in ancillary tier 1 capital",
    "计入附属二级资本": "Included in ancillary tier 2 capital",
    "风险分散效应": "Diversification effect",
    "损失吸收效应": "Loss absorption effect",
    "保险风险（寿）": "Insurance risk (life)",
    "保险风险（非寿）": "Insurance risk (non-life)",
    "非寿险业务保险风险": "Non-life insurance risk",
    "保费及准备金风险": "Premium and reserve risk",
    "巨灾风险": "Catastrophe risk",
    "风险分散": "Diversification",
    "赔付率": "Loss ratio",
    "费用率": "Expense ratio",
    "保险风险": "Insurance risk",
    "市场风险": "Market risk",
    "信用风险": "Credit risk",
    "利率风险": "Interest rate risk",
    "权益价格风险": "Equity price risk",
    "房地产价格风险": "Real estate price risk",
    "境外固定收益类资产价格风险": "Overseas fixed-income asset price risk",
    "境外权益类资产价格风险": "Overseas equity asset price risk",
    "汇率风险": "Foreign exchange risk",
    "利差风险": "Spread risk",
    "交易对手违约风险": "Counterparty default risk",
    "损失发生风险": "Loss occurrence risk",
    "退保风险": "Surrender risk",
    "费用风险": "Expense risk",
}

UNIT_NAMES_EN: dict[str, str] = {
    "百亿元": "RMB 10bn",
    "十亿元": "RMB bn",
    "亿元": "RMB 100 mn",
    "百万元": "RMB mn",
    "十万元": "RMB 100k",
    "万元": "RMB 10k",
    "元": "RMB",
    "%": "%",
    "％": "%",
    "‰": "‰",
    "倍": "x",
}

FIELD_NAMES_EN: dict[str, str] = {
    "公司": "Company",
    "公司名称": "Company",
    "报告期": "Reporting period",
    "指标名称": "Metric",
    "指标编码": "Metric code",
    "数值": "Value",
    "单位": "Unit",
    "披露状态": "Disclosure status",
    "同业分类": "Peer group",
    "公司类型": "Company type",
    "年度": "Year",
    "期间口径": "Period basis",
    "数据类型": "Data type",
    "监管下限": "Regulatory minimum",
    "保费": "Premium",
    "净利润": "Net profit",
    "承保利润": "Underwriting profit",
    "保费占比": "Premium share",
    "净利润占比": "Net profit share",
    "承保利润占比": "Underwriting profit share",
    "车险": "Motor",
    "非车险": "Non-motor",
    "险种": "Line of business",
    "原保险保费收入": "Original premium income",
    "同比增速": "YoY growth",
    "基期年度": "Base year",
    "合计": "Total",
    "来源": "Source",
    "收入排名": "Revenue rank",
    "利润排名": "Profit rank",
    "收入": "Revenue",
    "利润": "Profit",
    "类别": "Category",
    "盈亏": "Profit / loss",
    "标签": "Label",
    "公司数": "Company count",
    "有效公司数": "Valid companies",
    "综合成本率": "Combined ratio",
    "签单保费排名": "Signed premium rank",
    "盈亏平衡": "Break-even",
    "保费单位": "Premium unit",
    "状态": "Status",
    "原始公司名称": "Original company name",
    "标准公司名称": "Standard company name",
    "公司统一编码": "Company identifier",
    "报告类型": "Report type",
    "报告年度": "Reporting year",
    "报告季度": "Reporting quarter",
    "披露日期": "Disclosure date",
    "一级模块": "Level-one module",
    "二级模块": "Level-two module",
    "行次": "Line number",
    "是否预测": "Forecast",
    "来源页码": "Source page",
    "原始披露值": "Original disclosed value",
    "备注": "Notes",
    "来源类型": "Source type",
    "指标属性": "Metric attribute",
    "来源文件": "Source file",
    "来源工作表": "Source worksheet",
    "导入批次": "Import batch",
    "计算逻辑": "Calculation logic",
}
FIELD_NAMES_EN["类型"] = "Type"

DEFAULT_ANALYSIS_EN: dict[str, str] = {
    "近五年行业保费合计及车险/非车险结构变化": "Industry premium and motor/non-motor mix over the past five years",
    "最新年度按公司类别的保费、净利润、承保利润市场份额": "Latest-year market share by company category for premium, net profit and underwriting profit",
    "分险种展示原保险保费收入与同比增速（单位：亿元），仅列示机动车辆保险、健康险、农业保险、责任险和意外险，保留最近四个年度；每个险种一张保费柱状图与同比增速折线图的组合图，每行两个险种，同比按相邻有数年度计算。": "Original premium income and YoY growth by line of business (RMB 100 mn), limited to motor, health, agricultural, liability and accident insurance for the latest four years; each line has one combo chart with premium bars and a YoY growth line, two lines per row, with YoY calculated from the nearest year with data.",
    "近五年综合成本率与签单保费排名散点图（100% 盈亏平衡线），并汇总盈利/亏损公司数": "Five-year scatter of combined ratio against signed premium rank (100% break-even line), with profitable/loss-making company counts",
    "按行业合计口径计算综合/核心偿付能力充足率，并展示实际资本与最低资本": "Industry aggregate combined/core solvency ratios, with actual and minimum capital",
    "上方 KPMG Pink 折线展示综合偿付能力充足率，下方堆叠柱展示实际资本与最低资本；按年度口径展示。": "The KPMG Pink line shows the combined solvency ratio; stacked bars below show actual and minimum capital (annual basis).",
    "上方 KPMG Pink 折线展示核心偿付能力充足率，下方堆叠柱展示核心资本与最低资本；按年度口径展示。": "The KPMG Pink line shows the core solvency ratio; stacked bars below show core and minimum capital (annual basis).",
    "各公司实际资本年度变动走势，每家公司一个折线小图": "Annual actual capital trend for each company, shown as one small line chart per company",
    "各公司实际资本/认可资产率年度走势，每家公司一个折线小图": "Annual actual capital / recognised assets ratio for each company, shown as one small line chart per company",
    "各公司最低资本年度变动走势，每家公司一个折线小图": "Annual minimum capital trend for each company, shown as one small line chart per company",
    "每家公司近五年车险/非车险结构占比与总保费同比增速": "Five-year motor/non-motor mix and total premium growth for each company",
    "多公司实际资本/认可资产率跨期趋势对比。": "Actual capital / recognised assets ratio trend comparison across companies.",
    "100%堆叠柱展示核心一级、核心二级、附属一级和附属二级资本构成。": "100% stacked bars show the composition of core tier 1, core tier 2, ancillary tier 1 and ancillary tier 2 capital.",
    "非寿险业务保险风险构成：巨灾风险、准备金风险、保费风险和风险分散。": "Non-life insurance risk composition: catastrophe risk, reserve risk, premium risk and diversification.",
    "多公司保险风险/认可负债率跨期趋势对比。": "Insurance risk / recognised liabilities ratio trend comparison across companies.",
    "每家公司近五年赔付率、费用率堆叠及综合成本率变化。": "Five-year loss ratio, expense ratio stack and combined ratio for each company.",
    "各公司近五年投资收益率年度变动情况。": "Annual investment return movements for each company over the past five years.",
}


# 长句或高频短语，按长度从长到短替换，避免先替换短词破坏长句。
PHRASE_EN: dict[str, str] = {
    "公司级偿付能力对标报告": "Company Solvency Benchmarking Report",
    "当前没有公司数据。": "No company data.",
    "当前没有同时具备赔付率和费用率的年度数据。": "No annual data with both loss ratio and expense ratio is available.",
    "核心资本是指在持续经营状态下和破产清算状态下均可以吸收损失的资本。": "Core capital is capital that can absorb losses both on a going-concern basis and in liquidation.",
    "附属资本是指在破产清算状态下可以吸收损失的资本。": "Ancillary capital is capital that can absorb losses in liquidation.",
    "小型、外资系、农业保险和自保公司的核心资本占比较为相似，处于80%至100%区间；资本补充债券等进行资本补充，以支持偿付能力提升和业务持续健康发展。": "Small companies, foreign-invested insurers, agricultural insurers and captive insurers have broadly similar core capital shares, within the 80%–100% range. These companies use instruments such as capital supplementary bonds to support solvency and sustainable business development.",
    "部分集团子公司、大型公司及中型公司的附属资本占比较高，通常是在保司偿付能力充足率持续承压的情况下，通过发行次级定期债务、资本补充债券等进行资本补充，以支持偿付能力提升和业务持续健康发展。": "Some group subsidiaries, large companies and medium-sized companies have relatively high ancillary capital shares. When solvency ratios are under pressure, they commonly issue subordinated term debt or capital supplementary bonds to support solvency and sustainable business development.",
    "每家公司平铺展示最近 ": "Each company displays the latest ",
    " 个年度：下方为赔付率，上方为费用率，柱高合计为综合成本率；红色虚线为 100% 盈亏平衡线。柱顶数字为综合成本率，*表示按赔付率加费用率测算的值。": " years side by side. Loss ratio is below and expense ratio above; their combined height is the combined ratio. The red dashed line marks 100% break-even. Values above the bars show the combined ratio, with * indicating a calculated loss-plus-expense ratio.",
    "赔付率": "Loss ratio",
    "费用率": "Expense ratio",
    "100% 盈亏平衡线": "100% break-even line",
    "非寿险业务": "Non-life insurance",
    "保费及准备金风险": "Premium and reserve risk",
    "准备金风险": "Reserve risk",
    "巨灾风险": "Catastrophe risk",
    "风险分散": "Diversification",
    "风险分散率": "Diversification rate",
    "特征系数影响": "Feature-factor impact",
    "市场竞争": "Market competition",
    "财险公司列表": "the property insurance company list",
    "配置": "configuration",
    "保险公司偿付能力公司对标报告": "Insurance Company Solvency Benchmarking Report",
    "公司级图表设置与图片覆盖": "Company chart settings and image overrides",
    "公司内容分析与注释输入": "Company analysis and note inputs",
    "手动上传图片（PNG/JPG）": "Manual image upload (PNG/JPG)",
    "图表类型：按指标特征自动匹配（系统内置）": "Chart type: automatically matched to metric characteristics (built in)",
    "请在侧边栏公司报告导航中选择具体图表。": "Select a chart from the company report navigation in the sidebar.",
    "请在报告配置中至少选择一家展示公司。": "Select at least one company in the report settings.",
    "请先在 Step5 确认集成数据，或在 Step6 上传集成表。": "Confirm integrated data in Step 5, or upload an integrated workbook in Step 6.",
    "当前数据没有公司明细记录。": "No company detail records are available.",
    "当前数据没有可用报告期。": "No reporting periods are available.",
    "查看报告底层数据": "View underlying report data",
    "缺失指标编码：": "Missing metric codes: ",
    "一键AI分析": "One-click AI commentary",
    "一键 AI 分析": "One-click AI commentary",
    "特定追踪": "Track company",
    "排序方向": "Sort direction",
    "展示公司": "Companies",
    "显示单位": "Display unit",
    "公司类型": "Company type",
    "图表展示顺序依据": "Chart sort metric",
    "选择一家或多家公司": "Select one or more companies",
    "同业分类": "Peer group",
    "图片覆盖：": "Image override: ",
    "公司按“": "Companies grouped by “",
    "”分组，每家公司展示最近 ": "”; each company shows the latest ",
    " 个年度：左轴为车险/非车险的 100% 结构占比，右轴折线为总保费同比增速；非车险按“总签单保费 - 车险”计算。首年若缺少上一年度基数，则不显示折线点。": " years: the left axis shows the 100% motor/non-motor mix, and the right-axis line shows total premium growth. Non-motor premium is total signed premium less motor. No growth point is shown for the first year without a prior-year base.",
    "当前各公司都没有可比的连续年度保费基数，因此图内暂不显示同比增速折线。": "No company has a comparable consecutive-year premium base, so growth lines are not shown.",
    "保费增速图渲染失败：": "premium growth chart failed: ",
    "图表渲染失败：": "chart failed: ",
    "查看详细错误": "View detailed error",
    "横轴为「": "The x-axis is “",
    "」，纵轴为「": "”, and the y-axis is “",
    "」；数值越小表示排名越靠前，第 1 名位于右上角。每家小图的坐标轴按该公司自身排名范围自适应缩放，便于看出排名波动；刻度数字仍为真实名次。公司按利润排名年度轨迹归类为：逐年提升 / 稳健经营 / V形反转 / 大起大落 / 持续恶化。": "”. Lower values indicate a better rank, with rank 1 in the top-right corner. Each panel is scaled to the company’s own rank range; tick labels remain actual ranks. Companies are grouped by their annual profit-rank trajectory: Consistent improvement / Steady performance / V-shaped recovery / Highly volatile / Continuous deterioration.",
    "🔍 数据诊断：查看每家公司的收入/利润数据覆盖情况": "Data diagnostics: revenue/profit coverage by company",
    "下表显示每家公司每个报告期是否有「": "The table shows whether each company has “",
    "」和「": "” and “",
    "」数据。❌ 表示该期该指标缺失（未披露或未集成）。若发现大量 ❌，请到 STEP5/STEP6 检查原始数据是否完整。": "” data in each period. ❌ means the metric is missing (not disclosed or not integrated). If many ❌ appear, check the source data in STEP5/STEP6.",
    "无公司数据。": "No company data.",
    "没有公司能被归类到任何业绩模式。": "No company could be classified into a performance pattern.",
    "按年度口径展示：上方 KPMG Pink 折线为对应充足率，下方堆叠柱为资本规模；同组所有公司统一使用同一金额纵轴范围，便于直接比较资本规模。": "Annual view: the KPMG Pink line shows the solvency ratio, and stacked bars below show capital scale. All companies in the group share the same amount axis for direct comparison.",
    "图表说明：柱状图为综合偿付能力充足率；粉色折线为核心偿付能力充足率。各公司统一使用同一百分比纵轴范围，柱形颜色对应不同报告期。": "Chart note: bars show the combined solvency ratio and the pink line shows the core solvency ratio. All companies share the same percentage axis; bar colours identify reporting periods.",
    "核心偿付能力充足率（%）": "Core solvency ratio (%)",
    "综合偿付能力充足率（%）": "Combined solvency ratio (%)",
    "核心资本充足率": "Core capital adequacy ratio",
    "综合资本充足率": "Combined capital adequacy ratio",
    "保单未来盈余/核心资本比例": "Policy future surplus / core capital",
    "未来保单盈余": "Future policy surplus",
    "认可负债余额": "Recognised liabilities",
    "市场风险占比": "Market risk share",
    "保险风险占比": "Insurance risk share",
    "上年同期": "Prior-year period",
    "本期": "Current period",
    "堆叠柱组合图": "Stacked bar combination",
    "并列柱组合图": "Grouped bar combination",
    "新增视图：每个报告期的两项资本各自成柱，上方仍保留对应充足率折线。": "New view: the two capital items are shown as separate bars for each reporting period, with the corresponding solvency ratio line above.",
    "上方 KPMG Pink 折线展示核心资本占实际资本的比例，下方堆叠柱展示核心资本与附属资本；同组所有公司统一使用同一金额纵轴范围，便于直接比较资本规模。": "The KPMG Pink line shows core capital as a share of actual capital; stacked bars below show core and ancillary capital. All companies in the group share the same amount axis.",
    "核心资本占实际资本的比例": "Core capital / actual capital",
    "核心资本占实际资本的比例（%）": "Core capital / actual capital (%)",
    "核心资本与附属资本结构": "Core and ancillary capital structure",
    "计入各级资本的保单未来盈余构成占比": "Policy future surplus by capital tier",
    "各色块表示计入相应资本层级的保单未来盈余占该公司已披露保单未来盈余明细合计的比例；100%表示该公司披露的保单未来盈余全部计入了同一个资本层级，其他资本层级没有披露这个明细。": "Each segment shows policy future surplus in a capital tier as a share of the company’s total disclosed policy future surplus detail. 100% means all disclosed surplus was allocated to one tier; no detail was disclosed for other tiers.",
    "量化风险最低资本构成": "Quantitative risk minimum capital composition",
    "各类市场风险占比": "Market risk composition",
    "各类信用风险占比": "Credit risk composition",
    "柱高按各构成项目/量化风险最低资本的比例展示，实际金额仅保留在悬浮信息中；数据标签与对应比例折线图一致，负向抵减项目位于零线下方。": "Bar heights show each component as a share of quantitative risk minimum capital; amounts are available on hover. Negative offsets sit below the zero line.",
    "柱高按各构成项目/市场风险最低资本的比例展示，实际金额仅保留在悬浮信息中；负向风险分散效应位于零线下方。": "Bar heights show each component as a share of market risk minimum capital; amounts are available on hover. The negative diversification effect sits below the zero line.",
    "柱高按各构成项目/信用风险最低资本的比例展示，实际金额仅保留在悬浮信息中；负向风险分散效应位于零线下方。": "Bar heights show each component as a share of credit risk minimum capital; amounts are available on hover. The negative diversification effect sits below the zero line.",
    "按公司分面展示构成；负向抵减项目位于零线下方，所有颜色均来自 KPMG 色卡。": "Composition by company; negative offsets sit below the zero line. All colours come from the KPMG palette.",
    "100%堆叠柱显示核心一级、核心二级、附属一级和附属二级资本构成；所有公司和报告期的柱高一致，色块高度代表结构占比，悬浮可查看占比和金额。": "100% stacked bars show core tier 1, core tier 2, ancillary tier 1 and ancillary tier 2 capital. Bar heights are equal across companies and periods; segment heights show the mix, with shares and amounts on hover.",
    "未披露": "Not disclosed",
    "按公司展示抵减效应的跨期方向与幅度，零线用于区分正向增加和负向抵减。": "Offsetting effects by company over time; the zero line separates positive additions from negative offsets.",
    "偿付能力矩阵": "Solvency matrix",
    "市场—信用风险矩阵": "Market–credit risk matrix",
    "横轴50%、纵轴100%的红色虚线分别为核心和综合偿付能力充足率监管下限。": "Red dashed lines at 50% on the x-axis and 100% on the y-axis are the regulatory minima for the core and combined solvency ratios.",
    "深蓝虚线为样本中位数，用于识别市场风险和信用风险同时偏高的公司。": "The dark-blue dashed line is the sample median, highlighting companies with both high market and credit risk.",
    "展示 ": "Showing ",
    "；每个气泡代表一家公司，横纵轴均为占": "; each bubble is one company; both axes are shown as a share of ",
    "的比例，气泡面积代表": ". Bubble size represents ",
    "规模；深蓝虚线为样本横纵指标中位数。": " scale; the dark-blue dashed line is the sample median of both axes.",
    "每家公司一个年度小折线图，纵轴为 %；蓝色折线为该公司综合偿付能力充足率走势，红色虚线为监管下限 100%；仅标注首末年数值，悬停查看各年明细。": "One annual line chart per company; the y-axis is in %. The blue line is the company’s combined solvency ratio and the red dashed line is the 100% regulatory minimum. Only first/last-year values are labelled; hover for annual detail.",
    "能力五边形当前无法打分，诊断如下：": "The capability pentagon cannot be scored. Diagnostics:",
    "筛选后总记录数：": "Filtered records: ",
    "最新报告期「": "Latest reporting period “",
    "」在筛选后仅剩 ": "” has only ",
    " 行、": " rows and ",
    " 家公司；": " companies after filtering;",
    "要求的指标编码：": "Required metric codes: ",
    "数据中缺失的编码：": "Missing codes: ",
    "数据中实际存在的编码：": "Codes present: ",
    "无（5 个编码都在）": "None (all 5 codes present)",
    "常见原因：89 家数据的「指标编码」列与标准编码不一致（如用了中文名），或最新报告期这一期缺少上述 5 个指标。": "Common causes: the metric-code column for the 89 companies does not match the standard codes (for example, Chinese names were used), or the latest period lacks the five metrics above.",
    "查看原始数值与得分明细": "View raw values and scores",
    "每家公司一个年度折线小图，按公司类型分组分节展示。": "One annual line chart per company, grouped by company type.",
    "当前筛选范围没有可绘制的数据。": "No plottable data in the current selection.",
    "规模与结构": "Scale and structure",
    "行业原保费收入": "industry Direct Premium Written",
    "原保费收入": "Direct Premium Written",
    "保费规模与同比增速": "Premium scale and year-on-year growth",
    "左：原保费收入规模与同比增速　右：车险 / 非车险占比与同比增速": "Left: Direct Premium Written scale and YoY growth   Right: motor / non-motor mix and YoY growth",
    "原保费收入规模与同比增速": "Direct Premium Written scale and YoY growth",
    "柱：年度原保费收入　折线：同比增速（右轴，%）": "Bars: annual Direct Premium Written   Line: YoY growth (right axis, %)",
    "车险 / 非车险占比与同比增速": "Motor / non-motor mix and YoY growth",
    "柱：100% 堆叠占比　折线：车险 / 非车险同比增速（右轴，%）": "Bars: 100% stacked mix   Lines: motor / non-motor YoY growth (right axis, %)",
    "原保费收入（柱）": "Direct Premium Written (bars)",
    "原保费收入同比增速": "Direct Premium Written YoY growth",
    "当年原保费收入": "Current-year Direct Premium Written",
    "上年原保费收入": "Prior-year Direct Premium Written",
    "占原保费收入": "Share of Direct Premium Written",
    "车险（占比）": "Motor (share)",
    "非车险（占比）": "Non-motor (share)",
    "保费规模与结构": "Premium scale and structure",
    "柱：车险 / 非车险金额　折线：同比增速（右轴，%）": "Bars: motor / non-motor premium   Line: YoY growth (right axis, %)",
    "柱：车险 / 非车险金额": "Bars: motor / non-motor premium",
    "车险（柱）": "Motor (bars)",
    "非车险（柱）": "Non-motor (bars)",
    "车险同比": "Motor YoY",
    "非车险同比": "Non-motor YoY",
    "合计同比": "Total YoY",
    "0% 基准线": "0% baseline",
    "基期（无同比）": "Base year (no YoY)",
    "同比不可比": "YoY not comparable",
    "市场份额与集中度": "Market share and concentration",
    "样本覆盖 ": "Sample coverage: ",
    "保费集中度：": "Premium concentration: ",
    "公司类别市场份额（": "Company category market share (",
    " 年）": ")",
    "公司类别金额对比（": "Company category amounts (",
    "按公司类别汇总（": "Aggregated by company category (",
    "饼图展示各指标正值占比，负值不计入占比。": "Pies show positive values only; negative values are excluded from shares.",
    "保费 / 净利润 / 承保利润（含亏损）": "Premium / net profit / underwriting profit (incl. losses)",
    "承保利润（含亏损）": "Underwriting profit (incl. losses)",
    "承保利润：": "Underwriting profit: ",
    "绝对值占比：": "Absolute-value share: ",
    "绝对值占比": "Absolute-value share",
    "利润面板以灰色零轴区分正值与负值。": "The profit panel uses a grey zero axis to separate positive and negative values.",
    "查看分类与公司明细": "View category and company detail",
    "承保利润 = 签单保费 ×（1 - 综合成本率）的测算值。": "Underwriting profit is estimated as signed premium × (1 − combined ratio).",
    "查看行业年度明细": "View annual industry detail",
    "年度汇总": "Annual summary",
    "公司级明细（上传数据）": "Company detail (uploaded data)",
    "数据不完整的年度：": "Years with incomplete data: ",
    "缺少年度累计": "missing year-to-date",
    "年度累计覆盖不足": "insufficient year-to-date coverage",
    "车险拆分覆盖不足": "insufficient motor split coverage",
    "数据不完整": "incomplete data",
    "检测到 ": "Detected ",
    " 条公司年度值疑似单位/量级异常，图表未自动改写原始数值；请核对明细。": " company-year values with suspected unit/scale anomalies; charts do not overwrite the source values. Please review the detail.",
    "偿付能力披露整体情况": "Solvency disclosure overview",
    "行业合计口径": "industry aggregate basis",
    "实际资本合计": "Total actual capital",
    "最低资本合计": "Total minimum capital",
    "核心资本占实际资本比例暂不可用": "Core capital / actual capital is not available",
    "查看合计口径公司与公式明细": "View aggregate companies and formulas",
    "综合 = Σ实际资本 ": "Combined = Σ actual capital ",
    " ÷ Σ最低资本 ": " ÷ Σ minimum capital ",
    "核心 = Σ核心资本 ": "Core = Σ core capital ",
    "核心资本占实际资本 ": "Core capital / actual capital ",
    "合计口径仅纳入同时具备相应资本与正的最低资本的公司；卡片中的比率不是各公司充足率的简单平均。": "The aggregate basis includes only companies with the relevant capital and positive minimum capital; the ratios are not simple averages of company ratios.",
    "公式：综合偿付能力充足率 = Σ所有公司实际资本 / Σ所有公司最低资本；核心偿付能力充足率 = Σ（核心一级资本 + 核心二级资本）/ Σ所有公司最低资本。监管口径下，核心资本对应核心一级与核心二级资本之和。": "Formula: combined solvency ratio = Σ actual capital / Σ minimum capital; core solvency ratio = Σ (core tier 1 + core tier 2 capital) / Σ minimum capital. Under the regulatory basis, core capital equals core tier 1 plus core tier 2 capital.",
    "综合成本率（%）": "Combined ratio (%)",
    "签单保费排名（1 = 最高）": "Signed premium rank (1 = highest)",
    "公司数（家）": "Company count",
    "低于纵轴下限": "Below y-axis lower bound",
    "高于纵轴上限": "Above y-axis upper bound",
    "显示范围": "Display range",
    "盈亏状态": "Profit / loss status",
    "全样本图": "Full sample",
    "局部样本放大": "Zoomed sample",
    "总保费同比增速": "Total premium growth",
    "全行业平均投资收益率": "Industry average return",
    "全行业平均投资收益率（%）": "Industry average return (%)",
    "全行业平均": "Industry average",
    "展开此模块": "Show module",
    "偿付能力充足率指标": "Solvency ratio metrics",
    "主要经营指标（财险）": "Key operating metrics (P&C)",
    "S02-实际资本明细表": "S02 – Actual capital detail",
    "近三年（综合）投资收益率": "Three-year (combined) investment return",
    "S05-最低资本表": "S05 – Minimum capital",
    "流动性风险监测指标": "Liquidity risk monitoring metrics",
    "纳入综合口径": "Included in combined basis",
    "纳入核心口径": "Included in core basis",
    "Yes数据": "Yes",
    "_得分": " score",
    "财险": "Property & casualty",
    "资本充足率": "Capital adequacy ratio",
    "资本": "Capital",
    "具体图表（全部展示）": "Charts (show all)",
    "前十大展示口径": "Top 10 grouping",
    "实际资本/注册资本": "Actual capital / registered capital",
    "核心资本/注册资本": "Core capital / registered capital",
    "认可资产规模": "Recognised asset scale",
    "签单保费排名": "Signed premium rank",
    "综合成本率与签单保费排名": "Combined ratio and signed premium rank",
    "有效样本": "Valid sample",
    "样本公司数": "Sample companies",
    "盈利能力": "Profitability",
    "资本实力": "Capital strength",
    "承保风控能力": "Underwriting risk control",
    "业务拓展": "Business expansion",
    "基期": "Base period",
    "同比基期（无上年数据）": "YoY base period (no prior-year data)",
    "同比类别": "YoY category",
    "同比增速": "YoY growth",
    "保费规模": "Premium scale",
    "保费收入": "Premium income",
    "利率风险": "Interest rate risk",
    "权益价格风险": "Equity price risk",
    "房地产价格风险": "Real estate price risk",
    "境外固定收益类资产价格风险": "Overseas fixed-income asset price risk",
    "境外权益类资产价格风险": "Overseas equity asset price risk",
    "汇率风险": "Foreign exchange risk",
    "利差风险": "Spread risk",
    "交易对手违约风险": "Counterparty default risk",
    "损失发生风险": "Loss occurrence risk",
    "退保风险": "Surrender risk",
    "费用风险": "Expense risk",
    "缺少可绘制的完整公司数据": "lacks complete company data for plotting",
    "缺少气泡图所需指标": "is missing metrics required for the bubble chart",
    "最新报告期缺少气泡图所需指标。": "The latest reporting period is missing metrics required for the bubble chart.",
    "最新报告期": "Latest reporting period",
    "计入核心一级资本": "Included in core tier 1 capital",
    "计入核心二级资本": "Included in core tier 2 capital",
    "计入附属一级资本": "Included in ancillary tier 1 capital",
    "计入附属二级资本": "Included in ancillary tier 2 capital",
    "核心一级资本": "Core tier 1 capital",
    "核心二级资本": "Core tier 2 capital",
    "附属一级资本": "Ancillary tier 1 capital",
    "附属二级资本": "Ancillary tier 2 capital",
    "实际资本": "Actual capital",
    "最低资本": "Minimum capital",
    "认可资产": "Recognised assets",
    "认可负债": "Recognised liabilities",
    "风险分散效应": "Diversification effect",
    "损失吸收效应": "Loss absorption effect",
    "保险风险（寿）": "Insurance risk (life)",
    "保险风险（非寿）": "Insurance risk (non-life)",
    "保险风险": "Insurance risk",
    "市场风险": "Market risk",
    "信用风险": "Credit risk",
    "综合偿付能力充足率": "Combined solvency ratio",
    "核心偿付能力充足率": "Core solvency ratio",
    "偿付能力": "Solvency",
    "总资产": "Total assets",
    "保费增速": "Premium growth",
    "签单保费": "Signed premium",
    "净利润率": "Net profit margin",
    "注册资本": "Registered capital",
    "报告期": "Reporting period",
    "年度": "Year",
    "数值": "Value",
    "单位": "Unit",
    "车险": "Motor",
    "非车险": "Non-motor",
    "合计": "Total",
    "保费": "Premium",
    "净利润": "Net profit",
    "承保利润": "Underwriting profit",
    "公司类别": "Company category",
    "来源": "Source",
    "数据来源": "Data source",
    "构成": "Component",
    "金额": "Amount",
    "占合计": "Share of total",
    "占比": "Share",
    "增长率": "Growth rate",
    "当年金额": "Current-year amount",
    "上年金额": "Prior-year amount",
    "基期年度": "Base year",
    "未拆分": "Unallocated",
    "监管下限": "Regulatory minimum",
    "已披露": "Disclosed",
    "未披露": "Not disclosed",
    "盈亏平衡": "Break-even",
    "盈利": "Profit",
    "亏损": "Loss",
    "其他": "Other",
    "未分类": "Unclassified",
}


def translate_text(text: str, language: str | None = None) -> str:
    """Translate a display string with exact and phrase-level lookup."""
    if not is_english(language) or not isinstance(text, str) or not text:
        return text
    if text in COMPANY_NAMES_EN:
        return COMPANY_NAMES_EN[text]
    if text in PHRASE_EN:
        return PHRASE_EN[text]
    if text in DEFAULT_ANALYSIS_EN:
        return DEFAULT_ANALYSIS_EN[text]
    if text in CHART_NAMES_EN:
        return CHART_NAMES_EN[text]
    if text in LEVEL_NAMES_EN:
        return LEVEL_NAMES_EN[text]
    if text in CATEGORY_NAMES_EN:
        return CATEGORY_NAMES_EN[text]
    if text in PERFORMANCE_NAMES_EN:
        return PERFORMANCE_NAMES_EN[text]
    if text in DISCLOSURE_NAMES_EN:
        return DISCLOSURE_NAMES_EN[text]
    if text in UNIT_NAMES_EN:
        return UNIT_NAMES_EN[text]
    if text in FIELD_NAMES_EN:
        return FIELD_NAMES_EN[text]
    value_unit = re.fullmatch(r"数值（(.+)）", text)
    if value_unit:
        return f"Value ({unit_name(value_unit.group(1), language)})"
    unit_suffix = re.fullmatch(r"(.+)（([^）]+)）", text)
    if unit_suffix and (
        unit_suffix.group(2) in UNIT_NAMES_EN
        or unit_suffix.group(2) in {"%", "％", "‰", "倍"}
    ):
        return (
            f"{translate_text(unit_suffix.group(1), language)}"
            f" ({unit_name(unit_suffix.group(2), language)})"
        )
    result = text
    # Titles embedded in HTML previously followed a different replacement
    # order from selectbox options. Build one combined glossary and always
    # replace the longest source phrase first, so complete chart names win over
    # shorter entries such as “保险服务业绩”, “构成” or “净利润”.
    combined_replacements: dict[str, str] = {}
    for mapping in (
        COMPANY_NAMES_EN,
        PHRASE_EN,
        DEFAULT_ANALYSIS_EN,
        CHART_NAMES_EN,
        LEVEL_NAMES_EN,
        FIELD_NAMES_EN,
        CATEGORY_NAMES_EN,
        PERFORMANCE_NAMES_EN,
        DISCLOSURE_NAMES_EN,
        UNIT_NAMES_EN,
    ):
        for source, target in mapping.items():
            combined_replacements.setdefault(source, target)
    for source in sorted(combined_replacements, key=len, reverse=True):
        if source and source in result:
            result = result.replace(source, combined_replacements[source])
    result = re.sub(
        r" · 第 (\d+)/(\d+) 组（(\d+) 家公司）",
        r" · Group \1/\2 (\3 companies)",
        result,
    )
    result = re.sub(r"（(\d+) 家公司）", r" (\1 companies)", result)
    result = re.sub(r"（(\d+) 家）", r" (\1 companies)", result)
    result = re.sub(r"数值（([^）]+)）", r"Value (\1)", result)
    result = result.replace("跨期趋势", " trend over periods")
    result = result.replace("公司跨期对标", " company benchmark")
    result = result.replace("公司年度走势", " annual trend")
    result = result.replace("（单位）", " (unit)")
    return result


def chart_name(name: str, language: str | None = None) -> str:
    if not is_english(language):
        return str(name)
    value = str(name or "")
    return CHART_NAMES_EN.get(value, LEVEL_NAMES_EN.get(value, translate_text(value, language)))


def level_name(name: str, language: str | None = None) -> str:
    if not is_english(language):
        return str(name)
    value = str(name or "")
    return LEVEL_NAMES_EN.get(value, translate_text(value, language))


def chart_kind_name(name: str, language: str | None = None) -> str:
    if not is_english(language):
        return str(name)
    value = str(name or "")
    return CHART_KIND_NAMES_EN.get(value, translate_text(value, language))


def category_name(name: str, language: str | None = None) -> str:
    if not is_english(language):
        return str(name)
    value = str(name or "")
    return CATEGORY_NAMES_EN.get(value, PERFORMANCE_NAMES_EN.get(value, translate_text(value, language)))


def translate_mapping(mapping: dict, language: str | None = None) -> dict:
    if not is_english(language):
        return dict(mapping)
    return {category_name(key, language): value for key, value in mapping.items()}


# ---------------------------------------------------------------------------
# DataFrame 展示
# ---------------------------------------------------------------------------
COLUMN_NAMES_EN: dict[str, str] = {
    "公司": "Company",
    "公司名称": "Company",
    "报告期": "Reporting period",
    "指标编码": "Metric code",
    "指标名称": "Metric",
    "数值": "Value",
    "单位": "Unit",
    "期间口径": "Period basis",
    "数据类型": "Data type",
    "同业分类": "Peer group",
    "公司类型": "Company type",
    "年度": "Year",
    "保费": "Premium",
    "净利润": "Net profit",
    "承保利润": "Underwriting profit",
    "保费占比": "Premium share",
    "净利润占比": "Net profit share",
    "承保利润占比": "Underwriting profit share",
    "车险": "Motor",
    "非车险": "Non-motor",
    "险种": "Line of business",
    "原保险保费收入": "Original premium income",
    "同比增速": "YoY growth",
    "基期年度": "Base year",
    "合计": "Total",
    "来源": "Source",
    "收入排名": "Revenue rank",
    "利润排名": "Profit rank",
    "收入": "Revenue",
    "利润": "Profit",
    "类别": "Category",
    "盈亏": "Profit / loss",
    "标签": "Label",
    "公司数": "Company count",
    "有效公司数": "Valid companies",
    "综合成本率": "Combined ratio",
    "签单保费排名": "Signed premium rank",
    "盈亏平衡": "Break-even",
    "保费单位": "Premium unit",
    "公司类别": "Company category",
    "类型": "Type",
    "承保利润测算": "Estimated underwriting profit",
    "综合成本率口径": "Combined ratio basis",
    "保费口径": "Premium basis",
    "综合成本率报告期": "Combined ratio period",
    "保费报告期": "Premium period",
    "车险占比": "Motor share",
    "异常数": "Anomalies",
    "完整": "Complete",
    "公司数（家）": "Company count",
}
COLUMN_NAMES_EN.update(FIELD_NAMES_EN)


def translate_dataframe(
    frame: pd.DataFrame,
    language: str | None = None,
    *,
    translate_values: bool = True,
) -> pd.DataFrame:
    """Return a display copy with English column names and known category values."""
    if not is_english(language) or not isinstance(frame, pd.DataFrame):
        return frame
    result = frame.copy()
    rename = {}
    for column in result.columns:
        text = str(column)
        if text in COLUMN_NAMES_EN:
            rename[column] = COLUMN_NAMES_EN[text]
        elif "（" in text or "(" in text:
            base = text.split("（")[0].split("(")[0]
            if base in COLUMN_NAMES_EN:
                suffix = text[len(base):]
                rename[column] = f"{COLUMN_NAMES_EN[base]}{suffix}"
        if column not in rename:
            translated_column = translate_text(text, language)
            if translated_column != text:
                rename[column] = translated_column
    result = result.rename(columns=rename)
    if translate_values and is_english(language):
        # Translate units inside parenthetical column suffixes, e.g. 车险（亿元）.
        unit_pattern = re.compile(r"[（(]([^）)]+)[）)]\s*$")
        result = result.rename(
            columns={
                column: unit_pattern.sub(
                    lambda match: f" ({unit_name(match.group(1), language)})",
                    str(column),
                )
                for column in result.columns
                if unit_pattern.search(str(column))
            }
        )
    if translate_values:
        for column in result.columns:
            if pd.api.types.is_string_dtype(
                result[column].dtype
            ) or pd.api.types.is_object_dtype(result[column].dtype):
                if str(column) in {"Company", "公司", "公司名称"}:
                    result[column] = result[column].map(
                        lambda value: (
                            company_name(value, language)
                            if isinstance(value, str)
                            else value
                        )
                    )
                    continue
                result[column] = result[column].map(
                    lambda value: (
                        translate_text(value, language)
                        if isinstance(value, str)
                        else value
                    )
                )
    return result


# ---------------------------------------------------------------------------
# Altair / Plotly 图表
# ---------------------------------------------------------------------------
def _field_display_name(field: str, language: str | None) -> str:
    if not is_english(language):
        return field
    text = str(field or "")
    if text in FIELD_NAMES_EN:
        return FIELD_NAMES_EN[text]
    return translate_text(text, language)


def _translate_value(value: Any, language: str | None) -> Any:
    if not is_english(language) or not isinstance(value, str):
        return value
    if value in COMPANY_NAMES_EN:
        return COMPANY_NAMES_EN[value]
    if value in DISCLOSURE_NAMES_EN:
        return DISCLOSURE_NAMES_EN[value]
    if value in CATEGORY_NAMES_EN:
        return CATEGORY_NAMES_EN[value]
    if value in PERFORMANCE_NAMES_EN:
        return PERFORMANCE_NAMES_EN[value]
    if value in UNIT_NAMES_EN:
        return UNIT_NAMES_EN[value]
    if value == "高于纵轴上限":
        return "Above upper range"
    if value == "低于纵轴下限":
        return "Below lower range"
    # Never run free-text phrase replacement over data values: company names
    # such as 国元农险 must remain unchanged.
    return value


def _translate_chart_node(node: Any, language: str | None, *, in_values: bool = False) -> Any:
    if isinstance(node, list):
        return [_translate_chart_node(item, language, in_values=in_values) for item in node]
    if not isinstance(node, dict):
        if isinstance(node, str) and in_values:
            return _translate_value(node, language)
        return node

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in {"field", "field2", "name", "repeat"}:
            result[key] = value
            continue
        if key in {"domain", "sort"} and isinstance(value, list):
            result[key] = [_translate_value(item, language) for item in value]
            continue
        if key in {"values", "datasets"}:
            result[key] = _translate_chart_node(value, language, in_values=True)
            continue
        if key in {"title", "labelExpr", "description"} and isinstance(value, str):
            result[key] = translate_text(value, language)
            continue
        if key in {"title", "labelExpr", "description"} and isinstance(value, dict):
            translated = _translate_chart_node(value, language)
            if isinstance(translated, dict) and isinstance(translated.get("text"), str):
                translated["text"] = translate_text(translated["text"], language)
            result[key] = translated
            continue
        if key == "tooltip" and isinstance(value, list):
            tooltips = []
            for item in value:
                if isinstance(item, dict):
                    item = deepcopy(item)
                    field = str(item.get("field", ""))
                    if field and "title" not in item:
                        item["title"] = _field_display_name(field, language)
                    else:
                        item = _translate_chart_node(item, language)
                    tooltips.append(item)
                elif isinstance(item, str) and ":" in item:
                    field = item.split(":", 1)[0]
                    tooltips.append(
                        {
                            "field": field,
                            "type": "nominal" if item.endswith(":N") else "quantitative",
                            "title": _field_display_name(field, language),
                        }
                    )
                else:
                    tooltips.append(item)
            result[key] = tooltips
            continue
        if key in {"axis", "legend", "header"} and isinstance(value, dict):
            translated = _translate_chart_node(value, language)
            if isinstance(translated, dict) and isinstance(translated.get("title"), str):
                translated["title"] = translate_text(translated["title"], language)
            result[key] = translated
            continue
        if key == "mark" and isinstance(value, dict):
            translated = _translate_chart_node(value, language)
            if isinstance(translated, dict) and isinstance(translated.get("text"), str):
                translated["text"] = translate_text(translated["text"], language)
            result[key] = translated
            continue
        result[key] = _translate_chart_node(value, language, in_values=in_values)

    # Give unlabelled encoding fields a readable title.
    if "field" in node and isinstance(node.get("field"), str) and "title" not in node:
        if "axis" not in node and "legend" not in node:
            field = str(node["field"])
            if field not in {"数值", "值"}:
                result["title"] = _field_display_name(field, language)
    return result


class _LocalizedChart:
    """Minimal chart object that exposes a translated Vega-Lite spec.

    Streamlit only needs to_dict() from the chart object. Returning the
    translated spec this way avoids reconstructing the Altair object graph,
    which can lose mark-level properties such as dy on layered charts.
    """

    def __init__(self, spec: dict[str, Any]) -> None:
        self._spec = spec

    def to_dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return deepcopy(self._spec)


def localize_chart(chart: Any, language: str | None = None) -> Any:
    """Return a chart object with English display titles and category values."""
    if not is_english(language) or chart is None:
        return chart
    try:
        spec = chart.to_dict()
        translated = _translate_chart_node(spec, language)
        return _LocalizedChart(translated)
    except Exception:
        return chart


def translate_hover_text(text: str, language: str | None = None) -> str:
    """Translate a hover template without touching company/category data."""
    if not is_english(language) or not isinstance(text, str):
        return text
    result = translate_text(text, language)
    for source in sorted(UNIT_NAMES_EN, key=len, reverse=True):
        if source and source in result:
            result = result.replace(source, UNIT_NAMES_EN[source])
    return result.replace("：", ": ")


def _translate_plotly_values(value: Any, language: str | None = None) -> Any:
    """Recursively translate Plotly table/customdata values for display."""
    if value is None:
        return ""
    if isinstance(value, str):
        if value.strip().lower() in {"none", "nan", "null", "<na>"}:
            return ""
        return translate_text(value, language)
    if isinstance(value, dict):
        return {
            key: _translate_plotly_values(item, language)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_translate_plotly_values(item, language) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (bytes, bytearray)):
        try:
            return _translate_plotly_values(value.tolist(), language)
        except Exception:
            return value
    return value


_PLOTLY_REPORT_PERIOD_RE = re.compile(
    r"^\s*(20\d{2})年(?:(?:\s*<br\s*/?>\s*|\s*)(\d{1,2})月)?\s*$",
    flags=re.IGNORECASE,
)


def _translate_plotly_axis_value(value: Any, language: str | None = None) -> Any:
    """Translate display values without turning year categories into date axes."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.lower() in {"none", "nan", "null", "<na>"}:
        return ""
    period_match = _PLOTLY_REPORT_PERIOD_RE.fullmatch(stripped)
    if period_match:
        year, month = period_match.groups()
        return f"{year}-{int(month):02d}" if month else f"{year}YE"
    return translate_text(value, language)


def _plotly_trace_axis_name(trace: Any, attribute: str) -> str:
    """Return Plotly layout axis name (xaxis/xaxis2/yaxis/...) for a trace."""
    reference = getattr(trace, f"{attribute}axis", None) or attribute
    suffix = str(reference)[1:] if str(reference).startswith(attribute) else ""
    return f"{attribute}axis{suffix}"


def _is_numeric_plotly_axis_sequence(values: Any) -> bool:
    """Return True when a Plotly x/y sequence contains only numeric values.

    English localisation must never rebuild numeric axes.  Reassigning a
    NumPy/Pandas-backed sequence as a Python list is usually harmless, but
    different Plotly versions can infer a categorical axis after that
    conversion.  Keeping numeric sequences byte-for-byte out of the
    translation path makes chart rendering consistent across computers.
    """
    if isinstance(values, (str, bytes, bytearray, dict)):
        return False
    try:
        raw_values = list(values)
    except TypeError:
        return False
    if not raw_values:
        return True
    for value in raw_values:
        if value is None:
            continue
        try:
            if bool(pd.isna(value)):
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, bool) or not isinstance(value, Number):
            return False
    return True


def localize_plotly(figure: Any, language: str | None = None) -> Any:
    """Translate Plotly titles, annotations, legend and trace labels in place."""
    if not is_english(language) or figure is None:
        return figure
    try:
        for annotation in list(getattr(figure.layout, "annotations", ()) or ()):
            if getattr(annotation, "text", None):
                annotation.text = translate_text(str(annotation.text), language)
            # A number of Step 7 bar charts anchor growth-rate labels to the
            # original Chinese company name.  The trace categories are
            # translated below, so the annotation coordinate must use the
            # same display value or Plotly creates a second category and the
            # labels appear bunched together away from their bars.
            for coordinate, reference_name in (("x", "xref"), ("y", "yref")):
                value = getattr(annotation, coordinate, None)
                reference = str(getattr(annotation, reference_name, "") or coordinate)
                if (
                    isinstance(value, str)
                    and reference != "paper"
                    and not reference.endswith(" domain")
                ):
                    setattr(
                        annotation,
                        coordinate,
                        _translate_plotly_axis_value(value, language),
                    )
        axis_names = [
            key for key in figure.layout
            if str(key).startswith("xaxis") or str(key).startswith("yaxis")
        ]
        for axis_name in axis_names:
            axis = getattr(figure.layout, axis_name, None)
            axis_title = getattr(getattr(axis, "title", None), "text", None) if axis is not None else None
            if axis_title not in (None, ""):
                cleaned_title = str(axis_title).strip()
                axis.title.text = (
                    ""
                    if cleaned_title.lower() in {"none", "nan", "null", "<na>"}
                    else translate_text(cleaned_title, language)
                )
            if axis is not None:
                for attribute in ("ticktext", "categoryarray"):
                    values = getattr(axis, attribute, None)
                    if values is not None:
                        setattr(
                            axis,
                            attribute,
                            [
                                ""
                                if value is None or (isinstance(value, str) and value.strip().lower() in {"none", "nan", "null", "<na>"})
                                else _translate_plotly_axis_value(value, language)
                                if isinstance(value, str)
                                else value
                                for value in list(values)
                            ],
                        )
        if getattr(figure.layout, "title", None) is not None:
            title = figure.layout.title
            if getattr(title, "text", None):
                title.text = translate_text(str(title.text), language)
        for trace in figure.data:
            for attribute in ("name", "labels", "text", "x", "y", "hovertext", "legendgroup"):
                values = getattr(trace, attribute, None)
                if values is None:
                    continue
                # Numeric x/y data drives the chart geometry and therefore
                # must remain completely outside the display-translation
                # layer.  Only textual categories such as company names and
                # report periods are localised below.
                if attribute in {"x", "y"} and _is_numeric_plotly_axis_sequence(values):
                    continue
                if isinstance(values, str):
                    is_period_axis = (
                        attribute in {"x", "y"}
                        and _PLOTLY_REPORT_PERIOD_RE.fullmatch(values.strip()) is not None
                    )
                    setattr(
                        trace,
                        attribute,
                        "" if values.strip().lower() in {"none", "nan", "null", "<na>"}
                        else _translate_plotly_axis_value(values, language)
                        if attribute in {"x", "y"}
                        else translate_text(values, language),
                    )
                    if is_period_axis:
                        axis = getattr(
                            figure.layout,
                            _plotly_trace_axis_name(trace, attribute),
                            None,
                        )
                        if axis is not None and getattr(axis, "type", None) != "multicategory":
                            axis.type = "category"
                elif hasattr(values, "__iter__"):
                    # Keep numerical gaps in x/y as real None values, but never
                    # render Python missing-value markers as visible chart text.
                    blank_missing = attribute in {"labels", "text", "hovertext"}
                    raw_values = list(values)
                    has_period_axis_values = attribute in {"x", "y"} and any(
                        isinstance(value, str)
                        and _PLOTLY_REPORT_PERIOD_RE.fullmatch(value.strip()) is not None
                        for value in raw_values
                    )
                    setattr(
                        trace,
                        attribute,
                        [
                            ""
                            if blank_missing and (
                                value is None
                                or (isinstance(value, str) and value.strip().lower() in {"none", "nan", "null", "<na>"})
                            )
                            else _translate_plotly_axis_value(value, language)
                            if attribute in {"x", "y"} and isinstance(value, str)
                            else translate_text(str(value), language)
                            if isinstance(value, str)
                            else value
                            for value in raw_values
                        ],
                    )
                    if has_period_axis_values:
                        axis = getattr(
                            figure.layout,
                            _plotly_trace_axis_name(trace, attribute),
                            None,
                        )
                        if axis is not None and getattr(axis, "type", None) != "multicategory":
                            axis.type = "category"
            # go.Table把表头和单元格放在专用对象中，不属于普通text/x/y属性。
            header = getattr(trace, "header", None)
            if header is not None and getattr(header, "values", None) is not None:
                header.values = _translate_plotly_values(header.values, language)
            cells = getattr(trace, "cells", None)
            if cells is not None and getattr(cells, "values", None) is not None:
                cells.values = _translate_plotly_values(cells.values, language)
            customdata = getattr(trace, "customdata", None)
            if customdata is not None:
                trace.customdata = _translate_plotly_values(customdata, language)
            hovertemplate = getattr(trace, "hovertemplate", None)
            if isinstance(hovertemplate, str) and hovertemplate:
                trace.hovertemplate = translate_hover_text(hovertemplate, language)

        # English legend labels are often much longer than their Chinese
        # counterparts. Reserve additional space and let Plotly wrap them
        # below the chart instead of overlapping the x-axis and subplots.
        legend_names = []
        for trace in figure.data:
            if getattr(trace, "showlegend", True) is False:
                continue
            name = getattr(trace, "name", None)
            if isinstance(name, str) and name and name.lower() != "none":
                legend_names.append(re.sub(r"<[^>]+>", " ", name).strip())
        legend_chars = sum(len(name) for name in legend_names)
        if legend_names and (legend_chars > 90 or max(map(len, legend_names)) > 34):
            current_height = getattr(figure.layout, "height", None) or 400
            margin = getattr(figure.layout, "margin", None)
            current_bottom = getattr(margin, "b", None) if margin is not None else None
            current_bottom = current_bottom or 0
            figure.update_layout(
                height=max(current_height, 500),
                margin=dict(b=max(current_bottom, 170)),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.22,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=9),
                ),
            )
    except Exception:
        return figure
    return figure


# ---------------------------------------------------------------------------
# 报告注释
# ---------------------------------------------------------------------------
def translate_default_analysis(text: str, language: str | None = None) -> str:
    if not is_english(language):
        return text
    return DEFAULT_ANALYSIS_EN.get(str(text).strip(), str(text))


def unit_name(unit: str, language: str | None = None) -> str:
    if not is_english(language):
        return str(unit)
    return UNIT_NAMES_EN.get(str(unit), str(unit))


# ---------------------------------------------------------------------------
# 新准则财务报告洞察平台专用词汇
# ---------------------------------------------------------------------------
# 这些词汇只改变展示文本。下拉框仍返回原始中文值，数据筛选、字段匹配、
# 公式和 Excel 模板结构不会因为语言切换而改变。
COMPANY_NAMES_EN.update(
    {
        "工银安盛": "ICBC-AXA Life",
        "农银人寿": "ABC Life",
        "建信人寿": "CCB Life",
        "中银三星": "BOC-Samsung Life",
        "交银人寿": "BOCOM MSIG Life",
        "中邮人寿": "China Post Life",
        "招商信诺": "Cigna & CMB Life",
        "中信保诚": "CITIC-Prudential Life",
        "中荷人寿": "Sino-Dutch Life",
        "恒安标准养老": "Heng An Standard Pension",
        "平安健康": "Ping An Health",
        "平安养老": "Ping An Annuity",
        "人保健康": "PICC Health",
        "太保健康": "CPIC Health",
        "太平养老": "China Taiping Pension",
        "泰康养老": "Taikang Pension",
        "平安人寿": "Ping An Life",
        "中国人寿": "China Life",
        "新华保险": "New China Life",
        "人保寿险": "PICC Life",
        "太平人寿": "Taiping Life",
        "友邦人寿": "AIA China",
        "阳光人寿": "Sunshine Life",
        "太保寿险": "CPIC Life",
        "泰康人寿": "Taikang Life",
        "复星保德信": "Fosun Prudential Life",
        "中英人寿": "Aviva-COFCO Life",
        "中意人寿": "Generali China Life",
        "同方全球": "Aegon THTF Life",
        "恒安标准": "Heng An Standard Life",
        "陆家嘴国泰": "Cathay Lujiazui Life",
        "东吴人寿": "Soochow Life",
        "瑞泰人寿": "RuiTai Life",
        "国富人寿": "Guofu Life",
        "东方嘉富人寿": "Oriental Jiafu Life",
        "财信吉祥人寿": "Caixin Jixiang Life",
    }
)

LEVEL_NAMES_EN.update(
    {
        "关键年报数据": "Key Annual Report Data",
        "关键披露信息": "Key Disclosures",
        "关键业绩指标": "Key Performance Indicators",
        "附录": "Appendix",
        "保险服务业绩": "Insurance Service Result",
        "投资服务业绩": "Investment Service Result",
        "综合收益": "Comprehensive Income",
        "资产": "Assets",
        "合同服务边际": "Contractual Service Margin",
        "净资产": "Net Assets",
        "新业务": "New Business",
    }
)

CHART_NAMES_EN.update(
    {
        "关键数据预览": "Key Data Overview",
        "净利润的贡献 - 保险服务业绩和投资服务业绩": "Net Profit Contribution - Insurance and Investment Service Results",
        "税前利润、税率及净利润": "Profit Before Tax, Tax Rate and Net Profit",
        "净利润(亏损)": "Net Profit (Loss)",
        "保险服务收入": "Insurance Service Revenue",
        "保险服务收入的构成 - 非PAA和PAA合同组": "Insurance Service Revenue Mix - Non-PAA and PAA Contract Groups",
        "保险服务收入的构成 - 非PAA合同组的收入构成": "Insurance Service Revenue Mix - Non-PAA Contract Groups",
        "保险服务费用": "Insurance Service Expenses",
        "保险服务费用的构成 - 非PAA合同组的费用构成": "Insurance Service Expense Mix - Non-PAA Contract Groups",
        "业务及管理费（新准则分类）": "Operating and Administrative Expenses (New-standard Classification)",
        "保险服务业绩": "Insurance Service Result",
        "当期保险服务业绩构成": "Current-period Insurance Service Result Mix",
        "上期保险服务业绩构成": "Prior-period Insurance Service Result Mix",
        "净投资回报": "Net Investment Return",
        "承保财务净损益": "Net Insurance Finance Result",
        "投资服务业绩": "Investment Service Result",
        "其他综合收益": "Other Comprehensive Income",
        "其他综合收益 - 资产负债匹配": "OCI - Asset-Liability Matching",
        "其他综合收益 - 当期综合收益变动情况": "OCI - Current-period Comprehensive Income Movement",
        "其他综合收益 - 上期综合收益变动情况": "OCI - Prior-period Comprehensive Income Movement",
        "综合收益": "Comprehensive Income",
        "总资产": "Total Assets",
        "IFRS9 资产端分类": "IFRS 9 Asset Classification",
        "CSM 余额": "CSM Balance",
        "CSM/BEL占比": "CSM / BEL Ratio",
        "CSM余额滚动表": "CSM Roll-forward",
        "按过渡期计量方法拆分CSM": "CSM by Transition Measurement Approach",
        "当期摊销前 CSM 变动项占比": "Current-period Pre-amortisation CSM Movements",
        "上期摊销前 CSM 变动项占比": "Prior-period Pre-amortisation CSM Movements",
        "CSM趋势(摊销比率/持续率）": "CSM Trend (Amortisation / Continuity Ratios)",
        "净资产": "Net Assets",
        "综合净资产": "Comprehensive Net Assets",
        "新业务CSM": "New Business CSM",
        "新业务LC": "New Business Loss Component",
        "新业务价值明细（利润率/亏损率/RA率)": "New Business Value Details (Margin / Loss / RA Ratios)",
        "新业务 IFRS 利润率": "New Business IFRS Margin",
        "折现率": "Discount Rates",
        "非金融风险调整置信水平": "Confidence Level for Non-financial Risk Adjustment",
        "未来合同服务边际摊销": "Expected Future CSM Release",
        "保险规模与盈利": "Insurance Scale and Profitability",
        "保险增长与质量": "Insurance Growth and Quality",
        "双引擎盈利": "Dual-engine Profitability",
        "资产负债匹配": "Asset-Liability Matching",
        "综合净资产-规模与价值": "Comprehensive Net Assets - Scale and Value",
        "综合净资产-资本积累与未赚利润储备": "Comprehensive Net Assets - Capital Accumulation and Unearned Profit Reserve",
        "股东回报": "Shareholder Return",
        "新业务质量": "New Business Quality",
        "保险服务业绩明细表": "Insurance Service Result Detail",
        "新业务信息表": "New Business Information",
        "净利润的贡献-保险服务业绩和投资服务业绩": "Net Profit Contribution - Insurance and Investment Service Results",
        "税前利润": "Profit Before Tax",
        "保险服务收入的构成-非PAA和PAA合同组": "Insurance Service Revenue Mix - Non-PAA and PAA Contract Groups",
        "保险服务收入的构成-非PAA合同组的收入构成": "Insurance Service Revenue Mix - Non-PAA Contract Groups",
        "保险服务费用构成": "Insurance Service Expense Mix",
        "最新年保险服务业绩构成": "Latest-year Insurance Service Result Mix",
        "上一年保险服务业绩构成": "Prior-year Insurance Service Result Mix",
        "最新年摊销前 CSM 变动项占比": "Latest-year Pre-amortisation CSM Movements",
        "上一年摊销前 CSM 变动项占比": "Prior-year Pre-amortisation CSM Movements",
        "CSM摊销比率": "CSM Amortisation Ratio",
        "CSM持续率": "CSM Continuity Ratio",
    }
)

CATEGORY_NAMES_EN.update(
    {
        "银行系": "Bank-affiliated",
        "养老": "Pension",
        "健康": "Health",
        "头部": "Leading",
        "外资系": "Foreign-invested",
        "中型": "Mid-sized",
        "小型": "Small",
        "股东权益变动表": "Statement of Changes in Equity",
        "合同服务边际": "Contractual Service Margin",
        "I17新业务表": "IFRS 17 New Business",
        "保险服务收入": "Insurance Service Revenue",
        "保险服务费用": "Insurance Service Expenses",
        "利润表": "Income Statement",
        "资产负债表": "Statement of Financial Position",
        "其他披露信息": "Other Disclosures",
        "业务及管理费": "Operating and Administrative Expenses",
        "保险合同负债": "Insurance Contract Liabilities",
        "利源分析": "Profit Source Analysis",
    }
)

UNIT_NAMES_EN.update(
    {
        "百亿元人民币": "RMB 10 bn",
        "十亿元人民币": "RMB bn",
        "亿元人民币": "RMB 100 mn",
        "百万元人民币": "RMB mn",
        "十万元人民币": "RMB 100k",
        "万元人民币": "RMB 10k",
        "人民币元": "RMB",
        "(百万)人民币": "RMB mn",
        "(亿元)人民币": "RMB 100 mn",
        "（百万）人民币": "RMB mn",
        "（亿元）人民币": "RMB 100 mn",
    }
)

FIELD_NAMES_EN.update(
    {
        "报告年份": "Reporting year",
        "报告月份": "Reporting month",
        "报告期间": "Reporting period",
        "字段名": "Metric",
        "字段类型": "Metric type",
        "期初股东权益": "Opening shareholders' equity",
        "期末股东权益": "Closing shareholders' equity",
        "股东权益合计": "Total shareholders' equity",
        "综合收益总额": "Total comprehensive income",
        "净利润": "Net profit",
        "其他综合收益": "Other comprehensive income",
        "股东权益分配": "Distributions to shareholders",
        "其他权益变动": "Other equity movements",
        "CSM期初余额": "Opening CSM balance",
        "CSM期末余额": "Closing CSM balance",
        "CSM余额": "CSM balance",
        "CSM余额区间": "CSM balance range",
        "CSM余额增长率": "CSM balance growth rate",
        "CSM余额增长率区间": "CSM balance growth-rate range",
        "新业务CSM（集团口径）": "New business CSM (group basis)",
        "新业务CSM（寿险+健康险）": "New business CSM (life and health)",
        "CSM计息": "CSM interest accretion",
        "CSM调整": "CSM adjustments",
        "CSM摊销": "CSM release",
        "CSM摊销比例": "CSM amortisation ratio",
        "CSM其他": "Other CSM movements",
        "综合净资产": "Comprehensive net assets",
        "新业务RA": "New business RA",
        "新业务亏损合同（LC）——非PAA": "New business loss component (non-PAA)",
        "新业务未来现金流入现值": "PV of new business future cash inflows",
        "新业务未来现金流入现值（盈利）": "PV of profitable new business future cash inflows",
        "新业务未来现金流入现值（亏损）": "PV of loss-making new business future cash inflows",
        "新业务保费收入": "New business premium income",
        "保险服务收入合计": "Total insurance service revenue",
        "未采用保费分配法计量的保险合同保险服务收入": "Insurance service revenue - non-PAA contracts",
        "采用保费分配法计量的保险合同保险服务收入": "Insurance service revenue - PAA contracts",
        "合同服务边际的摊销": "CSM release",
        "非金融风险调整的变动": "Change in non-financial risk adjustment",
        "预计当期发生的保险服务费用": "Expected current-period insurance service expenses",
        "与当期服务或过去服务相关得保费经验调整": "Premium experience adjustments related to current or past service",
        "其他收入调整": "Other revenue adjustments",
        "保险获取现金流的摊销（保险服务收入）": "Insurance acquisition cash-flow amortisation (revenue)",
        "保险服务费用合计": "Total insurance service expenses",
        "未采用保费分配法计量的保险合同保险服务费用": "Insurance service expenses - non-PAA contracts",
        "采用保费分配法计量的保险合同保险服务费用": "Insurance service expenses - PAA contracts",
        "保险获取现金流的摊销（保险服务费用）": "Insurance acquisition cash-flow amortisation (expenses)",
        "亏损部分的确认及转回": "Recognition and reversal of loss components",
        "当期发生的赔款及其他相关费用": "Claims and other related expenses incurred in the period",
        "已发生赔款负债相关的履约现金流量变动": "Changes in fulfilment cash flows for incurred-claims liabilities",
        "采用保费分配法计量的保险合同保险业绩": "Insurance service result - PAA contracts",
        "税前利润总额": "Profit before tax",
        "保险服务收入": "Insurance service revenue",
        "保险服务费用": "Insurance service expenses",
        "保险服务业绩": "Insurance service result",
        "分出保费的分摊": "Allocation of reinsurance premiums",
        "减 ：摊回保险服务费用": "Less: recovered insurance service expenses",
        "提取保费准备金": "Premium reserve provision",
        "保险利润": "Insurance profit",
        "银行业务利息净收入": "Net banking interest income",
        "非银行业务利息收入": "Non-banking interest income",
        "利息收入": "Interest income",
        "投资收益": "Investment income",
        "公允价值变动损益": "Fair value gains or losses",
        "汇兑损益": "Foreign exchange gains or losses",
        "承保财务损益": "Insurance finance result",
        "减 ：分出再保险财务损益": "Less: reinsurance finance result",
        "分出再保险财务损益": "Reinsurance finance result",
        "承保财务净损益": "Net insurance finance result",
        "利息支出": "Interest expense",
        "其他资产减值损失": "Other asset impairment losses",
        "信用减值损失": "Credit impairment losses",
        "投资利润": "Investment profit",
        "非保险业务手续费及佣金净收入": "Net fee and commission income from non-insurance business",
        "其他业务收入": "Other operating income",
        "资产处置损益": "Gains or losses on asset disposal",
        "其他收益": "Other income",
        "税金及附加": "Taxes and surcharges",
        "业务及管理费": "Operating and administrative expenses",
        "其他业务成本": "Other operating costs",
        "加 ：营业外收入": "Add: non-operating income",
        "减 ：营业外支出": "Less: non-operating expenses",
        "其他利润": "Other profit",
        "可转损益的保险合同金融变动": "Insurance contract finance changes recyclable to profit or loss",
        "可转损益的分出再保险合同金融变动": "Reinsurance contract finance changes recyclable to profit or loss",
        "可转损益的负债OCI": "Liability OCI recyclable to profit or loss",
        "FVOCI债券公允价值": "FVOCI bond fair value movement",
        "可转损益OCI合计": "Total recyclable OCI",
        "不可转损益的负债OCI": "Liability OCI not recyclable to profit or loss",
        "FVOCI股权": "FVOCI equity movement",
        "不可转损益OCI合计": "Total non-recyclable OCI",
        "再保净损益": "Net reinsurance result",
        "净投资回报": "Net investment return",
        "OCI其他": "Other OCI",
        "货币资金": "Cash and cash equivalents",
        "定期存款": "Term deposits",
        "现金及流动性工具": "Cash and liquidity instruments",
        "长期股权投资": "Long-term equity investments",
        "投资性房地产": "Investment property",
        "指定FVOCI": "Designated FVOCI",
        "总资产": "Total assets",
        "折现率假设": "Discount-rate assumptions",
        "非金融风险的置信水平": "Confidence level for non-financial risk adjustment",
        "1年及1年以内合同服务边际": "CSM due within one year",
        "1-5年合同服务边际": "CSM due in 1-5 years",
        "5-10年合同服务边际": "CSM due in 5-10 years",
        "10-20年合同服务边际": "CSM due in 10-20 years",
        "20年合同服务边际": "CSM due after 20 years",
        "获取费用": "Acquisition expenses",
        "维持费用": "Maintenance expenses",
        "非履约费用": "Non-attributable expenses",
        "职工薪酬": "Employee compensation",
        "物业及设备支出": "Property and equipment expenses",
        "业务投入及监管费用支出": "Business development and regulatory expenses",
        "行政办公支出": "Administrative office expenses",
        "其他支出": "Other expenses",
        "BEL期初余额": "Opening BEL balance",
        "BEL期末余额": "Closing BEL balance",
        "RA期初余额": "Opening RA balance",
        "RA期末余额": "Closing RA balance",
        "期初保险合同负债总额": "Opening insurance contract liabilities",
        "期末保险合同负债总额": "Closing insurance contract liabilities",
        "保险合同净负债余额": "Net insurance contract liability balance",
        "编号": "No.",
        "项目": "Item",
        "投资收益率": "Investment return",
        "综合偿付能力充足率": "Comprehensive solvency ratio",
        "手续费及佣金支出": "Fee and commission expenses",
        "养老金管理费收入": "Pension management fee income",
        "其他费用": "Other expenses",
        "保险服务利润率": "Insurance service margin",
        "投资服务利润率": "Investment service margin",
        "总资产增长率": "Total asset growth",
        "净资产增长率": "Net asset growth",
        "综合净资产增长率": "Comprehensive net asset growth",
        "CSM增长率": "CSM growth",
        "新业务CSM增长率": "New business CSM growth",
        "新业务IFRS利润率": "New Business IFRS Margin",
        "新业务IFRS利润率变动率": "Change in new business IFRS margin",
        "OCI错配率": "OCI mismatch ratio",
        "ROE净资产收益率": "Return on equity (ROE)",
        # Step 7 scatter axes and reference-table labels.
        "保险服务收入增长率": "Insurance Service Revenue Growth Rate",
        "保险服务利润率变动（百分点）": "Change in Insurance Service Margin (percentage points)",
        "净投资回报率": "Net Investment Return Ratio",
        "公司数量": "Number of Companies",
        "FVOCI占比": "FVOCI Share",
        "FVOCI变动": "FVOCI Movement",
        "负债OCI变动": "Liability OCI Movement",
        "资负匹配率": "Asset-Liability Matching Ratio",
        "负债OCI占比": "Liability OCI Share",
        "净资产变动明细表（I9切换后）": "Net Asset Movement Details (after I9 adjustment)",
        "序号": "No.",
        "其他变动": "Other Movements",
        "分析指标": "Analysis Metric",
        "项目名称": "Item",
        "获取费用均值": "Average Acquisition Expense Share",
        "维持费用均值": "Average Maintenance Expense Share",
        "非履约费用均值": "Average Non-attributable Expense Share",
        "保险获取现金流摊销": "Insurance Acquisition Cash-flow Amortisation",
        "亏损部分确认及转回": "Recognition and Reversal of Loss Components",
        "当期赔款及费用": "Claims and Expenses Incurred in the Period",
        "已发生赔款负债变动": "Change in Liability for Incurred Claims",
        "PAA合同收入": "PAA Contract Revenue",
        "非PAA合同收入": "Non-PAA Contract Revenue",
        "合同服务边际释放": "CSM Release",
        "非金融风险调整变动": "Change in Non-financial Risk Adjustment",
        "预期保险服务费用": "Expected Insurance Service Expenses",
        "未采用保费分配法的保险合同": "Insurance Contracts Not Measured under the PAA",
        "采用保费分配法的保险合同": "Insurance Contracts Measured under the PAA",
        "合同服务边际的释放": "Release of Contractual Service Margin",
        "预期当期发生的保险服务费用": "Expected Insurance Service Expenses for the Period",
        "保险获取现金流的摊销": "Amortisation of Insurance Acquisition Cash Flows",
        "亏损部分的确认及转回": "Recognition and Reversal of Loss Components",
        "当期发生的赔款及其他相关费用": "Claims and Other Related Expenses Incurred in the Period",
        "已发生赔款负债相关的履约现金流量变动": "Change in Fulfilment Cash Flows for Incurred Claims",
        "保险服务业绩（不含再保收支净额）": "Insurance Service Result (excluding net reinsurance result)",
        "CSM释放在保险服务业绩中占比": "CSM Release as a Share of Insurance Service Result",
        "集团/业务条线-汇总": "Group / Business-line Total",
        "综合净资产/总资产": "Comprehensive Net Assets / Total Assets",
        "展开导航栏": "Navigation",
        # Step 8 scatter axes. Exact metric-range entries prevent partial
        # translations such as “Insurance Service RevenueGrowth rate区间”.
        "保险服务收入区间": "Insurance Service Revenue Range",
        "保险服务收入增长率区间": "Insurance Service Revenue Growth-rate Range",
        "净投资回报区间": "Net Investment Return Range",
        "净投资回报增长率": "Net Investment Return Growth Rate",
        "净投资回报增长率区间": "Net Investment Return Growth-rate Range",
        "保险服务费用区间": "Insurance Service Expenses Range",
        "保险服务费用增长率": "Insurance Service Expenses Growth Rate",
        "保险服务费用增长率区间": "Insurance Service Expenses Growth-rate Range",
        "承保财务净损益区间": "Net Insurance Finance Result Range",
        "承保财务净损益增长率": "Net Insurance Finance Result Growth Rate",
        "承保财务净损益增长率区间": "Net Insurance Finance Result Growth-rate Range",
        "保险服务业绩区间": "Insurance Service Result Range",
        "保险服务业绩增长率": "Insurance Service Result Growth Rate",
        "保险服务业绩增长率区间": "Insurance Service Result Growth-rate Range",
        "投资利润区间": "Investment Profit Range",
        "投资利润增长率": "Investment Profit Growth Rate",
        "投资利润增长率区间": "Investment Profit Growth-rate Range",
        "净利润区间": "Net Profit Range",
        "净利润增长率": "Net Profit Growth Rate",
        "净利润增长率区间": "Net Profit Growth-rate Range",
        "税前利润区间": "Profit Before Tax Range",
        "税前利润增长率": "Profit Before Tax Growth Rate",
        "税前利润增长率区间": "Profit Before Tax Growth-rate Range",
        "其他综合收益区间": "Other Comprehensive Income Range",
        "其他综合收益增长率": "Other Comprehensive Income Growth Rate",
        "其他综合收益增长率区间": "Other Comprehensive Income Growth-rate Range",
        "综合收益总额区间": "Total Comprehensive Income Range",
        "综合收益总额增长率": "Total Comprehensive Income Growth Rate",
        "综合收益总额增长率区间": "Total Comprehensive Income Growth-rate Range",
        "CSM余额区间": "CSM balance range",
        "CSM余额增长率区间": "CSM balance growth-rate range",
        "净资产区间": "Net Assets Range",
        "净资产增长率区间": "Net Assets Growth-rate Range",
        "综合净资产区间": "Comprehensive Net Assets Range",
        "综合净资产增长率区间": "Comprehensive Net Assets Growth-rate Range",
        "新业务CSM区间": "New Business CSM Range",
        "新业务CSM增长率区间": "New Business CSM Growth-rate Range",
        "新业务LC金额": "New Business Loss Component Amount",
        "新业务LC增长率": "New Business Loss Component Growth Rate",
        "新业务LC增长率区间": "New Business Loss Component Growth-rate Range",
        "保险服务利润率区间": "Insurance Service Margin Range",
        "净投资回报率区间": "Net Investment Return Ratio Range",
        "AC（债权投资）": "AC (Debt Investments)",
        "FVOCI（其他债权投资）": "FVOCI (Other Debt Investments)",
        "FVTPL（交易性金融资产）": "FVTPL (Financial Assets Held for Trading)",
        "指定FVOCI（其他权益工具）": "Designated FVOCI (Other Equity Instruments)",
        "净资产变动值": "Net Asset Movement",
        "其他项": "Other Items",
        "新业务盈利合同(CSM)": "New Business Profitable Contracts (CSM)",
        "新业务亏损合同(LC)": "New Business Loss-making Contracts (LC)",
        "与当期服务或过去服务相关的保费经验调整": "Premium Experience Adjustments Related to Current or Past Service",
        "当期发生的赔款及费用": "Claims and Expenses Incurred in the Period",
        "标签大小": "Label Size",
        "柱子宽度": "Bar Width",
        "公司名称大小": "Company-name Size",
        "柱宽": "Bar Width",
        "字号": "Font Size",
        "平均净资产": "Average Net Assets",
        "FVOCI债券": "FVOCI Bonds",
        "税后利润": "Profit After Tax",
        "新业务未来现金流入现值": "Present Value of New Business Future Cash Inflows",
        "保险服务利润率 vs 净投资回报率": "Insurance Service Margin vs Net Investment Return Ratio",
        "债权投资（以摊余成本法计量）": "Debt Investments<br>(Measured at Amortised Cost)",
        "其他债权投资（以公允价值计量入其他综合收益）": "Other Debt Investments<br>(Measured at Fair Value Through OCI)",
        "交易性金融资产（以公允价值计量入损益）": "Financial Assets Held for Trading<br>(Measured at Fair Value Through Profit or Loss)",
        "其他权益工具投资（以公允价值计量入其他综合收益）": "Other Equity Instrument Investments<br>(Measured at Fair Value Through OCI)",
        "债权投资<br>（以摊余成本法计量）": "Debt Investments<br>(Measured at Amortised Cost)",
        "其他债权投资<br>（以公允价值计量入其他综合收益）": "Other Debt Investments<br>(Measured at Fair Value Through OCI)",
        "交易性金融资产<br>（以公允价值计量入损益）": "Financial Assets Held for Trading<br>(Measured at Fair Value Through Profit or Loss)",
        "其他权益工具投资<br>（以公允价值计量入其他综合收益）": "Other Equity Instrument Investments<br>(Measured at Fair Value Through OCI)",
        "新业务 CSM": "New Business CSM",
        "CSM 计息": "CSM Interest Accretion",
        "CSM 调整": "CSM Adjustments",
        "类别代表值": "Category Representative Value",
        "样本数量": "Sample Size",
        "异常值": "Outlier",
        "保险利润": "Insurance Profit",
        "投资利润": "Investment Profit",
        "利润构成": "Profit Composition",
        "收入构成": "Revenue Composition",
        "费用构成": "Expense Composition",
    }
)

PHRASE_EN.update(
    {
        "虚线：样本中位数": "Dashed lines: sample medians",
        "虚线：零轴": "Dashed lines: zero axes",
        "虚线：Y＝－X": "Dashed line: Y = -X",
        "虚线：Y=X": "Dashed line: Y = X",
        "（远期）": " (forward)",
        "远期": "forward",
        "一键显示全部 (打印/导出)": "Show all (print/export)",
        "各公司平均占比情况": "Average Share by Company",
        "各公司平均占比": "Average Share across Companies",
        "样本均值": "Sample Mean",
        "样本中位数": "Sample Median",
        "分布数据明细": "Distribution Details",
        "分布 -": " Distribution -",
        "（无公司）": " (no companies)",
        "无对应数据": "No corresponding data",
        "无有效数据": "No valid data",
        "保险增长质量": "Insurance Growth and Quality",
        "综合净资产-过去利润与未来利润": "Comprehensive Net Assets - Accumulated and Future Profits",
        "类别代表值统一采用中位数。": "Category representative values use the median.",
        "异常值剔除明细": "Outlier Exclusions",
        "当前图参数设置": "Current Chart Settings",
        "参数设置": "Settings",
        "剔除异常值": "Exclude Outliers",
        "主要集中在": "is primarily concentrated in",
        "（中位数）": " (Median)",
        "中位数": "Median",
        "平均值": "Average",
        "均值": "Mean",
        "占比": "Share",
        "构成": "Composition",
        "变动": "Change",
        "变化": "Change",
        "区间": "Range",
        "分布": "Distribution",
        "样本": "Sample",
        "单位：百分比 (%)，顶部数字为总费用（亿元）": "Unit: percentage (%); top labels show total expenses (RMB 100 mn)",
        "单位：百分比 (%)": "Unit: percentage (%)",
        # Step 7 HTML table headers. These are kept as complete phrases so the
        # line-break markup and the preferred capitalisation remain intact.
        "净资产<br>%变化": "Net Assets<br>% Change",
        "净利润<br>%变化": "Net Profit<br>% Change",
        "CSM<br>%变化": "CSM<br>% Change",
        "NB CSM<br>%变化": "NB CSM<br>% Change",
        "保险服务收入<br>%变化": "Insurance Service Revenue<br>% Change",
        "保险合同净负债余额<br>%变化": "Net Insurance Contract Liability<br>% Change",
        "%变化": "% Change",
        "新准则财务报告洞察平台": "New Accounting Standards Financial Reporting Insights Platform",
        "公司级对标报告": "Company Benchmarking Report",
        "行业分类统计分析": "Industry Segmentation Analysis",
        "行业统计分析": "Industry Analysis",
        "自定义对标分析": "Custom Benchmarking Analysis",
        "当前身份": "Current role",
        "欢迎使用": "Welcome to ",
        "退出登录": "Log out",
        "访问权限": "Access role",
        "普通用户": "Standard user",
        "项目组成员": "Project team member",
        "安全验证": "Security verification",
        "请输入内部安全码": "Enter the internal access code",
        "选择您将使用的AI": "Select an AI provider",
        "请填写您使用AI的API Key": "Enter your AI API key",
        "自定义私有化节点": "Custom private endpoint",
        "指定模型版本": "Model name",
        "启 动 系 统": "Launch System",
        "系统版本": "System version",
        "数据源选择": "Data source",
        "直接引用集成后的数据": "Use integrated data",
        "上传集成表 Excel": "Upload integrated Excel workbook",
        "上传行业集成目标表": "Upload industry integrated data",
        "请先完成数据集成或上传目标底稿。": "Complete data integration or upload the target workbook first.",
        "图表类型": "Chart type",
        "簇状柱状图": "Clustered bar chart",
        "堆积柱状图": "Stacked bar chart",
        "折线对比图": "Line comparison chart",
        "饼图": "Pie chart",
        "内外环结构对比图": "Nested-donut comparison",
        "散点图": "Scatter plot",
        "核心配置面板": "Core Settings",
        "选择公司": "Select companies",
        "选择展示公司": "Select company",
        "选择对比公司": "Select peer companies",
        "选择报告期间": "Select reporting periods",
        "选择年份": "Select years",
        "选择构成指标": "Select composition metrics",
        "选择堆积指标": "Select stacked metrics",
        "选择显示指标": "Select metric",
        "显示数据标签": "Show data labels",
        "显示柱状图数据标签": "Show bar labels",
        "显示利润标签": "Show profit labels",
        "显示占比百分比标签": "Show percentage labels",
        "显示摊销累积比例": "Show cumulative release percentage",
        "显示数值": "Show values",
        "显示标签": "Show labels",
        "小数位数": "Decimal places",
        "数值单位换算": "Unit conversion",
        "开启透明背景模式": "Transparent background",
        "平均值线": "Mean line",
        "布局视角": "Layout view",
        "以公司为横轴": "Companies on the x-axis",
        "以期间为横轴": "Periods on the x-axis",
        "以年份为横轴": "Years on the x-axis",
        "数据模式": "Data mode",
        "单指标直显": "Single metric",
        "自定义公式运算": "Custom formula",
        "堆积模式": "Stacking mode",
        "单指标 / 公式": "Single metric / formula",
        "多指标占比": "Multi-metric share",
        "散点图模式": "Scatter mode",
        "单期指标模式": "Single-period metrics",
        "跨期公式模式": "Cross-period formulas",
        "按公司类型快速选择": "Quick-select by company type",
        "不按公司类型筛选": "No company-type filter",
        "全部类别": "All categories",
        "按类别筛选指标": "Filter metrics by category",
        "变量 A": "Variable A",
        "变量 B": "Variable B",
        "自定义公式": "Custom formula",
        "查看底层数据明细": "View underlying data",
        "自定义图例标签与颜色": "Custom legend labels and colours",
        "显示名称": "Display name",
        "公司报告导航": "Company Report Navigation",
        "一级模块": "Level-one module",
        "二级模块": "Level-two module",
        "具体图表": "Chart",
        "全部展示": "Show all",
        "一键显示全部": "Show all for print/export",
        "公司级图表设置与图片覆盖": "Company Chart Settings and Image Overrides",
        "公司内容分析与注释输入": "Company Analysis and Notes",
        "使用默认注释表": "Use default notes template",
        "内置默认注释表加载成功": "Built-in notes template loaded.",
        "使用默认坐标轴刻度表": "Use default axis-scale template",
        "清除刻度配置（恢复自动计算）": "Clear scale settings (restore automatic calculation)",
        "上传自定义坐标轴刻度表": "Upload a custom axis-scale workbook",
        "上传 Excel 分析注释表": "Upload analysis notes workbook",
        "自定义注释表上传成功": "Custom notes workbook uploaded.",
        "内置默认注释表从云端加载成功": "Built-in notes template loaded from the cloud.",
        "上传 Excel": "Upload Excel",
        "本期": "Current period",
        "对比期": "Comparison period",
        "展示公司": "Companies",
        "显示单位": "Display unit",
        "特定追踪": "Highlight company",
        "一键AI分析": "One-click AI commentary",
        "图表展示顺序依据": "Chart sort metric",
        "排序方向": "Sort direction",
        "降序 (从大到小)": "Descending (high to low)",
        "升序 (从小到大)": "Ascending (low to high)",
        "默认（总资产 降序）": "Default (total assets, descending)",
        "手动上传图片": "Manual image upload",
        "拖入截图文件": "Drop image files here",
        "各公司平均占比情况": "Average company shares",
        "注释": "Note",
        "单位": "Unit",
        "百分比": "Percentage",
        "百万元人民币": "RMB mn",
        "行业分析注释输入": "Industry Analysis Notes",
        "行业分析配置": "Industry Analysis Settings",
        "使用默认坐标轴刻度表": "Use default axis-scale template",
        "选择公司类型（可多选）": "Select company types",
        "同类型公司展示顺序": "Company order within each type",
        "排序依据字段": "Sort metric",
        "公司类型显示顺序": "Company-type display order",
        "具体图表（全部展示）": "Charts (show all)",
        "没有有效数据": "No valid data.",
        "无法计算行业平均构成": "Unable to calculate the industry average mix.",
        "无法计算行业平均费用构成": "Unable to calculate the industry average expense mix.",
        "无法计算行业平均利润构成": "Unable to calculate the industry average profit mix.",
        "无法计算行业平均资产构成": "Unable to calculate the industry average asset mix.",
        "请先在 Step 6 完成数据集成。": "Complete data integration in Step 6 first.",
        "暂无数据，请检查筛选条件。": "No data. Check the filters.",
        "暂无可用的指标字段。": "No metric fields are available.",
        "报告顺序由【模块ID】的先后顺序决定，请先在上方传入有模块ID的注释表文件。": "Report order follows the Module ID sequence. Upload a notes workbook containing Module IDs first.",
        "年份数量不足，至少需要两个年份。": "At least two reporting years are required.",
        "请先加载包含层级信息的注释表": "Load a notes workbook containing hierarchy information first.",
        "请先上传包含层级信息的注释表": "Upload a notes workbook containing hierarchy information first.",
        "请选择要查看的行业分析模块": "Select an industry analysis module.",
        "该分类下没有二级子模块": "No level-two modules are available in this category.",
        "该分类下暂无图表": "No charts are available in this category.",
        "气泡大小由": "Bubble size represents ",
        "决定": "",
        "仅表达相对规模": "relative scale only",
        "自动生成失败": "Automatic generation failed",
        "家上升": " companies increased",
        "家下降": " companies decreased",
        "家公司上升": " companies increased",
        "家公司下降": " companies decreased",
        "均值为": "average: ",
        "均值约": "average: ",
        "占比最高": "has the highest share",
        "增幅最大": "recorded the largest increase",
        "降幅最大": "recorded the largest decrease",
        "暂无": "No ",
        "数据": "data",
    }
)

DEFAULT_ANALYSIS_EN.update(
    {
        "净利润 = 保险利润+投资利润+其他利润（主要包括其他业务收入、营业外收支和所得税费用等）。": "Net profit equals insurance profit plus investment profit and other profit, mainly including other operating income, non-operating items and income tax expense.",
        "保险服务业绩=保险服务收入–保险服务费用。": "Insurance service result equals insurance service revenue less insurance service expenses.",
        "净投资回报=利息收入+投资收益+公允价值变动+汇兑损益-利息支出-其他资产减值损失 - 信用减值损失。": "Net investment return equals interest income, investment income, fair-value movements and foreign-exchange gains or losses, less interest expense and impairment losses.",
        "承保财务净损益 = 承保财务损益 - 分出再保险财务损益。": "Net insurance finance result equals insurance finance result less reinsurance finance result.",
        "投资利润 = 净投资回报 – 承保财务净损益。": "Investment profit equals net investment return less the net insurance finance result.",
        "综合收益总额 = 净利润+其他综合收益。": "Total comprehensive income equals net profit plus other comprehensive income.",
        "新业务IFRS利润率=(NBCSM–NBLC)/所有新业务未来现金流流入现值。": "New business IFRS margin equals (NB CSM - NB LC) divided by the present value of all new business future cash inflows.",
        "2025年和2024年收入构成比例基本稳定": "The revenue mix was broadly stable between 2025 and 2024.",
        "从长期险的收入构成来看，预期保险服务费用和合同服务边际释放为主要收入来源。": "For long-duration business, expected insurance service expenses and CSM release are the main sources of revenue.",
        "从长期险的费用构成来看，当期发生的赔款及费用和保险获取现金流的摊销为主要费用来源。": "For long-duration business, incurred claims and expenses and the amortisation of insurance acquisition cash flows are the main expense components.",
        "过渡日前的保险合同CSM余额占比逐年下降，但采用修正追溯法计量的合同的CSM余额占比目前仍居首位。": "The share of pre-transition insurance-contract CSM has declined over time, while contracts measured under the modified retrospective approach still account for the largest share.",
        "新业务CSM利润率=新业务CSM/新业务未来现金流入的折现值；\n新业务LC亏损率=新业务LC/新业务未来现金流入的折现值；\n新业务RA率=新业务RA/新业务未来现金流入的折现值。": "New business CSM margin, LC loss ratio and RA ratio are calculated against the present value of new business future cash inflows.",
    }
)

# Include target-specific field names in translated tables.
COLUMN_NAMES_EN.update(FIELD_NAMES_EN)


# ---------------------------------------------------------------------------
# 可维护的 Excel 翻译词典
# ---------------------------------------------------------------------------
TRANSLATION_WORKBOOK_FILENAME = "中英文翻译词典.xlsx"
TRANSLATION_WORKBOOK_SHEET = "翻译词典"
EXCEL_TRANSLATIONS_EN: dict[str, str] = {}


def load_translation_workbook(workbook_path: str | Path | None = None) -> int:
    """Load user-maintained translations and apply them as global overrides.

    The Python dictionaries remain a safe fallback when the workbook is absent,
    unreadable or contains an incomplete row. A valid enabled Excel row updates
    every built-in dictionary that already owns the same Chinese source string;
    a new source string is added to the general phrase dictionary.
    """
    path = Path(workbook_path) if workbook_path else (
        Path(__file__).resolve().parent / "templates" / TRANSLATION_WORKBOOK_FILENAME
    )
    if not path.is_file():
        return 0

    try:
        frame = pd.read_excel(
            path,
            sheet_name=TRANSLATION_WORKBOOK_SHEET,
            dtype=str,
            keep_default_na=False,
        )
    except Exception:
        return 0

    required_columns = {"中文原文", "英文译文", "Excel覆盖启用"}
    if not required_columns.issubset(frame.columns):
        return 0

    target_mappings = (
        COMPANY_NAMES_EN,
        PHRASE_EN,
        DEFAULT_ANALYSIS_EN,
        CHART_NAMES_EN,
        LEVEL_NAMES_EN,
        CATEGORY_NAMES_EN,
        PERFORMANCE_NAMES_EN,
        DISCLOSURE_NAMES_EN,
        UNIT_NAMES_EN,
        FIELD_NAMES_EN,
        COLUMN_NAMES_EN,
        CHART_KIND_NAMES_EN,
    )
    disabled_values = {"否", "no", "false", "0", "停用", "disabled"}
    loaded = 0

    for _, row in frame.iterrows():
        # Leading/trailing spaces are meaningful for several phrase fragments
        # (for example "（中位数）" -> " (Median)"). Preserve them exactly;
        # only use stripped copies to decide whether the cells are empty.
        source = str(row.get("中文原文", ""))
        target = str(row.get("英文译文", ""))
        enabled = str(row.get("Excel覆盖启用", "是")).strip().lower()
        if not source.strip() or not target.strip() or enabled in disabled_values:
            continue

        EXCEL_TRANSLATIONS_EN[source] = target
        matched_existing_dictionary = False
        for mapping in target_mappings:
            if source in mapping:
                mapping[source] = target
                matched_existing_dictionary = True
        if not matched_existing_dictionary:
            PHRASE_EN[source] = target
        loaded += 1

    return loaded


TRANSLATION_WORKBOOK_LOADED_ROWS = load_translation_workbook()


# Preserve the reference implementation and add reporting-period patterns used
# by the annual-report platform.
_translate_text_base = translate_text


def _has_streamlit_context() -> bool:
    """Return True only while the module is running inside a Streamlit session."""
    if st is None:
        return False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        try:
            return get_script_run_ctx(suppress_warning=True) is not None
        except TypeError:  # Older Streamlit releases do not expose this option.
            return get_script_run_ctx() is not None
    except Exception:
        return False


def _session_mapping(key: str) -> dict[str, str]:
    if not _has_streamlit_context():
        return {}
    try:
        value = st.session_state.get(key)
        if not isinstance(value, dict):
            value = {}
            st.session_state[key] = value
        return value
    except Exception:
        return {}


def _is_ai_translation_candidate(source: str, translated: str) -> bool:
    """Accept visible labels and report narratives, but never page code."""
    if not source or not translated or not re.search(r"[\u4e00-\u9fff]", translated):
        return False
    if len(source) > AI_TRANSLATION_MAX_ITEM_CHARS:
        return False
    lowered = source.lower()
    if any(
        token in lowered
        for token in (
            "<style",
            "<script",
            "data:image",
            "@media",
            "javascript:",
            "function(",
        )
    ):
        return False
    # Line breaks are intentionally allowed: Step 7/8 analysis paragraphs are
    # often stored in Excel with Alt+Enter. A single HTML line break is also
    # common in headers, while other markup remains excluded.
    markup_removed = re.sub(r"<br\s*/?>", "", source, flags=re.IGNORECASE)
    if "<" in markup_removed or ">" in markup_removed:
        return False
    # A CSS declaration can survive tag splitting as plain text. Do not queue
    # it even if a Chinese font name or comment is present.
    if "{" in source and "}" in source:
        return False
    return True


def _record_untranslated_label(source: str, translated: str) -> None:
    if not _is_ai_translation_candidate(source, translated):
        return
    pending = _session_mapping(AI_TRANSLATION_PENDING_KEY)
    if pending is not None:
        pending[source] = translated


def _apply_ai_translation_cache(text: str) -> str:
    """Apply user-approved AI translations inside plain text or HTML tables."""
    result = text
    for source, target in sorted(
        _session_mapping(AI_TRANSLATION_CACHE_KEY).items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if source and source in result and isinstance(target, str):
            result = result.replace(source, target)
    return result


def _record_untranslated_fragments(source: str, translated: str) -> None:
    """Queue visible HTML text nodes individually instead of sending page code."""
    if "<" not in translated:
        _record_untranslated_label(source, translated)
        return
    visible_html = re.sub(
        r"<(style|script)\b[^>]*>.*?</\1\s*>",
        "",
        translated,
        flags=re.IGNORECASE | re.DOTALL,
    )
    visible_html = re.sub(r"<!--.*?-->", "", visible_html, flags=re.DOTALL)
    for part in re.split(r"<[^>]+>", visible_html):
        fragment = html.unescape(part).strip()
        if fragment:
            _record_untranslated_label(fragment, fragment)


def _normalise_english_units(text: str) -> str:
    """Repair legacy mixed unit strings such as '十亿元RMB'."""
    replacements = {
        "百亿元RMB": "RMB 10 bn",
        "十亿元RMB": "RMB bn",
        "亿元RMB": "RMB 100 mn",
        "百万元RMB": "RMB mn",
        "十万元RMB": "RMB 100k",
        "万元RMB": "RMB 10k",
    }
    result = text
    for source, target in replacements.items():
        result = result.replace(source, target)
    result = result.replace("人民币", "RMB")
    result = re.sub(r"(?i)\bRMB\s*RMB\b", "RMB", result)
    result = re.sub(r"(?i)\bUnit\s*[：:]\s*", "Unit: ", result)
    return result


def translate_text(text: str, language: str | None = None) -> str:
    if is_english(language) and isinstance(text, str):
        duration_years = re.fullmatch(r"(\d{1,2})年", text.strip())
        if duration_years:
            return f"{duration_years.group(1)} years"
    result = _translate_text_base(text, language)
    if not is_english(language) or not isinstance(result, str):
        return result
    result = re.sub(r"(20\d{2})年<br>?(\d{1,2})月", r"\1-\2", result)
    result = re.sub(r"(20\d{2})年(\d{1,2})月", r"\1-\2", result)
    result = re.sub(r"(20\d{2})年", r"\1", result)
    result = _normalise_english_units(result)
    result = re.sub(r"(\d+)\s*家", r"\1 companies", result)
    result = result.replace("（", " (").replace("）", ")")
    result = re.sub(r"\s+\)", ")", result)
    if re.search(r"[\u4e00-\u9fff]", result):
        cached = _session_mapping(AI_TRANSLATION_CACHE_KEY).get(text)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
    result = _apply_ai_translation_cache(result)
    if re.search(r"[\u4e00-\u9fff]", result):
        _record_untranslated_fragments(text, result)
    return result


def _select_ai_translation_batch(items: dict[str, str]) -> dict[str, str]:
    """Prioritise narratives, then fill the request with shorter labels."""
    indexed_items = list(enumerate(items.items()))
    indexed_items.sort(
        key=lambda entry: (
            0
            if "\n" in entry[1][0]
            or "\n" in entry[1][1]
            or len(entry[1][0]) > 240
            or len(entry[1][1]) > 240
            else 1,
            entry[0],
        )
    )
    selected: dict[str, str] = {}
    selected_chars = 0
    for _, (source, current) in indexed_items:
        item_chars = len(source) + len(current)
        if len(selected) >= AI_TRANSLATION_MAX_ITEMS:
            break
        if selected and selected_chars + item_chars > AI_TRANSLATION_MAX_BATCH_CHARS:
            continue
        selected[source] = current
        selected_chars += item_chars
    return selected


class AIResponseFormatError(RuntimeError):
    """Raised when an AI gateway returns a non-compatible response."""


def _ai_content_to_text(content: Any) -> str:
    """Normalise message content returned by OpenAI-compatible SDKs."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"].strip()
        if isinstance(content.get("content"), str):
            return content["content"].strip()
    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(getattr(item, "text", None), str):
                parts.append(item.text)
        return "".join(parts).strip()
    return str(content).strip()


def _looks_like_network_intercept(text: str) -> bool:
    lowered = text.lstrip().lower()
    markers = (
        "<html",
        "<!doctype html",
        "access denied",
        "request blocked",
        "web filter",
        "proxy authentication required",
        "forbidden by policy",
    )
    return any(marker in lowered for marker in markers)


def extract_ai_response_text(response: Any) -> str:
    """Extract text from standard, dict, Responses-API or raw-text results.

    Some corporate gateways and older compatibility libraries return a plain
    string or dictionary instead of the OpenAI SDK's ChatCompletion object.
    Accept safe compatible forms and turn proxy/firewall pages into a clear
    diagnostic instead of leaking an ``'str' object has no attribute
    'choices'`` exception to the user.
    """
    if response is None:
        raise AIResponseFormatError("AI 接口没有返回内容。")

    if isinstance(response, str):
        text = response.strip()
        if not text:
            raise AIResponseFormatError("AI 接口返回了空字符串。")
        if _looks_like_network_intercept(text):
            raise AIResponseFormatError(
                "公司网络代理或防火墙返回了拦截页面，请联系 IT 放行当前 AI 接口域名。"
            )
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return text
        if isinstance(parsed, dict) and any(
            key in parsed for key in ("choices", "output_text", "output", "error")
        ):
            return extract_ai_response_text(parsed)
        # A translation request may legitimately return the requested JSON
        # mapping as the message body itself.
        return text

    if isinstance(response, dict):
        error = response.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message") or error.get("code") or str(error)
            else:
                message = str(error)
            raise AIResponseFormatError(f"AI 接口返回错误：{message}")
        output_text = response.get("output_text")
        if output_text not in (None, ""):
            return _ai_content_to_text(output_text)
        choices = response.get("choices")
        if isinstance(choices, (list, tuple)) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message", first)
                content = message.get("content") if isinstance(message, dict) else message
                text = _ai_content_to_text(content)
                if text:
                    return text
        output = response.get("output")
        if isinstance(output, (list, tuple)):
            text = _ai_content_to_text(output)
            if text:
                return text

    output_text = getattr(response, "output_text", None)
    if output_text not in (None, ""):
        return _ai_content_to_text(output_text)

    choices = getattr(response, "choices", None)
    if isinstance(choices, (list, tuple)) and choices:
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message", first)
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        text = _ai_content_to_text(content)
        if text:
            return text

    response_type = type(response).__name__
    raise AIResponseFormatError(
        f"AI 接口返回格式不兼容（类型：{response_type}）。请核对 openai 版本、接口地址和公司代理设置。"
    )


def translate_pending_labels_with_ai(
    items: dict[str, str],
    api_key: str,
    base_url: str,
    model_name: str,
) -> dict[str, str]:
    """Translate selected unresolved labels and report narratives with the LLM."""
    if not api_key.strip():
        raise ValueError("请先在登录页配置 API Key。")
    selected = _select_ai_translation_batch(items)
    if not selected:
        return {}

    from openai import OpenAI

    client = OpenAI(api_key=api_key.strip(), base_url=base_url.strip() or None)
    payload = [
        {"source": source, "current_translation": current}
        for source, current in selected.items()
    ]
    prompt = (
        "You translate display labels and narrative analysis paragraphs for an IFRS 17 "
        "insurance financial-reporting platform. Complete the English translation of "
        "every Chinese fragment; do not leave mixed Chinese-English wording. Preserve "
        "numbers, abbreviations (CSM, NB CSM, IFRS, RMB), punctuation, placeholders, "
        "paragraph line breaks and <br> tags. Use concise professional financial English. "
        "Return only one valid JSON "
        "object whose keys are the original source strings and whose values are the "
        "finished English labels or paragraphs.\n\nItems:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    response = client.chat.completions.create(
        model=model_name.strip() or "deepseek-flash",
        messages=[
            {"role": "system", "content": "Return only valid JSON. Do not add Markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    content = extract_ai_response_text(response)
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("AI 返回内容不是有效的翻译字典。")
    return {
        source: str(parsed[source]).strip()
        for source in selected
        if source in parsed and isinstance(parsed[source], str) and str(parsed[source]).strip()
    }


def translate_all_pending_labels_with_ai(
    items: dict[str, str],
    api_key: str,
    base_url: str,
    model_name: str,
    on_batch: Any = None,
) -> dict[str, str]:
    """Translate every queued item through safe bounded API batches.

    The 80-item/30,000-character request limits are intentionally retained so
    that the model can return reliable JSON and the API request does not exceed
    its context window.  The caller only clicks once; this helper keeps sending
    batches until the queue present at click time has been completed.
    """
    remaining = dict(items)
    completed_all: dict[str, str] = {}
    total = len(remaining)
    batch_number = 0

    while remaining:
        selected = _select_ai_translation_batch(remaining)
        if not selected:
            raise ValueError("剩余内容无法组成有效的 AI 翻译批次。")

        completed = translate_pending_labels_with_ai(
            remaining,
            api_key,
            base_url,
            model_name,
        )
        completed = {
            source: translation
            for source, translation in completed.items()
            if source in selected and isinstance(translation, str) and translation.strip()
        }
        if not completed:
            raise ValueError("AI 本批次未返回可用翻译，已停止后续批次。")

        batch_number += 1
        completed_all.update(completed)
        for source in completed:
            remaining.pop(source, None)

        if callable(on_batch):
            on_batch(
                dict(completed),
                len(completed_all),
                total,
                batch_number,
            )

    return completed_all


def _translate_option(value: Any, original_format=None, language: str | None = None) -> str:
    rendered = original_format(value) if original_format else value
    return translate_text(str(rendered), language)


def option_formatter():
    """Return a language-stable formatter for widgets created in this run."""
    language = get_language()
    return lambda value: _translate_option(value, language=language)


def _normalise_multiselect_values(
    values: Any,
    options: Any,
    original_format=None,
) -> list[Any]:
    """Map stale translated widget values back to their canonical raw options."""
    if values is None:
        return []
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        source_values = [values]
    else:
        source_values = list(values)
    option_values = list(options or [])
    normalised: list[Any] = []
    for value in source_values:
        matched = False
        for option in option_values:
            try:
                if value == option:
                    canonical = option
                    matched = True
                    break
            except Exception:
                pass
            try:
                rendered = original_format(option) if original_format else option
            except Exception:
                rendered = option
            candidates = {
                str(rendered),
                translate_text(str(rendered), LANG_EN),
            }
            if str(value) in candidates:
                canonical = option
                matched = True
                break
        if matched and canonical not in normalised:
            normalised.append(canonical)
    return normalised


class _LocalizedStreamlitProxy:
    """Translate Streamlit display arguments while preserving raw values."""

    _TEXT_METHODS = {
        "markdown", "caption", "title", "header", "subheader", "info",
        "warning", "error", "success", "toast", "text", "write",
    }
    _WIDGET_METHODS = {
        "button", "download_button", "file_uploader", "toggle", "checkbox",
        "text_input", "text_area", "number_input", "date_input", "time_input",
        "slider", "color_picker", "form_submit_button", "page_link",
    }
    _OPTION_METHODS = {"selectbox", "radio", "multiselect", "select_slider", "segmented_control"}

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> Any:
        target = getattr(object.__getattribute__(self, "_target"), name)
        if not callable(target):
            return target

        if name == "set_page_config":
            def page_config(*args: Any, **kwargs: Any) -> Any:
                return target(*args, **kwargs)
            return page_config

        if name in self._TEXT_METHODS:
            def text_call(*args: Any, **kwargs: Any) -> Any:
                if not is_english():
                    return target(*args, **kwargs)
                converted = []
                for value in args:
                    if isinstance(value, str):
                        converted.append(translate_text(value))
                    elif isinstance(value, pd.DataFrame):
                        converted.append(translate_dataframe(value))
                    else:
                        converted.append(value)
                return target(*converted, **kwargs)
            return text_call

        if name in self._WIDGET_METHODS:
            def widget_call(*args: Any, **kwargs: Any) -> Any:
                if not is_english():
                    return target(*args, **kwargs)
                converted = list(args)
                if converted and isinstance(converted[0], str):
                    converted[0] = translate_text(converted[0])
                elif isinstance(kwargs.get("label"), str):
                    kwargs["label"] = translate_text(kwargs["label"])
                for key in ("help", "placeholder"):
                    if isinstance(kwargs.get(key), str):
                        kwargs[key] = translate_text(kwargs[key])
                return target(*converted, **kwargs)
            return widget_call

        if name in self._OPTION_METHODS:
            def option_call(*args: Any, **kwargs: Any) -> Any:
                converted = list(args)
                original_format = kwargs.get("format_func")

                # Old app versions could persist translated multiselect values
                # (for example "Leading") even though the canonical option is
                # Chinese ("头部"). Normalise both the explicit default and the
                # keyed Streamlit state before widget validation runs.
                if name == "multiselect":
                    raw_options = (
                        converted[1]
                        if len(converted) > 1
                        else kwargs.get("options", [])
                    )
                    if "default" in kwargs:
                        kwargs["default"] = _normalise_multiselect_values(
                            kwargs.get("default"), raw_options, original_format
                        )
                    elif len(converted) > 2:
                        converted[2] = _normalise_multiselect_values(
                            converted[2], raw_options, original_format
                        )
                    widget_key = kwargs.get("key")
                    session_state = getattr(
                        object.__getattribute__(self, "_target"),
                        "session_state",
                        None,
                    )
                    if widget_key and session_state is not None:
                        try:
                            if widget_key in session_state:
                                current = session_state[widget_key]
                                canonical = _normalise_multiselect_values(
                                    current, raw_options, original_format
                                )
                                if canonical != current:
                                    session_state[widget_key] = canonical
                        except Exception:
                            pass

                if not is_english():
                    return target(*converted, **kwargs)
                if converted and isinstance(converted[0], str):
                    converted[0] = translate_text(converted[0])
                elif isinstance(kwargs.get("label"), str):
                    kwargs["label"] = translate_text(kwargs["label"])
                active_language = get_language()
                kwargs["format_func"] = lambda value: _translate_option(
                    value, original_format, active_language
                )
                for key in ("help", "placeholder"):
                    if isinstance(kwargs.get(key), str):
                        kwargs[key] = translate_text(kwargs[key])
                return target(*converted, **kwargs)
            return option_call

        if name == "tabs":
            def tabs_call(labels: Any, *args: Any, **kwargs: Any) -> Any:
                source_labels = [str(label) for label in labels]
                if is_english():
                    labels = [translate_text(label) for label in source_labels]
                else:
                    labels = source_labels

                # Stateful tabs store the displayed label. When the language changes,
                # map the old English/Chinese label to the same canonical Step number
                # before recreating the widget, so Step 7/8 does not jump to Step 6.
                tab_key = kwargs.get("key")
                session_state = getattr(
                    object.__getattribute__(self, "_target"),
                    "session_state",
                    None,
                )
                if tab_key and session_state is not None:
                    try:
                        current = session_state.get(tab_key)
                        if current and current not in labels:
                            step_match = re.search(r"Step\s*(\d+)", str(current), re.IGNORECASE)
                            if step_match:
                                step_token = step_match.group(1)
                                mapped = next(
                                    (
                                        label for label in labels
                                        if re.search(
                                            rf"Step\s*{re.escape(step_token)}\b",
                                            str(label),
                                            re.IGNORECASE,
                                        )
                                    ),
                                    None,
                                )
                                if mapped:
                                    session_state[tab_key] = mapped
                    except Exception:
                        pass

                try:
                    return target(labels, *args, **kwargs)
                except TypeError as exc:
                    # Compatibility fallback for older Streamlit releases that do
                    # not yet support stateful tabs.
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    fallback_kwargs = dict(kwargs)
                    for option in ("key", "default", "on_change", "args", "kwargs"):
                        fallback_kwargs.pop(option, None)
                    return target(labels, *args, **fallback_kwargs)
            return tabs_call

        if name in {"expander", "popover", "status"}:
            def container_call(*args: Any, **kwargs: Any) -> Any:
                converted = list(args)
                if is_english() and converted and isinstance(converted[0], str):
                    converted[0] = translate_text(converted[0])
                return target(*converted, **kwargs)
            return container_call

        if name in {"dataframe", "table"}:
            def dataframe_call(data: Any, *args: Any, **kwargs: Any) -> Any:
                if is_english() and isinstance(data, pd.DataFrame):
                    data = translate_dataframe(data)
                return target(data, *args, **kwargs)
            return dataframe_call

        if name == "plotly_chart":
            def plotly_call(figure: Any, *args: Any, **kwargs: Any) -> Any:
                if is_english():
                    try:
                        figure = localize_plotly(deepcopy(figure))
                    except Exception:
                        pass
                return target(figure, *args, **kwargs)
            return plotly_call

        if name == "metric":
            def metric_call(*args: Any, **kwargs: Any) -> Any:
                if not is_english():
                    return target(*args, **kwargs)
                converted = [translate_text(value) if isinstance(value, str) else value for value in args]
                for key in ("label", "value", "delta", "help"):
                    if isinstance(kwargs.get(key), str):
                        kwargs[key] = translate_text(kwargs[key])
                return target(*converted, **kwargs)
            return metric_call

        if name == "image":
            def image_call(*args: Any, **kwargs: Any) -> Any:
                if is_english() and isinstance(kwargs.get("caption"), str):
                    kwargs["caption"] = translate_text(kwargs["caption"])
                return target(*args, **kwargs)
            return image_call

        return target


localized_st = _LocalizedStreamlitProxy(st) if st is not None else None


def render_language_switch() -> None:
    """Render a clear, persistent language selector in the signed-in header."""
    if st is None:
        return
    current = language_label()
    if LANGUAGE_DISPLAY_KEY not in st.session_state:
        st.session_state[LANGUAGE_DISPLAY_KEY] = current
    st.selectbox(
        "🌐 Language / 语言",
        list(LANGUAGE_OPTIONS),
        key=LANGUAGE_DISPLAY_KEY,
        on_change=sync_language_from_display_control,
    )
    pending = _session_mapping(AI_TRANSLATION_PENDING_KEY)
    if is_english() and pending:
        with st.popover(f"✨ AI补全未翻译内容 ({len(pending)})"):
            st.caption(
                "本地字典仍是首选。只有点击下面按钮后，列表中的未翻译短标签和"
                "分析段落才会发送到登录时配置的 AI 接口。一次点击会自动分批"
                "处理当前全部内容，每批最多 80 条，以避免接口超限或 JSON 返回不完整。"
            )
            preview = list(_select_ai_translation_batch(pending))[:12]
            st.write(preview)
            if len(pending) > len(preview):
                st.caption(f"另有 {len(pending) - len(preview)} 条未显示。")
            if st.button("调用 AI 全部补全", key="i18n_ai_translate_button", type="primary"):
                api_key = str(st.session_state.get("api_key", ""))
                base_url = str(st.session_state.get("base_url", "https://api.deepseek.com"))
                model_name = str(st.session_state.get("model_name", "deepseek-flash"))
                if not api_key.strip():
                    st.warning("请先在登录页填写 API Key，再使用 AI 补全。")
                else:
                    progress_state = {"count": 0, "batches": 0, "total": len(pending)}
                    progress_bar = st.progress(0.0)
                    progress_text = st.empty()
                    try:
                        cache = _session_mapping(AI_TRANSLATION_CACHE_KEY)

                        def _save_completed_batch(
                            completed_batch: dict[str, str],
                            completed_count: int,
                            total_count: int,
                            batch_number: int,
                        ) -> None:
                            # Persist every successful batch immediately. If a
                            # later API request fails, earlier translations stay
                            # available and do not need to be requested again.
                            cache.update(completed_batch)
                            for source in completed_batch:
                                pending.pop(source, None)
                            progress_state.update(
                                count=completed_count,
                                batches=batch_number,
                                total=total_count,
                            )
                            progress_bar.progress(
                                min(completed_count / max(total_count, 1), 1.0)
                            )
                            progress_text.caption(
                                f"已完成 {completed_count}/{total_count} 条（第 {batch_number} 批）。"
                            )

                        with st.spinner("正在分批补全全部未翻译标签和分析段落…"):
                            completed = translate_all_pending_labels_with_ai(
                                dict(pending),
                                api_key,
                                base_url,
                                model_name,
                                on_batch=_save_completed_batch,
                            )
                        progress_bar.empty()
                        progress_text.empty()
                        # Do not call st.rerun() here. The language switch is rendered
                        # before the workflow tabs and uploaders; an immediate rerun at
                        # this point prevents those widgets from appearing in the run,
                        # so Streamlit may discard their state and return to Step 6.
                        # The updated cache is available immediately to the Step 6-8
                        # content that renders later in this same run.
                        st.success(
                            f"已自动完成 {len(completed)} 条翻译，共 "
                            f"{progress_state['batches']} 批；本页内容将直接使用翻译结果。"
                        )
                    except Exception as exc:
                        progress_bar.empty()
                        progress_text.empty()
                        if progress_state["count"]:
                            st.warning(
                                f"前 {progress_state['count']} 条已保存；后续批次可稍后继续补全。"
                            )
                        st.error(f"AI 补全失败：{exc}")
