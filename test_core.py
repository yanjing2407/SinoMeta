# -*- coding: utf-8 -*-
"""核心计算验证测试"""
import sys
sys.path.insert(0, '.')


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


def test_qimen_chai_case():
    """拆补法"拆"：节气后、符头前应回退到上一节气下元。
    2024-02-04 17:00 立春(16:27)后、符头2024-02-05己亥前 → 大寒下元=阳遁6局"""
    from qimen import get_dun_ju
    dun, ju = get_dun_ju(2024, 2, 4, 17)
    assert dun == '阳遁', f"应为阳遁, got {dun}"
    assert ju == 6, f"拆补法'拆'应取大寒下元6局, got {ju}"
    print("PASS: test_qimen_chai_case")


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


def test_qimen_dongzhi_yangdun():
    """冬至后应切换到阳遁。2024-12-21 冬至17:20:35，18:00应为阳遁"""
    from qimen import get_dun_ju
    dun, ju = get_dun_ju(2024, 12, 21, 18, 0)
    assert dun == '阳遁', f"冬至后应为阳遁, got {dun}"
    dun2, ju2 = get_dun_ju(2024, 12, 25, 12, 0)
    assert dun2 == '阳遁', f"冬至后数日仍应为阳遁, got {dun2}"
    print("PASS: test_qimen_dongzhi_yangdun")


if __name__ == '__main__':
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
    test_qimen_zhishi_no_zhong()
    test_qimen_day_offset()
    test_liuyao_day_offset()
    test_qimen_chaibuf()
    test_qimen_chai_case()
    test_liuyao_number_minute()
    test_jieqi_minute_window()
    test_qimen_dongzhi_yangdun()
    print("\n=== ALL TESTS PASSED ===")
