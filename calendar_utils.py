# -*- coding: utf-8 -*-
"""
中国传统术数 - 基础历法工具库
所有术数模块的公共依赖
"""

from datetime import date, timedelta
import math

# ==================== 基础常量 ====================

TIAN_GAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
DI_ZHI  = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']

# 六十甲子
LIU_SHI_JIA_ZI = [TIAN_GAN[i%10] + DI_ZHI[i%12] for i in range(60)]

# 天干 → 五行
TIAN_GAN_WX = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}

# 地支 → 五行
DI_ZHI_WX = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火',
             '午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}

# 天干 → 阴阳
TIAN_GAN_YY = {'甲':'阳','乙':'阴','丙':'阳','丁':'阴','戊':'阳','己':'阴','庚':'阳','辛':'阴','壬':'阳','癸':'阴'}

# 地支 → 阴阳
DI_ZHI_YY = {'子':'阳','丑':'阴','寅':'阳','卯':'阴','辰':'阳','巳':'阴',
             '午':'阳','未':'阴','申':'阳','酉':'阴','戌':'阳','亥':'阴'}

# 地支藏干（本气、中气、余气）
DI_ZHI_CANG = {
    '子':['癸'], '丑':['己','癸','辛'], '寅':['甲','丙','戊'], '卯':['乙'],
    '辰':['戊','乙','癸'], '巳':['丙','庚','戊'], '午':['丁','己'], '未':['己','丁','乙'],
    '申':['庚','壬','戊'], '酉':['辛'], '戌':['戊','辛','丁'], '亥':['壬','甲']
}

# 藏干力度权重
CANG_WEIGHT = {
    '子':[1.0], '丑':[0.6,0.2,0.2], '寅':[0.6,0.3,0.1], '卯':[1.0],
    '辰':[0.6,0.2,0.2], '巳':[0.6,0.3,0.1], '午':[0.7,0.3], '未':[0.6,0.2,0.2],
    '申':[0.6,0.3,0.1], '酉':[1.0], '戌':[0.6,0.2,0.2], '亥':[0.7,0.3]
}

# 五行生克
WX_SHENG = {'木':'火','火':'土','土':'金','金':'水','水':'木'}
WX_KE    = {'木':'土','土':'水','水':'火','火':'金','金':'木'}

# 八卦
BA_GUA = ['乾','兑','离','震','巽','坎','艮','坤']
BA_GUA_WX = {'乾':'金','兑':'金','离':'火','震':'木','巽':'木','坎':'水','艮':'土','坤':'土'}
BA_GUA_YY = {'乾':'阳','震':'阳','坎':'阳','艮':'阳','坤':'阴','巽':'阴','离':'阴','兑':'阴'}

# 洛书数（后天八卦九宫数）
LUO_SHU = {'坎':1,'坤':2,'震':3,'巽':4,'中':5,'乾':6,'兑':7,'艮':8,'离':9}
JIU_GONG_GUA = {1:'坎',2:'坤',3:'震',4:'巽',5:'中',6:'乾',7:'兑',8:'艮',9:'离'}

# 八卦方位
GUA_FW = {'坎':'北','艮':'东北','震':'东','巽':'东南','离':'南','坤':'西南','兑':'西','乾':'西北'}

# 先天数
XIAN_TIAN = {'乾':1,'兑':2,'离':3,'震':4,'巽':5,'坎':6,'艮':7,'坤':8}

# ==================== 核心函数 ====================

def true_solar_time(longitude, hour, minute=0, date_obj=None):
    """
    真太阳时 = 钟表时 + 经度修正 + 均时差

    参数:
        longitude: 东经度数（如北京116.4，上海121.5）
        hour, minute: 钟表时间
        date_obj: datetime.date对象，用于计算均时差
    返回:
        (真太阳时小时, 真太阳时分钟, 日偏移量)
        日偏移量: -1=前一天, 0=当天, +1=后一天
    """
    # 经度修正：以东经120°为标准时区基准，每度4分钟
    lon_fix = (longitude - 120.0) * 4  # 分钟

    # 均时差（Equation of Time）简化公式
    eot = 0.0
    if date_obj:
        doy = date_obj.timetuple().tm_yday
        B = math.radians((360 / 365.242) * (doy - 81))
        eot = 9.87 * math.sin(2*B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)

    total = hour * 60 + minute + lon_fix + eot

    day_offset = 0
    if total >= 1440:
        day_offset = 1
        total -= 1440
    elif total < 0:
        day_offset = -1
        total += 1440

    return int(total // 60), int(total % 60), day_offset


def get_jie_qi_month(a, b, c=None, d=None, e=None):
    """
    公历日期 → 节气月序号（1=寅月, 2=卯月, ..., 12=丑月）

    两种调用方式:
      get_jie_qi_month(month, day)                   — 旧接口，近似固定日期
      get_jie_qi_month(year, month, day, hour, minute) — 新接口，用 lunar_python 精确到分钟
      get_jie_qi_month(year, month, day, hour)        — 新接口，分钟默认0
    """
    if c is not None:
        return _get_jie_qi_month_precise(a, b, c, d or 0, e or 0)

    month, d_val = a, b
    jie = [(1,6,12),(2,4,1),(3,6,2),(4,5,3),(5,6,4),(6,6,5),(7,7,6),
           (8,8,7),(9,8,8),(10,8,9),(11,7,10),(12,7,11)]
    result = 11
    for m, dd, num in jie:
        if (month, d_val) >= (m, dd):
            result = num
    return result


def _get_jie_qi_month_precise(year, month, day, hour, minute=0):
    """用 lunar_python 精确到秒的节气数据确定月序号"""
    from lunar_python import Solar
    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()
    prev_jie = lunar.getPrevJie()
    jie_name = prev_jie.getName()
    JIE_TO_MONTH = {
        '立春':1, '惊蛰':2, '清明':3, '立夏':4, '芒种':5, '小暑':6,
        '立秋':7, '白露':8, '寒露':9, '立冬':10, '大雪':11, '小寒':12,
    }
    return JIE_TO_MONTH.get(jie_name, 11)


def nian_zhu(year, month=1, day=1, hour=None, minute=None):
    """年柱（立春为界）。传入 hour/minute 时使用 lunar_python 精确到秒的立春时刻"""
    if hour is not None:
        from lunar_python import Solar
        solar = Solar.fromYmdHms(year, month, day, hour, minute or 0, 0)
        ec = solar.getLunar().getEightChar()
        return ec.getYear()
    y = year - 1 if month < 2 or (month == 2 and day < 4) else year
    return TIAN_GAN[(y-4)%10] + DI_ZHI[(y-4)%12]


def yue_zhu(year_gan_or_year, month_num_or_month=None, day=None, hour=None, minute=None):
    """
    月柱。
    旧接口: yue_zhu(year_gan, month_num)  — 用年上起月法
    新接口: yue_zhu(year, month, day, hour, minute) — 用 lunar_python 精确节气
    """
    if day is not None and hour is not None:
        from lunar_python import Solar
        solar = Solar.fromYmdHms(year_gan_or_year, month_num_or_month, day, hour, minute or 0, 0)
        ec = solar.getLunar().getEightChar()
        return ec.getMonth()
    year_gan = year_gan_or_year
    month_num = month_num_or_month
    start_gan = {'甲':'丙','己':'丙','乙':'戊','庚':'戊','丙':'庚','辛':'庚',
                 '丁':'壬','壬':'壬','戊':'甲','癸':'甲'}[year_gan]
    zhi_map = {1:'寅',2:'卯',3:'辰',4:'巳',5:'午',6:'未',
               7:'申',8:'酉',9:'戌',10:'亥',11:'子',12:'丑'}
    return TIAN_GAN[(TIAN_GAN.index(start_gan) + month_num - 1) % 10] + zhi_map[month_num]


def ri_zhu(year, month, day):
    """
    日柱
    基准: 2000年1月7日 = 甲子日
    """
    delta = (date(year, month, day) - date(2000, 1, 7)).days
    return TIAN_GAN[delta % 10] + DI_ZHI[delta % 12]


def shi_zhu(ri_gan, hour):
    """
    时柱（日上起时法）
    口诀: 甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸何方发壬子是真途
    hour: 0-23，23点=早子时
    """
    start_gan = {'甲':'甲','己':'甲','乙':'丙','庚':'丙','丙':'戊','辛':'戊',
                 '丁':'庚','壬':'庚','戊':'壬','癸':'壬'}[ri_gan]
    idx = 0 if hour in (23, 0) else (hour + 1) // 2
    return TIAN_GAN[(TIAN_GAN.index(start_gan) + idx) % 10] + DI_ZHI[idx]


def shi_chen_idx(hour):
    """24小时 → 时辰序号(0=子,...,11=亥)"""
    return 0 if hour in (23, 0) else (hour + 1) // 2


def xun_kong(gan_zhi):
    """日干支 → 旬空地支（日柱所在旬的最后两个地支）"""
    idx = LIU_SHI_JIA_ZI.index(gan_zhi)
    s = (idx // 10) * 10
    return LIU_SHI_JIA_ZI[(s + 10) % 60][1], LIU_SHI_JIA_ZI[(s + 11) % 60][1]


# 地支关系
def dz_liu_he(a, b):
    """地支六合"""
    he = dict(zip('子丑寅卯辰巳午未申酉戌亥','丑子亥戌酉申未午巳辰卯寅'))
    return he.get(a) == b

def dz_chong(a, b):
    """地支六冲"""
    ch = {'子':'午','午':'子','丑':'未','未':'丑','寅':'申','申':'寅',
          '卯':'酉','酉':'卯','辰':'戌','戌':'辰','巳':'亥','亥':'巳'}
    return ch.get(a) == b

def dz_hai(a, b):
    """地支六害"""
    hai = {'子':'未','未':'子','丑':'午','午':'丑','寅':'巳','巳':'寅',
           '卯':'辰','辰':'卯','申':'亥','亥':'申','酉':'戌','戌':'酉'}
    return hai.get(a) == b

def dz_san_he(a, b, c):
    """地支三合局"""
    sets = [{'申','子','辰'}, {'亥','卯','未'}, {'寅','午','戌'}, {'巳','酉','丑'}]
    return {a, b, c} in sets

def wx_relation(wx1, wx2):
    """五行关系: 比和/我生/我克/生我/克我"""
    if wx1 == wx2: return '比和'
    if WX_SHENG.get(wx1) == wx2: return '我生(泄)'
    if WX_KE.get(wx1) == wx2: return '我克(耗)'
    for k, v in WX_SHENG.items():
        if v == wx1 and k == wx2: return '生我(印)'
    for k, v in WX_KE.items():
        if v == wx1 and k == wx2: return '克我(杀)'
    return '未知'


def get_precise_jieqi_table(year, month, day):
    """
    获取包含给定日期的节气表（返回前后各12个节气的精确时刻）。
    返回: dict { 节气名: Solar对象 }
    """
    from lunar_python import Solar
    solar = Solar.fromYmdHms(year, month, day, 12, 0, 0)
    lunar = solar.getLunar()
    return lunar.getJieQiTable()
