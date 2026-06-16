# -*- coding: utf-8 -*-
"""核心计算验证测试"""
import sys
sys.path.insert(0, '.')


def test_openai_base_url_normalization():
    from integrate import _openai_chat_url_candidates, normalize_openai_base_url
    from llm_store import _normalize_openai_base_url

    assert normalize_openai_base_url('https://xxapi.com.cn/') == 'https://xxapi.com.cn'
    assert normalize_openai_base_url('https://xxapi.com.cn/v1') == 'https://xxapi.com.cn/v1'
    assert normalize_openai_base_url(
        'https://xxapi.com.cn/v1/chat/completions'
    ) == 'https://xxapi.com.cn/v1'
    assert normalize_openai_base_url(
        'https://xxapi.com.cn/', append_v1=True
    ) == 'https://xxapi.com.cn/v1'
    assert _normalize_openai_base_url(
        'https://xxapi.com.cn/v1/chat/completions'
    ) == 'https://xxapi.com.cn/v1'
    assert _openai_chat_url_candidates('https://xxapi.com.cn/v1') == [
        'https://xxapi.com.cn/v1/chat/completions'
    ]
    assert _openai_chat_url_candidates('https://xxapi.com.cn/') == [
        'https://xxapi.com.cn/chat/completions',
        'https://xxapi.com.cn/v1/chat/completions',
    ]
    print("PASS: test_openai_base_url_normalization")


def test_lenient_mode_prompt():
    from integrate import _build_llm_messages

    sample = {
        '事件': '测试',
        '时空坐标': {
            '时间': '2024-06-15 12:00',
            '经度': 116.4,
            '纬度': 39.9,
            '城市估算': '北京',
        },
        '术数结果': {},
    }
    normal = _build_llm_messages(sample, "interpret", "角色提示", lenient_mode=False)
    relaxed = _build_llm_messages(sample, "interpret", "角色提示", lenient_mode=True)

    system_msg = relaxed[0]["content"]
    assert "本地宽松模式" in system_msg
    assert "输出要求" in system_msg
    assert "只输出给用户看的最终答案" in system_msg
    assert relaxed[1]["content"].startswith("/no_think")
    assert "不要输出思考过程" in relaxed[1]["content"]
    assert "过度拒答" in system_msg
    assert "本地宽松模式" not in normal[0]["content"]
    for marker in ("GODMODE", "RIOT", "JAILBREAK", "SAFETY RESTRICTIONS", "l33tspeak"):
        assert marker not in system_msg
    print("PASS: test_lenient_mode_prompt")


def test_dual_time_prompt_modes():
    from integrate import generate_advice_prompt, generate_prompt

    sample = {
        '事件': '测试双时间',
        '时空坐标': {
            '起卦时间': '2026-06-15 10:00',
            '出生时间': '1990-01-01 08:00',
            '经度': 116.4,
            '纬度': 39.9,
            '城市估算': '',
        },
        '术数结果': {'八字': {}, '大六壬': {}},
    }

    prompts = [
        generate_prompt(sample, mode='concise'),
        generate_prompt(sample, mode='expert'),
        generate_advice_prompt(sample, mode='concise'),
        generate_advice_prompt(sample, mode='expert'),
    ]
    for prompt in prompts:
        assert '起卦时间：2026-06-15 10:00' in prompt
        assert '出生时间：1990-01-01 08:00' in prompt
        assert '经度：116.4，纬度：39.9' in prompt
    print("PASS: test_dual_time_prompt_modes")


def test_expert_prompt_requires_all_method_sections():
    from integrate import generate_prompt

    sample = {
        '事件': '妈妈手术吉凶',
        '时空坐标': {
            '时间': '2026-06-15 10:00',
            '经度': 116.4,
            '纬度': 39.9,
            '城市估算': '北京',
        },
        '术数结果': {
            '八字': {},
            '紫微斗数': {},
            '奇门遁甲': {},
            '六爻': {},
            '梅花易数': {},
            '大六壬': {},
        },
    }

    prompt = generate_prompt(sample, mode='expert')
    assert '专家模式硬性输出规则' in prompt
    assert '不得省略、合并、只挑重点' in prompt
    for section in [
        '【八字视角】',
        '【紫微视角】',
        '【奇门视角】',
        '【六爻视角】',
        '【梅花视角】',
        '【大六壬视角】',
        '【综合断语】',
        '【风险提醒与行动建议】',
    ]:
        assert section in prompt
    print("PASS: test_expert_prompt_requires_all_method_sections")


def test_openai_excludes_reasoning_content():
    from integrate import _build_openai_payload, _extract_openai_content
    import json

    reasoning_only = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "本地模型只返回了思考字段",
                }
            }
        ]
    }
    with_content = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "正式回答",
                    "reasoning_content": "思考字段",
                }
            }
        ]
    }

    assert _extract_openai_content(reasoning_only) == ""
    assert _extract_openai_content(with_content) == "正式回答"

    default_payload = json.loads(_build_openai_payload([{"role": "user", "content": "你好"}], "cloud-model", False))
    assert "reasoning_effort" not in default_payload
    assert "chat_template_kwargs" not in default_payload

    local_payload = json.loads(
        _build_openai_payload(
            [{"role": "user", "content": "你好"}],
            "local-model",
            False,
            disable_thinking=True,
        )
    )
    assert local_payload["reasoning_effort"] == "none"
    assert local_payload["chat_template_kwargs"]["enable_thinking"] is False
    print("PASS: test_openai_excludes_reasoning_content")


def test_admin_provider_renderer_uses_provider_var():
    from pathlib import Path

    html = Path("static/admin.html").read_text(encoding="utf-8")
    assert "r.provider_configured" not in html
    assert "const configured=p.is_active" in html
    print("PASS: test_admin_provider_renderer_uses_provider_var")


def test_frontend_initial_load_retries():
    from pathlib import Path

    index_html = Path("static/index.html").read_text(encoding="utf-8")
    admin_html = Path("static/admin.html").read_text(encoding="utf-8")
    assert "fetchJsonWithRetry('/api/roles'" in index_html
    assert 'onclick="loadRoles()"' in index_html
    assert "retries:4" in admin_html
    print("PASS: test_frontend_initial_load_retries")


def test_frontend_copy_divination_without_event():
    from pathlib import Path

    index_html = Path("static/index.html").read_text(encoding="utf-8")
    assert "copyDivinationText" in index_html
    assert "复制卦象" in index_html
    assert "buildDivinationText(false)" in index_html
    assert "if(includeEvent) t+=`事件：" in index_html
    print("PASS: test_frontend_copy_divination_without_event")


def test_frontend_result_area_visible_by_default():
    from pathlib import Path

    index_html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<div id="resultArea">' in index_html
    assert '<div id="resultArea" style="display:none">' not in index_html
    assert "等待起卦。" in index_html
    print("PASS: test_frontend_result_area_visible_by_default")


def test_relationship_page_and_routes_present():
    from pathlib import Path

    main_py = Path("main.py").read_text(encoding="utf-8")
    relationship_html = Path("static/relationship.html").read_text(encoding="utf-8")
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    assert '@app.get("/relationship")' in main_py
    assert '@app.post("/api/relationship/divine")' in main_py
    assert '@app.post("/api/relationship/interpret")' in main_py
    assert '@app.post("/api/relationship/followup")' in main_py
    assert "关系复合盘" in relationship_html
    assert "copyDivinationText" in relationship_html
    assert "useFollowupQuestion" in relationship_html
    assert "推荐追问" in relationship_html
    assert "补充事实 / 回答追问" in relationship_html
    assert "context:$('context').value.trim()" in relationship_html
    assert "同盘追问" in relationship_html
    assert "沿用本盘继续解读" in relationship_html
    assert 'href="/relationship"' in index_html
    print("PASS: test_relationship_page_and_routes_present")


def test_relationship_divination_weak_description():
    from relationship import relationship_divination

    payload = {
        "event": "算算两个命主什么关系",
        "relation_type": "",
        "first_subject": {
            "gender": "男",
            "birth_year": 1982,
            "birth_month": 11,
            "birth_day": 12,
            "birth_hour": 13,
            "birth_minute": 15,
        },
        "second_subject": {
            "gender": "女",
            "birth_year": 1984,
            "birth_month": 8,
            "birth_day": 15,
            "birth_hour": 1,
            "birth_minute": 0,
        },
        "year": 2026,
        "month": 6,
        "day": 16,
        "hour": 6,
        "minute": 54,
        "longitude": 118.024093,
        "latitude": 36.814259,
    }
    result = relationship_divination(payload)
    relation = result["关系识别盘"]
    assert "关系描述" in relation
    assert "不作现实身份断言" in relation["一致性"]
    assert relation["盘面识别倾向"]["保守层级"] == "关系画像描述，不作现实身份断言"
    raw = result["原始盘要点"]
    assert raw["六爻"]["卦名"]
    assert raw["六爻"]["世爻"]
    assert raw["六爻"]["应爻"]
    assert raw["八字合盘"]["四柱对照"]
    meta = result["元解释器"]
    assert meta["问题识别"]["domain"] == "relationship"
    assert meta["权重调度"]["权重表"]
    assert any(row["术数"] == "关系复合卦" for row in meta["权重调度"]["权重表"])
    assert "用户结论" in meta
    assert meta["用户结论"]["一句话结论"]
    assert meta["用户结论"]["候选关系排行"]
    assert meta["用户结论"]["主框架"]["主框架"]
    assert meta["用户结论"]["动力"]
    assert meta["用户结论"]["信息缺口"]
    assert meta["用户结论"]["推荐追问"]
    assert "事实层" in meta["任务语义汇总"]
    assert "综合断语" in meta
    assert "不直接断言夫妻" in meta["综合断语"]["身份边界"]
    change = result["排盘变化校验"]
    assert change["请求指纹"]
    assert change["第二命主"]["四柱"]
    assert change["随命主变化"]["关系复合卦"]["本卦"]
    assert change["随起卦变化"]["六爻"]
    print("PASS: test_relationship_divination_weak_description")


def test_relationship_second_subject_change_diagnostics():
    from copy import deepcopy

    from relationship import relationship_divination

    payload = {
        "event": "算算两个命主什么关系",
        "relation_type": "",
        "first_subject": {
            "gender": "男",
            "birth_year": 1982,
            "birth_month": 11,
            "birth_day": 12,
            "birth_hour": 13,
            "birth_minute": 15,
        },
        "second_subject": {
            "gender": "女",
            "birth_year": 1984,
            "birth_month": 8,
            "birth_day": 15,
            "birth_hour": 1,
            "birth_minute": 0,
        },
        "year": 2026,
        "month": 6,
        "day": 16,
        "hour": 6,
        "minute": 54,
        "longitude": 118.024093,
        "latitude": 36.814259,
    }
    changed = deepcopy(payload)
    changed["second_subject"].update({
        "birth_year": 1986,
        "birth_month": 3,
        "birth_day": 21,
        "birth_hour": 9,
        "birth_minute": 30,
    })

    first = relationship_divination(payload)
    second = relationship_divination(changed)

    assert first["排盘变化校验"]["请求指纹"] != second["排盘变化校验"]["请求指纹"]
    assert first["排盘变化校验"]["第二命主"]["四柱"] != second["排盘变化校验"]["第二命主"]["四柱"]
    assert first["排盘变化校验"]["随命主变化"]["关系复合卦"]["第二命主数"] != second["排盘变化校验"]["随命主变化"]["关系复合卦"]["第二命主数"]
    assert first["当前问事盘"]["六爻"]["卦名"] == second["当前问事盘"]["六爻"]["卦名"]
    print("PASS: test_relationship_second_subject_change_diagnostics")


def test_relationship_parent_child_prior_suppresses_romance():
    from relationship import relationship_divination

    payload = {
        "event": "算算两个命主什么关系",
        "context": "这是我和儿子",
        "relation_type": "",
        "first_subject": {
            "gender": "男",
            "birth_year": 1982,
            "birth_month": 11,
            "birth_day": 12,
            "birth_hour": 13,
            "birth_minute": 15,
        },
        "second_subject": {
            "gender": "男",
            "birth_year": 2010,
            "birth_month": 8,
            "birth_day": 15,
            "birth_hour": 1,
            "birth_minute": 0,
        },
        "year": 2026,
        "month": 6,
        "day": 16,
        "hour": 6,
        "minute": 54,
        "longitude": 118.024093,
        "latitude": 36.814259,
    }
    result = relationship_divination(payload)
    user = result["元解释器"]["用户结论"]
    ranking = {item["类型"]: item["强度"] for item in user["候选关系排行"]}

    assert result["补充信息"] == "这是我和儿子"
    assert result["元解释器"]["关系先验"]["声明亲子"] is True
    assert user["主框架"]["主框架"] == "责任照护框架"
    assert ranking["亲缘/照护/长幼关系"] > ranking["婚恋/暧昧/亲密牵连"]
    assert "伴侣" not in user["推荐追问"][0]["问题"]
    print("PASS: test_relationship_parent_child_prior_suppresses_romance")


def test_relationship_stale_child_context_conflict():
    from relationship import relationship_divination

    payload = {
        "event": "算算两个命主什么关系",
        "context": "这是我和儿子",
        "relation_type": "",
        "first_subject": {
            "gender": "男",
            "birth_year": 1982,
            "birth_month": 11,
            "birth_day": 12,
            "birth_hour": 13,
            "birth_minute": 15,
        },
        "second_subject": {
            "gender": "女",
            "birth_year": 1990,
            "birth_month": 8,
            "birth_day": 15,
            "birth_hour": 1,
            "birth_minute": 0,
        },
        "year": 2026,
        "month": 6,
        "day": 16,
        "hour": 6,
        "minute": 54,
        "longitude": 118.024093,
        "latitude": 36.814259,
    }
    result = relationship_divination(payload)
    relation = result["关系识别盘"]
    prior = result["元解释器"]["关系先验"]

    assert prior["声明亲子"] is False
    assert prior["上下文冲突"]
    assert "上下文" in relation["主要来源"]
    assert "残留" in relation["关系描述"]
    print("PASS: test_relationship_stale_child_context_conflict")


def test_relationship_followup_contract_reuses_chart():
    from pathlib import Path

    main_py = Path("main.py").read_text(encoding="utf-8")
    relationship_py = Path("relationship.py").read_text(encoding="utf-8")

    assert "class RelationshipFollowupRequest" in main_py
    assert "chart: dict" in main_py
    assert "message: str" in main_py
    assert "relationship_divination(req.model_dump())" in main_py
    followup_section = main_py.split('async def relationship_followup', 1)[1].split('@app.get("/api/roles")', 1)[0]
    assert "relationship_divination(" not in followup_section
    assert "stream_relationship_followup" in followup_section
    assert "generate_relationship_followup_prompt" in relationship_py
    assert "不得重新起卦" in relationship_py
    print("PASS: test_relationship_followup_contract_reuses_chart")


def test_sqlite_busy_timeout():
    from llm_store import _connect

    conn = _connect()
    try:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy_timeout >= 5000
    finally:
        conn.close()
    print("PASS: test_sqlite_busy_timeout")


def test_jie_qi_month():
    from calendar_utils import get_jie_qi_month

    assert get_jie_qi_month(6, 15) == 5, f"June 15 should be 巳月(5), got {get_jie_qi_month(6, 15)}"
    assert get_jie_qi_month(2, 3) == 12, f"Feb 3 should be 丑月(12), got {get_jie_qi_month(2, 3)}"
    assert get_jie_qi_month(2, 5) == 1, f"Feb 5 should be 寅月(1), got {get_jie_qi_month(2, 5)}"
    assert get_jie_qi_month(1, 5) == 11, f"Jan 5 should be 子月(11), got {get_jie_qi_month(1, 5)}"
    assert get_jie_qi_month(1, 7) == 12, f"Jan 7 should be 丑月(12), got {get_jie_qi_month(1, 7)}"
    assert get_jie_qi_month(3, 7) == 2, f"Mar 7 should be 卯月(2), got {get_jie_qi_month(3, 7)}"
    assert get_jie_qi_month(8, 10) == 7, f"Aug 10 should be 申月(7), got {get_jie_qi_month(8, 10)}"
    assert get_jie_qi_month(12, 8) == 11, f"Dec 8 should be 子月(11), got {get_jie_qi_month(12, 8)}"
    print("PASS: test_jie_qi_month")


def test_true_solar_time():
    from calendar_utils import true_solar_time
    from datetime import date

    h, m, offset = true_solar_time(116.4, 12, 0, date_obj=date(2024, 6, 15))
    assert 0 <= h < 24, f"Hour out of range: {h}"
    assert offset == 0, f"Unexpected day offset: {offset}"

    h, m, offset = true_solar_time(80.0, 0, 0, date_obj=date(2024, 6, 15))
    assert offset == -1, f"Expected day_offset=-1 for far west at midnight, got {offset}"

    h, m, offset = true_solar_time(160.0, 23, 50, date_obj=date(2024, 6, 15))
    assert offset == 1, f"Expected day_offset=+1 for far east near midnight, got {offset}"
    print("PASS: test_true_solar_time")


def test_trigram_mapping():
    from meihua import gua_to_yao, yao_to_gua

    expected = {
        '乾': [1,1,1], '兑': [1,1,0], '离': [1,0,1], '震': [1,0,0],
        '巽': [0,1,1], '坎': [0,1,0], '艮': [0,0,1], '坤': [0,0,0]
    }
    for gua, yao in expected.items():
        result = gua_to_yao(gua)
        assert result == yao, f"{gua} expected {yao}, got {result}"
        back = yao_to_gua(yao)
        assert back == gua, f"yao_to_gua({yao}) expected {gua}, got {back}"
    print("PASS: test_trigram_mapping")


def test_meihua_bian_gua():
    """乾上坤下(天地否)动5爻: 上卦乾第二爻变 → 离上坤下(火地晋)"""
    from meihua import get_bian_gua
    bian_shang, bian_xia = get_bian_gua('乾', '坤', 5)
    assert bian_shang == '离', f"Expected 离, got {bian_shang}"
    assert bian_xia == '坤', f"Expected 坤, got {bian_xia}"

    # 乾为天动初爻: 下卦乾初爻变 → [0,1,1]=巽, 变卦=天风姤(乾上巽下)
    bian_shang2, bian_xia2 = get_bian_gua('乾', '乾', 1)
    assert bian_xia2 == '巽', f"乾动初爻下卦应变巽, got {bian_xia2}"
    assert bian_shang2 == '乾', f"上卦不动应仍为乾, got {bian_shang2}"
    print("PASS: test_meihua_bian_gua")


def test_najia_outer():
    from liuyao import zhuang_gua, NA_JIA_ZHI

    # 天地否: 乾上坤下
    result = zhuang_gua('乾', '坤', 1, 2024, 6, 15, 14, 30)
    # 外卦乾: NA_JIA_ZHI['乾'][3:6] = ['午','申','戌']
    assert result['六爻'][3]['干支'][1] == '午', f"Yao 4 expected 午, got {result['六爻'][3]['干支'][1]}"
    assert result['六爻'][4]['干支'][1] == '申', f"Yao 5 expected 申, got {result['六爻'][4]['干支'][1]}"
    assert result['六爻'][5]['干支'][1] == '戌', f"Yao 6 expected 戌, got {result['六爻'][5]['干支'][1]}"
    # 内卦坤: NA_JIA_ZHI['坤'][:3] = ['未','巳','卯']
    assert result['六爻'][0]['干支'][1] == '未', f"Yao 1 expected 未, got {result['六爻'][0]['干支'][1]}"
    print("PASS: test_najia_outer")


def test_liuyao_bian_zhi():
    """乾为天初爻动: 初爻纳甲子, 变卦下卦=巽, 巽NA_JIA_ZHI[:3]=['丑','亥','酉'], 变支应为丑"""
    from liuyao import zhuang_gua, NA_JIA_ZHI

    result = zhuang_gua('乾', '乾', 1, 2024, 6, 15, 14, 30)
    bian = result['六爻'][0]['变支']
    # 乾初爻动→下卦变巽, 巽内卦纳甲: NA_JIA_ZHI['巽'][:3] = ['丑','亥','酉']
    expected = NA_JIA_ZHI['巽'][0]  # 丑
    assert bian == expected, f"Bian_zhi expected {expected}, got {bian}"
    print("PASS: test_liuyao_bian_zhi")


def test_tao_hua():
    from bazi import TAO_HUA

    assert TAO_HUA['巳'] == '午', f"巳 taohua should be 午, got {TAO_HUA['巳']}"
    assert TAO_HUA['酉'] == '午', f"酉 taohua should be 午, got {TAO_HUA['酉']}"
    assert TAO_HUA['丑'] == '午', f"丑 taohua should be 午, got {TAO_HUA['丑']}"
    assert TAO_HUA['申'] == '酉', f"申 taohua should be 酉, got {TAO_HUA['申']}"
    assert TAO_HUA['子'] == '酉', f"子 taohua should be 酉, got {TAO_HUA['子']}"
    assert TAO_HUA['辰'] == '酉', f"辰 taohua should be 酉, got {TAO_HUA['辰']}"
    assert TAO_HUA['亥'] == '子', f"亥 taohua should be 子, got {TAO_HUA['亥']}"
    assert TAO_HUA['卯'] == '子', f"卯 taohua should be 子, got {TAO_HUA['卯']}"
    assert TAO_HUA['未'] == '子', f"未 taohua should be 子, got {TAO_HUA['未']}"
    assert TAO_HUA['寅'] == '卯', f"寅 taohua should be 卯, got {TAO_HUA['寅']}"
    print("PASS: test_tao_hua")


def test_qimen_offset_nonzero():
    from qimen import arrange_di_pan, get_zhi_fu_zhi_shi, arrange_tian_pan

    # 阳遁1局: 戊在1宫, 己在2宫, 庚在3宫, 辛在4宫, 壬在5宫, 癸在6宫, 丁在7宫, 丙在8宫, 乙在9宫
    di_pan = arrange_di_pan(1, True)

    # 时柱丙寅: 旬首=甲子(idx 0//10*10=0), 遁仪=戊, 戊在1宫 → zhi_fu_gong=1
    # 时干丙在地盘8宫 → shi_gan_gong=8, offset=7
    shi_gz = '丙寅'
    _, _, zhi_fu_gong = get_zhi_fu_zhi_shi(di_pan, shi_gz)
    assert zhi_fu_gong == 1, f"zhi_fu_gong expected 1, got {zhi_fu_gong}"

    tian_pan, tian_xing, shi_gan_gong = arrange_tian_pan(di_pan, zhi_fu_gong, True, '丙', shi_gz)
    assert shi_gan_gong == 8, f"shi_gan_gong expected 8, got {shi_gan_gong}"
    assert shi_gan_gong != zhi_fu_gong, "Offset should be non-zero"

    # 天盘应不等于地盘
    differ = any(tian_pan.get(g) != di_pan.get(g) for g in range(1, 10))
    assert differ, "Tian pan should differ from di pan"
    print("PASS: test_qimen_offset_nonzero")


def test_changsheng_yin_stem():
    """乙木(阴干)长生应在午，不是亥"""
    from bazi import get_chang_sheng_state
    result = get_chang_sheng_state('乙', '午')
    assert result == '长生', f"乙木长生在午, got {result}"
    # 甲木(阳干)长生在亥
    result2 = get_chang_sheng_state('甲', '亥')
    assert result2 == '长生', f"甲木长生在亥, got {result2}"
    print("PASS: test_changsheng_yin_stem")


def test_precise_jieqi_month():
    """节气交接时刻前后月柱切换（2024立春: 2024-02-04 16:27:07）"""
    from calendar_utils import _get_jie_qi_month_precise
    # 立春前一小时 → 应为丑月(12)
    assert _get_jie_qi_month_precise(2024, 2, 4, 15) == 12, "立春前应为丑月"
    # 立春后一小时 → 应为寅月(1)
    assert _get_jie_qi_month_precise(2024, 2, 4, 17) == 1, "立春后应为寅月"
    # 惊蛰 2024-03-05 10:22 前后
    assert _get_jie_qi_month_precise(2024, 3, 5, 9) == 1, "惊蛰前应为寅月"
    assert _get_jie_qi_month_precise(2024, 3, 5, 11) == 2, "惊蛰后应为卯月"
    print("PASS: test_precise_jieqi_month")


def test_bazi_lunar_python():
    """验证八字输出正确性"""
    from bazi import pa_pan
    r = pa_pan(1990, 5, 1, 8, 0, longitude=116.4)
    assert r['四柱']['年柱'] == '庚午', f"年柱应为庚午, got {r['四柱']['年柱']}"
    assert r['四柱']['月柱'] == '庚辰', f"月柱应为庚辰, got {r['四柱']['月柱']}"
    assert r['四柱']['日柱'] == '丙寅', f"日柱应为丙寅, got {r['四柱']['日柱']}"
    assert r['四柱']['时柱'] == '壬辰', f"时柱应为壬辰, got {r['四柱']['时柱']}"
    assert r['纳音']['日柱'] == '炉中火', f"日柱纳音应为炉中火, got {r['纳音']['日柱']}"
    print("PASS: test_bazi_lunar_python")


def test_bazi_dayun_uses_gender():
    from bazi import pa_pan

    male = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='男')
    female = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='女')

    assert male['大运']['顺逆'] == '顺行'
    assert female['大运']['顺逆'] == '逆行'
    assert male['大运']['运程'][0]['干支'] == '辛巳'
    assert female['大运']['运程'][0]['干支'] == '己卯'
    assert male['大运']['起运']['月数'] > 0
    print("PASS: test_bazi_dayun_uses_gender")


def test_qimen_zhishi_no_zhong():
    """验证值使永不为'中'"""
    from qimen import arrange_di_pan, get_zhi_fu_zhi_shi
    from calendar_utils import LIU_SHI_JIA_ZI
    # 测试所有9局 × 阳遁/阴遁，甲子时柱
    for ju in range(1, 10):
        for is_yang in (True, False):
            di_pan = arrange_di_pan(ju, is_yang)
            for sz in ['甲子', '甲午', '甲申', '甲戌', '甲辰', '甲寅']:
                _, men, _ = get_zhi_fu_zhi_shi(di_pan, sz)
                assert men != '中', f"局{ju} {'阳' if is_yang else '阴'}遁 {sz}: 值使不应为中, got {men}"
    print("PASS: test_qimen_zhishi_no_zhong")


def test_qimen_day_offset():
    """真太阳时跨日后奇门使用修正后日期"""
    from qimen import pa_pan
    from calendar_utils import ri_zhu
    r = pa_pan(2024, 1, 1, 23, 50, longitude=135.0)
    expected = ri_zhu(2024, 1, 2)
    assert r['日干支'] == expected, f"奇门跨日应用次日, expected {expected}, got {r['日干支']}"
    print("PASS: test_qimen_day_offset")


def test_liuyao_day_offset():
    """真太阳时跨日后六爻使用修正后日期"""
    from liuyao import pa_pan_by_time
    from calendar_utils import ri_zhu
    r = pa_pan_by_time(2024, 1, 1, 23, 50, longitude=135.0)
    expected = ri_zhu(2024, 1, 2)
    assert r['日干支'] == expected, f"六爻跨日应用次日, expected {expected}, got {r['日干支']}"
    print("PASS: test_liuyao_day_offset")


def test_qimen_chaibuf():
    """验证拆补法局数"""
    from qimen import get_dun_ju
    # 2024-06-15 14:00 → 芒种后（阳遁）
    dun, ju = get_dun_ju(2024, 6, 15, 14)
    assert dun == '阳遁', f"6月15日应为阳遁, got {dun}"
    assert 1 <= ju <= 9, f"局数应1-9, got {ju}"
    # 2024-08-15 10:00 → 立秋后（阴遁）
    dun2, ju2 = get_dun_ju(2024, 8, 15, 10)
    assert dun2 == '阴遁', f"8月15日应为阴遁, got {dun2}"
    assert 1 <= ju2 <= 9, f"局数应1-9, got {ju2}"
    # 2024-01-10 12:00 → 小寒后（阳遁）
    dun3, ju3 = get_dun_ju(2024, 1, 10, 12)
    assert dun3 == '阳遁', f"1月10日应为阳遁, got {dun3}"
    print("PASS: test_qimen_chaibuf")


def test_qimen_uses_full_24_jieqi():
    """lunar_python 的 getPrevJieQi 应返回完整24节气，奇门雨水后应查雨水局表。"""
    from qimen import _determine_yuan
    from lunar_python import Solar

    solar = Solar.fromYmdHms(2024, 2, 20, 12, 0, 0)
    table_jieqi, yuan = _determine_yuan(solar, solar.getLunar())
    assert table_jieqi == '雨水', f"雨水后应查雨水局表, got {table_jieqi}"
    assert yuan == 0, f"2024-02-20 甲寅符头日应为上元, got {yuan}"
    print("PASS: test_qimen_uses_full_24_jieqi")


def test_qimen_chai_case():
    """拆补法"拆"：节气后、符头前应回退到上一节气下元。
    2024-02-04 17:00 立春(16:27)后、符头2024-02-05己亥前 → 大寒下元=阳遁6局"""
    from qimen import get_dun_ju
    dun, ju = get_dun_ju(2024, 2, 4, 17)
    assert dun == '阳遁', f"应为阳遁, got {dun}"
    assert ju == 6, f"拆补法'拆'应取大寒下元6局, got {ju}"
    print("PASS: test_qimen_chai_case")


def test_qimen_find_futou_search_window():
    from qimen import _find_futou
    from calendar_utils import ri_zhu
    from datetime import date

    futou = _find_futou(date(2024, 2, 21))
    assert futou == date(2024, 2, 25), f"Expected 2024-02-25 己未, got {futou}"
    assert ri_zhu(futou.year, futou.month, futou.day)[0] == '己'
    print("PASS: test_qimen_find_futou_search_window")


def test_liuyao_gua64_unique():
    from liuyao import GUA_64

    assert len(GUA_64) == 64, f"GUA_64 should contain 64 unique hexagrams, got {len(GUA_64)}"
    print("PASS: test_liuyao_gua64_unique")


def test_liuyao_number_minute():
    """数字起卦排盘应保留分钟（影响时柱/真太阳时跨日）"""
    from liuyao import pa_pan_by_numbers
    r = pa_pan_by_numbers(3, 7, year=2024, month=1, day=1,
                          hour=23, minute=55, longitude=135.0)
    assert '卦名' in r
    print("PASS: test_liuyao_number_minute")


def test_jieqi_minute_window():
    """节气交接分钟窗口：2024-02-04 16:30 经度125 真太阳时16:35 > 立春16:27 → 寅月"""
    from calendar_utils import get_jie_qi_month, true_solar_time
    from datetime import date
    true_h, true_m, _ = true_solar_time(125, 16, 30, date_obj=date(2024, 2, 4))
    mnum = get_jie_qi_month(2024, 2, 4, true_h, true_m)
    assert mnum == 1, f"立春后应为寅月(1), got {mnum}"
    # 梅花在此条件下本卦应含兑（月数1影响上卦取数）
    from meihua import pa_pan as meihua_pan
    r = meihua_pan(2024, 2, 4, 16, 30, longitude=125.0)
    assert '兑' in r['本卦']['卦名'], f"精确寅月梅花本卦应含兑, got {r['本卦']['卦名']}"
    print("PASS: test_jieqi_minute_window")


def test_ziwei_basic():
    """紫微斗数基础验证：命宫、五行局、大限方向、大限起始"""
    from ziwei import pa_pan

    # 1990-05-01 08:00 男 庚午年
    r = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='男')
    assert r['命宫'] == '丑', f"命宫应为丑, got {r['命宫']}"
    assert '6局' in r['五行局'], f"应为火六局, got {r['五行局']}"
    # 火6局 农历初七 → 安紫微(商余补奇偶)落戌, 天府寅申线对称落午
    assert r['紫微星位'] == '戌', f"紫微星应为戌, got {r['紫微星位']}"
    assert r['天府星位'] == '午', f"天府星应为午, got {r['天府星位']}"
    assert r['大限方向'] == '顺行', f"庚年男应顺行, got {r['大限方向']}"
    assert r['大限'][0]['大限宫'] == r['命宫'], f"大限首步应从命宫起"
    assert '十二宫' in r
    assert len(r['十二宫']) == 12

    # 女命逆行
    r2 = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='女')
    assert r2['大限方向'] == '逆行', f"庚年女应逆行, got {r2['大限方向']}"

    # 四化：庚年 太阳禄 武曲权 太阴科 天同忌
    assert r['四化']['化禄'] == '太阳'
    assert r['四化']['化权'] == '武曲'
    assert r['四化']['化科'] == '太阴'
    assert r['四化']['化忌'] == '天同'
    print("PASS: test_ziwei_basic")


def test_ziwei_anziwei_formula():
    """安紫微公式（商数/余数/补数奇偶修正）对照权威参考表，寅宫起"""
    from ziwei import get_ziwei_zhi
    expected = {
        2: ['丑','寅','寅','卯','卯','辰','辰','巳','巳','午','午','未','未','申','申',
            '酉','酉','戌','戌','亥','亥','子','子','丑','丑','寅','寅','卯','卯','辰'],
        3: ['辰','丑','寅','巳','寅','卯','午','卯','辰','未','辰','巳','申','巳','午',
            '酉','午','未','戌','未','申','亥','申','酉','子','酉','戌','丑','戌','亥'],
        4: ['亥','辰','丑','寅','子','巳','寅','卯','丑','午','卯','辰','寅','未','辰',
            '巳','卯','申','巳','午','辰','酉','午','未','巳','戌','未','申','午','亥'],
        5: ['午','亥','辰','丑','寅','未','子','巳','寅','卯','申','丑','午','卯','辰',
            '酉','寅','未','辰','巳','戌','卯','申','巳','午','亥','辰','酉','午','未'],
        6: ['酉','午','亥','辰','丑','寅','戌','未','子','巳','寅','卯','亥','申','丑',
            '午','卯','辰','子','酉','寅','未','辰','巳','丑','戌','卯','申','巳','午'],
    }
    for ju, table in expected.items():
        for day in range(1, 31):
            got = get_ziwei_zhi(day, ju)
            assert got == table[day - 1], f"局{ju} 日{day}: 紫微应{table[day-1]}, got {got}"
    print("PASS: test_ziwei_anziwei_formula")


def test_ziwei_leap_month():
    """闰月排盘：以十五日为界，前半按本月、后半按下月；显示月与排盘月分离。
    2023 闰二月：03-23=闰2月初二(前半,排盘2)，04-06=闰2月十六(后半,排盘3)"""
    from ziwei import pa_pan

    # 闰二月前半（初二）→ 显示闰2月，排盘月=2
    r1 = pa_pan(2023, 3, 23, 12, 0, longitude=120.0, gender='男')
    assert r1['农历月日'] == '闰2月2日', f"应为闰2月2日, got {r1['农历月日']}"
    assert r1['排盘月'] == 2, f"前半月排盘月应为2, got {r1['排盘月']}"
    assert '前半月' in r1['闰月处理'], f"应标注前半月, got {r1['闰月处理']}"

    # 闰二月后半（十六）→ 显示仍为闰2月，排盘月=3
    r2 = pa_pan(2023, 4, 6, 12, 0, longitude=120.0, gender='男')
    assert r2['农历月日'] == '闰2月16日', f"应为闰2月16日, got {r2['农历月日']}"
    assert r2['排盘月'] == 3, f"后半月排盘月应为3, got {r2['排盘月']}"
    assert '后半月' in r2['闰月处理'], f"应标注后半月, got {r2['闰月处理']}"

    # 非闰月不应有闰月处理说明
    r3 = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='男')
    assert r3['闰月处理'] == '', f"非闰月不应有折算说明, got {r3['闰月处理']}"

    # 手动传参负数闰月（lunar_month=-2）应与自动转换路径一致归一化
    r4 = pa_pan(2023, 4, 6, 12, 0, longitude=120.0, gender='男',
                lunar_month=-2, lunar_day=16)
    assert r4['农历月日'] == '闰2月16日', f"手动负数闰月应为闰2月16日, got {r4['农历月日']}"
    assert r4['排盘月'] == 3, f"手动负数闰月后半排盘月应为3, got {r4['排盘月']}"
    assert r4['命宫'] == r2['命宫'], f"手动与自动路径命宫应一致, got {r4['命宫']} vs {r2['命宫']}"
    print("PASS: test_ziwei_leap_month")


def test_ziwei_registry():
    """通过 integrate 注册表调用紫微"""
    from integrate import multi_divination
    r = multi_divination('测试', 1990, 5, 1, 8, 0, longitude=116.4, gender='男', methods=['紫微'])
    assert '紫微斗数' in r['术数结果']
    assert r['术数结果']['紫微斗数']['命宫'] == '丑'
    print("PASS: test_ziwei_registry")


def test_qimen_dongzhi_yangdun():
    """冬至后应切换到阳遁。2024-12-21 冬至17:20:35，18:00应为阳遁"""
    from qimen import get_dun_ju
    dun, ju = get_dun_ju(2024, 12, 21, 18, 0)
    assert dun == '阳遁', f"冬至后应为阳遁, got {dun}"
    dun2, ju2 = get_dun_ju(2024, 12, 25, 12, 0)
    assert dun2 == '阳遁', f"冬至后数日仍应为阳遁, got {dun2}"
    print("PASS: test_qimen_dongzhi_yangdun")


def test_daliuren_basic():
    """大六壬基础验证：天盘、四课、三传、天将"""
    from daliuren import pa_pan
    r = pa_pan(2024, 6, 15, 14, 30, longitude=116.4, birth_year=1990, gender='男')

    # 基础字段存在
    assert '日干支' in r
    assert '时干支' in r
    assert '月将' in r
    assert '昼夜' in r
    assert '四课' in r
    assert '三传' in r

    # 四课应有4条
    assert len(r['四课']) == 4

    # 三传应有初中末和起传法
    sc = r['三传']
    assert '初传' in sc
    assert '中传' in sc
    assert '末传' in sc
    assert '起传法' in sc

    # 每传应有完整信息
    for pos in ['初传', '中传', '末传']:
        assert '干支' in sc[pos]
        assert '天将' in sc[pos]
        assert '五行' in sc[pos]
        assert '旺衰' in sc[pos]

    # 昼夜判断：14:30应为昼
    assert r['昼夜'] == '昼'

    print("PASS: test_daliuren_basic")


def test_daliuren_daytime_boundaries():
    from daliuren import is_daytime, get_gui_shen_pos

    assert is_daytime('寅') is False, "寅时应为夜"
    assert is_daytime('卯') is True, "卯时应为昼"
    assert is_daytime('申') is True, "申时应为昼"
    assert is_daytime('酉') is False, "酉时应为夜"
    assert get_gui_shen_pos('甲', '寅') == '未'
    assert get_gui_shen_pos('甲', '申') == '丑'
    print("PASS: test_daliuren_daytime_boundaries")


def test_daliuren_yue_jiang_uses_zhongqi():
    from daliuren import get_yue_jiang

    assert get_yue_jiang(2024, 1, 10, 12) == '丑', "小寒后冬至中气仍应取丑将"
    assert get_yue_jiang(2024, 2, 20, 12) == '亥', "雨水后应取亥将"
    print("PASS: test_daliuren_yue_jiang_uses_zhongqi")


def test_daliuren_registry():
    """通过 integrate 注册表调用大六壬"""
    from integrate import multi_divination
    r = multi_divination('测试', 2024, 6, 15, 14, 30, longitude=116.4,
                         birth_year=1990, gender='男', methods=['大六壬'])
    assert '大六壬' in r['术数结果']
    assert r['术数结果']['大六壬']['昼夜'] == '昼'
    print("PASS: test_daliuren_registry")


def test_daliuren_jiuzongmen_branches():
    """大六壬九宗门主分支应覆盖生产 get_san_chuan。"""
    import test_daliuren_jiuzongmen as t

    t.test_fu_yin()
    t.test_fan_yin()
    t.test_fan_yin_prefers_ke_when_present()
    t.test_zei_ke_single()
    t.test_zhi_yi()
    t.test_ke_fa()
    t.test_she_hai()
    t.test_she_hai_counts_path_relations()
    t.test_yao_ke()
    t.test_ba_zhuan()
    t.test_yao_ke_before_ba_zhuan()
    t.test_bie_ze()
    t.test_mao_xing()
    print("PASS: test_daliuren_jiuzongmen_branches")


if __name__ == '__main__':
    test_openai_base_url_normalization()
    test_lenient_mode_prompt()
    test_dual_time_prompt_modes()
    test_expert_prompt_requires_all_method_sections()
    test_openai_excludes_reasoning_content()
    test_admin_provider_renderer_uses_provider_var()
    test_frontend_initial_load_retries()
    test_frontend_copy_divination_without_event()
    test_relationship_page_and_routes_present()
    test_relationship_divination_weak_description()
    test_relationship_second_subject_change_diagnostics()
    test_relationship_parent_child_prior_suppresses_romance()
    test_relationship_stale_child_context_conflict()
    test_relationship_followup_contract_reuses_chart()
    test_sqlite_busy_timeout()
    test_jie_qi_month()
    test_true_solar_time()
    test_trigram_mapping()
    test_meihua_bian_gua()
    test_najia_outer()
    test_liuyao_bian_zhi()
    test_tao_hua()
    test_qimen_offset_nonzero()
    test_changsheng_yin_stem()
    test_precise_jieqi_month()
    test_bazi_lunar_python()
    test_bazi_dayun_uses_gender()
    test_qimen_zhishi_no_zhong()
    test_qimen_day_offset()
    test_liuyao_day_offset()
    test_qimen_chaibuf()
    test_qimen_uses_full_24_jieqi()
    test_qimen_chai_case()
    test_qimen_find_futou_search_window()
    test_liuyao_gua64_unique()
    test_liuyao_number_minute()
    test_jieqi_minute_window()
    test_qimen_dongzhi_yangdun()
    test_daliuren_basic()
    test_daliuren_daytime_boundaries()
    test_daliuren_yue_jiang_uses_zhongqi()
    test_daliuren_registry()
    test_daliuren_jiuzongmen_branches()
    test_ziwei_basic()
    test_ziwei_anziwei_formula()
    test_ziwei_leap_month()
    test_ziwei_registry()
    print("\n=== ALL TESTS PASSED ===")
