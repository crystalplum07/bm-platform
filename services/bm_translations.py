"""bm-platform 专属中英展示层：静态字典 + Streamlit 渲染挂钩 + AI 兜底翻译。

设计要点
--------
1. 不修改用户提供的 ``services/report_i18n.py``，本模块在导入时把 bm-platform
   专属字典合并注入其字典，并包装其 ``translate_text`` 作为唯一的翻译入口。
2. 通过包装 ``st.*`` 显示/控件函数与 ``st.plotly_chart``，让 app.py 与
   step7.py 的所有界面文案、图表标题/轴/图例/悬停提示自动走翻译层，
   无需逐条改写 5600 行代码；控件选项只改显示名（format_func），不改返回值，
   因此所有以中文字符串做条件判断的业务逻辑保持原样。
3. 字典未命中时，若英文模式 + 侧边栏 AI 开关开启 + 有 API Key，则在页面
   渲染结束后批量调用一次 LLM 翻译并缓存，再自动重跑一次；否则静默回退中文。
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from services import report_i18n as i18n

ROOT = Path(__file__).resolve().parents[1]
AI_CACHE_FILE = ROOT / "i18n_ai_cache.json"
AI_TOGGLE_KEY = "bm_ai_translate_enabled"
AI_BATCH_SIZE = 200
AI_TIMEOUT = 30

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_PERIOD_RE = re.compile(r"^\s*(\d{4})\s*年(?:\s*(\d{1,2})\s*月)?\s*$")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_COMPANY_SUFFIXES = ("财险", "产险", "寿险", "人寿", "保险", "农险", "再保险", "相互", "自保", "集团", "股份")

_SCOPE = {"active": True}
_installed = False
_orig_translate_text = None
_memory_cache: dict[str, str] = {}
_memory_misses: set[str] = set()
_memory_attempted: set[str] = set()
_file_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 1. bm-platform 专属字典
# ---------------------------------------------------------------------------
# 整串精确匹配：控件标签、选项、按钮、表头、状态提示。短词只放在这里，
# 避免像短语字典那样被当作子串替换而破坏数据字段名。
BM_EXACT_EN: dict[str, str] = {
    # ---- app.py 登录页 / 外壳 ----
    "新准则财务报告洞察平台": "IFRS Financial Reporting Insights Platform",
    "访问权限": "Access role",
    "普通用户": "Standard user",
    "项目组成员": "Project member",
    "安全验证": "Security code",
    "请输入内部安全码": "Enter the internal security code",
    "选择您将使用的AI": "Select your AI provider",
    "自定义私有化节点": "Custom private endpoint",
    "RPC 接口地址": "RPC endpoint",
    "指定模型版本": "Model version",
    "请填写您使用AI的API Key": "Your AI API key",
    "如何获取API key?": "How do I get an API key?",
    "启 动 系 统": "L A U N C H",
    "❌ 拒绝访问：普通用户安全码错误": "❌ Access denied: invalid standard-user security code",
    "❌ 拒绝访问：项目组成员安全码错误": "❌ Access denied: invalid project-member security code",
    "退出登录": "Log out",
    "🔒 您当前仅拥有数据可视化与报告生成模块的访问权限。": "🔒 You have access to visualisation and report generation only.",
    " 📊 Step 6 ／ 自定义对标分析 ": " 📊 Step 6 / Custom Benchmarking ",
    " 🖼️ Step 7 ／ 公司级对标报告 ": " 🖼️ Step 7 / Company Benchmarking Report ",
    " 📈 Step 8 ／ 行业分类统计分析 ": " 📈 Step 8 / Industry Analysis ",
    "### 📊 自定义对标分析": "### 📊 Custom Benchmarking",
    # ---- app.py Step6 控件 ----
    "数据源选择": "Data source",
    "直接引用集成后的数据": "Use integrated data",
    "上传集成表 Excel": "Upload integrated Excel",
    "上传行业集成目标表": "Upload industry integrated workbook",
    "💡 请先完成数据集成或上传目标底稿。": "💡 Complete data integration or upload a workbook first.",
    "🛠️ 核心配置面板": "🛠️ Chart configuration",
    "📈 1. 图表类型": "📈 1. Chart type",
    "簇状柱状图": "Clustered bar",
    "堆积柱状图": "Stacked bar",
    "折线对比图": "Line comparison",
    "饼图": "Pie chart",
    "内外环结构对比图": "Inner/outer ring comparison",
    "散点图": "Scatter plot",
    "散点图模式": "Scatter mode",
    "单期指标模式": "Single-period metric",
    "跨期公式模式": "Cross-period formula",
    "X轴跨期指标(便捷)": "X cross-period metric (quick)",
    "Y轴跨期指标(便捷)": "Y cross-period metric (quick)",
    "↧ 填入 X/Y 公式": "↧ Fill X/Y formulas",
    "X轴字段(便捷)": "X field (quick)",
    "Y轴字段(便捷)": "Y field (quick)",
    "✏️ X轴公式（支持 [字段] 与 [字段@报告期间]）": "✏️ X formula ([field] or [field@period])",
    "✏️ Y轴公式（支持 [字段] 与 [字段@报告期间]）": "✏️ Y formula ([field] or [field@period])",
    "X轴显示名称": "X axis label",
    "Y轴显示名称": "Y axis label",
    "🏗️ 选择公司": "🏗️ Select companies",
    "📅 选择报告期间": "📅 Select reporting periods",
    "📅 选择年份": "📅 Select years",
    "🎯 选择构成指标": "🎯 Select component metrics",
    "🏗️ 选择展示公司": "🏗️ Select display company",
    "堆积模式": "Stacked mode",
    "单指标 / 公式": "Single metric / formula",
    "多指标占比": "Multi-metric share",
    "🗂️ 按类别筛选指标": "🗂️ Filter metrics by category",
    "全部类别": "All categories",
    "🎯 选择堆积指标": "🎯 Select stacked metrics",
    "数据模式": "Data mode",
    "单指标直显": "Direct metric",
    "自定义公式运算": "Custom formula",
    "🎯 选择显示指标": "🎯 Select display metric",
    "变量 A": "Variable A",
    "变量 B": "Variable B",
    "无": "None",
    "✏️ 自定义公式 (使用 A 和 B)": "✏️ Custom formula (use A and B)",
    "🏢 按公司类型快速选择": "🏢 Quick select by company type",
    "不按公司类型筛选": "No company-type filter",
    "🏗️ 选择对比公司": "🏗️ Select peer companies",
    "🔍 布局视角": "🔍 Layout",
    "以公司为横轴": "Companies on x-axis",
    "以期间为横轴": "Periods on x-axis",
    "以年份为横轴": "Years on x-axis",
    "结构视角": "Structure view",
    "散点视角": "Scatter view",
    "🔢 小数位数": "🔢 Decimal places",
    "✅ 显示数据标签": "✅ Show data labels",
    "原始数值": "Raw values",
    "百分比(%)": "Percentage (%)",
    "📏 X轴单位": "📏 X unit",
    "📏 Y轴单位": "📏 Y unit",
    "单位": "Unit",
    "📏 数值单位换算": "📏 Value unit conversion",
    "📝 Y轴单位显示修改": "📝 Y unit label",
    "🌈 开启透明背景模式": "🌈 Transparent background",
    "平均值线": "Average line",
    "基准线颜色": "Baseline colour",
    "#### 🎨 自定义图例标签与颜色": "#### 🎨 Legend labels and colours",
    "显示名称": "Display name",
    "选择颜色": "Pick colour",
    "📄 查看底层数据明细": "📄 View underlying data",
    "🎨 查看 KPMG 官方色卡": "🎨 KPMG official colour palette",
    "未检测到 KPMG_CATEGORIES 色卡定义。": "No KPMG_CATEGORIES palette definition found.",
    "X轴字段": "X field",
    "Y轴字段": "Y field",
    "高级公式模式": "Advanced formula mode",
    "X轴公式": "X formula",
    "Y轴公式": "Y formula",
    "先选择字段；如需运算，开启高级公式，用 [字段名] 引用指标。": "Select fields first; for calculations enable advanced formulas and reference metrics with [field].",
    "暂无可用的指标字段。": "No metric fields available.",
    "公式为空": "Formula is empty",
    "❌ 散点图数据获取失败：": "❌ Failed to load scatter data: ",
    "散点图暂无可用数据，请检查公式、公司或报告期间。": "No scatter data available; check formulas, companies or periods.",
    "散点图暂无可用数据，请检查字段、公式、公司或年份。": "No scatter data available; check fields, formulas, companies or years.",
    "暂无数据，请检查筛选条件。": "No data; check the filters.",
    "环形图对比需要至少两个报告期间的数据。": "The ring comparison needs at least two reporting periods.",
    "环形图对比需要至少两年的数据。": "The ring comparison needs at least two years.",
    # ---- step7.py 侧边栏 / 控件 ----
    "展开导航栏": "Expand navigation",
    "本期": "Current period",
    "对比期": "Comparison period",
    "请输入安全码...": "Enter security code...",
    "使用默认注释表": "Use default notes workbook",
    "上传 Excel": "Upload Excel",
    "公司报告导航": "Company Report Navigation",
    "📁 一级模块": "📁 Level 1 module",
    "🖨️ 一键显示全部 (打印/导出)": "🖨️ Show all (print/export)",
    "具体图表": "Charts",
    "📂 二级模块": "📂 Level 2 module",
    "全部": "All",
    "⚙️ 公司级图表设置与图片覆盖": "⚙️ Company chart settings and image overrides",
    "公司类型": "Company type",
    "展示公司": "Companies",
    "显示单位": "Display unit",
    "十亿元": "RMB bn",
    "亿元": "RMB 100 mn",
    "百万元": "RMB mn",
    "十万元": "RMB 100k",
    "特定追踪": "Track company",
    "一键AI分析": "One-click AI commentary",
    "📊 图表展示顺序依据": "📊 Chart sort metric",
    "默认（总资产 降序）": "Default (Total assets, descending)",
    "排序方向": "Sort direction",
    "降序 (从大到小) ⬇️": "Descending ⬇️",
    "升序 (从小到大) ⬆️": "Ascending ⬆️",
    "📸 手动上传图片（png或jpg）": "📸 Upload images (PNG/JPG)",
    "拖入截图文件": "Drop screenshot files",
    "不匹配": "No match",
    "跳过": "Skip",
    "📥公司内容分析与注释输入": "📥 Company analysis and note inputs",
    "获取官方注释表模板": "Download official notes template",
    "需要安全码验证": "Security code required",
    "🔓验证下载": "🔓 Verify and download",
    "🔓点击下载（已自动填充分析内容）": "🔓 Download (analysis pre-filled)",
    "🖨️ 导出竖版 A4 PDF": "🖨️ Export portrait A4 PDF",
    "🖨️ 导出横版 16:9 PDF": "🖨️ Export landscape 16:9 PDF",
    "竖版适合文字多的页面，横版适合宽图表。勾选\"背景图形\"以保留颜色。": "Portrait suits text-heavy pages, landscape suits wide charts. Enable background graphics to keep colours.",
    "⚠️ 请先在 Step 6 完成数据集成。": "⚠️ Complete data integration in Step 6 first.",
    "✅ 验证成功，分析内容已自动填充，请点击下方按钮下载": "✅ Verified. Analysis content is filled in; click the button below to download.",
    "❌ 文件获取失败": "❌ Could not retrieve the file",
    "❌ 安全码错误": "❌ Incorrect security code",
    "✅ 内置默认注释表加载成功": "✅ Built-in default notes workbook loaded",
    "💡 请上传包含【图片文件名】【模块ID】【一级分类】【二级分类】【对应图表名称】【分析内容】【注释内容】的 Excel": "💡 Upload an Excel containing image file name, module ID, level 1/2 category, chart name, analysis and notes.",
    "⚠️ 请先加载包含层级信息的注释表": "⚠️ Load a notes workbook with hierarchy information first.",
    "⚠️ 报告顺序由【模块ID】的先后顺序决定，请先在上方传入有模块ID的注释表文件。": "⚠️ Report order follows the module ID sequence; upload a notes workbook with module IDs above.",
    "显示数据标签": "Show data labels",
    "显示柱状图数据标签": "Show bar data labels",
    "显示标签": "Show labels",
    "显示数值": "Show values",
    "显示占比百分比标签": "Show percentage labels",
    "显示利润标签": "Show profit labels",
    "标签大小": "Label size",
    "标签字号": "Label font size",
    "文字大小": "Font size",
    "字号": "Font size",
    "公司名称大小": "Company label size",
    "公司名字号": "Company label size",
    "公司字号": "Company label size",
    "柱子间距": "Bar spacing",
    "柱距调节 (越小柱子越粗)": "Bar spacing (smaller = wider bars)",
    "柱子宽度": "Bar width",
    "柱宽": "Bar width",
    "点大小": "Marker size",
    "高度比例": "Height ratio",
    "调整公司间距与柱子粗细": "Company spacing and bar width",
    "涨幅文字大小": "Growth label size",
    "间距": "Spacing",
    # ---- step7.py 表格 / 常见值 ----
    "公司名称": "Company",
    "报告年份": "Reporting year",
    "报告期": "Reporting period",
    "项目": "Item",
    "序号": "No.",
    "项目名称": "Item",
    "分析指标": "Metric",
    "各公司平均占比情况": "Average share by company",
    "各公司平均占比": "Average share by company",
    "获取费用均值": "Acquisition expense average",
    "维持费用均值": "Maintenance expense average",
    "非履约费用均值": "Non-fulfilment expense average",
    "未披露": "Not disclosed",
    "无对应数据": "No data available",
    "采用保费分配法": "PAA applied",
    "未采用保费分配法": "PAA not applied",
    "百分比 (%)": "Percentage (%)",
    "数据不完整的年度：": "Years with incomplete data: ",
    "查看底层数据明细": "View underlying data",
    # ---- 参考线 / 通用短语 ----
    "虚线：样本中位数": "Dashed: sample median",
    "虚线：零轴": "Dashed: zero axis",
    "虚线：Y＝－X": "Dashed: Y = −X",
    "虚线：Y=X": "Dashed: Y = X",
    # ---- 登录页 / 错误与提示 ----
    "⚠️ 严禁向境外节点传输涉密数据": "⚠️ Never transmit confidential data to overseas endpoints",
    "**1.** 前往各大模型官方开放平台注册账号。\n\n**2.** 在控制台生成 `sk-` 开头的密钥。\n\n**3.** 复制填入上方输入框即可体验 AI 功能。": "**1.** Register on your AI provider's official platform.\n\n**2.** Generate a key starting with `sk-` in the console.\n\n**3.** Paste it above to enable AI features.",
    "Logo 加载失败，请检查文件名是否为 Digi.png。错误信息: ": "Could not load the logo. Check that Digi.png exists. Details: ",
    "❌ 数据缺少必要字段：": "❌ Required columns missing: ",
    "✅ 当前数据表全部列名：": "✅ Columns in the current data: ",
    "公式无效: ": "Invalid formula: ",
    "无法识别的指标引用：": "Unrecognised metric reference: ",
    "公式计算出错：": "Formula calculation failed: ",
    "💡 支持高级公式：可写 [字段]（当期）或 [字段@报告期间]（跨期），例如 [总资产@2025-12] / [总资产@2025-06]、[总资产] - [总负债]": "💡 Advanced formulas: use [field] (current period) or [field@period] (cross-period), e.g. [Total assets@2025-12] / [Total assets@2025-06], [Total assets] - [Total liabilities]",
    "原始值: ": "Original: ",
    "单位: ": "Unit: ",
    "年份：": "Year: ",
    "期间：": "Period: ",
    "内:": "Inner: ",
    "外:": "Outer: ",
    "平均: ": "Average: ",
    "⚠️ AI报错: ": "⚠️ AI error: ",
    "⚠️ 数据报错: ": "⚠️ Data error: ",
    "❌ 错误：": "❌ Error: ",
    "❌ 加载失败：": "❌ Load failed: ",
    "✅ 验证成功": "✅ Verified",
    # ---- 注释模板中的一级/二级模块名（Excel 数据源，作为 radio 选项精确匹配） ----
    "关键年报数据": "Key Annual Report Data",
    "关键披露信息": "Key Disclosures",
    "关键业绩指标": "Key Performance Metrics",
    "附录": "Appendix",
    "净利润": "Net profit",
    "保险服务业绩": "Insurance service result",
    "投资服务业绩": "Investment service result",
    "综合收益": "Comprehensive income",
    "资产": "Assets",
    "合同服务边际": "Contractual service margin",
    "净资产": "Net assets",
    "新业务": "New business",
}

# 图表标题 / 轴标题 / 图例等：合入 CHART_NAMES_EN（精确 + 长词子串替换）。
BM_CHART_EN: dict[str, str] = {
    "保险规模与盈利": "Insurance scale and profitability",
    "保险服务利润率": "Insurance service margin",
    "保险增长质量": "Insurance growth quality",
    "保险服务收入增长率": "Insurance revenue growth",
    "保险服务利润率变动（百分点）": "Change in insurance service margin (pp)",
    "双引擎盈利": "Dual-engine profitability",
    "投资服务利润率": "Investment service margin",
    "资产负债匹配": "Asset-liability matching",
    "可转损益的负债OCI / 平均净资产": "Recyclable liability OCI / average net assets",
    "FVOCI债券 / 平均净资产": "FVOCI bonds / average net assets",
    "综合净资产-规模与价值": "Comprehensive net assets – scale and value",
    "综合净资产-过去利润与未来利润": "Comprehensive net assets – past and future profits",
    "总资产增长率": "Total asset growth",
    "综合净资产增长率": "Comprehensive net asset growth",
    "净资产增长率": "Net asset growth",
    "CSM增长率": "CSM growth",
    "股东回报": "Shareholder return",
    "ROE净资产收益率": "Return on equity (ROE)",
    "新业务质量": "New business quality",
    "新业务CSM增长率": "New business CSM growth",
    "新业务IFRS利润率变动率": "Change in new business IFRS margin",
    "净资产": "Net assets",
    "气泡大小由": "Bubble size is driven by ",
    "各公司平均占比情况": "Average share by company",
    "净资产变动明细表（I9切换后）": "Net asset movement detail (post IFRS 9 transition)",
    "资负 OCI 变动分析表": "Asset-liability OCI movement",
    "新会计准则业绩表现和洞察": "IFRS Financial Performance and Insights",
    "关键数据概览表": "Key metrics overview",
    "利润贡献与保险和投资利润占比": "Profit contribution and insurance/investment mix",
    "收入结构分析": "Revenue structure analysis",
    "CSM摊销比例": "CSM amortisation ratio",
    "CSM持续率": "CSM sustainability ratio",
    "CSM 趋势": "CSM trend",
    "CSM概览表": "CSM overview",
    "新业务价值及增长分析表": "New business value and growth",
    "业绩明细表": "Performance detail",
    "折现率假设表": "Discount rate assumptions",
    "非金融风险置信水平表": "Non-financial risk confidence level",
    "综合收益变动趋势": "Comprehensive income trend",
    "资产端分类": "Asset classification",
    "OCI变动分析": "OCI movement analysis",
    "权益变动明细": "Equity movement detail",
    "费用结构": "Expense structure",
    "投资收益、承保损益单柱图": "Investment return and underwriting result",
    "税前和净利润": "Pre-tax profit and net profit",
    # ---- Step7 注释模板 49 个图表模块名称（导航/标题的数据源） ----
    "关键数据预览": "Key metrics preview",
    "净利润的贡献 - 保险服务业绩和投资服务业绩": "Net profit contribution – insurance and investment service results",
    "税前利润、税率及净利润": "Pre-tax profit, tax rate and net profit",
    "净利润(亏损)": "Net profit (loss)",
    "保险服务收入": "Insurance service revenue",
    "保险服务收入的构成 - 非PAA和PAA合同组": "Insurance revenue composition – non-PAA and PAA groups",
    "保险服务收入的构成 - 非PAA合同组的收入构成": "Insurance revenue composition – non-PAA group detail",
    "保险服务费用": "Insurance service expenses",
    "保险服务费用的构成 - 非PAA合同组的费用构成": "Insurance expense composition – non-PAA group detail",
    "业务及管理费（新准则分类）": "Administrative expenses (IFRS classification)",
    "当期保险服务业绩构成": "Current-period insurance service result composition",
    "上期保险服务业绩构成": "Prior-period insurance service result composition",
    "净投资回报": "Net investment return",
    "承保财务净损益": "Net insurance finance result",
    "其他综合收益": "Other comprehensive income",
    "其他综合收益 - 资产负债匹配": "OCI – asset-liability matching",
    "其他综合收益 - 当期综合收益变动情况": "OCI – current-period comprehensive income movement",
    "其他综合收益 - 上期综合收益变动情况": "OCI – prior-period comprehensive income movement",
    "IFRS9 资产端分类": "IFRS 9 asset classification",
    "CSM 余额": "CSM balance",
    "CSM/BEL占比": "CSM / BEL ratio",
    "CSM余额滚动表": "CSM roll-forward",
    "按过渡期计量方法拆分CSM": "CSM by transition measurement approach",
    "当期摊销前 CSM 变动项占比": "Current-period pre-amortisation CSM movement mix",
    "上期摊销前 CSM 变动项占比": "Prior-period pre-amortisation CSM movement mix",
    "CSM趋势(摊销比率/持续率）": "CSM trend (amortisation / sustainability ratios)",
    "综合净资产": "Comprehensive net assets",
    "新业务CSM": "New business CSM",
    "新业务LC": "New business LC",
    "新业务价值明细（利润率/亏损率/RA率)": "New business value detail (margin / loss / RA ratios)",
    "新业务 IFRS 利润率": "New business IFRS margin",
    "折现率": "Discount rate",
    "非金融风险调整置信水平": "Non-financial risk adjustment confidence level",
    "未来合同服务边际摊销": "Future CSM amortisation",
    "保险增长与质量": "Insurance growth and quality",
    "综合净资产-资本积累与未赚利润储备": "Comprehensive net assets – capital accumulation and unearned profit reserves",
    "保险服务业绩明细表": "Insurance service result detail",
    "新业务信息表": "New business information",
}

# 数据字段/指标名：只合入精确查找字典，绝不参与子串替换，避免污染列名。
BM_FIELD_EN: dict[str, str] = {
    "保险服务收入合计": "Total insurance service revenue",
    "保险服务费用合计": "Total insurance service expenses",
    "保险服务业绩": "Insurance service result",
    "净投资回报": "Net investment return",
    "承保财务损益": "Insurance finance result",
    "承保财务净损益": "Net insurance finance result",
    "分出再保险财务损益": "Reinsurance finance result",
    "投资利润": "Investment profit",
    "税前利润总额": "Profit before tax",
    "净利润": "Net profit",
    "其他综合收益": "Other comprehensive income",
    "综合收益总额": "Total comprehensive income",
    "总资产": "Total assets",
    "期末股东权益": "Closing shareholders' equity",
    "CSM期末余额": "Closing CSM balance",
    "新业务CSM（集团口径）": "New business CSM (group basis)",
    "新业务亏损合同（LC）——非PAA": "New business onerous contracts (LC) – non-PAA",
    "新业务未来现金流入现值": "PV of future cash inflows, new business",
    "可转损益的负债OCI": "Recyclable liability OCI",
    "FVOCI债券公允价值": "FVOCI bonds fair value",
    "保险合同净负债余额": "Net insurance contract liability balance",
    "新业务CSM": "New business CSM",
    "折现率假设": "Discount rate assumption",
    "非金融风险的置信水平": "Non-financial risk confidence level",
    "获取费用": "Acquisition expenses",
    "维持费用": "Maintenance expenses",
    "非履约费用": "Non-fulfilment expenses",
    "可转损益OCI合计": "Total recyclable OCI",
    "不可转损益OCI合计": "Total non-recyclable OCI",
    "报告年度": "Reporting year",
    "报告月度": "Reporting month",
    "报告月份": "Reporting month",
    "报告期间": "Reporting period",
    "字段名": "Field",
    "指标名称": "Metric",
    "公司": "Company",
    "公司类型": "Company type",
    "同业分类": "Peer group",
}

# bm-platform 数据中的寿险/集团公司名。gi 项目自带的 COMPANY_NAMES_EN 全是
# 财险公司（人保财险、太保产险…），与本项目数据完全不匹配；未收录的公司名
# 由 AI 兜底翻译并写入 i18n_ai_cache.json，长期可人工合并进本字典。
BM_COMPANY_EN: dict[str, str] = {
    "新华保险": "New China Life", "太平人寿": "Taiping Life",
    "中国人寿": "China Life", "平安寿险": "Ping An Life",
    "太保寿险": "CPIC Life", "泰康人寿": "Taikang Life",
    "人保寿险": "PICC Life", "友邦人寿": "AIA Life",
    "中邮保险": "China Post Life", "建信人寿": "CCB Life",
    "工银安盛": "ICBC-AXA", "农银人寿": "ABC Life",
    "招商信诺": "Cigna & CMB", "中信保诚": "CITIC-Prudential",
    "光大永明": "Sun Life Everbright", "阳光人寿": "Sunshine Life",
    "富德生命": "Funde Sino Life", "华夏人寿": "Huaxia Life",
    "前海人寿": "Foresea Life", "百年人寿": "Aeon Life",
    "渤海人寿": "Bohai Life", "信泰人寿": "Sinatay Life",
    "大家人寿": "Dajia Life", "中意人寿": "Generali China",
    "中英人寿": "Aviva-COFCO", "恒大人寿": "Evergrande Life",
    "天安人寿": "Tian'an Life", "君康人寿": "Junkang Life",
    "弘康人寿": "Hongkang Life", "国华人寿": "Guohua Life",
    "横琴人寿": "Hengqin Life", "中华人寿": "China United Life",
    "民生人寿": "Minsheng Life", "合众人寿": "Union Life",
    "上海人寿": "Shanghai Life", "北京人寿": "Beijing Life",
    "珠江人寿": "Pearl River Life", "利安人寿": "Lian Life",
}

# 长片段：合入 PHRASE_EN，供动态 f-string / 图表注释做子串替换。
BM_PHRASE_EN: dict[str, str] = {
    "新准则财务报告洞察平台": "IFRS Financial Reporting Insights Platform",
    "欢迎使用新准则财务报告洞察平台": "Welcome to the IFRS Financial Reporting Insights Platform",
    "当前身份：": "Signed in as: ",
    "系统版本：v3.0 (Alpha) © 2026": "Version v3.0 (Alpha) © 2026",
    "Developed by KPMG ACT Life": "Developed by KPMG ACT Life",
    "本期报告时点：": "Current reporting date: ",
    "对比期报告时点：": "Comparison reporting date: ",
    "保险公司报告分析处理平台": "Insurance Report Analysis Platform",
    "* 注释：": "* Note: ",
    "（续）": " (continued)",
    "（单位：": " (Unit: ",
    "单位：": "Unit: ",
    "人民币": "RMB",
    "气泡大小由": "Bubble size is driven by ",
    "决定（log1p缩放，仅表达相对规模）。": " (log1p scaling, relative scale only).",
    "家公司上升，其中": " companies increased, of which ",
    "家公司下降，其中": " companies decreased, of which ",
    "家上升": " increased",
    "家下降": " decreased",
    "增幅最大": "the largest increase",
    "降幅最大": "the largest decrease",
    "家披露公司中，主要构成部分为": " of disclosing companies have ",
    "该项目占比均值约": " as the main component; its average share is about ",
    "均值约": "average of about ",
    "均值为": "average of ",
    "平均值线": "Average line",
    "规模与保险服务利润率的相关系数为": "Correlation between scale and insurance service margin: ",
    "同时观察收入增长与利润率变动，零轴划分": "Revenue growth and margin change are shown together; the zero axes define ",
    "家公司实现": " companies achieved ",
    "改善最多": "the strongest improvement",
    "承压最重": "the sharpest deterioration",
    "保险服务利润率最高：": "highest insurance service margin: ",
    "投资服务利润率最高：": "highest investment service margin: ",
    "越接近Y=-X虚线，表示资产端与负债端OCI": "The closer to the Y=-X dashed line, the more the asset and liability OCI ",
    "当期OCI错配率最小：": "lowest current-period OCI mismatch: ",
    "当期OCI错配率最大：": "highest current-period OCI mismatch: ",
    "家位于Y=X虚线下方，说明总资产扩张快于": " companies sit below the Y=X line, meaning total assets grew faster than ",
    "主要为净资产增长，CSM减少；相反，": "mainly net asset growth with declining CSM; conversely, ",
    "净资产规模与ROE并非天然正相关，实际盈利能力还需结合一次性收益、分红/增资等因素综合判断：": "Net asset scale is not inherently positively correlated with ROE; one-off gains, dividends and capital injections also matter: ",
    "净资产规模最大：": "largest net assets: ",
    "ROE最高：": "highest ROE: ",
    "样本ROE中位数约": "sample median ROE about ",
    "从新业务CSM的量与新业务IFRS利润率的价": "From new business CSM volume and new business IFRS margin ",
    "CSM利润率上升": "CSM margin increased",
    "CSM利润率下降": "CSM margin decreased",
    "获取费用绝对金额最高：": "highest acquisition expenses: ",
    "维持费用绝对金额最高：": "highest maintenance expenses: ",
    "非履约费用绝对金额最高：": "highest non-fulfilment expenses: ",
    "各公司税前利润与净利润对比详见图表，关注": "Pre-tax profit and net profit by company are shown in the chart; watch ",
    "保险利润占主导：": "Insurance profit dominant: ",
    "投资利润占主导：": "Investment profit dominant: ",
    "保险利润占比": "insurance profit share",
    "（自动生成失败：": "(auto-generation failed: ",
    "（%）": "(%)",
    "报告顺序由【模块ID】的先后顺序决定": "Report order follows the module ID sequence",
    "暂无【": "No ",
    "】数据，保持原始顺序": " data; original order retained",
    "请点击下方按钮下载": "click the button below to download",
    "图片 ": "Image ",
    " 对应：": " maps to: ",
    "注释表_": "Notes_",
    "投资利润: ": "Investment profit: ",
    "保险利润: ": "Insurance profit: ",
    "实际占比: ": "Actual share: ",
    "%变化 = 本期/对比期-1，即 ": "% change = current/comparison − 1, i.e. ",
    "CSM摊销比例 = CSM摊销/(摊销前的期末CSM)；": "CSM amortisation ratio = CSM amortisation / closing CSM before amortisation; ",
    "CSM持续率 = 新业务CSM/CSM摊销": "CSM sustainability ratio = new business CSM / CSM amortisation",
    "虚线：样本中位数": "Dashed: sample median",
    "查看底层数据明细": "View underlying data",
    # 气泡大小/规模类复合词必须先于"总资产""合计"等通用短词替换
    "总资产规模": "Total asset scale",
    "综合净资产规模": "Comprehensive net asset scale",
    "净资产规模": "Net asset scale",
    "税后利润": "Profit after tax",
    "新业务未来现金流入现值": "PV of future cash inflows, new business",
    "CSM期末余额": "Closing CSM balance",
    "⚠️ 严禁向境外节点传输涉密数据": "⚠️ Never transmit confidential data to overseas endpoints",
    "⚠️ AI报错: ": "⚠️ AI error: ",
    "⚠️ 数据报错: ": "⚠️ Data error: ",
    "前往各大模型官方开放平台注册账号": "Register on your AI provider's official platform",
    "在控制台生成": "Generate in the console",
    "开头的密钥": "a key starting with",
    "复制填入上方输入框即可体验 AI 功能": "Paste it above to enable AI features",
    " 最高，": " highest, ",
    " 最低。": " lowest.",
    "均值 ": "average ",
    "平均: ": "Average: ",
    "实际占比: ": "Actual share: ",
    "年份：": "Year: ",
    "期间：": "Period: ",
    "原始值: ": "Original: ",
    "（单位: ": " (Unit: ",
    "公司级对标报告": "Company Benchmarking Report",
    "公司报告导航": "Company Report Navigation",
    "保险公司": "insurance company",
    "业绩表现和洞察": "Performance and Insights",
    "关键数据概览": "Key metrics overview",
    "报告顺序由【模块ID】的先后顺序决定": "Report order follows the module ID sequence",
}


# ---------------------------------------------------------------------------
# 2. 语言作用域 / 会话状态
# ---------------------------------------------------------------------------
def set_scope(active: bool) -> None:
    """控制翻译是否生效；step8.py 渲染期间置 False 以保持原中文界面。"""
    _SCOPE["active"] = bool(active)


def is_scope_active() -> bool:
    return _SCOPE["active"]


def _should_translate(language: str | None = None) -> bool:
    if not _SCOPE["active"]:
        return False
    try:
        return i18n.is_english(language)
    except Exception:
        return False


def _state():
    try:
        return st.session_state
    except Exception:
        return None


def _get_cache() -> dict[str, str]:
    state = _state()
    if state is None:
        return _memory_cache
    if "bm_ai_cache" not in state:
        state["bm_ai_cache"] = _load_file_cache()
    return state["bm_ai_cache"]


def _get_strings(key: str, fallback: set[str]) -> set[str]:
    state = _state()
    if state is None:
        return fallback
    if key not in state:
        state[key] = set()
    return state[key]


def _load_file_cache() -> dict[str, str]:
    try:
        if AI_CACHE_FILE.is_file():
            data = json.loads(AI_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    except Exception as exc:
        print(f"[bm_i18n] Could not read {AI_CACHE_FILE.name}: {exc}")
    return {}


def _persist_cache(cache: dict[str, str]) -> None:
    """原子写，避免并发 rerun 写坏缓存文件。"""
    try:
        with _file_lock:
            AI_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".i18n_ai_", suffix=".json", dir=str(AI_CACHE_FILE.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(dict(cache), handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, AI_CACHE_FILE)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    except Exception as exc:
        print(f"[bm_i18n] Could not write {AI_CACHE_FILE.name}: {exc}")


def _api_config() -> tuple[str, str, str]:
    state = _state()
    if state is None:
        return "", "", ""
    try:
        return (
            str(state.get("api_key", "") or "").strip(),
            str(state.get("base_url", "") or "https://api.deepseek.com").strip(),
            str(state.get("model_name", "") or "deepseek-chat").strip(),
        )
    except Exception:
        return "", "", ""


def _toggle_on() -> bool:
    state = _state()
    return bool(state and state.get(AI_TOGGLE_KEY, False))


# ---------------------------------------------------------------------------
# 3. 翻译入口（包装 report_i18n.translate_text）
# ---------------------------------------------------------------------------
def _english_period(text: str) -> str:
    match = _PERIOD_RE.match(text)
    if not match:
        return ""
    year, month = match.group(1), match.group(2)
    if month and 1 <= int(month) <= 12:
        return f"{_MONTHS[int(month) - 1]} {year}"
    return year


def _looks_like_company(text: str) -> bool:
    return (
        len(text) <= 20
        and not re.search(r"[\s，,。；;：:（）()\[\]{}<>/\\]", text)
        and text.endswith(_COMPANY_SUFFIXES)
    )


def _is_protected(text: str) -> bool:
    """代码 / 超长 HTML / 已静态映射的字段名与公司名不送 AI。

    注意：未收录的公司名必须允许进入 AI 未命中队列，否则图表、图例、
    ticktext 里的寿险公司名会永远保持中文（用户明确要求公司名英译）。
    """
    if len(text) > 2000 or text in BM_FIELD_EN or text in i18n.COMPANY_NAMES_EN:
        return True
    if text.startswith(("http://", "https://", "data:")):
        return True
    lowered = text.lower()
    return any(token in lowered for token in ("<style", "<script", "<!doctype", "font-family:", "function("))


_GENERIC_NOT_COMPANY = {
    "再保险", "自保", "相互", "集团", "股份", "保险", "财险", "产险",
    "寿险", "人寿", "农险", "有限公司", "股份有限公司",
}


def _is_company_like(text: str) -> bool:
    """纯公司名（无标点/空格）单独处理，避免短语替换把公司名改坏。

    gi 字典含 "有" -> "Yes" 这类单字枚举，子串替换会把
    "某某人寿保险有限公司" 变成 "某某人寿保险Yes限公司"。
    """
    if not _CHINESE_RE.search(text) or len(text) > 24 or text in _GENERIC_NOT_COMPANY:
        return False
    if re.search(r"[\s，,。；;：:（）()\[\]{}<>/\\·|]", text):
        return False
    return "有限公司" in text or "股份" in text or text.endswith(_COMPANY_SUFFIXES)


def _translate_static(text: str) -> str:
    exact = BM_EXACT_EN.get(text.strip())
    if exact:
        return exact
    return _orig_translate_text(text)


def _patched_translate_text(text: str, language: str | None = None) -> str:
    if not isinstance(text, str) or not text or not _should_translate(language):
        return _orig_translate_text(text, language)
    exact = BM_EXACT_EN.get(text.strip())
    if exact:
        return exact
    cached = _get_cache().get(text)
    if isinstance(cached, str) and cached:
        return cached
    period = _english_period(text)
    if period:
        return period
    # 公司名：优先用官方英文名；未收录则保持中文并交给 AI 兜底，
    # 不走短语替换，避免 "有"->"Yes" 等单字枚举污染公司名。
    if _is_company_like(text):
        official_name = i18n.COMPANY_NAMES_EN.get(text)
        if official_name:
            return official_name
        _get_strings("bm_ai_misses", _memory_misses).add(text)
        return text
    result = _orig_translate_text(text, language)
    if isinstance(result, str) and _CHINESE_RE.search(result) and not _is_protected(text):
        _get_strings("bm_ai_misses", _memory_misses).add(text)
    return result


def translate_ui(text: Any, *, allow_ai: bool | None = None) -> Any:
    """翻译一段展示文案；CSS/JS 注入串只做静态字典替换，不产生 AI 未命中。"""
    if not isinstance(text, str) or not text or not _should_translate():
        return text
    if allow_ai is None:
        allow_ai = not _is_protected(text)
    if not allow_ai:
        return _translate_static(text)
    return _patched_translate_text(text)


# ---------------------------------------------------------------------------
# 4. AI 兜底：批量翻译 + 持久化 + 单次重跑
# ---------------------------------------------------------------------------
def _call_translation_api(texts: list[str], key: str, base: str, model: str) -> dict[str, str]:
    import openai

    client = openai.OpenAI(api_key=key, base_url=base, timeout=AI_TIMEOUT, max_retries=0)
    payload = {str(index): value for index, value in enumerate(texts)}
    system = (
        "You are a professional translator for an insurance financial reporting "
        "dashboard (KPMG, IFRS 17 / IFRS 9). Translate each Chinese UI string into "
        "concise professional English. Keep placeholders such as {...}, %{...}, "
        "HTML tags and attributes, numbers, formulas, punctuation and units unchanged. "
        "Chinese insurance company names MUST be rendered as their official English "
        "names (e.g. 新华保险 -> New China Life, 太平人寿 -> Taiping Life, "
        "中国人寿 -> China Life); do not transliterate and do not leave them in Chinese. "
        "Metric codes and pure numeric data values should be returned unchanged. "
        "Return ONLY a JSON object with exactly the same keys."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
    )
    content = (response.choices[0].message.content or "").strip()
    # 思考型模型（qwen3 等）会在正文前输出 <think>...</think>，需先剥离
    content = re.sub(
        r"<(?:think|thinking)>.*?</(?:think|thinking)>", "", content, flags=re.S | re.I
    ).strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        try:
            parsed = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            parsed = {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, str] = {}
    for index, value in enumerate(texts):
        translated = parsed.get(str(index))
        if isinstance(translated, str) and translated.strip() and translated.strip() != value:
            result[value] = translated.strip()
    return result


def _ai_status(pending: int, cache_size: int, error: str = "") -> None:
    """把 AI 兜底状态直接显示在侧边栏，避免错误只打印到服务器控制台。"""
    state = _state()
    if state is None or not _toggle_on():
        return
    key, _base, model = _api_config()
    try:
        if error:
            st.sidebar.warning(f"AI 翻译失败 / AI translation failed：{error}")
        elif not key:
            st.sidebar.caption("AI 翻译：未检测到 API Key，已回退中文")
        else:
            st.sidebar.caption(
                f"AI 翻译：已缓存 {cache_size} 条 · 本轮待翻译 {pending} 条 · {model}"
            )
    except Exception as exc:
        print(f"[bm_i18n] Could not render AI status: {exc}")


def flush_misses() -> int:
    """页面渲染结束后调用：批量翻译未命中串，写入缓存并最多触发一次重跑。

    入口有三处：app.py 脚本末尾、登录页 st.stop 前、以及被包装的 st.stop()
    内部——保证任何提前终止的分支也会收口，不会静默跳过 AI 翻译。
    """
    state = _state()
    misses = _get_strings("bm_ai_misses", _memory_misses)
    attempted = _get_strings("bm_ai_attempted", _memory_attempted)
    cache = _get_cache()
    key, base, model = _api_config()

    # context 含 API 配置指纹：改 key / endpoint / model 后自动清除 attempted 重试，
    # 避免"失败一次就永久拉黑"。保留本轮已收集的 misses，否则刚切到英文的
    # 那一轮会丢失全部待翻译文案。
    context = (
        i18n.get_language(), _toggle_on(),
        hashlib.sha1(key.encode("utf-8")).hexdigest()[:12], base, model,
    )
    if state is not None and state.get("bm_ai_context") != context:
        state["bm_ai_context"] = context
        attempted.clear()
        state.pop("bm_ai_rerun_sig", None)
        state.pop("bm_ai_last_error", None)

    if not _should_translate() or not _toggle_on():
        return 0
    if not key:
        _ai_status(len(misses), len(cache), "未配置 API Key")
        return 0

    pending = sorted(text for text in misses if text not in cache and text not in attempted)
    if not pending:
        last_error = str(state.get("bm_ai_last_error", "")) if state else ""
        _ai_status(0, len(cache), last_error)
        return 0

    translations: dict[str, str] = {}
    errors: list[str] = []
    for start in range(0, len(pending), AI_BATCH_SIZE):
        chunk = pending[start : start + AI_BATCH_SIZE]
        try:
            translations.update(_call_translation_api(chunk, key, base, model))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            print(f"[bm_i18n] AI translation batch failed ({len(chunk)} strings): {exc}")

    if errors:
        message = errors[0][:200]
        if state is not None:
            state["bm_ai_last_error"] = message
        # 防止同一批反复刷 API；改 key / 重拨开关时 context 变化会自动清除
        attempted.update(pending)
        _ai_status(len(pending), len(cache), message)
        return 0

    if state is not None:
        state.pop("bm_ai_last_error", None)
    # 请求成功但模型未给出译文的串标记后不再重复请求
    attempted.update(text for text in pending if text not in translations)
    if not translations:
        _ai_status(
            len(pending), len(cache),
            "接口已连通但模型未返回有效 JSON 译文，请检查模型名或换用支持 JSON 输出的模型",
        )
        return 0

    cache.update(translations)
    _persist_cache(cache)
    misses.difference_update(translations)
    print(f"[bm_i18n] AI translated {len(translations)} new strings -> {AI_CACHE_FILE.name}")

    sig = hashlib.sha1(
        ("|".join(pending) + "|" + i18n.get_language()).encode("utf-8")
    ).hexdigest()
    # 上传了数据/文档的那一轮不自动重跑：强制 rerun 会重建无 key 的上传控件，
    # 并可能让模板解析出的模块 ID / 导航序号状态错位。译文已写入缓存，
    # 下一次自然交互即会生效。
    if (
        state is not None
        and state.get("bm_ai_rerun_sig") != sig
        and not _UPLOAD_STATE["seen"]
    ):
        state["bm_ai_rerun_sig"] = sig
        st.rerun()
    return len(translations)


# ---------------------------------------------------------------------------
# 5. Streamlit 渲染挂钩
# ---------------------------------------------------------------------------
_DISPLAY_FUNCS = (
    "markdown", "caption", "write", "text", "title", "header", "subheader",
    "info", "warning", "error", "success",
)
_WIDGET_FUNCS = (
    "button", "download_button", "checkbox", "toggle", "text_input", "number_input",
    "text_area", "selectbox", "multiselect", "radio", "select_slider", "slider",
    "color_picker", "date_input", "time_input", "metric",
    "expander", "popover", "form_submit_button",
)
# 上传控件完全不参与翻译（含 label）：label 变化会改变 widget 自动 ID，
# 上传状态/文件句柄可能丢失，进而破坏注释模板解析。
_UPLOAD_STATE = {"seen": False}
_OPTION_FUNCS = frozenset({"selectbox", "multiselect", "radio", "select_slider"})
# 无 key 的控件 ID 由 label/参数/元素位置推导；label 翻译后 ID 变化会让
# widget state 丢失（数据源选择被重置 → 上传控件不渲染 → 文件被清理）。
# 给它们注入基于"调用位置"的稳定 key，跨语言、跨重跑保持不变。
_WIDGET_KEY_COUNTER: dict[str, int] = {}


def _stable_widget_key(prefix: str, location: str) -> str:
    base = f"{prefix}_{hashlib.sha1(location.encode('utf-8')).hexdigest()[:12]}"
    count = _WIDGET_KEY_COUNTER.get(base, 0) + 1
    _WIDGET_KEY_COUNTER[base] = count
    return base if count == 1 else f"{base}_{count}"


def localize_plotly_safe(figure):
    """逐属性容错的图表本地化。

    report_i18n.localize_plotly 用一个 try/except 包住整个循环，任一属性
    赋值失败（如 axis.title 非 Title 对象、trace.x 为特殊数组）就会放弃
    整张图的所有翻译，表现为"大部分图表翻译失败"。这里每个属性单独保护，
    并同步翻译 ticktext，避免公司名作类别轴时 tickvals/ticktext 错位。
    """
    if figure is None:
        return figure
    lang = i18n.get_language()

    def tr(value):
        return i18n.translate_text(value, lang) if isinstance(value, str) else value

    layout = getattr(figure, "layout", None)
    if layout is not None:
        try:
            title = getattr(layout, "title", None)
            if title is not None and getattr(title, "text", None):
                title.text = tr(title.text)
        except Exception as exc:
            print(f"[bm_i18n] layout.title: {exc}")
        for axis_name in ("xaxis", "yaxis"):
            try:
                axis = getattr(layout, axis_name, None)
                if axis is None:
                    continue
                axis_title = getattr(axis, "title", None)
                if axis_title is not None and getattr(axis_title, "text", None):
                    axis_title.text = tr(axis_title.text)
                ticktext = getattr(axis, "ticktext", None)
                if ticktext is not None:
                    axis.ticktext = [tr(value) for value in list(ticktext)]
            except Exception as exc:
                print(f"[bm_i18n] {axis_name}: {exc}")
        try:
            legend = getattr(layout, "legend", None)
            if legend is not None:
                legend_title = getattr(legend, "title", None)
                if legend_title is not None and getattr(legend_title, "text", None):
                    legend_title.text = tr(legend_title.text)
        except Exception as exc:
            print(f"[bm_i18n] legend: {exc}")
        for annotation in list(getattr(layout, "annotations", ()) or ()):
            try:
                if getattr(annotation, "text", None):
                    annotation.text = tr(annotation.text)
            except Exception as exc:
                print(f"[bm_i18n] annotation: {exc}")

    for trace in list(getattr(figure, "data", ()) or ()):
        for attribute in ("name", "labels", "text", "x"):
            try:
                values = getattr(trace, attribute, None)
                if values is None:
                    continue
                if isinstance(values, str):
                    setattr(trace, attribute, tr(values))
                elif hasattr(values, "__iter__"):
                    setattr(trace, attribute, [tr(value) for value in list(values)])
            except Exception as exc:
                print(f"[bm_i18n] trace.{attribute}: {exc}")
        try:
            hover = getattr(trace, "hovertemplate", None)
            if isinstance(hover, str) and hover:
                trace.hovertemplate = i18n.translate_hover_text(hover, lang)
        except Exception as exc:
            print(f"[bm_i18n] hovertemplate: {exc}")
    return figure


def _make_format_func(existing=None):
    """仅在调用方自带 format_func 时使用：在其结果上再套一层翻译。"""
    if existing is None:
        return None

    def fmt(value):
        rendered = existing(value)
        return translate_ui(rendered) if isinstance(rendered, str) else rendered
    return fmt


def _translate_options(options):
    """翻译选项显示名，同时返回「译文 -> 原值」映射，保证返回值仍是中文原值。"""
    if not isinstance(options, (list, tuple)):
        return None, {}
    translated, mapping = [], {}
    for item in options:
        if isinstance(item, str):
            shown = translate_ui(item)
            translated.append(shown)
            mapping[shown] = item
        else:
            translated.append(item)
    return (tuple(translated) if isinstance(options, tuple) else translated), mapping


def _restore(value, mapping):
    """把控件返回的「译文」还原成原始值（单选/多选/区间）。"""
    if not mapping:
        return value
    def one(item):
        try:
            return mapping.get(item, item)
        except TypeError:
            return item
    if isinstance(value, list):
        return [one(item) for item in value]
    if isinstance(value, tuple):
        return tuple(one(item) for item in value)
    return one(value)


def _reverse_map() -> dict[str, str]:
    """英文显示名 -> 中文原值，用于语言切换时归一化 session state。"""
    reverse: dict[str, str] = {}
    sources = (
        BM_EXACT_EN, BM_CHART_EN, BM_FIELD_EN, BM_PHRASE_EN, BM_COMPANY_EN,
        i18n.CHART_NAMES_EN, i18n.LEVEL_NAMES_EN, i18n.CATEGORY_NAMES_EN,
        i18n.DISCLOSURE_NAMES_EN, i18n.PERFORMANCE_NAMES_EN, i18n.UNIT_NAMES_EN,
    )
    for source in sources:
        for zh, en in source.items():
            if isinstance(en, str) and en and en != zh:
                reverse.setdefault(en, zh)
    return reverse


def normalize_language_switch() -> None:
    """每轮渲染开头重置上传标记；选项值不再翻译，无需改写 widget state。

    早期版本会把语言切换后残留的英文 widget state 反查回中文，但遍历并
    赋值 session_state 有误伤上传文件状态的风险。现在所有选项值恒为中文
    原值，widget state 不会残留译文，因此只保留轻量重置。
    """
    _UPLOAD_STATE["seen"] = False
    _WIDGET_KEY_COUNTER.clear()
    state = _state()
    if state is None:
        return
    state["bm_last_language"] = i18n.get_language()


def _english_period_to_zh(text: str, month_lookup: dict[str, int]) -> str:
    match = re.fullmatch(r"([A-Z][a-z]{2}) (\d{4})", text.strip())
    if match and match.group(1) in month_lookup:
        return f"{match.group(2)}年{month_lookup[match.group(1)]}月"
    return text


def install() -> None:
    """幂等安装：合并字典、包装翻译入口、挂钩 Streamlit 显示函数。"""
    global _installed, _orig_translate_text
    if _installed:
        return
    _installed = True

    # 1) 字典合并（本模块词条优先）
    # gi 字典里 "有"/"无" 这类单字枚举会参与短语子串替换，把
    # "…保险有限公司" 改成 "…保险Yes限公司"。摘出后仅保留精确匹配。
    for char in ("有", "无"):
        english = i18n.DISCLOSURE_NAMES_EN.pop(char, None)
        if english:
            BM_EXACT_EN.setdefault(char, english)
    i18n.COMPANY_NAMES_EN.update(BM_COMPANY_EN)
    i18n.PHRASE_EN.update(BM_PHRASE_EN)
    # 长字段名也登记为短语：gi 内置 PHRASE_EN 含"合计/收入/资本"等短词，
    # 若不先登记完整字段名，"保险服务收入合计"会被拆成"…收入Total"之类残句。
    i18n.PHRASE_EN.update({k: v for k, v in BM_FIELD_EN.items() if len(k) >= 4})
    i18n.CHART_NAMES_EN.update(BM_CHART_EN)
    # 图表名里含"保险服务收入""总资产"等短词，把完整字段名也放进同一字典，
    # 按长度降序替换时可保证"保险服务收入合计"不会被拆成"…收入合计"。
    i18n.CHART_NAMES_EN.update({k: v for k, v in BM_FIELD_EN.items() if len(k) >= 4})
    i18n.FIELD_NAMES_EN.update(BM_FIELD_EN)
    i18n.COLUMN_NAMES_EN.update(BM_FIELD_EN)

    # 2) 唯一翻译入口包装：让 localize_plotly / translate_hover_text /
    #    translate_dataframe 等所有下游函数自动获得 bm 字典与 AI 兜底。
    _orig_translate_text = i18n.translate_text
    i18n.translate_text = _patched_translate_text

    # 3) 纯展示函数：只翻译首个正文参数与 help/placeholder
    for name in _DISPLAY_FUNCS:
        original = getattr(st, name, None)
        if original is None or getattr(original, "_bm_i18n", False):
            continue

        def build_display(original):
            @functools.wraps(original)
            def wrapper(*args, **kwargs):
                if not _should_translate():
                    return original(*args, **kwargs)
                if args and isinstance(args[0], str):
                    args = (translate_ui(args[0]),) + args[1:]
                for field in ("help", "placeholder"):
                    if isinstance(kwargs.get(field), str):
                        kwargs[field] = translate_ui(kwargs[field])
                return original(*args, **kwargs)
            wrapper._bm_i18n = True
            return wrapper

        setattr(st, name, build_display(original))

    # 4) 控件：翻译 label 与选项显示名，并把返回值还原成中文原值，
    #    这样 app.py / step7.py 中所有 `if x == "普通用户"` 之类的判断不受影响。
    #    不使用 format_func：当前 Streamlit 会把格式化后的字符串写入 widget state，
    #    跨语言切换时可能残留英文值；直接翻译选项 + 返回值映射更稳。
    for name in _WIDGET_FUNCS:
        original = getattr(st, name, None)
        if original is None or getattr(original, "_bm_i18n", False):
            continue

        def build_widget(original, widget_name):
            @functools.wraps(original)
            def wrapper(*args, **kwargs):
                # 中英文模式都要注入：否则中文无 key、英文有 key，ID 仍不一致
                if widget_name in _OPTION_FUNCS and not kwargs.get("key"):
                    frame = inspect.currentframe()
                    caller = frame.f_back if frame is not None else None
                    location = (
                        f"{os.path.basename(caller.f_code.co_filename)}:{caller.f_lineno}"
                        if caller is not None
                        else str(args[0]) if args else "option"
                    )
                    kwargs["key"] = _stable_widget_key("bm_opt", location)
                if not _should_translate():
                    return original(*args, **kwargs)
                if args and isinstance(args[0], str):
                    args = (translate_ui(args[0]),) + args[1:]
                if isinstance(kwargs.get("label"), str):
                    kwargs["label"] = translate_ui(kwargs["label"])
                for field in ("help", "placeholder"):
                    if isinstance(kwargs.get(field), str):
                        kwargs[field] = translate_ui(kwargs[field])

                # 选项值一律保持中文原值，只翻译 label。
                # app.py / step7.py 大量使用 `if source_choice == "上传集成表 Excel"`
                # 这类分支，以及用返回值查 DataFrame 定位模块 ID。翻译选项会让
                # widget state 在语言切换后残留译文 → 分支不成立 → file_uploader
                # 不再渲染 → Streamlit 清理已上传文件，用户被迫重新上传。
                # 调用方自带 format_func 时仍在其结果上叠加翻译（format_func
                # 只影响显示，不影响返回值）。
                if widget_name in _OPTION_FUNCS and callable(kwargs.get("format_func")):
                    kwargs["format_func"] = _make_format_func(kwargs["format_func"])

                return original(*args, **kwargs)
            wrapper._bm_i18n = True
            return wrapper

        setattr(st, name, build_widget(original, name))

    # 5) Tab 标签是纯展示，可以直接翻译
    original_tabs = getattr(st, "tabs", None)
    if original_tabs is not None and not getattr(original_tabs, "_bm_i18n", False):
        @functools.wraps(original_tabs)
        def tabs_wrapper(labels, *args, **kwargs):
            if _should_translate():
                labels = [translate_ui(x) if isinstance(x, str) else x for x in labels]
            return original_tabs(labels, *args, **kwargs)
        tabs_wrapper._bm_i18n = True
        st.tabs = tabs_wrapper

    # 6) 所有 Plotly 图表统一出口（step7.py 的 show_chart 也走这里）
    original_plotly = getattr(st, "plotly_chart", None)
    if original_plotly is not None and not getattr(original_plotly, "_bm_i18n", False):
        @functools.wraps(original_plotly)
        def plotly_wrapper(figure, *args, **kwargs):
            if _should_translate() and figure is not None:
                try:
                    figure = localize_plotly_safe(figure)
                except Exception as exc:
                    print(f"[bm_i18n] localize_plotly_safe failed: {exc}")
            return original_plotly(figure, *args, **kwargs)
        plotly_wrapper._bm_i18n = True
        st.plotly_chart = plotly_wrapper

    # 7) components.html：打印按钮/表头等 HTML 只做静态替换，不送 AI
    original_html = getattr(components, "html", None)
    if original_html is not None and not getattr(original_html, "_bm_i18n", False):
        @functools.wraps(original_html)
        def html_wrapper(html, *args, **kwargs):
            if _should_translate() and isinstance(html, str):
                html = translate_ui(html, allow_ai=False)
            return original_html(html, *args, **kwargs)
        html_wrapper._bm_i18n = True
        components.html = html_wrapper

    # 8) 关键收口：app.py / step7.py 有多处 st.stop() 提前终止脚本，
    #    若不包装，挂在脚本末尾的 flush_misses() 永远执行不到，AI 翻译看似无效。
    original_stop = getattr(st, "stop", None)
    if original_stop is not None and not getattr(original_stop, "_bm_i18n", False):
        @functools.wraps(original_stop)
        def stop_wrapper(*args, **kwargs):
            try:
                flush_misses()
            except Exception as exc:
                print(f"[bm_i18n] flush before stop failed: {exc}")
            return original_stop(*args, **kwargs)
        stop_wrapper._bm_i18n = True
        st.stop = stop_wrapper

    # 9) 上传控件：只记录"本轮出现过"并注入稳定 key，绝不改 label / 参数值。
    #    用于让 AI 兜底的自动重跑避开上传轮；稳定 key 保证语言切换、侧边栏
    #    元素增减后 widget ID 不变，Streamlit 不会清理已上传文件。
    original_uploader = getattr(st, "file_uploader", None)
    if original_uploader is not None and not getattr(original_uploader, "_bm_i18n", False):
        @functools.wraps(original_uploader)
        def uploader_wrapper(*args, **kwargs):
            _UPLOAD_STATE["seen"] = True
            if not kwargs.get("key"):
                # 无 key 的上传控件 ID 由 label/参数/元素位置推导，跨语言切换
                # 时会变化。用"调用位置"生成恒定 key，文件状态即可保留。
                frame = inspect.currentframe()
                caller = frame.f_back if frame is not None else None
                location = (
                    f"{os.path.basename(caller.f_code.co_filename)}:{caller.f_lineno}"
                    if caller is not None
                    else str(args[0]) if args else "uploader"
                )
                kwargs["key"] = "bm_upload_" + hashlib.sha1(
                    location.encode("utf-8")
                ).hexdigest()[:12]
            return original_uploader(*args, **kwargs)
        uploader_wrapper._bm_i18n = True
        st.file_uploader = uploader_wrapper
