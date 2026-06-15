# -*- coding: utf-8 -*-
"""
大六壬起盘模块
==============
规则说明:
  大六壬是"三式"之一，专精人事吉凶推演。
  以"月将加占时"排天盘，结合日干支推四课三传，
  再配天将、遁干、神煞等综合判断。
  
  排盘步骤:
    1. 定月将：根据节气确定当月月将
    2. 排天盘：月将加占时，天盘地支顺排
    3. 推四课：日干寄宫得第一课，依次推四课
    4. 定三传：九宗门（贼克、知一/比用、涉害、遥克、昴星、别责、八专、伏吟、返吟）
    5. 配天将：十二天将随贵神排列
    6. 遁干：三传配天干
    7. 查神煞：旬空、驿马、桃花、华盖等
    8. 排本命行年
"""

from calendar_utils import (
    TIAN_GAN, DI_ZHI, TIAN_GAN_WX, DI_ZHI_WX, 
    WX_SHENG, WX_KE, true_solar_time, ri_zhu, shi_zhu, 
    shi_chen_idx, nian_zhu, get_jie_qi_month, xun_kong
)
from datetime import date

# ==================== 基础常量 ====================

# 月份→月将（按中气换将）
# 中气：雨水→亥登明、春分→戌天魁、谷雨→酉从魁、小满→申传送
#       夏至→未小吉、大暑→午胜光、处暑→巳太乙、秋分→辰天罡
#       霜降→卯太冲、小雪→寅功曹、冬至→丑大吉、大寒→子神后
ZHONGQI_TO_JIANG = {
    '雨水': '亥', '春分': '戌', '谷雨': '酉', '小满': '申',
    '夏至': '未', '大暑': '午', '处暑': '巳', '秋分': '辰',
    '霜降': '卯', '小雪': '寅', '冬至': '丑', '大寒': '子',
}

# 节气月→月将近似表（降级备用）
MONTH_TO_JIANG = {
    1:'亥', 2:'戌', 3:'酉', 4:'申', 5:'未', 6:'午',
    7:'巳', 8:'辰', 9:'卯', 10:'寅', 11:'丑', 12:'子'
}

def get_yue_jiang(year, month, day, hour, minute=0):
    """
    按中气确定月将
    大六壬以中气换月将，而非节气
    """
    try:
        from lunar_python import Solar
        solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
        lunar = solar.getLunar()
        # 获取当前或上一个中气
        prev_qi = lunar.getPrevQi()
        if prev_qi:
            qi_name = prev_qi.getName()
            if qi_name in ZHONGQI_TO_JIANG:
                return ZHONGQI_TO_JIANG[qi_name]
        # 如果获取失败，使用近似方法
    except:
        pass

    # 降级：使用节气月近似（虽然不准确，但至少能用）
    jq_month = get_jie_qi_month(month, day)
    return MONTH_TO_JIANG.get(jq_month, '子')

# 月将名
JIANG_NAME = {
    '亥':'登明','戌':'天魁','酉':'从魁','申':'传送',
    '未':'小吉','午':'胜光','巳':'太乙','辰':'天罡',
    '卯':'太冲','寅':'功曹','丑':'大吉','子':'神后'
}

# 日干寄宫
GAN_JI_GONG = {
    '甲':'寅','乙':'辰','丙':'巳','丁':'未','戊':'巳',
    '己':'未','庚':'申','辛':'戌','壬':'亥','癸':'丑'
}

# 地支六冲
CHONG = {'子':'午','午':'子','丑':'未','未':'丑','寅':'申','申':'寅',
         '卯':'酉','酉':'卯','辰':'戌','戌':'辰','巳':'亥','亥':'巳'}

# 十二天将
TIAN_JIANG_NAMES = ['贵人','螣蛇','朱雀','六合','勾陈','青龙',
                    '天空','白虎','太常','玄武','太阴','天后']

TIAN_JIANG_DESC = {
    '贵人':'主官禄贵人','螣蛇':'主惊恐怪异','朱雀':'主口舌文书',
    '六合':'主和合婚姻','勾陈':'主田土迟滞','青龙':'主喜庆财利',
    '天空':'主欺诈虚空','白虎':'主血光凶丧','太常':'主饮食官职',
    '玄武':'主盗贼暗昧','太阴':'主阴私女人','天后':'主婚姻女命',
}

# 天乙贵人位置（昼贵，夜贵）
GUI_SHEN = {
    '甲':('丑','未'),'戊':('丑','未'),'庚':('丑','未'),
    '乙':('子','申'),'己':('子','申'),
    '丙':('亥','酉'),'丁':('亥','酉'),
    '壬':('卯','巳'),'癸':('卯','巳'),
    '辛':('午','寅'),
}

# 常用神煞
YI_MA = {'寅':'申','午':'申','戌':'申','申':'寅','子':'寅','辰':'寅',
         '巳':'亥','酉':'亥','丑':'亥','亥':'巳','卯':'巳','未':'巳'}

HUA_GAI = {'子':'辰','丑':'辰','寅':'戌','卯':'戌','辰':'戌','巳':'未',
           '午':'未','未':'未','申':'丑','酉':'丑','戌':'丑','亥':'辰'}

TAO_HUA = {'寅':'卯','午':'卯','戌':'卯','巳':'酉','酉':'酉','丑':'酉',
           '申':'子','子':'子','辰':'子','亥':'午','卯':'午','未':'午'}


# ==================== 核心函数 ====================

def arrange_tian_pan(yue_jiang_zhi, shi_chen_zhi):
    """
    排天盘
    规则：月将加占时，地支顺排
    即将月将放在时辰地支位置，其余顺时针排列
    """
    yj_idx = DI_ZHI.index(yue_jiang_zhi)
    sc_idx = DI_ZHI.index(shi_chen_zhi)
    offset = (sc_idx - yj_idx) % 12
    return {DI_ZHI[i]: DI_ZHI[(i - offset) % 12] for i in range(12)}


def get_si_ke(ri_gan, ri_zhi, tian_pan):
    """
    推四课
    第一课(干阳神)=天盘[干寄宫]上加干寄宫
    第二课(干阴神)=天盘[第一课上支]上加第一课上支
    第三课(支阳神)=天盘[日支]上加日支
    第四课(支阴神)=天盘[第三课上支]上加第三课上支
    """
    gg = GAN_JI_GONG[ri_gan]
    k1u = tian_pan[gg]; k1l = gg
    k2u = tian_pan[k1u]; k2l = k1u
    k3u = tian_pan[ri_zhi]; k3l = ri_zhi
    k4u = tian_pan[k3u]; k4l = k3u
    return [('第一课(干阳)',k1u,k1l), ('第二课(干阴)',k2u,k2l),
            ('第三课(支阳)',k3u,k3l), ('第四课(支阴)',k4u,k4l)]


def ke_relation(upper, lower):
    """判断上下支的克贼关系"""
    uw, lw = DI_ZHI_WX[upper], DI_ZHI_WX[lower]
    if WX_KE.get(lw) == uw: return '贼'
    if WX_KE.get(uw) == lw: return '克'
    if WX_SHENG.get(lw) == uw: return '上生'
    if WX_SHENG.get(uw) == lw: return '下生'
    if uw == lw: return '比和'
    return '无克'


def get_san_chuan(si_ke, tian_pan, ri_gan):
    """
    三传取法（九宗门主干实现）

    常规取法：
    1. 贼克（下克上）
    2. 知一/比用（多克时取与日干阴阳同者，不可决时涉害）
    3. 伏吟、返吟为天盘整体特殊局；返吟有克时仍先从克贼取传
    4. 遥克（无四课克贼时，看日干与四课上神遥克）
    5. 八专（四课上下支完全相同）
    6. 别责、昴星

    参数:
        si_ke: [(name, 上支, 下支), ...] 四课列表
        tian_pan: {地支: 天盘地支} 天盘映射
        ri_gan: 日干

    返回: {'初传': str, '中传': str, '末传': str, '起传法': str}
    """
    # 提取支阳
    zhi_yang = si_ke[2]

    # 收集克贼关系
    zei = []  # 贼（下克上）
    kek = []  # 克（上克下）
    bi_he = []

    for name, u, l in si_ke:
        r = ke_relation(u, l)
        if r == '贼':
            zei.append((name, u, l))
        elif r == '克':
            kek.append((name, u, l))
        elif r == '比和':
            bi_he.append((name, u, l))

    # 1. 贼克法：先取下克上；多处则知一/涉害择传
    if zei:
        return _resolve_ke_candidates(zei, tian_pan, ri_gan, '贼克')

    # 2. 无下克上时，处理上克下（克法）；多处同样知一/涉害择传
    if kek:
        return _resolve_ke_candidates(kek, tian_pan, ri_gan, '克法')

    # 3. 伏吟（天盘地盘相同）
    if all(tian_pan[dz] == dz for dz in DI_ZHI):
        chu = GAN_JI_GONG[ri_gan]
        return _complete(chu, tian_pan, '伏吟')

    # 4. 返吟（天盘地盘相冲）。有克贼时已在前面取传；无克才按返吟专法。
    if all(tian_pan[dz] == CHONG[dz] for dz in DI_ZHI):
        chu = zhi_yang[2]
        return _complete(chu, tian_pan, '返吟')

    # 5. 遥克法：无四课克贼时，看日干与四课上支五行遥克
    yk = _yao_ke(si_ke, tian_pan, ri_gan)
    if yk:
        return yk

    # 6. 八专判断：四课上下支完全相同（且都是比和）
    # 放在遥克之后，避免同时满足时抢先取八专。
    if all(u == l for _, u, l in si_ke) and len(bi_he) == 4:
        yang = ri_gan in '甲丙戊庚壬'
        c1 = tian_pan['酉'] if yang else tian_pan['卯']
        return _complete(c1, tian_pan, '八专')

    # 7. 别责法：四课无克且无遥克，取日干寄宫与日支下神相克者
    gan_xia = GAN_JI_GONG[ri_gan]  # 干下神
    zhi_xia = zhi_yang[2]  # 支下神（第三课下支）
    gan_zhi_xia_relation = ke_relation(gan_xia, zhi_xia)

    if gan_zhi_xia_relation == '克':
        # 干下神克支下神：初传取支下神
        return _complete(zhi_xia, tian_pan, '别责(干克支下神)')
    if gan_zhi_xia_relation == '贼':
        # 支下神克干下神：初传取干下神
        return _complete(gan_xia, tian_pan, '别责(支克干下神)')

    # 8. 昴星法（默认兜底）
    yang = ri_gan in '甲丙戊庚壬'
    c1 = tian_pan['酉'] if yang else tian_pan['卯']
    return _complete(c1, tian_pan, f'昴星({"阳" if yang else "阴"}日)')


def _complete(c1, tp, method):
    """补全三传：初传→中传→末传"""
    return {
        '初传': c1,
        '中传': tp[c1],
        '末传': tp[tp[c1]],
        '起传法': method
    }


def _resolve_ke_candidates(candidates, tp, ri_gan, ktype):
    """处理四课克贼候选：单一克贼直取，多候选用知一，仍不可决用涉害。"""
    if len(candidates) == 1:
        return _complete(candidates[0][1], tp, ktype)

    same = [item for item in candidates if _same_yin_yang(item[1], ri_gan)]
    if len(same) == 1:
        yang = ri_gan in '甲丙戊庚壬'
        return _complete(same[0][1], tp, f'知一({"阳" if yang else "阴"}日-{ktype})')
    if len(same) > 1:
        return _she_hai(same, tp, ri_gan, ktype, '知一后')
    return _she_hai(candidates, tp, ri_gan, ktype, '')


def _same_yin_yang(zhi, gan):
    """判断地支阴阳是否与日干一致。"""
    yang_zhi = {'子', '寅', '辰', '午', '申', '戌'}
    yang_gan = gan in '甲丙戊庚壬'
    return (zhi in yang_zhi) == yang_gan


def _she_hai(candidates, tp, ri_gan, ktype, prefix=''):
    """
    涉害择传。

    这里用于多个克贼经知一仍不可决时的稳定择传：先取涉害克数较深者，
    再按孟、仲、季支作为同分裁决，避免多候选退化为随列表顺序取值。
    """
    branch_rank = {
        '寅': 2, '申': 2, '巳': 2, '亥': 2,  # 孟
        '子': 1, '午': 1, '卯': 1, '酉': 1,  # 仲
        '辰': 0, '戌': 0, '丑': 0, '未': 0,  # 季
    }

    def score(item):
        _, upper, lower = item
        depth = _she_hai_depth(upper, lower)
        return depth, branch_rank.get(upper, 0)

    chosen = max(candidates, key=score)
    label_prefix = prefix if prefix else ''
    return _complete(chosen[1], tp, f'{label_prefix}涉害({ktype})')


def _she_hai_depth(upper, lower):
    """统计上神从所临下支回归本位途中遇到的克数。"""
    count = 0
    start = DI_ZHI.index(lower)
    end = DI_ZHI.index(upper)
    steps = (end - start) % 12
    for i in range(steps + 1):
        ground = DI_ZHI[(start + i) % 12]
        relation = ke_relation(upper, ground)
        if relation in ('贼', '克'):
            count += 1
    return count

def _yao_ke(si_ke, tp, ri_gan):
    """
    遥克法：日干与四课上支五行遥克

    分为两种：
    - 蒿矢：四课上支克日干五行
    - 弹射：日干五行克四课上支
    """
    ri_gan_wx = TIAN_GAN_WX[ri_gan]

    # 1. 蒿矢：上支克日干
    for name, u, l in si_ke:
        u_wx = DI_ZHI_WX[u]
        if WX_KE.get(u_wx) == ri_gan_wx:
            return _complete(u, tp, '遥克(蒿矢)')

    # 2. 弹射：日干克上支
    for name, u, l in si_ke:
        u_wx = DI_ZHI_WX[u]
        if WX_KE.get(ri_gan_wx) == u_wx:
            return _complete(u, tp, '遥克(弹射)')

    return None


# ==================== 天将排列 ====================

def is_daytime(shi_chen_zhi):
    """昼夜判断：卯至申为昼，酉至寅为夜"""
    return 3 <= DI_ZHI.index(shi_chen_zhi) <= 8

def get_gui_shen_pos(ri_gan, shi_chen_zhi):
    """天乙贵人位置"""
    is_day = is_daytime(shi_chen_zhi)
    day_pos, night_pos = GUI_SHEN[ri_gan]
    return day_pos if is_day else night_pos

def arrange_tian_jiang(ri_gan, shi_chen_zhi):
    """排十二天将：昼顺夜逆"""
    is_day = is_daytime(shi_chen_zhi)
    gui_pos = get_gui_shen_pos(ri_gan, shi_chen_zhi)
    gui_idx = DI_ZHI.index(gui_pos)
    
    result = {}
    for i, name in enumerate(TIAN_JIANG_NAMES):
        idx = (gui_idx + i) % 12 if is_day else (gui_idx - i) % 12
        result[DI_ZHI[idx]] = name
    return result


# ==================== 遁干 ====================

def get_dun_gan(ri_gan, zhi):
    """五子遁法：三传配天干"""
    start = {'甲':'甲','己':'甲','乙':'丙','庚':'丙',
             '丙':'戊','辛':'戊','丁':'庚','壬':'庚',
             '戊':'壬','癸':'壬'}
    sg = start[ri_gan]
    offset = DI_ZHI.index(zhi)
    return TIAN_GAN[(TIAN_GAN.index(sg) + offset) % 10]


# ==================== 旺衰判断 ====================

def get_wang_shuai(zhi, month_zhi):
    """判断地支在月令的旺衰：旺/相/休/囚/死"""
    month_wx = DI_ZHI_WX[month_zhi]
    zhi_wx = DI_ZHI_WX[zhi]
    
    if zhi_wx == month_wx: return '旺'
    if WX_SHENG.get(month_wx) == zhi_wx: return '相'
    if WX_SHENG.get(zhi_wx) == month_wx: return '休'
    if WX_KE.get(month_wx) == zhi_wx: return '囚'
    if WX_KE.get(zhi_wx) == month_wx: return '死'
    return '休'


# ==================== 行年 ====================

def get_xing_nian(birth_year, gender, current_year):
    """行年推算：男一岁从寅顺行，女一岁从申逆行（虚岁）"""
    age = current_year - birth_year + 1  # 虚岁
    if gender == '男':
        idx = (2 + age - 1) % 12
    else:
        idx = (8 - age + 1) % 12
    return DI_ZHI[idx % 12]


# ==================== 主函数 ====================

def pa_pan(year, month, day, hour, minute=0, longitude=120.0,
           birth_year=None, gender='男'):
    """
    大六壬起盘（九宗门主干实现）

    参数:
        year/month/day/hour/minute: 占时（公历）
        longitude: 经度(真太阳时修正)
        birth_year: 求测者出生年份(用于本命行年)
        gender: 求测者性别

    返回: dict 完整大六壬盘面

    实现范围:
        - 月将按中气换将
        - 九宗门主干：贼克、知一/比用、涉害、八专、遥克、别责、昴星、伏吟、返吟
        - 十二天将、四课、三传、遁干、神煞、本命行年
    """
    # 1. 真太阳时
    dt_obj = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt_obj)

    # 跨日处理
    from datetime import timedelta
    if day_offset != 0:
        dt_obj = dt_obj + timedelta(days=day_offset)
        year, month, day = dt_obj.year, dt_obj.month, dt_obj.day
    
    # 2. 日柱时柱
    rz = ri_zhu(year, month, day)
    sz = shi_zhu(rz[0], true_h)
    ri_gan = rz[0]
    ri_zhi = rz[1]
    shi_zhi = sz[1]
    
    # 3. 月将
    yue_jiang = get_yue_jiang(year, month, day, true_h, true_m)
    
    # 4. 天盘
    tian_pan = arrange_tian_pan(yue_jiang, shi_zhi)
    
    # 5. 四课
    si_ke = get_si_ke(ri_gan, ri_zhi, tian_pan)
    
    # 6. 三传
    san_chuan = get_san_chuan(si_ke, tian_pan, ri_gan)
    
    # 7. 十二天将
    tian_jiang = arrange_tian_jiang(ri_gan, shi_zhi)
    
    # 8. 遁干
    dun_gan = {
        '初传': get_dun_gan(ri_gan, san_chuan['初传']),
        '中传': get_dun_gan(ri_gan, san_chuan['中传']),
        '末传': get_dun_gan(ri_gan, san_chuan['末传']),
    }
    
    # 9. 天将加三传
    chuan_tian_jiang = {
        '初传': tian_jiang.get(san_chuan['初传'], ''),
        '中传': tian_jiang.get(san_chuan['中传'], ''),
        '末传': tian_jiang.get(san_chuan['末传'], ''),
    }
    
    # 10. 旬空
    kong1, kong2 = xun_kong(rz)

    # 11. 月令地支（用于旺衰判断）
    nian_zhi = nian_zhu(year, month, day)[1]
    # 根据精确节气月推算月令地支（寅月=正月，卯月=二月...）
    jq_month = get_jie_qi_month(year, month, day, true_h, true_m)
    yue_zhi = DI_ZHI[(jq_month + 1) % 12]  # 寅=2, 所以正月(1)对应寅(索引2)

    # 12. 三传旺衰（用月令地支判断）
    wang_shuai = {
        '初传': get_wang_shuai(san_chuan['初传'], yue_zhi),
        '中传': get_wang_shuai(san_chuan['中传'], yue_zhi),
        '末传': get_wang_shuai(san_chuan['末传'], yue_zhi),
    }

    # 13. 神煞
    shen_sha = {
        '驿马': YI_MA.get(nian_zhi, ''),
        '华盖': HUA_GAI.get(nian_zhi, ''),
        '桃花': TAO_HUA.get(nian_zhi, ''),
        '旬空': [kong1, kong2],
        '空亡落传': [k for k in ['初传','中传','末传']
                    if san_chuan[k] in (kong1, kong2)],
    }

    # 14. 本命行年
    ben_ming = None
    xing_nian = None
    if birth_year:
        ben_ming = DI_ZHI[(birth_year - 4) % 12]
        xing_nian = get_xing_nian(birth_year, gender, year)
    
    # 组装四课详情
    si_ke_detail = []
    for name, u, l in si_ke:
        si_ke_detail.append({
            '课名': name,
            '上支': u, '下支': l,
            '上天将': tian_jiang.get(u, ''),
            '上支五行': DI_ZHI_WX[u],
            '下支五行': DI_ZHI_WX[l],
            '关系': ke_relation(u, l),
        })
    
    # 组装天盘详情
    tian_pan_detail = {}
    for dz in DI_ZHI:
        tian_pan_detail[dz] = {
            '天盘': tian_pan[dz],
            '天将': tian_jiang.get(dz, ''),
            '天将含义': TIAN_JIANG_DESC.get(tian_jiang.get(dz, ''), ''),
        }
    
    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '经度': longitude,
        '日干支': rz,
        '时干支': sz,
        '月将': f'{yue_jiang}({JIANG_NAME[yue_jiang]})',
        '月将地支': yue_jiang,
        '昼夜': '昼' if is_daytime(shi_zhi) else '夜',
        '贵神位置': get_gui_shen_pos(ri_gan, shi_zhi),
        '天盘': tian_pan,
        '天盘详情': tian_pan_detail,
        '四课': si_ke_detail,
        '三传': {
            '初传': {
                '地支': san_chuan['初传'],
                '天干': dun_gan['初传'],
                '干支': dun_gan['初传'] + san_chuan['初传'],
                '天将': chuan_tian_jiang['初传'],
                '天将含义': TIAN_JIANG_DESC.get(chuan_tian_jiang['初传'], ''),
                '五行': DI_ZHI_WX[san_chuan['初传']],
                '旺衰': wang_shuai['初传'],
            },
            '中传': {
                '地支': san_chuan['中传'],
                '天干': dun_gan['中传'],
                '干支': dun_gan['中传'] + san_chuan['中传'],
                '天将': chuan_tian_jiang['中传'],
                '天将含义': TIAN_JIANG_DESC.get(chuan_tian_jiang['中传'], ''),
                '五行': DI_ZHI_WX[san_chuan['中传']],
                '旺衰': wang_shuai['中传'],
            },
            '末传': {
                '地支': san_chuan['末传'],
                '天干': dun_gan['末传'],
                '干支': dun_gan['末传'] + san_chuan['末传'],
                '天将': chuan_tian_jiang['末传'],
                '天将含义': TIAN_JIANG_DESC.get(chuan_tian_jiang['末传'], ''),
                '五行': DI_ZHI_WX[san_chuan['末传']],
                '旺衰': wang_shuai['末传'],
            },
            '起传法': san_chuan['起传法'],
        },
        '神煞': shen_sha,
        '本命': ben_ming,
        '行年': xing_nian,
    }


# ==================== 测试 ====================
if __name__ == '__main__':
    result = pa_pan(2024, 6, 15, 14, 30, longitude=116.4, birth_year=1990, gender='男')
    
    print(f"日干支: {result['日干支']}")
    print(f"时干支: {result['时干支']}")
    print(f"月将: {result['月将']}")
    print(f"昼夜: {result['昼夜']}  贵神: {result['贵神位置']}")
    
    print(f"\n四课:")
    for ke in result['四课']:
        print(f"  {ke['课名']}: {ke['上支']}({ke['上天将']})加{ke['下支']} → {ke['关系']}")
    
    sc = result['三传']
    print(f"\n三传({sc['起传法']}):")
    for pos in ['初传','中传','末传']:
        p = sc[pos]
        print(f"  {pos}: {p['干支']} {p['天将']}({p['天将含义']}) {p['五行']}({p['旺衰']})")
    
    print(f"\n神煞: {result['神煞']}")
    print(f"本命: {result['本命']}  行年: {result['行年']}")
