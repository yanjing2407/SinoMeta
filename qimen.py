# -*- coding: utf-8 -*-
"""
奇门遁甲起盘模块（时家奇门·拆补法）
=================================
规则说明:
  奇门遁甲以"时辰"为基本单位，将时空分解为九宫格局。
  
  核心概念:
    - 阳遁/阴遁: 冬至后阳遁（顺排），夏至后阴遁（逆排）
    - 九局: 根据节气和日干支确定阳遁/阴遁1-9局
    - 三奇六仪: 戊己庚辛壬癸丁丙乙（注意这个特殊顺序）
    - 九星: 天蓬、天芮、天冲、天辅、天禽、天心、天柱、天任、天英
    - 八门: 休、生、伤、杜、景、死、惊、开（中宫无门）
    - 八神: 值符、螣蛇、太阴、六合、白虎/勾陈、玄武/朱雀、九地、九天
    - 值符/值使: 随时辰更替，是动态坐标轴
  
  排盘步骤:
    1. 确定阳遁/阴遁 + 局数
    2. 地盘排布三奇六仪
    3. 天盘随值符落宫加临
    4. 九星随天盘
    5. 八门随值使落宫
    6. 八神随值符
"""

from datetime import date, datetime, timedelta
from calendar_utils import (
    TIAN_GAN, DI_ZHI, LIU_SHI_JIA_ZI, TIAN_GAN_WX, JIU_GONG_GUA, LUO_SHU,
    true_solar_time, get_jie_qi_month, ri_zhu, shi_chen_idx, shi_zhu
)

# ==================== 奇门专用常量 ====================

# 三奇六仪的排列顺序（这是奇门最特殊的规则）
# 戊(1)己(2)庚(3)辛(4)壬(5)癸(6)丁(7)丙(8)乙(9)
# 阳遁时按此顺序顺排入九宫，阴遁逆排
SAN_QI_LIU_YI = ['戊','己','庚','辛','壬','癸','丁','丙','乙']

# 九星（按九宫序排列，5=天禽寄坤2）
JIU_XING = {1:'天蓬', 2:'天芮', 3:'天冲', 4:'天辅', 5:'天禽',
            6:'天心', 7:'天柱', 8:'天任', 9:'天英'}

# 九星五行
JIU_XING_WX = {'天蓬':'水','天芮':'土','天冲':'木','天辅':'木','天禽':'土',
               '天心':'金','天柱':'金','天任':'土','天英':'火'}

# 九星吉凶
JIU_XING_JI = {'天蓬':'凶','天芮':'凶','天冲':'吉','天辅':'吉','天禽':'中',
               '天心':'吉','天柱':'凶','天任':'吉','天英':'小凶'}

# 八门（按九宫序，5无门）
BA_MEN = {1:'休', 2:'死', 3:'伤', 4:'杜', 5:'中',
          6:'开', 7:'惊', 8:'生', 9:'景'}

# 八门五行
BA_MEN_WX = {'休':'水','死':'土','伤':'木','杜':'木','中':'土',
             '开':'金','惊':'金','生':'土','景':'火'}

# 八门吉凶
BA_MEN_JI = {'休':'吉','死':'凶','伤':'凶','杜':'中','开':'吉','惊':'凶','生':'吉','景':'中'}

# 八神（阳遁顺排，阴遁逆排）
# 阳遁: 值符→螣蛇→太阴→六合→白虎→玄武→九地→九天
# 阴遁: 值符→螣蛇→太阴→六合→勾陈→朱雀→九地→九天
BA_SHEN_YANG = ['值符','螣蛇','太阴','六合','白虎','玄武','九地','九天']
BA_SHEN_YIN  = ['值符','螣蛇','太阴','六合','勾陈','朱雀','九地','九天']

# 九宫飞泊路线（洛书轨迹，1→2→3→4→5→6→7→8→9）
# 这是奇门排宫的核心路线
FEI_PO = [1,2,3,4,5,6,7,8,9]  # 简化，实际按洛书飞

# 阳遁九宫起始宫位表（局数→戊所在宫）
# 1局戊在1宫，2局戊在2宫，...，9局戊在9宫
YANG_DUN_START = {1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 7:7, 8:8, 9:9}
YIN_DUN_START  = {1:9, 2:8, 3:7, 4:6, 5:5, 6:4, 7:3, 8:2, 9:1}

# 洛书飞泊顺序（从1宫开始: 1→2→3→4→5→6→7→8→9→1...）
# 阳遁按此顺序排三奇六仪
LUO_SHU_ORDER = [1,2,3,4,5,6,7,8,9]


# ==================== 确定局数（拆补法） ====================

# 24节气三元局数表（拆补法核心数据）
# 格式: 节气名 → (上元局数, 中元局数, 下元局数)
JIEQI_JU_TABLE = {
    # 阳遁（冬至→芒种）
    '冬至': (1, 7, 4), '小寒': (2, 8, 5), '大寒': (3, 9, 6),
    '立春': (8, 5, 2), '雨水': (9, 6, 3), '惊蛰': (1, 7, 4),
    '春分': (3, 9, 6), '清明': (4, 1, 7), '谷雨': (5, 2, 8),
    '立夏': (4, 1, 7), '小满': (5, 2, 8), '芒种': (6, 3, 9),
    # 阴遁（夏至→大雪）
    '夏至': (9, 3, 6), '小暑': (8, 2, 5), '大暑': (7, 1, 4),
    '立秋': (2, 5, 8), '处暑': (1, 4, 7), '白露': (9, 3, 6),
    '秋分': (7, 1, 4), '寒露': (6, 9, 3), '霜降': (5, 8, 2),
    '立冬': (6, 9, 3), '小雪': (5, 8, 2), '大雪': (4, 7, 1),
}

# 阳遁节气集合
YANG_DUN_JIEQI = {'冬至','小寒','大寒','立春','雨水','惊蛰',
                  '春分','清明','谷雨','立夏','小满','芒种'}

# 24节气按时间先后的循环顺序（用于拆补法"拆"时回退到上一节气）
JIEQI_ORDER = ['冬至','小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨',
               '立夏','小满','芒种','夏至','小暑','大暑','立秋','处暑','白露',
               '秋分','寒露','霜降','立冬','小雪','大雪']


def _prev_jieqi_name(name):
    """返回循环顺序中 name 的上一个节气名"""
    if name not in JIEQI_ORDER:
        return name
    return JIEQI_ORDER[(JIEQI_ORDER.index(name) - 1) % len(JIEQI_ORDER)]


def get_dun_ju(year, month, day, hour, minute=0):
    """
    确定阳遁/阴遁及局数（拆补法）

    拆补法规则:
      1. 找到当前日期所处的"节"或"气"（用 lunar_python 精确到秒）
      2. 阳遁/阴遁由冬至/夏至决定
      3. 找符头（节后第一个甲日或己日），确定上/中/下元
      4. 拆：节气后、符头前的日子属于上一节的下元
      5. 补：符头后按5天一元划分
    """
    from lunar_python import Solar

    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()

    # 判断阳遁阴遁：看当前处于冬至后还是夏至后
    is_yang = _is_yang_dun(solar)

    # 确定查表用的节气名 + 上中下元
    # 拆补法："拆"的情形（节气后、符头前）须用上一节气的下元
    table_jieqi, yuan = _determine_yuan(solar, lunar)

    # 查表得局数
    ju_tuple = JIEQI_JU_TABLE.get(table_jieqi, (1, 7, 4))
    ju = ju_tuple[yuan]  # yuan: 0=上, 1=中, 2=下

    dun_type = '阳遁' if is_yang else '阴遁'
    return dun_type, ju


def _is_yang_dun(solar):
    """
    判断阳遁/阴遁：冬至后→阳遁，夏至后→阴遁

    策略：从当前日期向前推1.5年，向后推0.5年，
    在这个时间段内找冬至和夏至的准确时刻，
    比较哪个离当前时间更近。
    """
    from lunar_python import Solar
    from datetime import timedelta

    current_dt = solar.toYmdHms()
    year = solar.getYear()
    month = solar.getMonth()
    day = solar.getDay()

    dong_zhi_solar = None
    xia_zhi_solar = None

    # 向前推550天，向后推180天，覆盖相邻的冬至/夏至
    for offset_days in range(-550, 180, 15):
        try:
            check_solar = Solar.fromYmdHms(year, month, day, 12, 0, 0).next(offset_days)
            jq_table = check_solar.getLunar().getJieQiTable()

            if '冬至' in jq_table:
                dz = jq_table['冬至']
                if dz.toYmdHms() <= current_dt:
                    if dong_zhi_solar is None or dz.toYmdHms() > dong_zhi_solar.toYmdHms():
                        dong_zhi_solar = dz

            if '夏至' in jq_table:
                xz = jq_table['夏至']
                if xz.toYmdHms() <= current_dt:
                    if xia_zhi_solar is None or xz.toYmdHms() > xia_zhi_solar.toYmdHms():
                        xia_zhi_solar = xz
        except:
            pass

    # 比较哪个更近（时间戳更大的更近）
    if dong_zhi_solar and xia_zhi_solar:
        return dong_zhi_solar.toYmdHms() >= xia_zhi_solar.toYmdHms()
    elif dong_zhi_solar:
        return True
    elif xia_zhi_solar:
        return False

    # 兜底：月份判断
    m = solar.getMonth()
    return m <= 6 or m == 12


def _determine_yuan(solar, lunar):
    """
    拆补法确定查表用的节气名 + 上/中/下元。

    规则：从节气后找第一个天干为甲或己的日作为符头，
    符头起5天为上元，次5天为中元，再5天为下元。
    节气后、符头前的日子属于"上一个节气"的下元（拆），
    此时须用上一节气名查局数表，而非当前节气。

    返回: (查表用节气名, yuan索引[0=上,1=中,2=下])
    """
    prev_jq = lunar.getPrevJieQi()
    current_jieqi = prev_jq.getName()
    jq_solar = prev_jq.getSolar()

    # 节气日期
    jq_date = date(jq_solar.getYear(), jq_solar.getMonth(), jq_solar.getDay())
    current_date = date(solar.getYear(), solar.getMonth(), solar.getDay())

    # 找节气后第一个符头（天干为甲或己的日）
    futou_date = _find_futou(jq_date)

    # 计算当前日距离符头的天数
    days_from_futou = (current_date - futou_date).days

    if days_from_futou < 0:
        # 拆：当前日在本节气符头之前 → 属于上一个节气的下元
        return _prev_jieqi_name(current_jieqi), 2  # 上一节气·下元
    elif days_from_futou < 5:
        return current_jieqi, 0  # 上元
    elif days_from_futou < 10:
        return current_jieqi, 1  # 中元
    else:
        return current_jieqi, 2  # 下元


def _find_futou(jq_date):
    """从节气日起，找第一个天干为甲或己的符头日"""
    for i in range(10):
        check_date = jq_date + timedelta(days=i)
        rz = ri_zhu(check_date.year, check_date.month, check_date.day)
        if rz[0] in ('甲', '己'):
            return check_date
    return jq_date


# ==================== 地盘排布 ====================

def arrange_di_pan(ju, is_yang):
    """
    排地盘三奇六仪
    
    规则:
      - 阳遁: 戊从ju宫开始，按1→2→3→4→5→6→7→8→9顺序排列
      - 阴遁: 戊从ju宫开始，按9→8→7→6→5→4→3→2→1逆序排列
    
    示例(阳遁1局):
      宫1=戊, 宫2=己, 宫3=庚, 宫4=辛, 宫5=壬, 宫6=癸, 宫7=丁, 宫8=丙, 宫9=乙
    """
    di_pan = {}
    
    if is_yang:
        # 阳遁顺排
        for i, qi_yi in enumerate(SAN_QI_LIU_YI):
            gong = ((ju - 1 + i) % 9) + 1  # 从ju宫开始顺排
            di_pan[gong] = qi_yi
    else:
        # 阴遁逆排
        for i, qi_yi in enumerate(SAN_QI_LIU_YI):
            gong = ((ju - 1 - i) % 9) + 1  # 从ju宫开始逆排
            if gong <= 0:
                gong += 9
            di_pan[gong] = qi_yi
    
    return di_pan


# ==================== 值符值使 ====================

def get_zhi_fu_zhi_shi(di_pan, shi_chen_gan_zhi):
    """
    找值符（星）和值使（门）

    规则:
      1. 找时柱的旬首
      2. 找旬首的遁仪（甲子→戊, 甲戌→己, 甲申→庚, 甲午→辛, 甲辰→壬, 甲寅→癸）
      3. 该遁仪在地盘的宫位 = 值符原始宫位
      4. 该宫的九星 = 值符星，该宫的八门 = 值使门
    """
    JIA_DUN = {
        '甲子': '戊', '甲戌': '己', '甲申': '庚',
        '甲午': '辛', '甲辰': '壬', '甲寅': '癸'
    }

    # 找时柱的旬首
    idx = LIU_SHI_JIA_ZI.index(shi_chen_gan_zhi)
    xun_shou_idx = (idx // 10) * 10
    xun_shou = LIU_SHI_JIA_ZI[xun_shou_idx]

    # 旬首的遁仪
    xun_shou_yi = JIA_DUN[xun_shou]

    # 找遁仪在地盘的宫位
    target_gong = None
    for gong, qi_yi in di_pan.items():
        if qi_yi == xun_shou_yi:
            target_gong = gong
            break

    if target_gong is None:
        target_gong = 5

    # 中宫(5)无门，天禽寄坤2
    if target_gong == 5:
        zhi_fu_xing = JIU_XING[5]  # 天禽
        zhi_fu_men = BA_MEN[2]     # 寄坤2宫取"死"门
        return zhi_fu_xing, zhi_fu_men, 2

    # 值符 = 该宫的九星，值使 = 该宫的八门
    zhi_fu_xing = JIU_XING[target_gong]
    zhi_fu_men = BA_MEN[target_gong]

    return zhi_fu_xing, zhi_fu_men, target_gong


# ==================== 天盘排布 ====================

def arrange_tian_pan(di_pan, zhi_fu_gong, is_yang, shi_gan, shi_chen_gan_zhi):
    """
    排天盘
    
    规则:
      - 值符（星）随时干落宫
      - 天盘三奇六仪 = 地盘奇仪随值符飞临
      - 九星随天盘转动
    """
    # 时干落宫
    DUN_YI_MAP = {'甲子':'戊','甲戌':'己','甲申':'庚','甲午':'辛','甲辰':'壬','甲寅':'癸'}
    
    if shi_gan == '甲':
        idx = LIU_SHI_JIA_ZI.index(shi_chen_gan_zhi)
        xun_shou = LIU_SHI_JIA_ZI[(idx//10)*10]
        target_yi = DUN_YI_MAP.get(xun_shou, '戊')
    else:
        target_yi = shi_gan
    
    # 找时干在地盘的宫位
    shi_gan_gong = None
    for gong, qi_yi in di_pan.items():
        if qi_yi == target_yi:
            shi_gan_gong = gong
            break
    if shi_gan_gong is None:
        shi_gan_gong = 5
    
    # 值符从原宫(zhi_fu_gong)飞到时干宫(shi_gan_gong)
    # 天盘转动：所有天盘星随值符偏移（转盘法阳遁阴遁同方向）

    tian_pan = {}  # 宫→天盘奇仪
    tian_pan_xing = {}  # 宫→九星

    offset = shi_gan_gong - zhi_fu_gong
    
    # 天盘奇仪 = 把地盘整体平移
    for gong in range(1, 10):
        src_gong = gong  # 地盘来源宫
        # 天盘落宫
        dst_gong = ((gong + offset - 1) % 9) + 1
        if dst_gong <= 0:
            dst_gong += 9
        tian_pan[dst_gong] = di_pan[src_gong]
        tian_pan_xing[dst_gong] = JIU_XING[src_gong]
    
    # 中宫寄坤2：5宫内容并入2宫
    if 5 in tian_pan:
        tian_pan[2] = tian_pan[5]
        tian_pan_xing[2] = tian_pan_xing[5]
    
    return tian_pan, tian_pan_xing, shi_gan_gong


# ==================== 八门排布 ====================

def arrange_ba_men(zhi_fu_men, zhi_fu_gong, shi_gan_gong, is_yang):
    """
    排八门（转盘法）

    规则:
      - 值使（门）随时干落宫
      - 其余门保持相对位置转动（转盘法阳遁阴遁同方向偏移）
      - 中5宫无门，5宫寄2宫参与转动
    """
    # 八宫顺序（不含中5宫）
    GONG_SEQ = [1, 8, 3, 4, 9, 2, 7, 6]  # 洛书顺时针序

    men_pan = {}

    # 值使原始宫位
    zhi_shi_gong = None
    for gong, men in BA_MEN.items():
        if men == zhi_fu_men and gong != 5:
            zhi_shi_gong = gong
            break
    if zhi_shi_gong is None:
        zhi_shi_gong = 1

    # 值使落宫（时干宫，如果是5则寄2）
    target_gong = shi_gan_gong if shi_gan_gong != 5 else 2

    # 计算在GONG_SEQ中的偏移
    src_idx = GONG_SEQ.index(zhi_shi_gong) if zhi_shi_gong in GONG_SEQ else 0
    dst_idx = GONG_SEQ.index(target_gong) if target_gong in GONG_SEQ else 0

    if is_yang:
        shift = (dst_idx - src_idx) % 8
    else:
        shift = (dst_idx - src_idx) % 8

    # 排列8门到8宫
    for i, gong in enumerate(GONG_SEQ):
        new_idx = (i + shift) % 8
        new_gong = GONG_SEQ[new_idx]
        men_pan[new_gong] = BA_MEN[gong] if gong != 5 else BA_MEN[2]

    return men_pan


# ==================== 八神排布 ====================

def arrange_ba_shen(zhi_fu_xing, shi_gan_gong, is_yang):
    """
    排八神

    规则:
      - 值符随天盘值符星落宫
      - 阳遁顺排，阴遁逆排
      - 八神不入中5宫，遇5跳过
    """
    shen_list = BA_SHEN_YANG if is_yang else BA_SHEN_YIN
    shen_pan = {}

    gong = shi_gan_gong
    if gong == 5:
        gong = 2  # 起始中宫寄坤2

    for i, shen in enumerate(shen_list):
        shen_pan[gong] = shen

        # 下一个宫
        if is_yang:
            gong = gong % 9 + 1
        else:
            gong = (gong - 2) % 9 + 1

        # 跳过中5宫
        if gong == 5:
            if is_yang:
                gong = gong % 9 + 1  # → 6
            else:
                gong = (gong - 2) % 9 + 1  # → 4

    return shen_pan


# ==================== 格局判断 ====================

def judge_ge_ju(tian_pan, di_pan, men_pan, shen_pan):
    """
    判断常用格局
    """
    ge_ju = []
    
    for gong in range(1, 10):
        if gong == 5:
            continue
        
        tian_yi = tian_pan.get(gong, '')
        di_yi = di_pan.get(gong, '')
        men = men_pan.get(gong, '')
        shen = shen_pan.get(gong, '')
        
        # 天盘乙+开门+天心星 = 乙奇+开门+天心 = 大吉
        # 天盘丙+生门+天任星 = 丙奇+生门+天任 = 大吉
        # 天盘丁+休门+天蓬星 = 丁奇+休门+天蓬(需水) = 吉
        
        # 奇仪格局
        if tian_yi == di_yi:
            ge_ju.append(f"宫{gong}: {tian_yi}加{di_yi}(伏吟)")
        elif gong in [1,8,9,6,3,4,2,7]:
            # 检查反吟（对宫相同）
            opp = {1:9, 9:1, 2:8, 8:2, 3:7, 7:3, 4:6, 6:4}
            opp_gong = opp.get(gong)
            if opp_gong and tian_yi == di_pan.get(opp_gong, ''):
                ge_ju.append(f"宫{gong}: {tian_yi}加{di_yi}(反吟)")
        
        # 三奇得使
        if tian_yi in ['乙','丙','丁'] and men in ['开','休','生']:
            ge_ju.append(f"宫{gong}: {tian_yi}奇得{men}门(三奇得使)")
        
        # 门迫/门迫
        men_wx = BA_MEN_WX.get(men, '')
        gong_wx = {'坎':'水','坤':'土','震':'木','巽':'木','中':'土','乾':'金','兑':'金','艮':'土','离':'火'}.get(
            JIU_GONG_GUA.get(gong, ''), '')
        if men_wx and gong_wx:
            from calendar_utils import WX_KE
            if WX_KE.get(gong_wx) == men_wx:
                ge_ju.append(f"宫{gong}: {men}门受迫(门迫)")
    
    return ge_ju


# ==================== 主函数 ====================

def pa_pan(year, month, day, hour, minute=0, longitude=120.0):
    """
    奇门遁甲起盘
    
    参数: 同八字模块
    返回: dict 完整奇门盘面
    """
    # 1. 真太阳时
    dt = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt)

    # 跨日处理
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt + timedelta(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day

    # 2. 时辰干支
    rz = ri_zhu(act_y, act_m, act_d)
    sz = shi_zhu(rz[0], true_h)
    shi_gan = sz[0]

    # 3. 确定局数
    dun_type, ju = get_dun_ju(act_y, act_m, act_d, true_h, true_m)
    is_yang = (dun_type == '阳遁')
    
    # 4. 地盘
    di_pan = arrange_di_pan(ju, is_yang)
    
    # 5. 值符值使
    zhi_fu_xing, zhi_fu_men, zhi_fu_gong = get_zhi_fu_zhi_shi(di_pan, sz)
    
    # 6. 天盘
    tian_pan, tian_xing, shi_gan_gong = arrange_tian_pan(
        di_pan, zhi_fu_gong, is_yang, shi_gan, sz)
    
    # 7. 八门
    men_pan = arrange_ba_men(zhi_fu_men, zhi_fu_gong, shi_gan_gong, is_yang)
    
    # 8. 八神
    shen_pan = arrange_ba_shen(zhi_fu_xing, shi_gan_gong, is_yang)
    
    # 9. 格局
    ge_ju = judge_ge_ju(tian_pan, di_pan, men_pan, shen_pan)
    
    # 10. 旬空
    from calendar_utils import xun_kong
    kong1, kong2 = xun_kong(rz)
    
    # 组装九宫详细信息
    palaces = {}
    for gong in range(1, 10):
        if gong == 5:
            continue
        gua_name = JIU_GONG_GUA.get(gong, '')
        palaces[gong] = {
            '八卦': gua_name,
            '方位': {'坎':'北','艮':'东北','震':'东','巽':'东南','离':'南','坤':'西南','兑':'西','乾':'西北'}.get(gua_name, ''),
            '天盘': tian_pan.get(gong, ''),
            '地盘': di_pan.get(gong, ''),
            '九星': tian_xing.get(gong, ''),
            '八门': men_pan.get(gong, ''),
            '八神': shen_pan.get(gong, ''),
            '星吉凶': JIU_XING_JI.get(tian_xing.get(gong, ''), ''),
            '门吉凶': BA_MEN_JI.get(men_pan.get(gong, ''), ''),
        }
    
    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '经度': longitude,
        '遁型': dun_type,
        '局数': ju,
        '日干支': rz,
        '时干支': sz,
        '值符星': zhi_fu_xing,
        '值使门': zhi_fu_men,
        '旬空': [kong1, kong2],
        '格局': ge_ju,
        '九宫': palaces,
    }


if __name__ == '__main__':
    result = pa_pan(2024, 6, 15, 14, 30, longitude=116.4)
    print(f"遁型: {result['遁型']}{result['局数']}局")
    print(f"值符: {result['值符星']}, 值使: {result['值使门']}")
    for gong, info in result['九宫'].items():
        print(f"  {gong}宫({info['八卦']}/{info['方位']}): "
              f"天={info['天盘']} 地={info['地盘']} "
              f"星={info['九星']}({info['星吉凶']}) "
              f"门={info['八门']}({info['门吉凶']}) "
              f"神={info['八神']}")
