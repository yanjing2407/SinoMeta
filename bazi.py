# -*- coding: utf-8 -*-
"""
四柱八字起盘模块
规则说明:
  1. 输入出生时间+经纬度 → 真太阳时修正 → 排四柱（年月日时各一组干支）
  2. 以日干为"我"，对照其他天干得十神
  3. 统计五行力量判断日主强弱
  4. 查神煞（天乙贵人、驿马、桃花、旬空等）
"""

from datetime import date, timedelta
from calendar_utils import (
    TIAN_GAN, DI_ZHI, LIU_SHI_JIA_ZI, TIAN_GAN_WX, DI_ZHI_WX,
    TIAN_GAN_YY, DI_ZHI_CANG, CANG_WEIGHT, WX_SHENG, WX_KE,
    true_solar_time, get_jie_qi_month, nian_zhu, yue_zhu, ri_zhu, shi_zhu, xun_kong
)

# ==================== 十神表 ====================
# 规则: 以日干五行为"我"，查其他天干五行的生克关系+阴阳异同
# 同我=比劫，我生=食伤，我克=财，克我=官杀，生我=印
# 阴阳相同=偏，阴阳相异=正

def get_shi_shen(ri_gan, other_gan):
    """计算十神"""
    ri_wx, ot_wx = TIAN_GAN_WX[ri_gan], TIAN_GAN_WX[other_gan]
    same_yy = (TIAN_GAN_YY[ri_gan] == TIAN_GAN_YY[other_gan])
    
    if ri_wx == ot_wx:
        return '比肩' if same_yy else '劫财'
    
    # 我生
    if WX_SHENG[ri_wx] == ot_wx:
        return '食神' if same_yy else '伤官'
    
    # 我克
    if WX_KE[ri_wx] == ot_wx:
        return '偏财' if same_yy else '正财'
    
    # 克我
    if WX_KE[ot_wx] == ri_wx:
        return '七杀' if same_yy else '正官'
    
    # 生我
    if WX_SHENG[ot_wx] == ri_wx:
        return '偏印' if same_yy else '正印'
    
    return '未知'


# ==================== 十二长生 ====================
# 规则: 阳干顺行，阴干逆行

CHANG_SHENG = {
    '木': {'亥':'长生','子':'沐浴','丑':'冠带','寅':'临官','卯':'帝旺',
           '辰':'衰','巳':'病','午':'死','未':'墓','申':'绝','酉':'胎','戌':'养'},
    '火': {'寅':'长生','卯':'沐浴','辰':'冠带','巳':'临官','午':'帝旺',
           '未':'衰','申':'病','酉':'死','戌':'墓','亥':'绝','子':'胎','丑':'养'},
    '金': {'巳':'长生','午':'沐浴','未':'冠带','申':'临官','酉':'帝旺',
           '戌':'衰','亥':'病','子':'死','丑':'墓','寅':'绝','卯':'胎','辰':'养'},
    '水': {'申':'长生','酉':'沐浴','戌':'冠带','亥':'临官','子':'帝旺',
           '丑':'衰','寅':'病','卯':'死','辰':'墓','巳':'绝','午':'胎','未':'养'},
    '土': {'寅':'长生','卯':'沐浴','辰':'冠带','巳':'临官','午':'帝旺',
           '未':'衰','申':'病','酉':'死','戌':'墓','亥':'绝','子':'胎','丑':'养'},
}

CHANG_SHENG_ORDER = ['长生','沐浴','冠带','临官','帝旺','衰','病','死','墓','绝','胎','养']

# 阴干长生起始地支
YIN_GAN_CS_START = {'乙':'午', '丁':'酉', '己':'酉', '辛':'子', '癸':'卯'}


def get_chang_sheng_state(ri_gan, zhi):
    """十二长生查询，阳干顺行，阴干逆行"""
    wx = TIAN_GAN_WX[ri_gan]
    is_yang = (TIAN_GAN_YY[ri_gan] == '阳')

    if is_yang:
        return CHANG_SHENG.get(wx, {}).get(zhi, '未知')

    # 阴干：从固定长生位逆排
    start_zhi = YIN_GAN_CS_START.get(ri_gan)
    if start_zhi is None:
        return '未知'
    start_idx = DI_ZHI.index(start_zhi)
    target_idx = DI_ZHI.index(zhi)
    # 逆行: 从start_idx往回数
    offset = (start_idx - target_idx) % 12
    return CHANG_SHENG_ORDER[offset]


# ==================== 神煞表 ====================

# 天乙贵人（以日干查，见于四柱地支即为贵人）
TIAN_YI = {'甲':['丑','未'],'乙':['子','申'],'丙':['亥','酉'],'丁':['亥','酉'],
           '戊':['丑','未'],'己':['子','申'],'庚':['丑','未'],'辛':['午','寅'],
           '壬':['卯','巳'],'癸':['卯','巳']}

# 驿马（以年支查，冲三合局首字）
YI_MA = {'寅':'申','午':'申','戌':'申','申':'寅','子':'寅','辰':'寅',
         '巳':'亥','酉':'亥','丑':'亥','亥':'巳','卯':'巳','未':'巳'}

# 桃花（以年支查，三合局沐浴位）
TAO_HUA = {'寅':'卯','午':'卯','戌':'卯','巳':'午','酉':'午','丑':'午',
           '申':'酉','子':'酉','辰':'酉','亥':'子','卯':'子','未':'子'}


# ==================== 五行旺衰分析 ====================

def analyze_wuxing(pillars):
    """
    统计四柱中各五行的力量值
    规则:
      - 天干各计1分，月干加成0.5
      - 地支藏干按权重计分，月支加成50%
      - 月令（月支本气五行）额外+2分（月令最旺）
    """
    score = {'木':0,'火':0,'土':0,'金':0,'水':0}
    
    for pos in ['年柱','月柱','日柱','时柱']:
        gz = pillars[pos]
        # 天干
        gwx = TIAN_GAN_WX[gz[0]]
        bonus = 0.5 if pos == '月柱' else 0
        score[gwx] += 1.0 + bonus
        
        # 地支藏干
        zhi = gz[1]
        cang = DI_ZHI_CANG[zhi]
        wt = CANG_WEIGHT[zhi]
        for i, cg in enumerate(cang):
            cwx = TIAN_GAN_WX[cg]
            w = wt[i]
            if pos == '月柱':
                w *= 1.5
            score[cwx] += w
    
    # 月令加成
    month_wx = DI_ZHI_WX[pillars['月柱'][1]]
    score[month_wx] += 2.0
    
    return score


def judge_qiang_ruo(pillars):
    """
    判断日主强弱
    规则: 帮身力量(比劫+印) vs 耗身力量(食伤+财+官杀)
    帮身>50%为身强，否则身弱
    """
    ri_gan = pillars['日柱'][0]
    ri_wx = TIAN_GAN_WX[ri_gan]
    score = analyze_wuxing(pillars)
    
    # 生我者=印
    sheng_wo = [wx for wx, v in WX_SHENG.items() if v == ri_wx]
    
    help_score = score[ri_wx]  # 比劫
    for wx in sheng_wo:
        help_score += score[wx]
    
    total = sum(score.values())
    ratio = help_score / total if total > 0 else 0
    
    label = '身强' if ratio >= 0.5 else '身弱'
    desc = f"帮身(比劫+印)占比{ratio:.0%}，{label}。用神宜{'克泄耗' if ratio>=0.5 else '生扶'}。"
    return label, round(ratio, 2), desc


# ==================== 主函数 ====================

def pa_pan(year, month, day, hour, minute=0, longitude=120.0, gender='男'):
    """
    八字起盘（使用 lunar_python 精确节气边界）

    参数:
        year, month, day: 公历出生日期
        hour, minute: 出生时间(24小时制)
        longitude: 经度(东经)，用于真太阳时修正
        gender: 性别（男/女）
    返回:
        dict 完整八字盘面信息
    """
    from lunar_python import Solar

    # 1. 真太阳时修正
    dt = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt)

    # 真太阳时跨日处理
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt + timedelta(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day

    # 2. 用 lunar_python 排四柱（精确到节气秒级边界）
    solar = Solar.fromYmdHms(act_y, act_m, act_d, true_h, true_m, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(2)

    nz = ec.getYear()
    yz = ec.getMonth()
    rz = ec.getDay()
    sz = ec.getTime()

    pillars = {'年柱': nz, '月柱': yz, '日柱': rz, '时柱': sz}

    # 3. 十神（lunar_python 提供）
    ri_gan = rz[0]
    shi_shen = {
        '年柱': {
            '天干': ec.getYearShiShenGan(),
            '地支藏干': ec.getYearShiShenZhi()
        },
        '月柱': {
            '天干': ec.getMonthShiShenGan(),
            '地支藏干': ec.getMonthShiShenZhi()
        },
        '日柱': {
            '天干': '日主',
            '地支藏干': ec.getDayShiShenZhi()
        },
        '时柱': {
            '天干': ec.getTimeShiShenGan(),
            '地支藏干': ec.getTimeShiShenZhi()
        },
    }

    # 4. 五行力量（自行实现，lunar_python 不提供）
    wx_score = analyze_wuxing(pillars)

    # 5. 日主强弱
    qr_label, qr_score, qr_desc = judge_qiang_ruo(pillars)

    # 6. 神煞
    all_zhi = [pillars[k][1] for k in ['年柱','月柱','日柱','时柱']]
    nian_zhi = pillars['年柱'][1]
    xunkong_str = ec.getDayXunKong()
    xunkong_list = [xunkong_str[0], xunkong_str[1]] if len(xunkong_str) == 2 else list(xunkong_str)
    shen_sha = {
        '天乙贵人': [z for z in all_zhi if z in TIAN_YI.get(ri_gan, [])],
        '驿马': [z for z in all_zhi if z == YI_MA.get(nian_zhi, '')],
        '桃花': [z for z in all_zhi if z == TAO_HUA.get(nian_zhi, '')],
        '旬空': xunkong_list,
        '落空地支': [z for z in all_zhi if z in xunkong_list]
    }

    # 7. 十二长生（lunar_python 提供）
    chang_sheng = {
        '年柱': ec.getYearDiShi(),
        '月柱': ec.getMonthDiShi(),
        '日柱': ec.getDayDiShi(),
        '时柱': ec.getTimeDiShi(),
    }

    # 8. 纳音
    na_yin = {
        '年柱': ec.getYearNaYin(),
        '月柱': ec.getMonthNaYin(),
        '日柱': ec.getDayNaYin(),
        '时柱': ec.getTimeNaYin(),
    }

    # 9. 生肖
    sx = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
          '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'}

    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '经度': longitude,
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '性别': gender,
        '四柱': pillars,
        '十神': shi_shen,
        '纳音': na_yin,
        '五行力量': wx_score,
        '日主五行': TIAN_GAN_WX[ri_gan],
        '日主阴阳': TIAN_GAN_YY[ri_gan],
        '日主强弱': {'判断': qr_label, '得分': qr_score, '说明': qr_desc},
        '十二长生': chang_sheng,
        '神煞': shen_sha,
        '生肖': sx.get(nz[1], ''),
    }


# ==================== 测试 ====================
if __name__ == '__main__':
    result = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='男')
    for k, v in result.items():
        print(f"  {k}: {v}")
