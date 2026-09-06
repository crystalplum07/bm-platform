#左下角搜索并打开 Anaconda Prompt（那个黑框框）。
#输入 D: 并按回车。
#输入 cd D:\程序-ILS 并按回车。
#输入 streamlit run app.py 并按回车。

#pip install -U kaleido
#pip install python-pptx
import pdfplumber
import fitz  # PyMuPDF
import json
import re
import io
import time
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import streamlit as st
import requests
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from pptx import Presentation
from pptx.util import Inches, Pt
from plotly.subplots import make_subplots
import streamlit.components.v1 as components  # 确保引入 components
from step7 import show_step_7_content
from step8 import show_step_8_content
import streamlit.components.v1 as components
import numpy as np # 先兼容numpy数值类型，转换为Python原生数字




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





#_______________________________________________________________________
# 1. 先定义这个名单（全局变量）


# ==========================================
# 全局配置：勾稽校验规则（动态年份版）
# ==========================================


# ==================== 1. 页面基础配置 (必须在最顶端且仅此一份) ====================
st.set_page_config(
    page_title="DigiLife 观衡·财精数据洞察平台 ", 
    page_icon="Digi.png",  # ✨ 修改点：加上 .png 后缀
    layout="wide"
)
# 放在这里最合适：页面刚开始渲染，就立刻注入这段隐形的保活脚本
# ==========================================
components.html("""
<script>
    // 600000 毫秒 = 10 分钟 (建议改成 5 分钟 300000 更稳)
    setInterval(() => {
        window.parent.document.dispatchEvent(new Event('mousemove'));
    }, 300000);
</script>
""", height=0, width=0)
# ==================== 2. 设置左上角 Logo ====================
# 注意：确保 Digi.png 文件和 app.py 在同一个文件夹里
try:
    st.logo(
        "Digi.png",       # ✨ 修改点：加上 .png 后缀
        icon_image="Digi.png" # ✨ 修改点：加上 .png 后缀
    )
except Exception as e:
    st.error(f"Logo 加载失败，请检查文件名是否为 Digi.png。错误信息: {e}")


# ==================== 辅助函数：单位嗅探 ====================
def get_report_unit(text):
    """该公司披露年报的金额单位"""
    if not text: return None
    m1 = re.search(r'(?:金额)?单位[：:\s]*((?:人民币)?[元十百千万亿]+)', text)
    if m1: return m1.group(1).strip()
    m2 = re.search(r'(人民币[十百千万亿]+元)', text)
    if m2: return m2.group(1).strip()
    if "人民币元" in text: return "人民币元"
    return None

# ==================== 后台引擎：调用 DeepSeek 提取单页表格 ====================
import base64

# ==================== 新增后台引擎：调用 Vision VLM 提取图片表格 ====================
def extract_single_page_vision(pdf_bytes, page_num, expected_name, api_key, base_url, model_name):
    """将 PDF 转为高清图片，使用视觉大模型提取表格"""
    try:
        # 1. 内存中将 PDF 页面转为 Base64 高清图
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if page_num < 1 or page_num > len(doc):
            return None, ""
        page = doc.load_page(page_num - 1)
        
        # 放大 3倍截图，保证文字清晰
        zoom_matrix = fitz.Matrix(3.0, 3.0) 
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        img_data = pix.tobytes("png")
        base64_image = base64.b64encode(img_data).decode('utf-8')
        doc.close()

        # 2. 设置读图的 Prompt
        prompt = f"""你是一个四大会计师事务所的资深数字化审计专家。
我为你提供了一张【保险公司年报的单页高清截图】，目标是精准提取：【{expected_name}】。
表格中的【数字是由图片构成的】，请发挥强大的视觉识别能力，提取所有文字和表格。
【强制要求】：
1. 所有的科目名、数字金额之间，必须被 "|" 隔开。严禁使用连续空格。
2. 精准对齐多级表头！如果有留白单元格，必须用 "|" 占位补齐！
3. 绝不能漏掉任何一行数据，保留金额里的逗号和括号。
4. 纯文本输出，不要使用 Markdown 代码块。不需要输出 SHEET_NAME 标签，直接排版。"""

        # 3. 呼叫视觉大模型
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            temperature=0.0
        )
        
        # 4. 解析结果
        result_text = response.choices[0].message.content.strip()
        result_text = re.sub(r'^```(csv|text)?\n?', '', result_text, flags=re.MULTILINE).replace("```", "").strip()
        
        lines = result_text.split('\n')
        parsed_data = []
        max_cols = 0
        for row in lines:
            clean_row = row.strip()
            if not clean_row: continue
            if re.match(r'^[\s\|-]+$', clean_row) and '-' in clean_row: continue
            
            if clean_row.startswith('|'): clean_row = clean_row[1:]
            if clean_row.endswith('|'): clean_row = clean_row[:-1]
            
            cols = [col.strip() for col in clean_row.split('|')] if '|' in clean_row else [clean_row]
            parsed_data.append(cols)
            max_cols = max(max_cols, len(cols))
            
        for row in parsed_data:
            if len(row) < max_cols:
                row.extend([''] * (max_cols - len(row)))
                
        return pd.DataFrame(parsed_data), "【提示：该页已使用 OCR 视觉引擎处理，原文本为图片结构】"
        
    except Exception as e:
        return None, f"图像处理失败: {str(e)}"
def extract_single_page(pdf_bytes, page_num, expected_name, api_key, base_url, model_name):
    """使用 pdfplumber 提取文本，并用 LLM 转换为结构化数据"""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            return None, ""
        page = pdf.pages[page_num - 1]
        raw_text = page.extract_text(layout=True)
        
    if not raw_text:
        return None, ""

    prompt = f"""你是一个四大会计师事务所的资深数字化审计专家。
当前任务：提取【{expected_name}】。
请将以下纯文本中的【段落文字】原样保留为一行，将【财务表格】转化为用 "|" 严格分隔的标准网格格式。
【强制要求】：
1. 所有的科目名、附注编号、数字金额之间，必须被 "|" 隔开。严禁使用连续空格。
2. 精准对齐多级表头！如果某个单元格是空的，必须用 "|" 占位补齐！
3. 绝不能漏掉任何一行数据，保留金额里的逗号和括号。
4. 纯文本输出，不要使用 Markdown 代码块。不需要输出 SHEET_NAME，直接输出转化后的数据。

以下是原始文本，请开始输出：
{raw_text}"""


    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    
    result_text = response.choices[0].message.content.strip()
    result_text = re.sub(r'^```(csv|text)?\n?', '', result_text, flags=re.MULTILINE)
    result_text = result_text.replace("```", "").strip()
    
    # 转换为 DataFrame
    lines = result_text.split('\n')
    parsed_data = []
    max_cols = 0
    for row in lines:
        clean_row = row.strip()
        if not clean_row: continue
        # 忽略大模型可能生成的 markdown 分割线
        if re.match(r'^[\s\|-]+$', clean_row) and '-' in clean_row: continue
        
        if clean_row.startswith('|'): clean_row = clean_row[1:]
        if clean_row.endswith('|'): clean_row = clean_row[:-1]
        
        if '|' not in clean_row:
            cols = [clean_row]
        else:
            cols = [col.strip() for col in clean_row.split('|')]
        parsed_data.append(cols)
        max_cols = max(max_cols, len(cols))
        
    for row in parsed_data:
        if len(row) < max_cols:
            row.extend([''] * (max_cols - len(row)))
            
    return pd.DataFrame(parsed_data), raw_text

# ==================== 后台引擎：调用 DeepSeek (混合双引擎) ====================
def ai_find_pages(pdf_bytes, api_key, target_tables, base_url, model_name):
    """混合双引擎：AI负责读目录推算主表，Python雷达负责深潜寻找附注表"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # 1. 提取前 60 页（扩大视野，确保覆盖大型公司报表区）
    toc_text = ""
    for i in range(min(60, len(doc))):
        page = doc.load_page(i)
        # 获取文本并去掉多余换行，保留前 1200 个字（通常页眉和目录都在这里）
        page_text = page.get_text("text").replace("\n", " ")
        # 压缩多余空格，节省 AI 的 Token，让它看得更多
        page_text = " ".join(page_text.split())
        toc_text += f"---第{i+1}页---\n{page_text[:1200]}\n"
    # 2. ⚡ 附注专属雷达特征矩阵
    feature_matrix = {
        "保险合同-未采用保费分配法按计量组成部分分析 (原保险)": [
            ["未采用保费分配法", "不采用保费分配法"], 
            ["计量组成部分", "履约现金流量"], 
            ["合同服务边际", "非金融风险调整", "未来现金流量"] 
        ],
        "保险合同-非PAA按未到期责任负债和已发生赔款负债分析 (原保险)": [
            ["未采用保费分配法", "不采用保费分配法"], 
            ["未到期责任负债"], 
            ["已发生赔款负债", "已发生赔款"]
        ],
        "保险合同-PAA按未到期责任负债和已发生赔款负债分析 (原保险)": [
            ["采用保费分配法"], 
            ["未到期责任负债"], 
            ["已发生赔款负债", "已发生赔款"]
        ],
        "保险合同-当期初始确认对资产负债表的影响": [
            ["初始确认的合同", "初始确认的保险合同", "初始确认的影响","如下表所示","如表所示"],  
            ["非亏损合同", "亏损合同"],  
            ["未来现金流出", "未来现金流入", "保险获取现金流量"] 
        ],
        "业务及管理费 (附注)": [
            ["业务及管理费"],
            ["职工薪酬", "折旧", "办公费", "宣传费", "租赁"] # 增加二级科目关键词
        ],
        "评估假设-折现率假设": [
            ["折现率假设", "折现率曲线","精算假设"]
        ],
        "投资资产": [
            [
                "投资组合情况",
                "投资资产",
                "投资组合",
                "投资资产组合",
                "按投资对象分类"
            ],
            [
                "现金及现金等价物",
                "定期存款",
                "债券",
                "债务",
                "股票",
                "基金",
                "长期股权投资",
                "投资性房地产"
            ]
        ],
    }
    
    simple_title_OR = {
        "保险服务收入表 (附注)": ["保险服务收入"],
        "保险服务支出/费用表 (附注)": ["保险服务支出", "保险服务费用"],
        "其他综合收益/损益表 (附注)": ["其他综合收益", "其他综合损益"]
    }
    
    context_anchors = ["项目注释", "财务报表附注", "报表附注", "项目附注"]
    currency_indicators = ["人民币百万元", "人民币千元", "人民币元", "单位：千元", "单位：百万元"]
    time_indicators = ["本年", "上年", "本期", "上期", "期末", "期初", "年初", "年末"]
    
    found_hints = {table: [] for table in target_tables if table in feature_matrix or table in simple_title_OR}
    page_type_map = {} 
    
    for i in range(20, len(doc)):
        page = doc.load_page(i)
        text_raw = page.get_text("text")
        text_clean = text_raw.replace("\n", "").replace(" ", "")
        header_text = text_clean[:800]
        
        is_group = "本集团" in header_text or "合并" in header_text
        is_company = "本公司" in header_text or "母公司" in header_text
        if is_group:
            page_type_map[i+1] = 'group'
        elif is_company:
            page_type_map[i+1] = 'company'
        
        is_in_notes = any(anchor in text_clean for anchor in context_anchors)
        has_currency = any(c in text_clean for c in currency_indicators)
        has_time = any(t in text_clean for t in time_indicators)
        is_continued_table = "(续)" in header_text or "（续）" in header_text
        
        try:
            has_actual_table = len(page.find_tables().tables) > 0
        except:
            has_actual_table = False
            
        is_table_page = is_continued_table or has_actual_table or (has_currency and has_time)
        
        if is_in_notes and is_table_page:
            for table, condition_groups in feature_matrix.items():
                if table in target_tables:
                    if "(原保险)" in table and ("再保险" in header_text or "分出" in header_text):
                        continue
                    if all(any(kw in text_clean for kw in group) for group in condition_groups):
                        if any(kw in header_text for kw in condition_groups[0]) or \
                           (len(condition_groups)>1 and any(kw in header_text for kw in condition_groups[1])):
                            if (i + 1) not in found_hints[table]:
                                found_hints[table].append(i + 1)
                                
            for table, any_of_words in simple_title_OR.items():
                if table in target_tables:
                    if "保险" in table and ("再保险" in header_text or "分出" in header_text):
                        continue
                    if any(kw in header_text for kw in any_of_words):
                        if (i + 1) not in found_hints[table]:
                            found_hints[table].append(i + 1)

    doc.close()
    
    for table, pages in found_hints.items():
        if not pages:
            continue
        group_pages = [p for p in pages if page_type_map.get(p) == 'group']
        company_pages = [p for p in pages if page_type_map.get(p) == 'company']
        
        if group_pages and company_pages:
            found_hints[table] = [p for p in pages if p not in company_pages]
    
    hint_text = "\n\n【⚡ Python程序附注雷达线索】\n"
    for table, pages in found_hints.items():
        if pages:
            pages = sorted(list(set(pages)))
            hint_text += f"- {table} 真实表格物理页码位于: {pages[:4]}\n"
    
    prompt = f"""你是一个顶级的寿险审计专家，任务是定位 PDF 中的核心财务报表页码。

【关键定位逻辑（双模式自适应）】
模式 A：目录驱动（适用于有目录的报表）
- 如果前几页存在“目录”或“Contents”，请识别目标报表对应的页码。
- 计算物理偏移量（封面/说明页占用的页数），得出真实的物理页码。

模式 B：标题驱动（适用于无目录或目录不全的报表，如太平人寿）
- 如果没有明确目录，请直接扫描文本中 `---第N页---` 标记下方的页眉或正文大标题。
- 例如：若在 `---第8页---` 下方看到“合并利润表”，则物理页码即为 8。

【通用执行准则】
1. 🎯 如果需求表单名称包含“（合并）”，优先寻找：
   合并资产负债表
   合并利润表
   合并现金流量表
   合并股东权益变动表

2. 🎯 如果需求表单名称包含“（公司）”，优先寻找：
   公司资产负债表
   公司利润表
   公司现金流量表
   公司股东权益变动表

3. 🎯 如果年报中没有区分“合并”和“公司”，仅出现：
   资产负债表
   利润表
   现金流量表
   股东权益变动表

则同一页码同时返回给：
   对应的（合并）
   对应的（公司）
4. 🎯 跨页逻辑：由于财务报表通常包含“(续)”，请务必返回所有相关的物理页码数组。
   - 示例：若第 3 页是资产负债表，第 4 页是其负债部分的续表，返回 [3, 4]。
5. 🎯 附注表线索（最高优先级）：对于带有“(附注)”或“保险合同”字样的复杂底表，请【无脑完全信任】下方提供的【Python程序附注雷达线索】，直接返回线索中的页码。
6. 🎯 特别提醒：现金流量表有时在目录中比较隐蔽，请仔细搜寻；若无目录，请在资产负债表和利润表之后的 5-10 页内搜寻其标题。

需求表单列表：
{json.dumps(target_tables, ensure_ascii=False)}

【待扫描文本内容（前 60 页）】：
{toc_text}

【⚡ Python程序附注雷达辅助线索】：
{hint_text}

【强制输出格式】
只输出合法 JSON，键为表单名，值为物理页码数组。找不到填 [0]。
⚠️ 警告：输出的 JSON 的键（Key）必须【完全包含】《需求表单列表》中的所有字段，【绝对不能有任何遗漏】！如果文中真的找不到，请严格对应填写 [0]。
格式示例：{{"合并利润表": [8, 9], "资产负债表 (合并优先)": [2, 3, 4]}}"""


    client = OpenAI(api_key=api_key, base_url=base_url) # 网址动态化
    response = client.chat.completions.create(
        model=model_name, # 模型动态化
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    result_text = response.choices[0].message.content.strip()
    result_text = result_text.replace("```json", "").replace("```", "").strip()
    return json.loads(result_text)

# ==================== 全量 CSS 美化 ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: "PingFang SC", "HarmonyOS Sans", "Microsoft YaHei", "Noto Sans SC", sans-serif !important; color: #4A5568; }
    .stApp { background: linear-gradient(160deg, #F8FAFC 0%, #F1F5F9 50%, #E2E8F0 100%); }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #B0BEC5; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #90A4AE; }
    ::selection { background: #B8C5D6; color: #1E293B; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #E2E8F0 0%, #CBD5E1 100%) !important; border-right: 1px solid #94A3B8; }
    [data-testid="stSidebar"] .stTextInput label, [data-testid="stSidebar"] .stMarkdown { color: #334155 !important; font-weight: 500; }
    h1 { color: #111827 !important; font-weight: 600 !important; letter-spacing: 2px; border-bottom: none !important; padding-bottom: 10px; background: transparent !important; }
    h3 { color: #1E293B !important; font-size: 17px !important; font-weight: 600 !important; letter-spacing: 1px; background: rgba(255, 255, 255, 0.45) !important; backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.8); border-radius: 8px !important; padding: 8px 18px !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03), inset 0 1px 0 rgba(255, 255, 255, 0.5) !important; width: fit-content; margin-bottom: 18px !important; margin-top: 10px !important; }
    .stButton > button { font-size: 14px !important; font-weight: 600 !important; letter-spacing: 1.5px; background-color: #94A3B8; color: #FFFFFF; border: 1px solid #64748B; border-radius: 4px; padding: 8px 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); transition: all 0.2s ease; }
    .stButton > button:hover { background-color: #64748B; border-color: #475569; color: #F8FAFC; transform: translateY(-1px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
    .stButton > button:active { transform: translateY(1px); box-shadow: none; }
    .stButton > button:disabled { background-color: #CBD5E1 !important; color: #94A3B8 !important; border-color: #CBD5E1 !important; box-shadow: none !important; cursor: not-allowed; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; background-color: transparent; border-bottom: 2px solid #CBD5E1; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; letter-spacing: 0.5px; background-color: #EDF2F7; color: #64748B; border-radius: 6px 6px 0 0; border: 1px solid #CBD5E1; border-bottom: none; padding: 10px 22px; transition: all 0.15s ease; }
    .stTabs [data-baseweb="tab"]:hover { background-color: #E2E8F0; color: #475569; }
    .stTabs [aria-selected="true"] { background-color: #94A3B8 !important; color: #FFFFFF !important; font-weight: 600 !important; border-color: #64748B !important; }
    .stTextInput > div > div > input, .stNumberInput > div > div > input { background-color: #FFFFFF !important; border: 1px solid #CBD5E1 !important; border-radius: 4px !important; color: #1E293B !important; font-weight: 500; transition: border-color 0.2s ease; }
    .stTextInput > div > div > input:focus, .stNumberInput > div > div > input:focus { border-color: #64748B !important; box-shadow: 0 0 0 2px rgba(100,116,139,0.15) !important; }
    .stMultiSelect [data-baseweb="tag"] { background-color: #CBD5E1 !important; color: #1E293B !important; border-radius: 4px !important; font-size: 13px !important; }
    [data-testid="stFileUploader"] section { border: 2px dashed #B0BEC5 !important; border-radius: 8px !important; background-color: #FAFBFC !important; transition: border-color 0.2s ease; }
    [data-testid="stFileUploader"] section:hover { border-color: #78909C !important; background-color: #F5F7FA !important; }
    hr { border: none !important; height: 1px !important; background: linear-gradient(to right, transparent, #B0BEC5, transparent) !important; margin: 20px 0 !important; }
    .info-card { background: #FFFFFF; border: 1px solid #E2E8F0; border-left: 4px solid #94A3B8; border-radius: 6px; padding: 20px 24px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
    .info-card h4 { color: #475569; margin: 0 0 8px 0; font-weight: 600; font-size: 15px; }
    .info-card p, .info-card li { color: #64748B; font-size: 14px; line-height: 1.8; }
    .info-card.pink { border-left-color: #D4A5A5; }
    .info-card.green { border-left-color: #A5C4B5; }
    .info-card.blue { border-left-color: #94A3B8; }
    .sidebar-brand { text-align: center; padding: 8px 0 16px 0; border-bottom: 1px solid #B0BEC5; margin-bottom: 20px; }
    .sidebar-brand .logo-text { font-size: 20px; font-weight: 700; color: #475569; letter-spacing: 3px; }
    .sidebar-brand .logo-sub { font-size: 11px; color: #94A3B8; letter-spacing: 4px; margin-top: 4px; }
    .placeholder-section { text-align: center; padding: 40px 20px; color: #94A3B8; }
    .placeholder-section .big-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.6; }
    .placeholder-section p { font-size: 14px; line-height: 2; color: #64748B; }
</style>
""", unsafe_allow_html=True)



# ==========================================
# 🔐 1. 初始化系统状态变量 
# ==========================================
for k, v in {'logged_in':False, 'user_role':None, 'api_key':"", 'base_url':"https://api.deepseek.com", 'model_name':"deepseek-chat"}.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 🚪 2. 独立登录界面 (极致压缩 + 旗舰科技发光主题)
# ==========================================
if not st.session_state['logged_in']:
    
    # 这段专属暗色 CSS 仅在登录界面生效，登录后自动恢复上方的主系统浅色配置
    st.markdown("""<style>
    header {visibility: hidden;}
    .stApp {background: linear-gradient(135deg, #040B16 0%, #0A1931 50%, #002266 100%); color: #E2E8F0;}
    /* 毛玻璃卡片底座，微微泛青蓝光 */
    [data-testid="column"]:nth-of-type(2) {background: rgba(255,255,255,0.08); backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px); border-radius: 20px; border: 1px solid rgba(0,243,255,0.3); box-shadow: 0 15px 35px rgba(0,0,0,0.5), inset 0 0 15px rgba(0,243,255,0.15); padding: 40px 30px; margin-top: 6vh;}
    
    /* 💎 寿研数智年报平台 - 银青渐变全息发光 */
    .title-glow {background: linear-gradient(90deg, #FFFFFF 0%, #76D2FF 50%, #00F3FF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; filter: drop-shadow(0 0 15px rgba(0,243,255,0.6));}

    div[data-baseweb="input"]>div, div[data-baseweb="select"]>div {background: rgba(0,0,0,0.4)!important; border: 1px solid rgba(0,243,255,0.3)!important; border-radius: 8px!important;}
    div[data-baseweb="input"]>div:focus-within, div[data-baseweb="select"]>div:focus-within {border-color: #00F3FF!important; box-shadow: 0 0 12px rgba(0,243,255,0.5)!important;}
    
    div[data-testid="stRadio"] label p {color: #FFFFFF!important; font-weight: bold!important; font-size: 14px!important;}
    
    /* CSS：AI 下拉框和 API 框的文字颜色为 #00F3FF */
    label p, .stSelectbox label p, .stTextInput label p {color: #00F3FF!important; letter-spacing: 1px!important;}
    input, .stSelectbox span {color: #FFFFFF!important; font-size: 14px!important;}
    
    /* 大按钮发光样式 */
    button[kind="primary"] {background: linear-gradient(90deg, #0044CC, #0088FF)!important; border: 1px solid rgba(0,243,255,0.5)!important; box-shadow: 0 0 15px rgba(0,136,255,0.4)!important; color: white!important; font-weight: bold!important; letter-spacing: 2px!important; border-radius: 8px!important; margin-top: 5px!important;}
    button[kind="primary"]:hover {box-shadow: 0 0 25px rgba(0,243,255,0.8)!important; transform: scale(1.02);}
    
    /* 将 popover 悬浮窗按钮伪装成靠右的超链接小字 */
    [data-testid="stPopover"] {display: flex; justify-content: flex-end;}
    [data-testid="stPopover"] button {background: transparent!important; border: none!important; box-shadow: none!important; color: #94A3B8!important; font-size: 12px!important; font-weight: normal!important; padding: 0!important; min-height: 0!important; text-decoration: underline; margin-top: 8px; margin-bottom: 15px;}
    [data-testid="stPopover"] button:hover {color: #00F3FF!important;}
    </style>""", unsafe_allow_html=True)

    _, col2, _ = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<div style='text-align:center; margin-bottom:30px;'><h1 style='font-size:32px; margin:0;'><span class='title-glow'>寿研数智年报平台</span></h1><p style='color:#76D2FF; font-size:11px; letter-spacing:4px; margin-top:8px; font-weight:bold;'>ACTUARIAL INTELLIGENCE</p></div>", unsafe_allow_html=True)
        
        u_type = st.radio("访问权限", ["普通用户", "项目组成员"], label_visibility="collapsed", horizontal=True)
        
        # 不管选什么角色，都显示密码输入框
        sec_code = st.text_input("安全验证", type="password", placeholder="请输入内部安全码") 
        
        # 字典映射压缩代码体积
        ai_map = {"阿里云百炼 (通义千问)": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"), "DeepSeek (深度求索)": ("https://api.deepseek.com", "deepseek-chat"), "月之暗面 (Kimi)": ("https://api.moonshot.cn/v1", "moonshot-v1-8k"), "智谱AI (GLM-4)": ("https://open.bigmodel.cn/api/paas/v4", "glm-4"), "OpenAI (ChatGPT)": ("https://api.openai.com/v1", "gpt-4o")}
        ai_pr = st.selectbox("选择您将使用的AI", list(ai_map.keys()) + ["自定义私有化节点"])
        
        d_url, d_mod = ai_map.get(ai_pr, ("https://api.deepseek.com", "deepseek-chat"))
        if ai_pr == "自定义私有化节点":
            d_url, d_mod = st.text_input("RPC 接口地址", "https://api.deepseek.com"), st.text_input("指定模型版本", "deepseek-chat")

        api_input = st.text_input("请填写您使用AI的API Key", type="password", placeholder=" sk-... (不填则仅开放年报检测、数据合并及可视化本地分析功能)")
        
        # 条件判断：只有选了 OpenAI 时才显示红字警告，否则用一个很小的空白顶位
        if "OpenAI" in ai_pr:
            st.markdown("<p style='font-size:11px; color:#F87171; text-align:right; margin-top:4px; margin-bottom:0;'>⚠️ 严禁向境外节点传输涉密数据</p>", unsafe_allow_html=True)
        
        # 伪装成超链接小字的帮助菜单
        with st.popover("如何获取API key?"):
            st.markdown("**1.** 前往各大模型官方开放平台注册账号。\n\n**2.** 在控制台生成 `sk-` 开头的密钥。\n\n**3.** 复制填入上方输入框即可体验 AI 功能。")

        # 启动大按钮
        if st.button("启 动 系 统", type="primary", use_container_width=True):
            # 分别校验普通用户和项目组成员的密码
            if u_type == "普通用户" and sec_code != "KPMG1234": 
                st.error("❌ 拒绝访问：普通用户安全码错误")
            elif u_type == "项目组成员" and sec_code != "KPMG666": 
                st.error("❌ 拒绝访问：项目组成员安全码错误")
            else: 
                st.session_state.update({'logged_in':True, 'user_role':u_type, 'api_key':api_input, 'base_url':d_url, 'model_name':d_mod})
                st.rerun()

        st.markdown("<div style='text-align:center; color:#94A3B8; font-size:11px; margin-top:30px; letter-spacing:1px;'>系统版本：v3.0 (Alpha) © 2026<br>Developed by 林友沐Bella@KPMG</div>", unsafe_allow_html=True)

    # 阻止程序继续往下渲染主系统界面
    st.stop()
# ==========================================
# 📊 3. 主系统界面 (根据角色分发权限)
# ==========================================
else:
    # 代码规范锁：0123456789
    api_key = st.session_state.get('api_key', "")
    base_url = st.session_state.get('base_url', "https://api.deepseek.com")
    model_name = st.session_state.get('model_name', "deepseek-chat")
    user_role = st.session_state.get('user_role', "普通用户") 

    # 顶部状态栏与退出按钮
    top_col1, top_col2 = st.columns([8, 1])
    with top_col1:
        st.markdown(
            f"<div class='no-print' style='color: #6c757d; font-size: 14px; margin-top: 8px;'>"
            f"当前身份：<b>{user_role}</b> | 欢迎使用寿研数智分析平台"
            f"</div>", 
            unsafe_allow_html=True
        )
    with top_col2:
        if st.button("退出登录"):
            st.session_state['logged_in'] = False
            st.rerun()
            
    # ==================== 主界面标题 ====================
    st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'>", unsafe_allow_html=True)
    st.markdown("<h1 class='no-print' style='font-weight:700; padding-top:10px;'>寿研数智・年报处理平台</h1>", unsafe_allow_html=True)

    # ---------------- 核心权限控制 ----------------
    if st.session_state['user_role'] == "项目组成员":
        # 如果是项目组成员，显示 Step 6 到 Step 8 三个 Tab
        tab6, tab7, tab8 = st.tabs([
            " 📊 Step 6 ／ 自定义对标分析 ",
            " 🖼️ Step 7 ／ 公司级对标报告 ",
            " 📈 Step 8 ／ 行业分类统计分析 ",
        ])
        
        # ─────────── 以下是各 Tab 对应的内容 ───────────
        KPMG_CATEGORIES = {
            "Primary Colors": {"KPMG Blue": "#00338D", "Cobalt Blue": "#1E49E2", "Dark Blue": "#0C233C", "Light Blue": "#ACEAFF", "Pacific Blue": "#00B8F5", "Purple": "#7213EA", "Pink": "#FD349C"},
            "Accent Colors": {"Blue": "#76D2FF", "Dark Purple": "#510DBC", "Light Purple": "#B497FF", "Dark Pink": "#AB0D82", "Light Pink": "#FFA3DA", "Dark Green": "#098E7E", "Green": "#00C0AE", "Light Green": "#63EBB2"},
            "Traffic Light": {"Red": "#ED2124", "Amber": "#F1C44D", "Positive Green": "#269924"}
        }
        DEFAULT_COLORS = list(KPMG_CATEGORIES["Primary Colors"].values()) + list(KPMG_CATEGORIES["Accent Colors"].values())
        
        import streamlit as st
        import pandas as pd
        import numpy as np
        import re
        import plotly.graph_objects as go
        import plotly.express as px

        # ─────────── 全局常量（保留原KPMG规范） ───────────
        KPMG_COLOR_MAP = {
            "Lightest": "#BFE8FF",   # Pacific Blue (light)
            "Light": "#76D2FF",      # Blue (original Light Blue)
            "Primary": "#1E49E2",    # Cobalt Blue
            "Dark": "#00338D",       # KPMG Blue (original Primary Blue)
        }
        DEFAULT_COLORS = list(KPMG_COLOR_MAP.values())

        # ─────────── Step 6 可视化分析面板（改造后完整代码） ───────────
        with tab6:
            st.markdown("### 📊 自定义对标分析")

            # ── 数据源选择 ───────────────────────────────────────────────────────
            if 'integrated_data' not in st.session_state:
                st.session_state['integrated_data'] = None

            source_choice = st.radio(
                "数据源选择", ["直接引用集成后的数据", "上传集成表 Excel"], horizontal=True
            )
            df_raw = None

            if source_choice == "上传集成表 Excel":
                viz_file = st.file_uploader("上传行业集成目标表", type=["xlsx"])
                if viz_file:
                    df_raw = pd.read_excel(viz_file)
                    st.session_state['integrated_data'] = df_raw
            else:
                df_raw = st.session_state.get('integrated_data')

            if df_raw is None:
                st.info("💡 请先完成数据集成或上传目标底稿。")
                st.stop()

            # ==========================================
            # 🌟 提速秘籍 1：锁定数据预处理 (只算一次)
            # 改造点：基于报告年度+月度生成标准化报告期间，生成跨期计算专用宽表
            # ==========================================
            @st.cache_data(show_spinner=False)
            def prepare_viz_data(df_in):
                df_clean = df_in.copy()
                # 1. 列名清洗（兼容Excel脏格式）
                df_clean.columns = (
                    df_clean.columns.astype(str)
                    .str.strip()
                    .str.replace('\n', '', regex=False)
                    .str.replace('\r', '', regex=False)
                    .str.replace('\ufeff', '', regex=False)
                )

                # ========== 适配你的真实列名：报告年份 → 报告年度；报告月份 → 报告月度 ==========
                rename_mapping = {
                    "报告年份": "报告年度",
                    "报告月份": "报告月度"
                }
                df_clean.rename(columns=rename_mapping, inplace=True)

                # ========== 校验关键时间字段是否存在 ==========
                required_time_cols = ["报告年度", "报告月度"]
                missing_cols = [c for c in required_time_cols if c not in df_clean.columns]
                if missing_cols:
                    st.error(f"❌ 数据缺少必要字段：{','.join(missing_cols)}")
                    st.info(f"✅ 当前数据表全部列名：{list(df_clean.columns)}")
                    raise ValueError(f"缺失时间字段：{missing_cols}")

                # ── 核心改造1：基于报告年度+报告月度生成标准化报告期间 ──────────────
                # 清洗报告年度：转字符串、去掉末尾.0（如2025.0 → 2025）
                df_clean['报告年度'] = df_clean['报告年度'].astype(str).str.replace('.0', '', regex=False).str.strip()
                # 清洗报告月度：提取数字、补零到两位（如1→01、12→12、"1月"→01）
                df_clean['报告月度'] = df_clean['报告月度'].astype(str).str.extract(r'(\d+)', expand=False).str.zfill(2).str.strip()
                # 生成标准化报告期间：YYYY‑MM格式（如2025‑06、2025‑12）
                df_clean['报告期间'] = df_clean['报告年度'] + '-' + df_clean['报告月度']
                # 按报告期间排序的key（用于后续排序）
                df_clean['期间排序key'] = df_clean['报告年度'].astype(int) * 100 + df_clean['报告月度'].astype(int)

                # 2. 数值列自动识别
                val_col = "(百万)人民币" if "(百万)人民币" in df_clean.columns else df_clean.columns[-1]

                # 3. 去重：保留月度维度的唯一性
                dedup_cols = ['公司', '报告期间', '字段名']
                if '类别' in df_clean.columns:
                    dedup_cols.append('类别')
                df_clean = df_clean.drop_duplicates(subset=dedup_cols, keep='first')

                # 4. 标准透视表：按公司+报告期间+字段名聚合（保留月度粒度）
                df_pivot = (
                    df_clean.groupby(['公司', '报告期间', '字段名'])[val_col]
                    .sum().unstack('字段名').reset_index()
                )

                # ── 核心改造2：生成跨期计算专用宽表（行=公司，列=指标@报告期间） ──────────────
                df_cross_period = df_clean.pivot_table(
                    index='公司',
                    columns=['字段名', '报告期间'],
                    values=val_col,
                    aggfunc='sum'
                ).reset_index()
                # 扁平化列名，生成用户可直接引用的格式
                # 仅对 (字段名, 报告期间) 元组列做 "字段名@报告期间" 转换；
                # '公司' 列（可能是标量或 ('公司','') 元组）统一保留为 '公司'。
                # 注：df_cross_period 已由 pivot_table(index='公司') 自带 '公司' 列，
                #     无需再与 df_pivot 合并，故不再做冗余 merge。
                df_cross_period.columns = [
                    ('公司' if col[0] == '公司' else f"{col[0]}@{col[1]}") if isinstance(col, tuple) else col
                    for col in df_cross_period.columns
                ]

                # 5. 提取所有可选列表
                all_fields = sorted([x for x in df_clean['字段名'].unique().tolist() if isinstance(x, str) and x.strip()])
                all_types = sorted(df_clean['类别'].dropna().astype(str).unique().tolist()) if '类别' in df_clean.columns else []
                all_co_types = sorted(df_clean['公司类型'].dropna().astype(str).unique().tolist()) if '公司类型' in df_clean.columns else []

                all_periods_sorted = sorted(
                    df_clean['报告期间'].unique().tolist(),
                    key=lambda x: int(x.split('-')[0]) * 100 + int(x.split('-')[1])
                )
                all_cross_fields = [col for col in df_cross_period.columns if '@' in col]

                return df_clean, df_pivot, df_cross_period, val_col, all_fields, all_types, all_co_types, all_periods_sorted, all_cross_fields

            # ==========================================
            # 调用缓存的数据处理函数 (只算一次)
            # ==========================================
            df_clean, df_pivot, df_cross_period, val_col, all_fields, all_types, all_co_types, all_periods_sorted, all_cross_fields = prepare_viz_data(df_raw)

            # ── 动态期间颜色计算 (极速，无需缓存) ──
            n_periods = len(all_periods_sorted)
            dynamic_period_colors = {}
            target_colors = []
            if n_periods == 3:
                target_colors = [KPMG_COLOR_MAP["Light"], KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            elif n_periods == 2:
                target_colors = [KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            else:
                target_colors = [KPMG_COLOR_MAP["Lightest"], KPMG_COLOR_MAP["Light"], KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            num_colors_to_use = len(target_colors)
            if n_periods > 0:
                for idx, period in enumerate(all_periods_sorted):
                    color_index = 0
                    if n_periods > 1:
                        proportion = idx / (n_periods - 1)
                        color_index = int(proportion * (num_colors_to_use - 1))
                    color_index = min(color_index, num_colors_to_use - 1)
                    dynamic_period_colors[str(period)] = target_colors[color_index]

            # ==========================================
            # 封装交互展示区
            # 说明：原先使用 @st.fragment，但 fragment 位于 with st.tabs() 内时，
            # 在部分 Streamlit 版本中控件交互无法触发重渲染，导致无法切换图表类型/公司。
            # 改为普通函数：任意控件变化都会触发整段重跑（prepare_viz_data 已缓存，性能无忧）。
            # ==========================================
            def render_viz_dashboard(df_clean, df_pivot, df_cross_period, val_col, all_fields, all_types, all_co_types, dynamic_period_colors, all_cross_fields):
                import re, plotly.graph_objects as go, plotly.express as px

                def safe_num(s):
                    return pd.to_numeric(
                        s.astype(str).str.strip()
                        .str.replace(",", "", regex=False)
                        .str.replace("(", "-", regex=False)
                        .str.replace(")", "", regex=False)
                        .replace(["", "nan", "None", "未披露", "—", "-"], np.nan),
                        errors="coerce",
                    )

                def safe_formula_eval(wide_df, formula, cross_df=None):
                    expr = str(formula).strip()
                    if not expr:
                        raise ValueError("公式为空")
                    local_dict = {}
                    work = wide_df.copy()
                    if cross_df is not None:
                        work = work.merge(cross_df, on='公司', how='left')
                    missing = []
                    for i, ref in enumerate(re.findall(r"\[(.*?)\]", expr)):
                        key = f"V{i}"
                        if '@' in ref and cross_df is not None and ref in work.columns:
                            series = work[ref]
                        elif ref in work.columns:
                            series = work[ref]
                        else:
                            missing.append(ref)
                            series = pd.Series(np.nan, index=work.index)
                        local_dict[key] = safe_num(series)
                        expr = expr.replace(f"[{ref}]", key)
                    if missing:
                        raise ValueError("无法识别的指标引用：" + "、".join(missing) + "（请检查字段名与报告期间是否正确）")
                    try:
                        return pd.Series(
                            pd.eval(expr, local_dict=local_dict, engine="python"),
                            index=work.index,
                        ).replace([np.inf, -np.inf], np.nan)
                    except Exception as e:
                        raise ValueError(f"公式计算出错：{e}")

                # ── 核心配置面板 ───────────────────────────────────────────────────────
                with st.expander("🛠️ 核心配置面板", expanded=True):
                    r1c1, r1c2, r1c3 = st.columns([1.5, 1, 1])
                    is_pct_stack_mode = False

                    with r1c1:
                        chart_type = st.selectbox("📈 1. 图表类型", ["簇状柱状图", "堆积柱状图", "折线对比图", "饼图", "内外环结构对比图", "散点图"])

                        if chart_type == "散点图":
                            calc_mode, plot_df_base = "散点图", pd.DataFrame()
                            st.caption("💡 支持高级公式：可写 [字段]（当期）或 [字段@报告期间]（跨期），例如 [总资产@2025-12] / [总资产@2025-06]、[总资产] - [总负债]")

                            # 便捷选择：改动后点击按钮即可把所选指标填入下方公式框；公式框始终可手动编写任意表达式
                            sc_cols = st.columns(2)
                            with sc_cols[0]:
                                scatter_mode = st.radio("散点图模式", ["单期指标模式", "跨期公式模式"], horizontal=True, key="scatter_mode")
                            with sc_cols[1]:
                                if scatter_mode == "跨期公式模式" and all_cross_fields:
                                    x_pick = st.selectbox("X轴跨期指标(便捷)", all_cross_fields, index=0, key="scatter_x_cross")
                                    y_pick = st.selectbox("Y轴跨期指标(便捷)", all_cross_fields, index=min(1, len(all_cross_fields)-1), key="scatter_y_cross")
                                    if st.button("↧ 填入 X/Y 公式", key="fill_cross"):
                                        st.session_state["scatter_x_formula"] = f"[{x_pick}]"
                                        st.session_state["scatter_y_formula"] = f"[{y_pick}]"
                                elif all_fields:
                                    x_pick = st.selectbox("X轴字段(便捷)", all_fields, index=0, key="scatter_x_field")
                                    y_pick = st.selectbox("Y轴字段(便捷)", all_fields, index=min(1, len(all_fields)-1), key="scatter_y_field")
                                    if st.button("↧ 填入 X/Y 公式", key="fill_single"):
                                        st.session_state["scatter_x_formula"] = f"[{x_pick}]"
                                        st.session_state["scatter_y_formula"] = f"[{y_pick}]"
                                else:
                                    st.info("暂无可用的指标字段。")

                            # 高级公式输入（核心功能，始终可编辑）
                            x_default = f"[{all_fields[0]}]" if all_fields else ""
                            y_default = f"[{all_fields[min(1, len(all_fields)-1)]}]" if all_fields else ""
                            x_formula = st.text_input("✏️ X轴公式（支持 [字段] 与 [字段@报告期间]）", value=x_default, key="scatter_x_formula")
                            y_formula = st.text_input("✏️ Y轴公式（支持 [字段] 与 [字段@报告期间]）", value=y_default, key="scatter_y_formula")

                            # 轴标题自定义
                            x_axis_title_custom = st.text_input("X轴显示名称", value=x_formula.replace('[', '').replace(']', ''), key="scatter_x_title")
                            y_axis_title_custom = st.text_input("Y轴显示名称", value=y_formula.replace('[', '').replace(']', ''), key="scatter_y_title")

                            # 公司+期间选择
                            all_cos_list = sorted(df_pivot['公司'].unique().tolist())
                            selected_cos = st.multiselect("🏗️ 选择公司", all_cos_list, default=all_cos_list[:min(8, len(all_cos_list))], key="scatter_selected_cos")
                            scatter_periods = st.multiselect("📅 选择报告期间", all_periods_sorted, default=all_periods_sorted[-1:], key="scatter_periods")

                        elif "环" in chart_type or chart_type == "饼图":
                            calc_mode = "结构分析"
                            selected_multi_fields = st.multiselect("🎯 选择构成指标", all_fields, default=all_fields[:min(3, len(all_fields))])
                            selected_cos = st.selectbox("🏗️ 选择展示公司", sorted(df_pivot['公司'].unique().tolist()))
                            # 饼图/环形图支持选择报告期间
                            selected_period = st.selectbox("📅 选择报告期间", all_periods_sorted, index=len(all_periods_sorted)-1)
                            plot_df_base = df_clean[(df_clean['字段名'].isin(selected_multi_fields)) & (df_clean['公司'] == selected_cos) & (df_clean['报告期间'] == selected_period)].copy().rename(columns={val_col: 'final_val'})

                        else:
                            if chart_type == "堆积柱状图":
                                stack_sub = st.radio("堆积模式", ["单指标 / 公式", "多指标占比"], horizontal=True, key="stack_sub_mode")
                                is_pct_stack_mode = (stack_sub == "多指标占比")

                            if is_pct_stack_mode:
                                calc_mode = "多指标占比"
                                pct_field_pool = sorted(df_clean[df_clean['类别'] == st.selectbox("🗂️ 按类别筛选指标", ["全部类别"] + all_types, key="pct_type_filter")]['字段名'].unique().tolist()) if all_types and st.session_state.get("pct_type_filter") not in [None, "全部类别"] else all_fields
                                selected_pct_fields = st.multiselect("🎯 选择堆积指标", pct_field_pool, default=pct_field_pool[:min(3, len(pct_field_pool))], key="pct_stack_fields")
                                plot_df_base = df_clean[df_clean['字段名'].isin(selected_pct_fields)][['公司', '报告期间', '字段名', val_col]].copy().rename(columns={val_col: 'final_val'}) if selected_pct_fields else pd.DataFrame(columns=['公司', '报告期间', '字段名', 'final_val'])
                            else:
                                calc_mode = st.radio("数据模式", ["单指标直显", "自定义公式运算"], horizontal=True)
                                if calc_mode == "单指标直显":
                                    filtered_fields = sorted(df_clean[df_clean['类别'] == st.selectbox("🗂️ 按类别筛选指标", ["全部类别"] + all_types, key="type_filter_single")]['字段名'].unique().tolist()) if all_types and st.session_state.get("type_filter_single") not in [None, "全部类别"] else all_fields
                                    target_field = st.selectbox("🎯 选择显示指标", filtered_fields)
                                    plot_df_base = df_pivot[['公司', '报告期间', target_field]].rename(columns={target_field: 'final_val'}).copy()
                                else:
                                    v1, v2 = st.columns(2)
                                    var_a = v1.selectbox("变量 A", all_fields, index=0)
                                    var_b = v2.selectbox("变量 B", ["无"] + all_fields, index=1 if len(all_fields) > 1 else 0)
                                    formula_input = st.text_input("✏️ 自定义公式 (使用 A 和 B)", value="A - B")
                                    try:
                                        A_data, B_data = safe_num(df_pivot[var_a]).fillna(0), (safe_num(df_pivot[var_b]).fillna(0) if var_b != "无" else 0)
                                        df_pivot['final_val'] = pd.Series(pd.eval(formula_input, local_dict={'A': A_data, 'B': B_data}), index=df_pivot.index).replace([np.inf, -np.inf], np.nan).fillna(0)
                                        plot_df_base = df_pivot[['公司', '报告期间', 'final_val']].copy()
                                    except Exception as e:
                                        st.error(f"公式无效: {e}")
                                        plot_df_base = pd.DataFrame(columns=['公司', '报告期间', 'final_val'])

                            all_cos_list = sorted(df_pivot['公司'].unique().tolist())
                            if all_co_types:
                                co_type_sel = st.selectbox("🏢 按公司类型快速选择", ["不按公司类型筛选"] + all_co_types, key="co_type_sel")
                                if co_type_sel != "不按公司类型筛选" and st.session_state.get('_prev_co_type_sel') != co_type_sel:
                                    st.session_state['selected_cos_ms'] = sorted(df_clean[df_clean['公司类型'] == co_type_sel]['公司'].unique().tolist())
                                    st.session_state['_prev_co_type_sel'] = co_type_sel
                            selected_cos = st.multiselect("🏗️ 选择对比公司", all_cos_list, default=all_cos_list[:min(2, len(all_cos_list))], key="selected_cos_ms")

                    with r1c2:
                        x_axis_mode = "散点视角" if chart_type == "散点图" else (st.radio("🔍 布局视角", ["以公司为横轴", "以期间为横轴"]) if "环" not in chart_type else "结构视角")
                        decimals = st.number_input("🔢 小数位数", 0, 4, 0)
                        show_value = st.toggle("✅ 显示数据标签", value=True)

                    with r1c3:
                        unit_options = {"原始数值": 1.0, "亿元": 0.01, "十亿元": 0.001, "百分比(%)": 100.0}
                        if chart_type == "散点图":
                            ux, uy = st.columns(2)
                            with ux:
                                selected_unit_x = st.selectbox("📏 X轴单位", list(unit_options.keys()), key="scatter_unit_x")
                                multiplier_x = unit_options[selected_unit_x]
                            with uy:
                                selected_unit_y = st.selectbox("📏 Y轴单位", list(unit_options.keys()), key="scatter_unit_y")
                                multiplier_y = unit_options[selected_unit_y]
                            # 散点图不使用统一的 multiplier / y_axis_title 注解，但 line 977 会引用 selected_unit，这里给默认值避免 NameError
                            selected_unit = "原始数值"
                            multiplier = 1.0
                            y_axis_title = "单位"
                        else:
                            selected_unit = st.selectbox("📏 数值单位换算", list(unit_options.keys()))
                            multiplier = unit_options[selected_unit]
                            y_axis_title = st.text_input("📝 Y轴单位显示修改", value=f"单位: {selected_unit.split(' ')[0]}")
                        is_transparent = st.toggle("🌈 开启透明背景模式")
                        show_avg = st.checkbox("平均值线") if "柱" in chart_type else False
                        avg_color = st.color_picker("基准线颜色", value="#ED2124") if show_avg else "#ED2124"

                # ── 数据计算与筛选 ───────────────────────────────────────────────────────
                if chart_type == "散点图":
                    scatter_df = df_pivot.copy()
                    # 核心：调用支持跨期的公式计算函数，传入跨期宽表
                    try:
                        scatter_df["X"] = safe_formula_eval(scatter_df, x_formula, df_cross_period) * multiplier_x
                        scatter_df["Y"] = safe_formula_eval(scatter_df, y_formula, df_cross_period) * multiplier_y
                    except ValueError as e:
                        st.error(f"❌ 散点图数据获取失败：{e}")
                        st.stop()
                    # 筛选公司和期间
                    plot_df = scatter_df[scatter_df["公司"].isin(selected_cos) & scatter_df["报告期间"].isin(scatter_periods)].dropna(subset=["X", "Y"]).copy()
                    if plot_df.empty:
                        st.warning("散点图暂无可用数据，请检查公式、公司或报告期间。")
                        st.stop()
                    color_val = "公司"
                else:
                    if plot_df_base.empty:
                        st.warning("暂无数据，请检查筛选条件。")
                        st.stop()
                    if calc_mode in ("结构分析", "多指标占比"):
                        cos_filter = [selected_cos] if isinstance(selected_cos, str) else selected_cos
                        plot_df, color_val = plot_df_base[plot_df_base['公司'].isin(cos_filter)].copy(), "字段名"
                    else:
                        plot_df = plot_df_base[plot_df_base['公司'].isin(selected_cos)].copy()
                        color_val = "报告期间" if x_axis_mode == "以公司为横轴" else "公司"
                    plot_df['绘制金额'] = safe_num(plot_df['final_val']).fillna(0) * multiplier

                # ── 自定义图例标签与颜色 ───────────────────────────────────────────────────────
                st.markdown("#### 🎨 自定义图例标签与颜色")
                legend_col = "公司" if chart_type == "散点图" else color_val
                unique_items = sorted(plot_df[legend_col].dropna().unique().tolist())
                rename_map, color_map, c_cols = {}, {}, st.columns(4)
                for i, item in enumerate(unique_items):
                    with c_cols[i % 4]:
                        st.caption(f"原始值: {item}")
                        new_label = st.text_input("显示名称", value=str(item), key=f"rename_{chart_type}_{item}")
                        default_c = dynamic_period_colors.get(str(item), DEFAULT_COLORS[i % len(DEFAULT_COLORS)] if 'DEFAULT_COLORS' in globals() else "#1E49E2")
                        new_color = st.color_picker("选择颜色", value=default_c, key=f"color_{chart_type}_{item}")
                        rename_map[item], color_map[new_label] = new_label, new_color
                if chart_type != "散点图":
                    plot_df[color_val] = plot_df[color_val].map(rename_map)
                else:
                    plot_df["_legend_show"] = plot_df[color_val].map(rename_map).fillna(plot_df[color_val])

                # ── 图表渲染 ───────────────────────────────────────────────────────
                fig, fmt = go.Figure(), f'.{decimals}f'
                suffix, label_fmt = ("%" if selected_unit == "百分比(%)" else ""), f'%{{y:.{decimals}f}}{"%" if selected_unit == "百分比(%)" else ""}'

                if chart_type == "散点图":
                    for item in rename_map.values():
                        d = plot_df[plot_df["_legend_show"] == item]
                        if d.empty: continue
                        fig.add_trace(go.Scatter(
                            x=d["X"], y=d["Y"], name=str(item),
                            mode="markers+text" if show_value else "markers",
                            text=d["公司"] if show_value else None,
                            textposition="top center",
                            marker=dict(size=14, color=color_map.get(item, "#1E49E2"), line=dict(width=1.4, color="white")),
                            customdata=np.stack([d["公司"], d["报告期间"]], axis=-1),
                            hovertemplate="<b>%{customdata[0]}</b><br>期间：%{customdata[1]}<br>X=%{x}<br>Y=%{y}<extra></extra>"
                        ))
                    _ux_label = "" if selected_unit_x == "原始数值" else f"（单位：{selected_unit_x}）"
                    _uy_label = "" if selected_unit_y == "原始数值" else f"（单位：{selected_unit_y}）"
                    fig.update_xaxes(title=x_axis_title_custom + _ux_label, zeroline=True, zerolinecolor="#999", showgrid=True, gridcolor="#f0f0f0")
                    fig.update_yaxes(title=y_axis_title_custom + _uy_label, zeroline=True, zerolinecolor="#999", showgrid=True, gridcolor="#f0f0f0")

                elif "柱状图" in chart_type:
                    barmode = 'group' if "簇状" in chart_type else 'relative'
                    if is_pct_stack_mode:
                        plot_df['x_label'] = plot_df['公司'] + ' ' + plot_df['报告期间']
                        plot_df['_total'] = plot_df.groupby('x_label')['绘制金额'].transform('sum').replace(0, np.nan)
                        plot_df['绘制占比'] = (plot_df['绘制金额'] / plot_df['_total'] * 100).fillna(0)
                        for item in rename_map.values():
                            d = plot_df[plot_df[color_val] == item]
                            fig.add_trace(go.Bar(x=d['x_label'], y=d['绘制占比'], name=str(item), marker_color=color_map[item],
                                text=d.apply(lambda r: f"{r['绘制占比']:.{decimals}f}%<br>{r['绘制金额']:.{decimals}f}", axis=1) if show_value else None, textposition='inside'))
                        fig.update_yaxes(range=[0, 105]); barmode = 'relative'
                    else:
                        for item in rename_map.values():
                            d = plot_df[plot_df[color_val] == item]
                            fig.add_trace(go.Bar(x=d["公司" if color_val == "报告期间" else "报告期间"], y=d["绘制金额"], name=str(item), marker_color=color_map[item],
                                text=d["绘制金额"] if show_value else None, texttemplate=label_fmt if show_value else None, textposition='outside'))
                        fig.update_layout(barmode=barmode)

                elif "折线对比图" in chart_type:
                    for item in rename_map.values():
                        d = plot_df[plot_df[color_val] == item]
                        fig.add_trace(go.Scatter(x=d["公司" if color_val == "报告期间" else "报告期间"], y=d["绘制金额"], name=str(item),
                            mode='lines+markers+text' if show_value else 'lines+markers', marker_color=color_map[item],
                            text=d["绘制金额"], texttemplate=label_fmt, textposition="top center"))

                elif chart_type == "饼图":
                    d = plot_df[plot_df['报告期间'] == plot_df['报告期间'].max()]
                    fig = px.pie(d, values='绘制金额', names=color_val, hole=0.4, color=color_val, color_discrete_map=color_map)
                    fig.update_traces(textinfo='percent+label' if show_value else 'percent')

                elif chart_type == "内外环结构对比图":
                    periods_ring = sorted(plot_df['报告期间'].unique().tolist())
                    if len(periods_ring) < 2: st.warning("环形图对比需要至少两个报告期间的数据。")
                    else:
                        d_outer, d_inner = plot_df[plot_df['报告期间'] == periods_ring[-1]], plot_df[plot_df['报告期间'] == periods_ring[0]]
                        fig.add_trace(go.Pie(labels=d_outer[color_val], values=d_outer['绘制金额'], hole=0.7, name=periods_ring[-1], marker=dict(colors=[color_map[f] for f in d_outer[color_val]]), textinfo='percent+label' if show_value else 'percent'))
                        fig.add_trace(go.Pie(labels=d_inner[color_val], values=d_inner['绘制金额'], hole=0.4, name=periods_ring[0], domain={'x': [0.15, 0.85], 'y': [0.15, 0.85]}, marker=dict(colors=[color_map[f] for f in d_inner[color_val]]), textinfo='percent' if show_value else 'none'))
                        fig.update_layout(annotations=[dict(text=f'内:{periods_ring[0]}<br>外:{periods_ring[-1]}', x=0.5, y=0.5, font_size=12, showarrow=False)])

                # ── 图表布局优化 ───────────────────────────────────────────────────────
                bg_color = "rgba(0,0,0,0)" if is_transparent else "white"
                if show_avg and "柱" in chart_type and not is_pct_stack_mode:
                    avg_v = plot_df['绘制金额'].mean()
                    fig.add_hline(y=avg_v, line_dash="dash", line_color=avg_color, annotation_text=f"平均: {avg_v:{fmt}}{suffix}", annotation_font=dict(color=avg_color))

                fig.update_layout(font_family="Microsoft YaHei", plot_bgcolor=bg_color, paper_bgcolor=bg_color,
                    margin=dict(t=120, l=10, r=10, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    annotations=[] if chart_type == "散点图" else [dict(x=0, y=1.18, xref='paper', yref='paper', text=f"<b>{y_axis_title}</b>", showarrow=False, font=dict(size=14, color="#333333"), xanchor='left')])
                fig.update_xaxes(showgrid=True if chart_type == "散点图" else False)
                fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")

                # ── 渲染图表与明细数据 ───────────────────────────────────────────────────────
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("📄 查看底层数据明细"):
                    if chart_type == "散点图":
                        # 散点图明细展示：公司 / 期间 / X / Y + 公式引用的原始字段
                        def _extract_fields(formula):
                            _f = []
                            for _p in str(formula).split('['):
                                if ']' in _p:
                                    _f.append(_p.split(']')[0])
                            return _f
                        _tokens = _extract_fields(x_formula) + _extract_fields(y_formula)
                        _plot_cols, _cross_cols = [], []
                        for _t in _tokens:
                            if '@' in _t:
                                if _t in df_cross_period.columns and _t not in _cross_cols:
                                    _cross_cols.append(_t)
                            else:
                                if _t in plot_df.columns and _t not in _plot_cols:
                                    _plot_cols.append(_t)
                        _detail_cols = [c for c in ["公司", "报告期间", "X", "Y"] if c in plot_df.columns]
                        _detail = plot_df[_detail_cols].copy()
                        if _cross_cols:
                            _detail = _detail.merge(df_cross_period[["公司"] + _cross_cols], on="公司", how="left")
                        for _c in _plot_cols:
                            if _c not in _detail.columns:
                                _detail[_c] = plot_df[_c]
                        st.dataframe(_detail, use_container_width=True)
                    else:
                        st.dataframe(plot_df, use_container_width=True)

            # ── 调用封装好的交互展示区 ───────────────────────────────────────────────────────
            render_viz_dashboard(df_clean, df_pivot, df_cross_period, val_col, all_fields, all_types, all_co_types, dynamic_period_colors, all_cross_fields)

         
        # ─────────── Step 7 固定图的展示和 PPT ───────────
        with tab7:
            show_step_7_content()
            
            
        # ─────────── Step 8 固定图的展示和 PPT ───────────
        with tab8:
            show_step_8_content()
        
        
        
        
        
            
    else:
        # 如果是 普通用户，只开放 6 和 7 两个 Tab
        st.warning("🔒 您当前仅拥有数据可视化与报告生成模块的访问权限。")
        tab6, tab7 = st.tabs([
            " 📊 Step 6 ／ 自定义对标分析 ",
            " 🖼️ Step 7 ／ 公司级对标报告 "
        ])
        
        # ─────────── KPMG 官方色卡 ───────────
        KPMG_CATEGORIES = {
            "Primary Colors": {"KPMG Blue": "#00338D", "Cobalt Blue": "#1E49E2", "Dark Blue": "#0C233C", "Light Blue": "#ACEAFF", "Pacific Blue": "#00B8F5", "Purple": "#7213EA", "Pink": "#FD349C"},
            "Accent Colors": {"Blue": "#76D2FF", "Dark Purple": "#510DBC", "Light Purple": "#B497FF", "Dark Pink": "#AB0D82", "Light Pink": "#FFA3DA", "Dark Green": "#098E7E", "Green": "#00C0AE", "Light Green": "#63EBB2"},
            "Traffic Light": {"Red": "#ED2124", "Amber": "#F1C44D", "Positive Green": "#269924"}
        }
        DEFAULT_COLORS = list(KPMG_CATEGORIES["Primary Colors"].values()) + list(KPMG_CATEGORIES["Accent Colors"].values())
        
        # ─────────── Step 6 可视化分析面板 ───────────
        with tab6:
            st.markdown("### 📊 自定义对标分析")
        
            # ── 数据源选择 ───────────────────────────────────────────────────────
            if 'integrated_data' not in st.session_state:
                st.session_state['integrated_data'] = None
        
            source_choice = st.radio(
                "数据源选择", ["直接引用集成后的数据", "上传集成表 Excel"], horizontal=True
            )
            df_raw = None
        
            if source_choice == "上传集成表 Excel":
                viz_file = st.file_uploader("上传行业集成目标表", type=["xlsx"])
                if viz_file:
                    df_raw = pd.read_excel(viz_file)
                    st.session_state['integrated_data'] = df_raw
            else:
                df_raw = st.session_state.get('integrated_data')
        
            if df_raw is None:
                st.info("💡 请先完成数据集成或上传目标底稿。")
                st.stop()
        
            # ==========================================
            # 🌟 提速秘籍 1：锁定数据预处理 (只算一次)
            # ==========================================
            @st.cache_data(show_spinner=False)
            def prepare_viz_data(df_in):
                df_clean = df_in.copy()
                df_clean.columns = (
                    df_clean.columns.astype(str)
                    .str.strip()
                    .str.replace('\n', '', regex=False)
                    .str.replace('\r', '', regex=False)
                    .str.replace('\ufeff', '', regex=False)
                )
                df_clean['报告年份'] = df_clean['报告年份'].astype(str).str.replace('.0', '', regex=False)
                val_col = "(百万)人民币" if "(百万)人民币" in df_clean.columns else df_clean.columns[-1]
        
                # 去重
                dedup_cols = ['公司', '报告年份', '字段名']
                if '类别' in df_clean.columns:
                    dedup_cols.append('类别')
                df_clean = df_clean.drop_duplicates(subset=dedup_cols, keep='first')
        
                # 透视表
                df_pivot = (
                    df_clean.groupby(['公司', '报告年份', '字段名'])[val_col]
                    .sum().unstack('字段名').reset_index()
                )
        
                # 提取选项列表
                all_fields = sorted([x for x in df_clean['字段名'].unique().tolist() if isinstance(x, str) and x.strip()])
                all_types    = sorted(df_clean['类别'].dropna().astype(str).unique().tolist()) if '类别'    in df_clean.columns else []
                all_co_types = sorted(df_clean['公司类型'].dropna().astype(str).unique().tolist()) if '公司类型' in df_clean.columns else []
        
                all_years_sorted = sorted(
                    [y for y in df_clean['报告年份'].unique() if str(y).isdigit()],
                    key=lambda x: int(x)
                )
                
                return df_clean, df_pivot, val_col, all_fields, all_types, all_co_types, all_years_sorted
        
            # 调用缓存的数据处理函数
            df_clean, df_pivot, val_col, all_fields, all_types, all_co_types, all_years_sorted = prepare_viz_data(df_raw)
        
            # ── 动态年份颜色计算 (极速，无需缓存) ──────────────────────────────────
            KPMG_COLOR_MAP = {
                "Lightest": "#BFE8FF",     # Pacific Blue (light)
                "Light": "#76D2FF",      # Blue (original Light Blue)
                "Primary": "#1E49E2",     # Cobalt Blue
                "Dark": "#00338D",       # KPMG Blue (original Primary Blue)
            }
            
            n_years = len(all_years_sorted)
            dynamic_year_colors = {}
            target_colors = []
            
            if n_years == 3:
                target_colors = [KPMG_COLOR_MAP["Light"], KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            elif n_years == 2:
                target_colors = [KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            else:
                target_colors = [KPMG_COLOR_MAP["Lightest"], KPMG_COLOR_MAP["Light"], KPMG_COLOR_MAP["Primary"], KPMG_COLOR_MAP["Dark"]]
            
            num_colors_to_use = len(target_colors)
            if n_years > 0:
                for idx, year in enumerate(all_years_sorted):
                    color_index = 0
                    if n_years > 1:
                        proportion = idx / (n_years - 1)
                        color_index = int(proportion * (num_colors_to_use - 1))
                    color_index = min(color_index, num_colors_to_use - 1)
                    dynamic_year_colors[str(year)] = target_colors[color_index]
        
            # ── KPMG 色卡 ────────────────────────────────────────────────────────
            with st.expander("🎨 查看 KPMG 官方色卡"):
                # 确保全局存在 KPMG_CATEGORIES 变量
                if 'KPMG_CATEGORIES' in globals():
                    for cat_name, cat_colors in KPMG_CATEGORIES.items():
                        st.markdown(f"**{cat_name}**")
                        html_str = "".join([
                            f'<div style="display:inline-block;margin-right:15px;margin-bottom:8px;">'
                            f'<div style="width:14px;height:14px;background-color:{c};display:inline-block;'
                            f'border-radius:3px;vertical-align:middle;border:1px solid #ddd;"></div>'
                            f'<span style="font-size:13px;vertical-align:middle;"> {n} <b>({c})</b></span></div>'
                            for n, c in cat_colors.items()
                        ])
                        st.markdown(html_str, unsafe_allow_html=True)
                else:
                    st.caption("未检测到 KPMG_CATEGORIES 色卡定义。")
        
            st.divider()
        
            # ==========================================
            # 🌟 提速秘籍 2：锁定 UI 与绘图更新范围 (片段刷新)
            # ==========================================
            @st.fragment
            def render_viz_dashboard(df_clean, df_pivot, val_col, all_fields, all_types, all_co_types, dynamic_year_colors):
                import re, plotly.graph_objects as go, plotly.express as px
            
                def safe_num(s):
                    return pd.to_numeric(s.astype(str).str.strip().str.replace(",", "", regex=False).str.replace("(", "-", regex=False).str.replace(")", "", regex=False).replace(["", "nan", "None", "未披露", "—", "-"], np.nan), errors="coerce")
            
                def safe_formula_eval(wide_df, formula):
                    expr, local_dict = str(formula).strip(), {}
                    for i, field in enumerate(re.findall(r"\[(.*?)\]", expr)):
                        key = f"V{i}"
                        local_dict[key] = safe_num(wide_df[field]) if field in wide_df.columns else pd.Series(np.nan, index=wide_df.index)
                        expr = expr.replace(f"[{field}]", key)
                    try:
                        return pd.Series(pd.eval(expr, local_dict=local_dict, engine="python"), index=wide_df.index).replace([np.inf, -np.inf], np.nan)
                    except Exception:
                        return pd.Series(np.nan, index=wide_df.index)
            
                with st.expander("🛠️ 核心配置面板", expanded=True):
                    r1c1, r1c2, r1c3 = st.columns([1.5, 1, 1])
                    is_pct_stack_mode = False
            
                    with r1c1:
                        chart_type = st.selectbox("📈 1. 图表类型", ["簇状柱状图", "堆积柱状图", "折线对比图", "饼图", "内外环结构对比图", "散点图"])
            
                        if chart_type == "散点图":
                            calc_mode, plot_df_base = "散点图", pd.DataFrame()
                            st.caption("先选择字段；如需运算，开启高级公式，用 [字段名] 引用指标。")
                            x_field = st.selectbox("X轴字段", all_fields, index=0, key="scatter_x_field")
                            y_field = st.selectbox("Y轴字段", all_fields, index=min(1, len(all_fields)-1), key="scatter_y_field")
                            use_formula = st.checkbox("高级公式模式", value=False, key="scatter_formula_on")
                            x_formula = st.text_input("X轴公式", value=f"[{x_field}]", key="scatter_x_formula") if use_formula else f"[{x_field}]"
                            y_formula = st.text_input("Y轴公式", value=f"[{y_field}]", key="scatter_y_formula") if use_formula else f"[{y_field}]"
                            x_axis_title_custom = st.text_input("X轴显示名称", value=x_field, key="scatter_x_title")
                            y_axis_title_custom = st.text_input("Y轴显示名称", value=y_field, key="scatter_y_title")
            
                            all_cos_list = sorted(df_pivot['公司'].unique().tolist())
                            selected_cos = st.multiselect("🏗️ 选择公司", all_cos_list, default=all_cos_list[:min(8, len(all_cos_list))], key="scatter_selected_cos")
                            years_sorted = sorted(df_pivot['报告年份'].unique().tolist(), key=lambda x: int(x) if str(x).isdigit() else 9999)
                            scatter_years = st.multiselect("📅 选择年份", years_sorted, default=years_sorted[-1:], key="scatter_years")
            
                        elif "环" in chart_type or chart_type == "饼图":
                            calc_mode = "结构分析"
                            selected_multi_fields = st.multiselect("🎯 选择构成指标", all_fields, default=all_fields[:min(3, len(all_fields))])
                            selected_cos = st.selectbox("🏗️ 选择展示公司", sorted(df_pivot['公司'].unique().tolist()))
                            plot_df_base = df_clean[(df_clean['字段名'].isin(selected_multi_fields)) & (df_clean['公司'] == selected_cos)].copy().rename(columns={val_col: 'final_val'})
            
                        else:
                            if chart_type == "堆积柱状图":
                                stack_sub = st.radio("堆积模式", ["单指标 / 公式", "多指标占比"], horizontal=True, key="stack_sub_mode")
                                is_pct_stack_mode = (stack_sub == "多指标占比")
            
                            if is_pct_stack_mode:
                                calc_mode = "多指标占比"
                                pct_field_pool = sorted(df_clean[df_clean['类别'] == st.selectbox("🗂️ 按类别筛选指标", ["全部类别"] + all_types, key="pct_type_filter")]['字段名'].unique().tolist()) if all_types and st.session_state.get("pct_type_filter") not in [None, "全部类别"] else all_fields
                                selected_pct_fields = st.multiselect("🎯 选择堆积指标", pct_field_pool, default=pct_field_pool[:min(3, len(pct_field_pool))], key="pct_stack_fields")
                                plot_df_base = df_clean[df_clean['字段名'].isin(selected_pct_fields)][['公司', '报告年份', '字段名', val_col]].copy().rename(columns={val_col: 'final_val'}) if selected_pct_fields else pd.DataFrame(columns=['公司', '报告年份', '字段名', 'final_val'])
                            else:
                                calc_mode = st.radio("数据模式", ["单指标直显", "自定义公式运算"], horizontal=True)
                                if calc_mode == "单指标直显":
                                    filtered_fields = sorted(df_clean[df_clean['类别'] == st.selectbox("🗂️ 按类别筛选指标", ["全部类别"] + all_types, key="type_filter_single")]['字段名'].unique().tolist()) if all_types and st.session_state.get("type_filter_single") not in [None, "全部类别"] else all_fields
                                    target_field = st.selectbox("🎯 选择显示指标", filtered_fields)
                                    plot_df_base = df_pivot[['公司', '报告年份', target_field]].rename(columns={target_field: 'final_val'}).copy()
                                else:
                                    v1, v2 = st.columns(2)
                                    var_a = v1.selectbox("变量 A", all_fields, index=0)
                                    var_b = v2.selectbox("变量 B", ["无"] + all_fields, index=1 if len(all_fields) > 1 else 0)
                                    formula_input = st.text_input("✏️ 自定义公式 (使用 A 和 B)", value="A - B")
                                    try:
                                        A_data, B_data = safe_num(df_pivot[var_a]).fillna(0), (safe_num(df_pivot[var_b]).fillna(0) if var_b != "无" else 0)
                                        df_pivot['final_val'] = pd.Series(pd.eval(formula_input, local_dict={'A': A_data, 'B': B_data}), index=df_pivot.index).replace([np.inf, -np.inf], np.nan).fillna(0)
                                        plot_df_base = df_pivot[['公司', '报告年份', 'final_val']].copy()
                                    except Exception as e:
                                        st.error(f"公式无效: {e}")
                                        plot_df_base = pd.DataFrame(columns=['公司', '报告年份', 'final_val'])
            
                            all_cos_list = sorted(df_pivot['公司'].unique().tolist())
                            if all_co_types:
                                co_type_sel = st.selectbox("🏢 按公司类型快速选择", ["不按公司类型筛选"] + all_co_types, key="co_type_sel")
                                if co_type_sel != "不按公司类型筛选" and st.session_state.get('_prev_co_type_sel') != co_type_sel:
                                    st.session_state['selected_cos_ms'] = sorted(df_clean[df_clean['公司类型'] == co_type_sel]['公司'].unique().tolist())
                                    st.session_state['_prev_co_type_sel'] = co_type_sel
                            selected_cos = st.multiselect("🏗️ 选择对比公司", all_cos_list, default=all_cos_list[:min(2, len(all_cos_list))], key="selected_cos_ms")
            
                    with r1c2:
                        x_axis_mode = "散点视角" if chart_type == "散点图" else (st.radio("🔍 布局视角", ["以公司为横轴", "以年份为横轴"]) if "环" not in chart_type else "结构视角")
                        decimals = st.number_input("🔢 小数位数", 0, 4, 0)
                        show_value = st.toggle("✅ 显示数据标签", value=True)
            
                    with r1c3:
                        unit_options = {"原始数值": 1.0, "亿元": 0.01, "十亿元": 0.001, "百分比(%)": 100.0}
                        selected_unit = st.selectbox("📏 数值单位换算", list(unit_options.keys()))
                        multiplier = unit_options[selected_unit]
                        y_axis_title = st.text_input("📝 Y轴单位显示修改", value=f"单位: {selected_unit.split(' ')[0]}")
                        is_transparent = st.toggle("🌈 开启透明背景模式")
                        show_avg = st.checkbox("平均值线") if "柱" in chart_type else False
                        avg_color = st.color_picker("基准线颜色", value="#ED2124") if show_avg else "#ED2124"
            
                if chart_type == "散点图":
                    scatter_df = df_pivot.copy()
                    scatter_df["X"], scatter_df["Y"] = safe_formula_eval(scatter_df, x_formula) * multiplier, safe_formula_eval(scatter_df, y_formula) * multiplier
                    plot_df = scatter_df[scatter_df["公司"].isin(selected_cos) & scatter_df["报告年份"].isin(scatter_years)].dropna(subset=["X", "Y"]).copy()
                    if plot_df.empty:
                        st.warning("散点图暂无可用数据，请检查字段、公式、公司或年份。")
                        st.stop()
                    color_val = "公司"
                else:
                    if plot_df_base.empty:
                        st.warning("暂无数据，请检查筛选条件。")
                        st.stop()
                    if calc_mode in ("结构分析", "多指标占比"):
                        cos_filter = [selected_cos] if isinstance(selected_cos, str) else selected_cos
                        plot_df, color_val = plot_df_base[plot_df_base['公司'].isin(cos_filter)].copy(), "字段名"
                    else:
                        plot_df = plot_df_base[plot_df_base['公司'].isin(selected_cos)].copy()
                        color_val = "报告年份" if x_axis_mode == "以公司为横轴" else "公司"
                    plot_df['绘制金额'] = safe_num(plot_df['final_val']).fillna(0) * multiplier
            
                st.markdown("#### 🎨 自定义图例标签与颜色")
                # ✅ 散点图用公司名做图例key，其他图用color_val
                legend_col = "公司" if chart_type == "散点图" else color_val
                unique_items = sorted(plot_df[legend_col].dropna().unique().tolist())
                rename_map, color_map, c_cols = {}, {}, st.columns(4)
                for i, item in enumerate(unique_items):
                    with c_cols[i % 4]:
                        st.caption(f"原始值: {item}")
                        new_label = st.text_input("显示名称", value=str(item), key=f"rename_{chart_type}_{item}")
                        default_c = dynamic_year_colors.get(str(item), DEFAULT_COLORS[i % len(DEFAULT_COLORS)] if 'DEFAULT_COLORS' in globals() else "#1E49E2")
                        new_color = st.color_picker("选择颜色", value=default_c, key=f"color_{chart_type}_{item}")
                        rename_map[item], color_map[new_label] = new_label, new_color
                # ✅ 散点图不做map，保留原始公司名
                if chart_type != "散点图":
                    plot_df[color_val] = plot_df[color_val].map(rename_map)
                else:
                    plot_df["_legend_show"] = plot_df[color_val].map(rename_map).fillna(plot_df[color_val])
            
                fig, fmt = go.Figure(), f'.{decimals}f'
                suffix, label_fmt = ("%" if selected_unit == "百分比(%)" else ""), f'%{{y:.{decimals}f}}{"%" if selected_unit == "百分比(%)" else ""}'
            
                if chart_type == "散点图":
                    for item in rename_map.values():
                        d = plot_df[plot_df["_legend_show"] == item]  # ✅ 用_legend_show
                        if d.empty: continue
                        fig.add_trace(go.Scatter(
                            x=d["X"], y=d["Y"], name=str(item),
                            mode="markers+text" if show_value else "markers",
                            text=d["公司"] if show_value else None,  # ✅ 公司列还是原始值
                            textposition="top center",
                            marker=dict(size=14, color=color_map.get(item, "#1E49E2"), line=dict(width=1.4, color="white")),
                            customdata=np.stack([d["公司"], d["报告年份"]], axis=-1),
                            hovertemplate="<b>%{customdata[0]}</b><br>年份：%{customdata[1]}<br>X=%{x}<br>Y=%{y}<extra></extra>"
                        ))
                    fig.update_xaxes(title=x_axis_title_custom, zeroline=True, zerolinecolor="#999", showgrid=True, gridcolor="#f0f0f0")
                    fig.update_yaxes(title=y_axis_title_custom, zeroline=True, zerolinecolor="#999", showgrid=True, gridcolor="#f0f0f0")
            
                elif "柱状图" in chart_type:
                    barmode = 'group' if "簇状" in chart_type else 'relative'
                    if is_pct_stack_mode:
                        plot_df['x_label'] = plot_df['公司'] + ' ' + plot_df['报告年份']
                        plot_df['_total'] = plot_df.groupby('x_label')['绘制金额'].transform('sum').replace(0, np.nan)
                        plot_df['绘制占比'] = (plot_df['绘制金额'] / plot_df['_total'] * 100).fillna(0)
                        for item in rename_map.values():
                            d = plot_df[plot_df[color_val] == item]
                            fig.add_trace(go.Bar(x=d['x_label'], y=d['绘制占比'], name=str(item), marker_color=color_map[item],
                                text=d.apply(lambda r: f"{r['绘制占比']:.{decimals}f}%<br>{r['绘制金额']:.{decimals}f}", axis=1) if show_value else None, textposition='inside'))
                        fig.update_yaxes(range=[0, 105]); barmode = 'relative'
                    else:
                        for item in rename_map.values():
                            d = plot_df[plot_df[color_val] == item]
                            fig.add_trace(go.Bar(x=d["公司" if color_val == "报告年份" else "报告年份"], y=d["绘制金额"], name=str(item), marker_color=color_map[item],
                                text=d["绘制金额"] if show_value else None, texttemplate=label_fmt if show_value else None, textposition='outside'))
                    fig.update_layout(barmode=barmode)
            
                elif "折线对比图" in chart_type:
                    for item in rename_map.values():
                        d = plot_df[plot_df[color_val] == item]
                        fig.add_trace(go.Scatter(x=d["公司" if color_val == "报告年份" else "报告年份"], y=d["绘制金额"], name=str(item),
                            mode='lines+markers+text' if show_value else 'lines+markers', marker_color=color_map[item],
                            text=d["绘制金额"], texttemplate=label_fmt, textposition="top center"))
            
                elif chart_type == "饼图":
                    d = plot_df[plot_df['报告年份'] == plot_df['报告年份'].max()]
                    fig = px.pie(d, values='绘制金额', names=color_val, hole=0.4, color=color_val, color_discrete_map=color_map)
                    fig.update_traces(textinfo='percent+label' if show_value else 'percent')
            
                elif chart_type == "内外环结构对比图":
                    years_ring = sorted(plot_df['报告年份'].unique().tolist())
                    if len(years_ring) < 2: st.warning("环形图对比需要至少两年的数据。")
                    else:
                        d_outer, d_inner = plot_df[plot_df['报告年份'] == years_ring[-1]], plot_df[plot_df['报告年份'] == years_ring[0]]
                        fig.add_trace(go.Pie(labels=d_outer[color_val], values=d_outer['绘制金额'], hole=0.7, name=years_ring[-1], marker=dict(colors=[color_map[f] for f in d_outer[color_val]]), textinfo='percent+label' if show_value else 'percent'))
                        fig.add_trace(go.Pie(labels=d_inner[color_val], values=d_inner['绘制金额'], hole=0.4, name=years_ring[0], domain={'x': [0.15, 0.85], 'y': [0.15, 0.85]}, marker=dict(colors=[color_map[f] for f in d_inner[color_val]]), textinfo='percent' if show_value else 'none'))
                        fig.update_layout(annotations=[dict(text=f'内:{years_ring[0]}<br>外:{years_ring[-1]}', x=0.5, y=0.5, font_size=12, showarrow=False)])
            
                bg_color = "rgba(0,0,0,0)" if is_transparent else "white"
                if show_avg and "柱" in chart_type and not is_pct_stack_mode:
                    avg_v = plot_df['绘制金额'].mean()
                    fig.add_hline(y=avg_v, line_dash="dash", line_color=avg_color, annotation_text=f"平均: {avg_v:{fmt}}{suffix}", annotation_font=dict(color=avg_color))
            
                fig.update_layout(font_family="Microsoft YaHei", plot_bgcolor=bg_color, paper_bgcolor=bg_color,
                    margin=dict(t=120, l=10, r=10, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    annotations=[] if chart_type == "散点图" else [dict(x=0, y=1.18, xref='paper', yref='paper', text=f"<b>{y_axis_title}</b>", showarrow=False, font=dict(size=14, color="#333333"), xanchor='left')])
                fig.update_xaxes(showgrid=True if chart_type == "散点图" else False)
                fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
            
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("📄 查看底层数据明细"):
                    st.dataframe(plot_df, use_container_width=True)
        
            # ==========================================
            # 在页面上调用封装好的交互展示区
            # ==========================================
            render_viz_dashboard(df_clean, df_pivot, val_col, all_fields, all_types, all_co_types, dynamic_year_colors)
         
                
         
            
        # ─────────── Step 7 固定图的展示和 PPT ───────────
        with tab7:
            show_step_7_content()            
 


 

# ==================== 页脚 ====================
st.markdown("")