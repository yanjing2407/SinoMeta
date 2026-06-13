# -*- coding: utf-8 -*-
"""
紫微斗数起盘模块（三合派）
=========================
规则说明（每个步骤的来源与逻辑）:

  排盘步骤:
    1. 定命宫、身宫 → 寅月起子时，顺数月逆数时=命宫，顺数月顺数时=身宫
    2. 十二宫逆布   → 命宫起，逆时针排列兄弟、夫妻...父母
    3. 各宫配天干   → 同年上起月法，从寅宫起配天干
    4. 命宫纳音定局 → 命宫干支→纳音→五行局(水2/木3/金4/土5/火6)
    5. 紫微星定位   → 局数+农历日→商数/余数/补数奇偶修正法, 从寅宫起
    6. 天府星定位   → 紫微与天府以寅申线对称
    7. 安紫微系6星 → 从紫微位逆时针布：紫微+0,天机-1,太阳-3,武曲-4,天同-5,廉贞-8
    8. 安天府系8星 → 从天府位顺时针布：天府+0,太阴+1,贪狼+2,巨门+3,天相+4,天梁+5,七杀+6,破军+10
    9. 安辅星      → 左辅右弼(月起)、文昌文曲(时起)、禄存擎羊陀罗(年起)、天魁天钺(年起)、火星铃星(年支+时)、地空地劫(时起)
    10. 安四化     → 年干决定禄权科忌所落星曜
    11. 判庙旺利陷 → 各星在各宫的强弱状态

  重要说明:
    - 年柱：采用八字立春年（非农历春节年），影响四化、禄存、魁钺等
    - 月柱：使用农历月（非节气月），闰月按本系统规则处理
    - 农历转换：使用 lunar_python 库精确转换
"""

from calendar_utils import (
    TIAN_GAN, DI_ZHI, TIAN_GAN_WX, true_solar_time, nian_zhu, get_jie_qi_month
)
from datetime import date, timedelta

# ==================== 基础常量 ====================

SHI_ER_GONG = ['命宫','兄弟','夫妻','子女','财帛','疾厄',
               '迁移','仆役','官禄','田宅','福德','父母']

# ===== 六十甲子纳音表 =====
_jia_zi = [TIAN_GAN[i%10]+DI_ZHI[i%12] for i in range(60)]
_na_yin_list = [
    '海中金','海中金','炉中火','炉中火','大林木','大林木','路旁土','路旁土','剑锋金','剑锋金',
    '山头火','山头火','涧下水','涧下水','城头土','城头土','白蜡金','白蜡金','杨柳木','杨柳木',
    '泉中水','泉中水','屋上土','屋上土','霹雳火','霹雳火','松柏木','松柏木','长流水','长流水',
    '沙中金','沙中金','山下火','山下火','平地木','平地木','壁上土','壁上土','金箔金','金箔金',
    '覆灯火','覆灯火','天河水','天河水','大驿土','大驿土','钗钏金','钗钏金','桑柘木','桑柘木',
    '大溪水','大溪水','沙中土','沙中土','天上火','天上火','石榴木','石榴木','大海水','大海水',
]
NA_YIN = dict(zip(_jia_zi, _na_yin_list))

# 纳音五行→局数: 金四局, 木三局, 水二局, 火六局, 土五局
NA_YIN_JU = {'金':4, '木':3, '水':2, '火':6, '土':5}

# ===== 紫微星位置公式（最核心的算法） =====
# 三合派安紫微：商数/余数/补数奇偶修正法（从寅宫起，见 get_ziwei_zhi）
#   1. 农历日 ÷ 局数 → 商、余；整除时补数=0、商不变，否则补数=局-余、商+1
#   2. 补数偶(含0)从寅顺行 (商-1)+补数；补数奇从寅逆行 (商-1)-补数

# 紫微与天府的对称关系（以寅申线为轴）
ZIWEI_TIANFU = {
    '子':'辰','丑':'卯','寅':'寅','卯':'丑','辰':'子','巳':'亥',
    '午':'戌','未':'酉','申':'申','酉':'未','戌':'午','亥':'巳'
}

# 紫微系六星偏移（从紫微位逆时针）
ZW_XI = {'紫微':0, '天机':-1, '太阳':-3, '武曲':-4, '天同':-5, '廉贞':-8}

# 天府系八星偏移（从天府位顺时针）
TF_XI = {'天府':0, '太阴':1, '贪狼':2, '巨门':3, '天相':4, '天梁':5, '七杀':6, '破军':10}

# ===== 辅星安法表 =====

# 左辅：正月起辰，每月顺行
def _zuofu(m): return DI_ZHI[(4+m-1)%12]
# 右弼：正月起戌，每月逆行
def _youbi(m): return DI_ZHI[(10-m+1)%12]

# 文昌：戌起子时，逆行
def _wenchang(shi_idx): return DI_ZHI[(10-shi_idx)%12]
# 文曲：辰起子时，顺行
def _wenqu(shi_idx): return DI_ZHI[(4+shi_idx)%12]

# 禄存
LU_CUN = {'甲':'寅','乙':'卯','丙':'巳','丁':'午','戊':'巳',
          '己':'午','庚':'申','辛':'酉','壬':'亥','癸':'子'}

# 天魁天钺
TIAN_KUI = {'甲':'丑','乙':'子','丙':'亥','丁':'亥','戊':'丑',
            '己':'子','庚':'未','辛':'午','壬':'卯','癸':'卯'}
TIAN_YUE = {'甲':'未','乙':'申','丙':'酉','丁':'酉','戊':'未',
            '己':'申','庚':'丑','辛':'寅','壬':'巳','癸':'巳'}

# 地空地劫
def _dikong(s): return DI_ZHI[(11-s)%12]   # 亥起逆行
def _dijie(s): return DI_ZHI[(11+s)%12]    # 亥起顺行

# 天马
TIAN_MA = {'寅':'申','午':'申','戌':'申','申':'寅','子':'寅','辰':'寅',
           '巳':'亥','酉':'亥','丑':'亥','亥':'巳','卯':'巳','未':'巳'}

# 火星铃星
def _huoxing(year_zhi, shi_idx):
    g = {'寅':0,'午':0,'戌':0,'申':1,'子':1,'辰':1,
         '巳':2,'酉':2,'丑':2,'亥':3,'卯':3,'未':3}.get(year_zhi,0)
    start = {0:1, 1:2, 2:3, 3:9}  # 丑/寅/卯/酉
    return DI_ZHI[(start[g]+shi_idx)%12]

def _lingxing(year_zhi, shi_idx):
    g = {'寅':0,'午':0,'戌':0,'申':1,'子':1,'辰':1,
         '巳':2,'酉':2,'丑':2,'亥':3,'卯':3,'未':3}.get(year_zhi,0)
    start = {0:3, 1:10, 2:10, 3:10}  # 卯/戌/戌/戌
    return DI_ZHI[(start[g]+shi_idx)%12]

# ===== 四化星 =====
SI_HUA = {
    '甲': ('廉贞','破军','武曲','太阳'),
    '乙': ('天机','天梁','紫微','太阴'),
    '丙': ('天同','天机','文昌','廉贞'),
    '丁': ('太阴','天同','天机','巨门'),
    '戊': ('贪狼','太阴','右弼','天机'),
    '己': ('武曲','贪狼','天梁','文曲'),
    '庚': ('太阳','武曲','太阴','天同'),
    '辛': ('巨门','太阳','文曲','文昌'),
    '壬': ('天梁','紫微','左辅','武曲'),
    '癸': ('破军','巨门','太阴','贪狼'),
}

# ===== 庙旺利陷表 =====
# M=庙(极旺) W=旺(强) L=利(中等) P=平 X=陷(衰弱)
MW = {
    '紫微':{'子':'M','丑':'M','寅':'W','卯':'L','辰':'W','巳':'L','午':'M','未':'M','申':'W','酉':'L','戌':'W','亥':'X'},
    '天机':{'子':'M','丑':'X','寅':'W','卯':'M','辰':'W','巳':'M','午':'X','未':'X','申':'W','酉':'L','戌':'X','亥':'L'},
    '太阳':{'子':'X','丑':'X','寅':'L','卯':'W','辰':'M','巳':'M','午':'M','未':'M','申':'L','酉':'X','戌':'X','亥':'X'},
    '武曲':{'子':'M','丑':'X','寅':'L','卯':'X','辰':'W','巳':'M','午':'M','未':'W','申':'L','酉':'W','戌':'L','亥':'X'},
    '天同':{'子':'M','丑':'X','寅':'L','卯':'X','辰':'X','巳':'W','午':'X','未':'W','申':'M','酉':'M','戌':'L','亥':'M'},
    '廉贞':{'子':'X','丑':'M','寅':'L','卯':'X','辰':'X','巳':'M','午':'M','未':'M','申':'L','酉':'X','戌':'X','亥':'X'},
    '天府':{'子':'M','丑':'W','寅':'M','卯':'W','辰':'M','巳':'M','午':'M','未':'W','申':'M','酉':'W','戌':'M','亥':'M'},
    '太阴':{'子':'M','丑':'M','寅':'L','卯':'W','辰':'X','巳':'X','午':'X','未':'X','申':'L','酉':'W','戌':'M','亥':'M'},
    '贪狼':{'子':'M','丑':'X','寅':'X','卯':'L','辰':'X','巳':'W','午':'X','未':'W','申':'L','酉':'W','戌':'X','亥':'M'},
    '巨门':{'子':'M','丑':'X','寅':'X','卯':'M','辰':'X','巳':'L','午':'X','未':'L','申':'X','酉':'M','戌':'X','亥':'X'},
    '天相':{'子':'M','丑':'X','寅':'W','卯':'X','辰':'W','巳':'L','午':'L','未':'W','申':'L','酉':'X','戌':'L','亥':'M'},
    '天梁':{'子':'M','丑':'W','寅':'X','卯':'W','辰':'X','巳':'M','午':'M','未':'M','申':'X','酉':'W','戌':'X','亥':'X'},
    '七杀':{'子':'W','丑':'X','寅':'M','卯':'X','辰':'L','巳':'M','午':'M','未':'L','申':'M','酉':'X','戌':'W','亥':'X'},
    '破军':{'子':'X','丑':'W','寅':'X','卯':'X','辰':'W','巳':'X','午':'W','未':'X','申':'X','酉':'W','戌':'X','亥':'W'},
    '文昌':{'子':'L','丑':'X','寅':'X','卯':'M','辰':'X','巳':'W','午':'X','未':'W','申':'L','酉':'M','戌':'X','亥':'X'},
    '文曲':{'子':'L','丑':'X','寅':'X','卯':'M','辰':'W','巳':'W','午':'X','未':'W','申':'L','酉':'M','戌':'X','亥':'X'},
}
MW_DESC = {'M':'庙','W':'旺','L':'利','P':'平','X':'陷'}
MW_SCORE = {'M':5, 'W':4, 'L':3, 'P':2, 'X':1}

# ==================== 核心函数 ====================

def get_ming_gong_zhi(month_num, hour):
    """命宫地支：寅起子时，顺月逆时"""
    shi_idx = 0 if hour in (23,0) else (hour+1)//2
    return DI_ZHI[(2+month_num-1-shi_idx)%12]

def get_shen_gong_zhi(month_num, hour):
    """身宫地支：寅起子时，顺月顺时"""
    shi_idx = 0 if hour in (23,0) else (hour+1)//2
    return DI_ZHI[(2+month_num-1+shi_idx)%12]

def get_gong_gan(year_gan, gong_zhi):
    """宫位天干：从寅宫起，按年干配天干"""
    start = {'甲':'丙','己':'丙','乙':'戊','庚':'戊','丙':'庚','辛':'庚',
             '丁':'壬','壬':'壬','戊':'甲','癸':'甲'}[year_gan]
    offset = (DI_ZHI.index(gong_zhi) - 2) % 12
    return TIAN_GAN[(TIAN_GAN.index(start) + offset) % 10]

def get_wu_xing_ju(gan_zhi):
    """命宫干支→五行局数"""
    ny = NA_YIN.get(gan_zhi, '')
    for wx, ju in NA_YIN_JU.items():
        if wx in ny:
            return ju, ny
    return 2, ny

def get_ziwei_zhi(day, ju):
    """紫微星所在宫位地支（三合派：商数/余数/补数奇偶修正）

    1. 农历日 ÷ 局数 → 商(shang)、余(r)
    2. 整除时补数=0、商不变；否则补数=局数-余、商+1
    3. 补数为偶(含0)：从寅顺行 (商-1)+补数
       补数为奇：    从寅逆行 (商-1)-补数
    """
    q, r = divmod(day, ju)
    if r == 0:
        bu, shang = 0, q
    else:
        bu, shang = ju - r, q + 1
    if bu % 2 == 0:
        offset = (shang - 1) + bu
    else:
        offset = (shang - 1) - bu
    return DI_ZHI[(2 + offset) % 12]

def arrange_12_gong(ming_zhi):
    """从命宫起逆布十二宫"""
    base = DI_ZHI.index(ming_zhi)
    return {name: DI_ZHI[(base-i)%12] for i, name in enumerate(SHI_ER_GONG)}

def arrange_stars(ziwei_zhi):
    """安十四主星"""
    tf_zhi = ZIWEI_TIANFU[ziwei_zhi]
    zw_base = DI_ZHI.index(ziwei_zhi)
    tf_base = DI_ZHI.index(tf_zhi)
    
    stars = {}
    for xing, off in ZW_XI.items():
        stars[xing] = DI_ZHI[(zw_base+off)%12]
    for xing, off in TF_XI.items():
        stars[xing] = DI_ZHI[(tf_base+off)%12]
    return stars

def arrange_fu_xing(year_gan, year_zhi, month_num, hour):
    """安辅星"""
    shi_idx = 0 if hour in (23,0) else (hour+1)//2
    lc = LU_CUN[year_gan]
    lc_idx = DI_ZHI.index(lc)
    
    return {
        '左辅': _zuofu(month_num),
        '右弼': _youbi(month_num),
        '文昌': _wenchang(shi_idx),
        '文曲': _wenqu(shi_idx),
        '禄存': lc,
        '擎羊': DI_ZHI[(lc_idx+1)%12],
        '陀罗': DI_ZHI[(lc_idx-1)%12],
        '天魁': TIAN_KUI[year_gan],
        '天钺': TIAN_YUE[year_gan],
        '火星': _huoxing(year_zhi, shi_idx),
        '铃星': _lingxing(year_zhi, shi_idx),
        '地空': _dikong(shi_idx),
        '地劫': _dijie(shi_idx),
        '天马': TIAN_MA.get(year_zhi,''),
    }

def get_si_hua(year_gan):
    """获取四化"""
    lu, quan, ke, ji = SI_HUA[year_gan]
    return {'化禄': lu, '化权': quan, '化科': ke, '化忌': ji}

def get_miao_wang(xing, zhi):
    """查庙旺"""
    code = MW.get(xing, {}).get(zhi, 'P')
    return MW_DESC.get(code, '平'), code

def da_xian_direction(year_gan, gender):
    """大限方向：阳男阴女顺行"""
    gender_norm = gender.strip()[0] if gender else '男'
    yang = year_gan in '甲丙戊庚壬'
    if gender_norm in ('男', 'M', 'm'):
        return 1 if yang else -1  # 1=顺, -1=逆
    else:
        return -1 if yang else 1

# ==================== 主函数 ====================

def pa_pan(year, month, day, hour, minute=0, longitude=120.0, gender='男',
           lunar_month=None, lunar_day=None):
    """
    紫微斗数起盘
    
    参数:
        year/month/day/hour/minute: 公历出生时间
        longitude: 经度(真太阳时修正)
        gender: 性别
        lunar_month/lunar_day: 农历月日(可选，不传则近似推算)
    
    返回: dict 完整紫微命盘
    """
    # 1. 真太阳时修正
    dt_obj = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt_obj)

    # 跨日处理
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt_obj + timedelta(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day

    # 2. 年柱
    nz = nian_zhu(act_y, act_m, act_d, true_h, true_m)
    year_gan = nz[0]
    year_zhi = nz[1]

    # 3. 农历月日（用 lunar_python 精确转换）
    #    闰月处理：lunar.getMonth() 闰月返回负数（闰二月=-2），不能直接排宫。
    #    采用三合派常见「以十五日为界」规则：闰月前半(≤15日)按本月排，后半按下月排。
    #    区分两个概念：
    #      - 真实农历月(display_month / is_leap_month)：用于显示
    #      - 排盘折算月(lunar_month)：用于命宫/身宫/月系辅星计算
    from lunar_python import Solar
    is_leap_month = False
    display_month = lunar_month        # 真实农历月（闰月时为基础月数，配合 is_leap_month）
    leap_pai_note = ''                 # 闰月排盘折算说明
    if lunar_month is None or lunar_day is None:
        solar = Solar.fromYmdHms(act_y, act_m, act_d, true_h, true_m, 0)
        lunar = solar.getLunar()
        raw_month = lunar.getMonth()
        if lunar_day is None:
            lunar_day = lunar.getDay()
        if lunar_month is None:
            if raw_month < 0:
                is_leap_month = True
                base_month = -raw_month
                display_month = base_month
                # 前半月按本月排，后半月按下月排（下月超过12回到正月）
                if lunar_day <= 15:
                    lunar_month = base_month
                    leap_pai_note = f'前半月，按{base_month}月排'
                else:
                    lunar_month = (base_month % 12) + 1
                    leap_pai_note = f'后半月，按{lunar_month}月排'
            else:
                lunar_month = raw_month
                display_month = raw_month

    # 手动传参路径：若调用方直接传入负数闰月（如 lunar_month=-2），同样按
    # 「以十五日为界」归一化，避免负月直接流入排宫计算。
    if lunar_month is not None and lunar_month < 0:
        is_leap_month = True
        base_month = -lunar_month
        display_month = base_month
        if (lunar_day or 1) <= 15:
            lunar_month = base_month
            leap_pai_note = f'前半月，按{base_month}月排'
        else:
            lunar_month = (base_month % 12) + 1
            leap_pai_note = f'后半月，按{lunar_month}月排'
    elif display_month is None:
        display_month = lunar_month

    # 4. 命宫身宫
    ming_zhi = get_ming_gong_zhi(lunar_month, true_h)
    shen_zhi = get_shen_gong_zhi(lunar_month, true_h)
    
    # 5. 十二宫
    gong_12 = arrange_12_gong(ming_zhi)
    
    # 6. 各宫天干
    gong_gan = {name: get_gong_gan(year_gan, zhi) for name, zhi in gong_12.items()}
    
    # 7. 五行局
    ming_gz = gong_gan['命宫'] + ming_zhi
    ju, na_yin = get_wu_xing_ju(ming_gz)
    
    # 8. 紫微星
    ziwei_zhi = get_ziwei_zhi(lunar_day, ju)
    
    # 9. 十四主星
    all_stars = arrange_stars(ziwei_zhi)
    
    # 10. 辅星
    fu_xing = arrange_fu_xing(year_gan, year_zhi, lunar_month, true_h)
    
    # 11. 四化
    si_hua = get_si_hua(year_gan)
    
    # 12. 组装盘面
    # 反向映射：地支→宫名列表
    zhi_to_gong = {}
    for name, zhi in gong_12.items():
        zhi_to_gong.setdefault(zhi, []).append(name)
    
    pan_mian = {}
    for name in SHI_ER_GONG:
        zhi = gong_12[name]
        gan = gong_gan[name]
        
        # 该宫的主星及庙旺
        zhuxing_list = [x for x, p in all_stars.items() if p == zhi]
        zhuxing_mw = {}
        for xing in zhuxing_list:
            desc, code = get_miao_wang(xing, zhi)
            zhuxing_mw[xing] = desc
        
        # 该宫的辅星及庙旺
        fuxing_list = [x for x, p in fu_xing.items() if p == zhi]
        fuxing_mw = {}
        for xing in fuxing_list:
            desc, code = get_miao_wang(xing, zhi)
            fuxing_mw[xing] = desc
        
        # 四化标记
        hua_marks = {}
        for hua_type, xing_name in si_hua.items():
            if xing_name in zhuxing_list or xing_name in fuxing_list:
                hua_marks[xing_name] = hua_type
        
        pan_mian[name] = {
            '天干': gan,
            '地支': zhi,
            '干支': gan + zhi,
            '主星': {xing: zhuxing_mw[xing] for xing in zhuxing_list},
            '辅星': {xing: fuxing_mw[xing] for xing in fuxing_list},
            '四化': hua_marks,
            '身宫标记': (zhi == shen_zhi),
        }
    
    # 13. 大限信息
    dx_dir = da_xian_direction(year_gan, gender)
    dx_info = []
    gong_idx = DI_ZHI.index(ming_zhi)
    for i in range(12):
        age_start = ju + i * 10
        age_end = age_start + 9
        dx_zhi = DI_ZHI[(gong_idx + i * dx_dir) % 12]
        dx_gong_name = [n for n, z in gong_12.items() if z == dx_zhi]
        dx_info.append({
            '年龄段': f'{age_start}-{age_end}岁',
            '大限宫': dx_zhi,
            '宫名': dx_gong_name[0] if dx_gong_name else '',
        })
    
    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '农历月日': f'{"闰" if is_leap_month else ""}{display_month}月{lunar_day}日',
        '排盘月': lunar_month,
        '闰月处理': leap_pai_note if is_leap_month else '',
        '性别': gender,
        '年柱': nz,
        '命宫': ming_zhi,
        '身宫': shen_zhi,
        '五行局': f'{na_yin}·{ju}局',
        '紫微星位': ziwei_zhi,
        '天府星位': ZIWEI_TIANFU[ziwei_zhi],
        '四化': si_hua,
        '大限方向': '顺行' if dx_dir == 1 else '逆行',
        '大限': dx_info,
        '十二宫': pan_mian,
    }


# ==================== 测试 ====================
if __name__ == '__main__':
    result = pa_pan(1990, 5, 1, 8, 0, longitude=116.4, gender='男')
    
    print(f"命宫: {result['命宫']}  身宫: {result['身宫']}")
    print(f"五行局: {result['五行局']}")
    print(f"紫微星: {result['紫微星位']}  天府星: {result['天府星位']}")
    print(f"四化: {result['四化']}")
    print(f"大限方向: {result['大限方向']}")
    print()
    
    for name, info in result['十二宫'].items():
        parts = []
        if info['主星']:
            for xing, mw in info['主星'].items():
                hua = info['四化'].get(xing, '')
                parts.append(f"{xing}({mw}{'·'+hua if hua else ''})")
        if info['辅星']:
            for xing, mw in info['辅星'].items():
                hua = info['四化'].get(xing, '')
                parts.append(f"{xing}({mw}{'·'+hua if hua else ''})")
        
        shen = ' ★身宫' if info['身宫标记'] else ''
        stars_str = ' '.join(parts) if parts else '空宫'
        print(f"  {name}({info['干支']}){shen}: {stars_str}")
    
    print(f"\n大限:")
    for dx in result['大限'][:6]:
        print(f"  {dx['年龄段']}: {dx['宫名']}({dx['大限宫']})")
