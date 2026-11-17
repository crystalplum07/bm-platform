import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import inspect
import ast
from pathlib import Path

import report_i18n as i18n


def test_core_text_and_company_translation():
    assert i18n.translate_text("新准则财务报告洞察平台", "en") == (
        "New Accounting Standards Financial Reporting Insights Platform"
    )
    assert i18n.translate_text("保险服务收入", "en") == "Insurance Service Revenue"
    assert i18n.translate_text("平安人寿", "en") == "Ping An Life"
    assert i18n.translate_text("2025年6月", "en") == "2025-6"
    assert i18n.translate_text("2025年", "en") == "2025"


def test_packaged_excel_dictionary_is_loaded():
    assert i18n.TRANSLATION_WORKBOOK_LOADED_ROWS >= 1000
    assert i18n.EXCEL_TRANSLATIONS_EN["中国人寿"] == "China Life"


def test_excel_dictionary_overrides_existing_and_adds_new_entries(monkeypatch):
    existing_source = "展开导航栏"
    new_source = "测试新增维护词条"
    disabled_source = "测试停用维护词条"
    mappings = [
        i18n.COMPANY_NAMES_EN,
        i18n.PHRASE_EN,
        i18n.DEFAULT_ANALYSIS_EN,
        i18n.CHART_NAMES_EN,
        i18n.LEVEL_NAMES_EN,
        i18n.CATEGORY_NAMES_EN,
        i18n.PERFORMANCE_NAMES_EN,
        i18n.DISCLOSURE_NAMES_EN,
        i18n.UNIT_NAMES_EN,
        i18n.FIELD_NAMES_EN,
        i18n.COLUMN_NAMES_EN,
        i18n.CHART_KIND_NAMES_EN,
        i18n.EXCEL_TRANSLATIONS_EN,
    ]
    sentinel = object()
    snapshots = {
        (id(mapping), source): mapping.get(source, sentinel)
        for mapping in mappings
        for source in (existing_source, new_source, disabled_source)
    }
    workbook_path = (
        Path(i18n.__file__).resolve().parent
        / "templates"
        / i18n.TRANSLATION_WORKBOOK_FILENAME
    )
    frame = pd.DataFrame(
        [
            {
                "中文原文": existing_source,
                "英文译文": "Compact navigation",
                "Excel覆盖启用": "是",
            },
            {
                "中文原文": new_source,
                "英文译文": "New maintained label",
                "Excel覆盖启用": "是",
            },
            {
                "中文原文": disabled_source,
                "英文译文": "Disabled label",
                "Excel覆盖启用": "否",
            },
        ]
    )
    monkeypatch.setattr(i18n.pd, "read_excel", lambda *args, **kwargs: frame)

    try:
        loaded = i18n.load_translation_workbook(workbook_path)
        assert loaded == 2
        assert i18n.translate_text(existing_source, "en") == "Compact navigation"
        assert i18n.translate_text(new_source, "en") == "New maintained label"
        assert i18n.translate_text(disabled_source, "en") == disabled_source
    finally:
        for mapping in mappings:
            for source in (existing_source, new_source, disabled_source):
                original = snapshots[(id(mapping), source)]
                if original is sentinel:
                    mapping.pop(source, None)
                else:
                    mapping[source] = original


def test_dataframe_translation_does_not_mutate_source():
    source = pd.DataFrame(
        {"公司": ["中国人寿"], "字段名": ["保险服务收入"], "报告年份": [2025]}
    )
    result = i18n.translate_dataframe(source, "en")
    assert list(source.columns) == ["公司", "字段名", "报告年份"]
    assert list(result.columns) == ["Company", "Metric", "Reporting year"]
    assert result.iloc[0]["Company"] == "China Life"
    assert result.iloc[0]["Metric"] == "Insurance Service Revenue"


def test_plotly_translation_uses_display_copy():
    source = go.Figure(
        go.Bar(x=["中国人寿"], y=[1], name="保险服务收入")
    )
    source.update_layout(title="保险服务收入", xaxis_title="公司", yaxis_title="百万元")
    result = i18n.localize_plotly(go.Figure(source), "en")
    assert source.layout.title.text == "保险服务收入"
    assert result.layout.title.text == "Insurance Service Revenue"
    assert result.layout.xaxis.title.text == "Company"
    assert result.data[0].name == "Insurance Service Revenue"
    assert list(result.data[0].x) == ["China Life"]


def test_step7_composite_headers_and_compound_units():
    assert i18n.translate_text(" 🖼️ Step 7 ／ 公司级对标报告 ", "en") == (
        " 🖼️ Step 7 ／ Company Benchmarking Report "
    )
    assert i18n.translate_text("净资产<br>%变化", "en") == "Net Assets<br>% Change"
    assert i18n.translate_text("保险合同净负债余额<br>%变化", "en") == (
        "Net Insurance Contract Liability<br>% Change"
    )
    assert i18n.translate_text("单位：十亿元人民币", "en") == "Unit: RMB bn"


def test_step8_axis_and_plotly_table_values_are_translated():
    assert i18n.translate_text("CSM余额增长率区间（%）", "en") == (
        "CSM balance growth-rate range (%)"
    )
    source = go.Figure(
        go.Table(
            header={"values": ["编号", "公司"]},
            cells={"values": [[1], ["中国人寿"]]},
        )
    )
    result = i18n.localize_plotly(go.Figure(source), "en")
    assert list(result.data[0].header.values) == ["No.", "Company"]
    assert list(result.data[0].cells.values[1]) == ["China Life"]


def test_screenshot_scatter_annotations_axes_and_forward_rate():
    expected = {
        "虚线：样本中位数": "Dashed lines: sample medians",
        "虚线：零轴": "Dashed lines: zero axes",
        "保险服务收入增长率": "Insurance Service Revenue Growth Rate",
        "保险服务利润率变动（百分点）": (
            "Change in Insurance Service Margin (percentage points)"
        ),
        "1.74%-12.61%（远期）": "1.74%-12.61% (forward)",
    }
    for source, target in expected.items():
        assert i18n.translate_text(source, "en") == target

    figure = go.Figure(go.Scatter(x=[1], y=[2]))
    figure.update_xaxes(title_text="保险服务收入增长率")
    figure.update_yaxes(title_text="保险服务利润率变动（百分点）")
    figure.add_annotation(text="<b>虚线：样本中位数</b>", x=1, y=2)
    translated = i18n.localize_plotly(figure, "en")
    assert translated.layout.xaxis.title.text == "Insurance Service Revenue Growth Rate"
    assert translated.layout.yaxis.title.text == (
        "Change in Insurance Service Margin (percentage points)"
    )
    assert translated.layout.annotations[0].text == "<b>Dashed lines: sample medians</b>"
    assert i18n.translate_text("<td>1.74%-12.61%（远期）</td>", "en") == (
        "<td>1.74%-12.61% (forward)</td>"
    )


def test_step7_and_step8_known_table_labels_have_no_chinese_residue():
    visible_labels = [
        "🖨️ 一键显示全部 (打印/导出)",
        "项目",
        "序号",
        "公司名称",
        "分析指标",
        "报告年份",
        "报告期",
        "未披露",
        "FVOCI占比",
        "FVOCI变动",
        "负债OCI变动",
        "资负匹配率",
        "负债OCI占比",
        "净资产变动明细表（I9切换后）",
        "其他变动",
        "各公司平均占比情况",
        "各公司平均占比（样本均值）",
        "获取费用均值",
        "维持费用均值",
        "非履约费用均值",
        "未采用保费分配法的保险合同",
        "采用保费分配法的保险合同",
        "合同服务边际的释放",
        "非金融风险调整的变动",
        "预期当期发生的保险服务费用",
        "保险获取现金流的摊销",
        "亏损部分的确认及转回",
        "当期发生的赔款及其他相关费用",
        "已发生赔款负债相关的履约现金流量变动",
        "保险服务业绩（不含再保收支净额）",
        "CSM释放在保险服务业绩中占比",
        "集团/业务条线-汇总",
        "综合净资产/总资产",
        "净资产变动值",
        "其他项",
        "新业务盈利合同(CSM)",
        "新业务亏损合同(LC)",
        "与当期服务或过去服务相关的保费经验调整",
        "PAA合同收入",
        "非PAA合同收入",
        "合同服务边际释放",
        "非金融风险调整变动",
        "预期保险服务费用",
        "保险获取现金流摊销",
        "亏损部分确认及转回",
        "当期赔款及费用",
        "已发生赔款负债变动",
        "分布数据明细",
        "公司数量",
        "3家",
        "（无公司）",
        "单位：百分比 (%)，顶部数字为总费用（亿元）",
        "无对应数据",
        "无有效数据",
        "可转损益的负债OCI / 平均净资产",
        "FVOCI债券 / 平均净资产",
        "税后利润(百万元)",
        "新业务未来现金流入现值(百万元)",
    ]
    residues = {
        source: i18n.translate_text(source, "en")
        for source in visible_labels
        if re.search(r"[\u4e00-\u9fff]", i18n.translate_text(source, "en"))
    }
    assert residues == {}


def test_all_step8_scatter_axis_metadata_translates_fully():
    labels = [
        "保险服务收入区间（亿元）",
        "保险服务收入增长率区间（%）",
        "净投资回报区间（亿元）",
        "净投资回报增长率区间（%）",
        "保险服务费用区间（亿元）",
        "保险服务费用增长率区间（%）",
        "承保财务净损益区间（亿元）",
        "承保财务净损益增长率区间（%）",
        "保险服务业绩区间（亿元）",
        "保险服务业绩增长率区间（%）",
        "投资利润区间（亿元）",
        "投资利润增长率区间（%）",
        "净利润区间（亿元）",
        "净利润增长率区间（%）",
        "税前利润区间（亿元）",
        "税前利润增长率区间（%）",
        "其他综合收益区间（亿元）",
        "其他综合收益增长率区间（%）",
        "综合收益总额区间（亿元）",
        "综合收益总额增长率区间（%）",
        "CSM余额区间（亿元）",
        "CSM余额增长率区间（%）",
        "净资产区间（亿元）",
        "净资产增长率区间（%）",
        "综合净资产区间（亿元）",
        "综合净资产增长率区间（%）",
        "新业务CSM区间（亿元）",
        "新业务CSM增长率区间（%）",
        "新业务LC金额（亿元）",
        "新业务LC增长率区间（%）",
        "保险服务利润率区间（%）",
        "净投资回报率区间（%）",
    ]
    residues = {
        source: i18n.translate_text(source, "en")
        for source in labels
        if re.search(r"[\u4e00-\u9fff]", i18n.translate_text(source, "en"))
    }
    assert residues == {}


def test_step8_html_titles_use_the_same_complete_chart_translation():
    cases = {
        "<h3>净利润的贡献-保险服务业绩和投资服务业绩</h3>": (
            "<h3>Net Profit Contribution - Insurance and Investment Service Results</h3>"
        ),
        "<h3>保险服务收入的构成-非PAA和PAA合同组</h3>": (
            "<h3>Insurance Service Revenue Mix - Non-PAA and PAA Contract Groups</h3>"
        ),
        "<h3>最新年保险服务业绩构成</h3>": (
            "<h3>Latest-year Insurance Service Result Mix</h3>"
        ),
    }
    for source, target in cases.items():
        assert i18n.translate_text(source, "en") == target


def test_statistical_and_insurance_terms_are_in_the_local_dictionary():
    assert i18n.translate_text("各公司平均占比（中位数）", "en") == (
        "Average Share across Companies (Median)"
    )
    assert i18n.translate_text("类别代表值统一采用中位数。", "en") == (
        "Category representative values use the median."
    )
    assert i18n.translate_text("新业务 CSM", "en") == "New Business CSM"
    assert i18n.translate_text("CSM 计息", "en") == "CSM Interest Accretion"
    assert i18n.translate_text("CSM 调整", "en") == "CSM Adjustments"


def test_plotly_none_axis_titles_are_not_rendered_and_long_english_legends_get_space():
    figure = go.Figure()
    legend_sources = [
        "债权投资<br>（以摊余成本法计量）",
        "其他债权投资<br>（以公允价值计量入其他综合收益）",
        "交易性金融资产<br>（以公允价值计量入损益）",
        "其他权益工具投资<br>（以公允价值计量入其他综合收益）",
    ]
    for source in legend_sources:
        figure.add_bar(x=["2025YE"], y=[25], name=source)
    figure.update_layout(height=380, margin={"b": 20}, legend={"orientation": "h"})

    result = i18n.localize_plotly(figure, "en")
    assert result.layout.xaxis.title.text is None
    assert result.layout.yaxis.title.text is None
    assert all(not re.search(r"[\u4e00-\u9fff]", trace.name) for trace in result.data)
    assert result.layout.height >= 500
    assert result.layout.margin.b >= 170


def test_plotly_missing_value_markers_never_appear_as_visible_text():
    figure = go.Figure()
    figure.add_bar(
        x=["2024YE", "2025YE"],
        y=[40, 60],
        name="None",
        text=[None, "None"],
    )
    figure.update_xaxes(title_text="None", ticktext=["None", "2025YE"])
    figure.update_yaxes(title_text="null")

    result = i18n.localize_plotly(figure, "en")
    assert result.data[0].name == ""
    assert list(result.data[0].text) == ["", ""]
    assert result.layout.xaxis.title.text == ""
    assert result.layout.yaxis.title.text == ""
    assert list(result.layout.xaxis.ticktext) == ["", "2025YE"]


def test_plotly_report_periods_remain_categories_and_keep_bar_widths():
    figure = make_subplots(rows=1, cols=2)
    figure.add_bar(
        x=["2024年", "2025年"],
        y=[40, 60],
        width=0.55,
        row=1,
        col=1,
    )
    figure.add_bar(
        x=["2024年<br>12月", "2025年<br>12月"],
        y=[45, 55],
        width=0.55,
        row=1,
        col=2,
    )

    result = i18n.localize_plotly(figure, "en")

    assert list(result.data[0].x) == ["2024YE", "2025YE"]
    assert list(result.data[1].x) == ["2024-12", "2025-12"]
    assert result.layout.xaxis.type == "category"
    assert result.layout.xaxis2.type == "category"
    assert result.data[0].width == 0.55
    assert result.data[1].width == 0.55


def test_plotly_localisation_never_changes_numeric_line_data():
    figure = go.Figure()
    series = {
        "中国人寿": np.array([0.123, 0.121], dtype=np.float64),
        "平安人寿": np.array([0.090, 0.084], dtype=np.float64),
        "友邦人寿": np.array([0.104, 0.152], dtype=np.float64),
    }
    for company, values in series.items():
        figure.add_scatter(
            x=["2024年12月", "2025年12月"],
            y=values,
            name=company,
            mode="lines+markers",
        )
    figure.update_yaxes(tickformat=".1%")

    result = i18n.localize_plotly(figure, "en")

    assert [trace.name for trace in result.data] == [
        "China Life",
        "Ping An Life",
        "AIA China",
    ]
    for trace, expected in zip(result.data, series.values()):
        assert list(trace.x) == ["2024-12", "2025-12"]
        np.testing.assert_array_equal(np.asarray(trace.y), expected)
        assert all(isinstance(value, (float, np.floating)) for value in trace.y)
    assert result.layout.xaxis.type == "category"
    assert result.layout.yaxis.tickformat == ".1%"


def test_plotly_categorical_annotation_coordinates_follow_translated_companies():
    figure = go.Figure(
        go.Bar(x=["中国人寿", "平安人寿"], y=[100, 120])
    )
    figure.add_annotation(
        x="中国人寿",
        y=130,
        text="增长率 20%",
        showarrow=False,
    )

    result = i18n.localize_plotly(figure, "en")

    assert list(result.data[0].x) == ["China Life", "Ping An Life"]
    assert result.layout.annotations[0].x == "China Life"


def test_english_navigation_trigger_uses_compact_label():
    assert i18n.translate_text("展开导航栏", "en") == "Navigation"


def test_ai_queue_accepts_multiline_analysis_but_excludes_page_code(monkeypatch):
    narrative = (
        "下表展示本期和对比期不同保险公司采用的折现率假设。\n"
        "披露水平整体较为一致，并采用自下而上的方式。"
    )
    assert i18n._is_ai_translation_candidate(narrative, narrative)
    assert not i18n._is_ai_translation_candidate("中" * 2001, "中" * 2001)

    captured = []
    monkeypatch.setattr(
        i18n,
        "_record_untranslated_label",
        lambda source, translated: captured.append((source, translated)),
    )
    html = (
        "<style>.label{font-family:'微软雅黑';}</style>"
        f"<div><p>{narrative}</p></div>"
        "<script>const message = '不要发送这段中文';</script>"
    )
    i18n._record_untranslated_fragments(html, html)
    assert captured == [(narrative, narrative)]


def test_multiline_analysis_is_queued_and_cached_without_losing_breaks(monkeypatch):
    pending = {}
    cache = {}

    def fake_session_mapping(key):
        return cache if key == i18n.AI_TRANSLATION_CACHE_KEY else pending

    monkeypatch.setattr(i18n, "_session_mapping", fake_session_mapping)
    source = "这是未收录的保险分析段落第一行。\n这是第二行，需要完整翻译。"
    partially_translated = i18n.translate_text(source, "en")
    assert source in pending
    assert re.search(r"[\u4e00-\u9fff]", partially_translated)

    completed = "This is the first line of the analysis.\nThis is the second line."
    cache[source] = completed
    assert i18n.translate_text(source, "en") == completed


def test_ai_batch_prioritises_analysis_paragraphs_over_short_labels():
    items = {f"短标签{i}": f"短标签{i}" for i in range(80)}
    narrative = "第一段分析内容。\n第二段分析内容。"
    items[narrative] = narrative

    selected = i18n._select_ai_translation_batch(items)
    assert len(selected) == i18n.AI_TRANSLATION_MAX_ITEMS
    assert narrative in selected


def test_one_click_ai_completion_processes_every_safe_batch(monkeypatch):
    items = {f"待翻译标签{i}": f"待翻译标签{i}" for i in range(187)}
    api_calls = []
    progress = []

    def fake_translate_batch(remaining, api_key, base_url, model_name):
        selected = i18n._select_ai_translation_batch(remaining)
        api_calls.append(list(selected))
        return {source: f"English {index}" for index, source in enumerate(selected)}

    monkeypatch.setattr(
        i18n,
        "translate_pending_labels_with_ai",
        fake_translate_batch,
    )

    completed = i18n.translate_all_pending_labels_with_ai(
        items,
        "test-key",
        "https://example.invalid",
        "test-model",
        on_batch=lambda batch, done, total, number: progress.append(
            (len(batch), done, total, number)
        ),
    )

    assert len(completed) == 187
    assert [len(batch) for batch in api_calls] == [80, 80, 27]
    assert progress[-1] == (27, 187, 187, 3)


def test_ai_response_text_accepts_sdk_dict_and_raw_string_formats():
    class Message:
        content = "standard result"

    class Choice:
        message = Message()

    class Completion:
        choices = [Choice()]

    assert i18n.extract_ai_response_text(Completion()) == "standard result"
    assert i18n.extract_ai_response_text(
        {"choices": [{"message": {"content": "dictionary result"}}]}
    ) == "dictionary result"
    assert i18n.extract_ai_response_text(
        '{"choices":[{"message":{"content":"json result"}}]}'
    ) == "json result"
    assert i18n.extract_ai_response_text('{"中文":"English"}') == (
        '{"中文":"English"}'
    )


def test_ai_response_text_reports_company_network_interception_clearly():
    blocked_page = "<!DOCTYPE html><html><body>Access Denied</body></html>"
    try:
        i18n.extract_ai_response_text(blocked_page)
    except i18n.AIResponseFormatError as exc:
        assert "公司网络代理或防火墙" in str(exc)
    else:
        raise AssertionError("Expected a clear network-interception error")


def test_option_proxy_keeps_raw_chinese_value(monkeypatch):
    calls = {}

    class FakeStreamlit:
        def selectbox(self, label, options, **kwargs):
            calls["label"] = label
            calls["formatted"] = kwargs["format_func"](options[0])
            return options[0]

    monkeypatch.setattr(i18n, "get_language", lambda: i18n.LANG_EN)
    proxy = i18n._LocalizedStreamlitProxy(FakeStreamlit())
    selected = proxy.selectbox("公司类型", ["银行系", "养老"])
    assert selected == "银行系"
    assert calls == {"label": "Company type", "formatted": "Bank-affiliated"}


def test_multiselect_proxy_repairs_stale_english_session_values(monkeypatch):
    calls = {}

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {"s7_company_types": ["Leading"]}

        def multiselect(self, label, options, **kwargs):
            calls["label"] = label
            calls["default"] = kwargs["default"]
            calls["state"] = list(self.session_state[kwargs["key"]])
            calls["formatted"] = kwargs["format_func"]("头部")
            return list(self.session_state[kwargs["key"]])

    fake = FakeStreamlit()
    monkeypatch.setattr(i18n, "get_language", lambda: i18n.LANG_EN)
    proxy = i18n._LocalizedStreamlitProxy(fake)
    selected = proxy.multiselect(
        "公司类型",
        ["全部", "头部", "银行系"],
        default=["Leading"],
        key="s7_company_types",
    )

    assert selected == ["头部"]
    assert calls == {
        "label": "Company type",
        "default": ["头部"],
        "state": ["头部"],
        "formatted": "Leading",
    }


def test_tabs_keep_the_same_step_when_switching_back_to_chinese(monkeypatch):
    english_step7 = " 🖼️ Step 7 ／ Company Benchmarking Report "
    chinese_step7 = " 🖼️ Step 7 ／ 公司级对标报告 "
    calls = {}

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {"workflow_main_tab": english_step7}

        def tabs(self, labels, **kwargs):
            calls["labels"] = labels
            calls["state"] = self.session_state[kwargs["key"]]
            return labels

    fake = FakeStreamlit()
    monkeypatch.setattr(i18n, "get_language", lambda: i18n.LANG_ZH)
    proxy = i18n._LocalizedStreamlitProxy(fake)
    proxy.tabs(
        [
            " 📊 Step 6 ／ 自定义对标分析 ",
            chinese_step7,
            " 📈 Step 8 ／ 行业分类统计分析 ",
        ],
        key="workflow_main_tab",
        on_change="rerun",
    )

    assert calls["state"] == chinese_step7


def test_ai_completion_does_not_interrupt_the_run_before_workflow_widgets():
    source = inspect.getsource(i18n.render_language_switch)
    tree = ast.parse(source)
    rerun_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rerun"
    ]
    assert rerun_calls == []


def test_show_all_report_no_longer_inserts_fixed_appendix_png_pages():
    step7_source = (
        Path(i18n.__file__).resolve().parent / "step7.py"
    ).read_text(encoding="utf-8")
    assert "render_appendix_insert_pages" not in step7_source
    assert "appendix_urls" not in step7_source
    assert "%E6%96%B0%E5%87%86%E5%88%991.png" not in step7_source
    assert "%E6%96%B0%E5%87%86%E5%88%992.png" not in step7_source
    assert "%E6%96%B0%E5%87%86%E5%88%993.png" not in step7_source
