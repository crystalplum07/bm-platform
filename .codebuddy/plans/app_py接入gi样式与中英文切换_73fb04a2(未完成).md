---
name: app.py接入gi样式与中英文切换
overview: 参照 app-gi.py 的架构，为 bm-platform 的 app.py 接入 ui/theme.py 的 KPMG 网页样式，并新建 services/report_i18n.py 实现中英文切换（侧边栏顶部 radio，切换先于绘制同步），翻译范围覆盖 app.py 外壳与 step7.py 全部界面文案。
todos:
  - id: catalog-strings
    content: 使用 [subagent:code-explorer] 梳理 app.py 与 step7.py 全部用户可见中文文案清单（分类+行号）
    status: pending
  - id: create-i18n-module
    content: 新建 services/report_i18n.py 与 translations/step7_en.py：语言常量、set_language/get_language、t() 及英译字典骨架
    status: pending
    dependencies:
      - catalog-strings
  - id: app-shell-i18n
    content: 修改 app.py：接入 ui/theme.py 样式、侧边栏顶部语言 radio（key=s7_language_display）、先于绘制同步语言、外壳文案 t() 包裹并补英译
    status: pending
    dependencies:
      - create-i18n-module
  - id: step7-sidebar-and-table
    content: step7.py 侧边栏控件、汇总表表头与说明文案 t() 包裹，补充英译字典
    status: pending
    dependencies:
      - app-shell-i18n
  - id: step7-charts-i18n
    content: step7.py 各图表模块标题/轴标题/图例/悬停提示 t() 包裹，补充英译字典
    status: pending
    dependencies:
      - step7-sidebar-and-table
  - id: step7-notes-and-buttons
    content: step7.py notes_dict 注释、按钮、提示及 AI 点评 prompt 语种适配 t() 包裹，补全英译字典
    status: pending
    dependencies:
      - step7-charts-i18n
  - id: verify-i18n
    content: py_compile 校验，运行 Streamlit 抽查中英文切换（登录页/页签/Step7 各模块/打印导出）
    status: pending
    dependencies:
      - step7-notes-and-buttons
---

## 产品概述

参照 `app-gi.py` 的架构，对 `bm-platform/app.py` 进行两项改造：

1. **网页样式接入**：复用用户已放入的 `ui/theme.py`（KPMG 蓝色系平台级 CSS + 打印样式 + STEP6-8 侧边栏样式），替换 app.py 现有灰蓝色系 CSS；
2. **中英文切换**：在侧边栏顶部增加横排 radio「中文 / English」（默认中文），切换立即生效（先于页面绘制同步语言状态），覆盖 app.py 外壳与 step7.py 全部界面文案。

## 核心功能

- 登录页、顶部状态栏、页签、按钮、Step 6 面板文案随语言切换显示中/英文
- Step 7 公司级对标报告（侧边栏控件、汇总表、约 30 个图表模块的标题/轴/图例/悬停提示、notes_dict 注释、下载按钮等）全部文案支持中/英文切换
- AI 点评 prompt 按当前语言要求模型输出对应语种
- 语言状态持久于 session，切换控件与 app-gi.py 一致（key=`s7_language_display`）

## 边界

- `ui/` 包来自另一项目，仅复用自包含的 `theme.py`（及不依赖缺失模块的部分）；不整体套用 app-gi.py 编排（其 report_pages/config 依赖 step7_solvency、config/ 等不存在的资源）
- step8.py 维持中文，不翻译
- 默认语言为中文，中文模式下所有文案显示与现状完全一致

## 技术栈

- 现有项目：Streamlit + Plotly（app.py 入口编排、step7.py 单文件实现）
- 新增：`services/report_i18n.py` 纯 Python i18n 模块，无第三方依赖

## 实现方案

### 关键设计决策

1. **t() 以中文原文为键**：`t(s)` 在英文模式下查英译字典，命中返回英文、未命中原样返回中文；中文模式下恒等返回。这样无需大规模重构 f-string 与字典键设计，未翻译文案自然回退中文，可分批推进，零风险。
2. **语言同步先于绘制**（参照 app-gi.py `_sync_language_before_paint`）：语言 radio 渲染后、主界面绘制前调用 `set_language`，避免切换后需下一次 rerun 才刷新。
3. **样式替换**：删除 app.py line 439-480 的旧 CSS，改为 `from ui.theme import render_app_styles, render_analysis_tab_styles`；暗色登录页自包含 CSS 保留（theme.py 未覆盖登录页），仅将其中文案改用 t()。
4. **翻译字典分文件**：英译字典量大（step7 全部文案），集中放在 `services/translations/step7_en.py`，主模块仅做加载与查询，避免 report_i18n.py 膨胀。

### 架构

```mermaid
flowchart LR
    A[app.py 入口] --> B[ui.theme.render_app_styles]
    A --> C[侧边栏语言 radio<br/>key=s7_language_display]
    C --> D[_sync_language_before_paint]
    D --> E[services.report_i18n<br/>set_language / t]
    E --> F[app.py 外壳文案]
    E --> G[step7.show_step_7_content<br/>全部 t() 包裹文案]
    G --> H[translations/step7_en.py<br/>中文→英译字典]
```

### 目录结构

```
bm-platform/
├── services/
│   ├── __init__.py                  # [NEW] 空包
│   ├── report_i18n.py               # [NEW] LANG_ZH/LANG_EN、LANGUAGE_LABELS、set_language/get_language、t()；与 st.session_state['app_language'] 双向同步
│   └── translations/
│       ├── __init__.py              # [NEW] 空包
│       └── step7_en.py              # [NEW] dict：中文原文 → 英文；分批补充（外壳文案、Step6 文案、step7 全部文案）
├── ui/theme.py                      # [REUSE] 直接复用，不改
├── app.py                           # [MODIFY] 接入 theme 样式；侧边栏顶部语言 radio；_sync_language_before_paint()；外壳文案 t() 包裹（登录页/标题/页签/按钮/Step6 界面文案）
└── step7.py                         # [MODIFY] 用户可见文案全部 t() 包裹：侧边栏控件 → 汇总表表头 → 各图表模块标题/轴标题/图例/hovertemplate → notes_dict → 按钮/提示；AI prompt 追加按语言输出要求
```

### report_i18n.py 核心接口

```python
LANG_ZH, LANG_EN = "zh", "en"
LANGUAGE_LABELS = {"中文": LANG_ZH, "English": LANG_EN}

def set_language(lang: str) -> None: ...   # 同步模块级当前语言与 st.session_state["app_language"]
def get_language() -> str: ...
def t(s: str) -> str: ...                  # 英文且命中字典返回英文，否则原样返回
```

### 执行要点

- step7.py 文案量约数百条，按模块分批（每批一个 todolist 项），每批完成即 py_compile，避免一次大改引入语法错误
- hovertemplate/annotation/HTML 表头中的中文均在 t() 覆盖范围内；数据字段名（如"保险服务收入合计"）为数据列名不翻译，仅翻译展示文案
- 性能：t() 为 dict 查询 O(1)，无缓存需求；不引入任何 rerun 逻辑变更
- 回退安全：字典未命中文案原样显示中文，不报错

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose：全面梳理 step7.py（约 5306 行）与 app.py 中所有用户可见中文文案，按类别（侧边栏控件/汇总表/图表模块/notes_dict/按钮提示/AI prompt）输出位置清单，供翻译批量化推进
- Expected outcome：得到带行号的文案清单，作为 t() 包裹与英译字典编制的依据，避免遗漏