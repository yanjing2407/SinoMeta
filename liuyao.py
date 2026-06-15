# -*- coding: utf-8 -*-
"""
六爻纳甲起盘模块
==============
规则说明:
  六爻以"事"为核心，通过起卦得到64卦中某一卦，装上纳甲、六亲，
  根据用神、动爻、日月建等判断事情吉凶。
  
  排盘步骤:
    1. 起卦（摇卦法/数字法/时间法）
    2. 定卦名（上卦+下卦）
    3. 装纳甲（每爻配天干地支）
    4. 配六亲（以卦宫五行为我，各爻地支五行对照）
    5. 安世应
    6. 标日月建、旬空、月破
    7. 识别动爻变卦
"""

from datetime import date, timedelta
from calendar_utils import (
    TIAN_GAN, DI_ZHI, TIAN_GAN_WX, DI_ZHI_WX, BA_GUA, BA_GUA_WX,
    XIAN_TIAN, LUO_SHU, true_solar_time, ri_zhu, shi_zhu, shi_chen_idx, xun_kong
)

# 八卦爻象映射（从初爻到三爻，1=阳 0=阴）
GUA_YAO = {
    '乾':[1,1,1], '兑':[1,1,0], '离':[1,0,1], '震':[1,0,0],
    '巽':[0,1,1], '坎':[0,1,0], '艮':[0,0,1], '坤':[0,0,0]
}
YAO_GUA = {tuple(v): k for k, v in GUA_YAO.items()}

# ==================== 64卦表 ====================
# 格式: (上卦, 下卦) → 卦名
GUA_64 = {
    ('乾','乾'):'乾为天', ('坤','坤'):'坤为地', ('震','震'):'震为雷',
    ('巽','巽'):'巽为风', ('坎','坎'):'坎为水', ('离','离'):'离为火',
    ('艮','艮'):'艮为山', ('兑','兑'):'兑为泽',
    ('坤','乾'):'地天泰', ('乾','坤'):'天地否',
    ('坎','坤'):'水地比', ('坤','坎'):'地水师',
    ('震','坤'):'雷地豫', ('坤','震'):'地雷复',
    ('巽','乾'):'风天小畜', ('乾','巽'):'天风姤',
    ('离','乾'):'火天大有', ('乾','离'):'天火同人',
    ('坎','乾'):'水天需', ('乾','坎'):'天水讼',
    ('离','坤'):'火地晋', ('坤','离'):'地火明夷',
    ('艮','乾'):'山天大畜', ('乾','艮'):'天山遁',
    ('兑','乾'):'泽天夬', ('乾','兑'):'天泽履',
    ('震','乾'):'雷天大壮', ('乾','震'):'天雷无妄',
    ('巽','坤'):'风地观', ('坤','巽'):'地风升',
    ('艮','坤'):'山地剥', ('坤','艮'):'地山谦',
    ('兑','坤'):'泽地萃', ('坤','兑'):'地泽临',
    ('震','坎'):'雷水解', ('坎','震'):'水雷屯',
    ('巽','坎'):'风水涣', ('坎','巽'):'水风井',
    ('离','震'):'火雷噬嗑', ('震','离'):'雷火丰',
    ('坎','离'):'水火既济', ('离','坎'):'火水未济',
    ('艮','震'):'山雷颐', ('震','艮'):'雷山小过',
    ('兑','震'):'泽雷随', ('震','兑'):'雷泽归妹',
    ('巽','离'):'风火家人', ('离','巽'):'火风鼎',
    ('坎','艮'):'水山蹇', ('艮','坎'):'山水蒙',
    ('离','兑'):'火泽睽', ('兑','离'):'泽火革',
    ('艮','巽'):'山风蛊', ('巽','艮'):'风山渐',
    ('兑','坎'):'泽水困', ('坎','兑'):'水泽节',
    ('艮','离'):'山火贲', ('离','艮'):'火山旅',
    ('兑','巽'):'泽风大过', ('巽','兑'):'风泽中孚',
    ('艮','兑'):'山泽损', ('兑','艮'):'泽山咸',
    ('巽','震'):'风雷益', ('震','巽'):'雷风恒',
}

# ==================== 八宫归属 ====================
# 每个卦属于一个宫（八纯卦），宫的五行决定六亲
BA_GONG = {
    '乾为天':'乾', '天风姤':'乾', '天山遁':'乾', '天地否':'乾',
    '风地观':'乾', '山地剥':'乾', '火地晋':'乾', '火天大有':'乾',
    
    '坎为水':'坎', '水泽节':'坎', '水雷屯':'坎', '水火既济':'坎',
    '泽火革':'坎', '雷火丰':'坎', '地火明夷':'坎', '地水师':'坎',
    
    '艮为山':'艮', '山火贲':'艮', '山天大畜':'艮', '山泽损':'艮',
    '火泽睽':'艮', '天泽履':'艮', '风泽中孚':'艮', '风山渐':'艮',
    
    '震为雷':'震', '雷地豫':'震', '雷水解':'震', '雷风恒':'震',
    '地风升':'震', '水风井':'震', '泽风大过':'震', '泽雷随':'震',
    
    '巽为风':'巽', '风天小畜':'巽', '风火家人':'巽', '风雷益':'巽',
    '天雷无妄':'巽', '火雷噬嗑':'巽', '山雷颐':'巽', '山风蛊':'巽',
    
    '离为火':'离', '火山旅':'离', '火风鼎':'离', '火水未济':'离',
    '山水蒙':'离', '风水涣':'离', '天水讼':'离', '天火同人':'离',
    
    '坤为地':'坤', '地雷复':'坤', '地泽临':'坤', '地天泰':'坤',
    '雷天大壮':'坤', '泽天夬':'坤', '水天需':'坤', '水地比':'坤',
    
    '兑为泽':'兑', '泽水困':'兑', '泽地萃':'兑', '泽山咸':'兑',
    '水山蹇':'兑', '地山谦':'兑', '雷山小过':'兑', '雷泽归妹':'兑',
}

# ==================== 纳甲 ====================
# 规则: 乾纳甲壬(内甲外壬)，坤纳乙癸，震纳庚，巽纳辛，坎纳戊，离纳己，艮纳丙，兑纳丁
NA_JIA_GAN = {
    '乾': ('甲', '壬'), '坤': ('乙', '癸'), '震': ('庚', '庚'),
    '巽': ('辛', '辛'), '坎': ('戊', '戊'), '离': ('己', '己'),
    '艮': ('丙', '丙'), '兑': ('丁', '丁')
}

# 各卦六爻地支（从初爻到上爻）
NA_JIA_ZHI = {
    '乾': ['子','寅','辰','午','申','戌'],
    '坤': ['未','巳','卯','丑','亥','酉'],
    '震': ['子','寅','辰','午','申','戌'],
    '巽': ['丑','亥','酉','未','巳','卯'],
    '坎': ['寅','辰','午','申','戌','子'],
    '离': ['卯','丑','亥','酉','未','巳'],
    '艮': ['辰','午','申','戌','子','寅'],
    '兑': ['巳','卯','丑','亥','酉','未']
}

# 世应位置（从初爻起，第几爻为世，第几爻为应）
SHI_YING = {
    '乾为天': (6, 3), '天风姤': (1, 4), '天山遁': (2, 5), '天地否': (3, 6),
    '风地观': (4, 1), '山地剥': (5, 2), '火地晋': (4, 1), '火天大有': (3, 6),
    
    '坎为水': (6, 3), '水泽节': (1, 4), '水雷屯': (2, 5), '水火既济': (3, 6),
    '泽火革': (4, 1), '雷火丰': (5, 2), '地火明夷': (4, 1), '地水师': (3, 6),
    
    '艮为山': (6, 3), '山火贲': (1, 4), '山天大畜': (2, 5), '山泽损': (3, 6),
    '火泽睽': (4, 1), '天泽履': (5, 2), '风泽中孚': (4, 1), '风山渐': (3, 6),
    
    '震为雷': (6, 3), '雷地豫': (1, 4), '雷水解': (2, 5), '雷风恒': (3, 6),
    '地风升': (4, 1), '水风井': (5, 2), '泽风大过': (4, 1), '泽雷随': (3, 6),
    
    '巽为风': (6, 3), '风天小畜': (1, 4), '风火家人': (2, 5), '风雷益': (3, 6),
    '天雷无妄': (4, 1), '火雷噬嗑': (5, 2), '山雷颐': (4, 1), '山风蛊': (3, 6),
    
    '离为火': (6, 3), '火山旅': (1, 4), '火风鼎': (2, 5), '火水未济': (3, 6),
    '山水蒙': (4, 1), '风水涣': (5, 2), '天水讼': (4, 1), '天火同人': (3, 6),
    
    '坤为地': (6, 3), '地雷复': (1, 4), '地泽临': (2, 5), '地天泰': (3, 6),
    '雷天大壮': (4, 1), '泽天夬': (5, 2), '水天需': (4, 1), '水地比': (3, 6),
    
    '兑为泽': (6, 3), '泽水困': (1, 4), '泽地萃': (2, 5), '泽山咸': (3, 6),
    '水山蹇': (4, 1), '地山谦': (5, 2), '雷山小过': (4, 1), '雷泽归妹': (3, 6),
}


# ==================== 六亲 ====================
def get_liu_qin(gong_wx, yao_zhi):
    """以卦宫五行为我，查各爻六亲"""
    yao_wx = DI_ZHI_WX[yao_zhi]
    from calendar_utils import WX_SHENG, WX_KE
    
    if gong_wx == yao_wx:
        return '兄弟'
    if WX_SHENG.get(gong_wx) == yao_wx:
        return '子孙'
    if WX_KE.get(gong_wx) == yao_wx:
        return '妻财'
    if WX_SHENG.get(yao_wx) == gong_wx:
        return '父母'
    if WX_KE.get(yao_wx) == gong_wx:
        return '官鬼'
    return '未知'


# ==================== 起卦方法 ====================

def qi_gua_by_time(year, month, day, hour, minute=0):
    """
    时间起卦法（梅花易数方式，但用于六爻排盘）
    规则: 
      上卦 = (年+月+日) % 8 → 先天数
      下卦 = (年+月+日+时) % 8 → 先天数
      动爻 = (年+月+日+时) % 6 + 1
    """
    from calendar_utils import nian_zhu, get_jie_qi_month
    nz = nian_zhu(year, month, day, hour, minute)
    nian_zhi_idx = DI_ZHI.index(nz[1])
    mnum = get_jie_qi_month(year, month, day, hour, minute)
    shi_idx = shi_chen_idx(hour)
    
    num1 = nian_zhi_idx + 1 + mnum + day
    num2 = num1 + shi_idx + 1
    
    shang_idx = num1 % 8  # 0-7 → 先天数1-8
    xia_idx = num2 % 8
    
    if shang_idx == 0: shang_idx = 8
    if xia_idx == 0: xia_idx = 8
    
    # 先天数→八卦
    XT = {1:'乾',2:'兑',3:'离',4:'震',5:'巽',6:'坎',7:'艮',8:'坤'}
    shang_gua = XT[shang_idx]
    xia_gua = XT[xia_idx]
    
    # 动爻
    dong_yao = num2 % 6
    if dong_yao == 0: dong_yao = 6
    
    return shang_gua, xia_gua, dong_yao


def qi_gua_by_numbers(num1, num2, dong=None):
    """
    数字起卦法
    num1 → 上卦 = num1 % 8
    num2 → 下卦 = num2 % 8
    dong → 动爻 = (num1+num2) % 6，或指定
    """
    XT = {1:'乾',2:'兑',3:'离',4:'震',5:'巽',6:'坎',7:'艮',8:'坤'}
    
    s = num1 % 8
    x = num2 % 8
    if s == 0: s = 8
    if x == 0: x = 8
    
    if dong is None:
        dong = (num1 + num2) % 6
    if dong == 0: dong = 6
    
    return XT[s], XT[x], dong


def qi_gua_by_yao(yao_list):
    """
    摇卦法输入
    yao_list: 6个数字，从初爻到上爻
      1=阳爻, 0=阴爻
      动爻用 3(阳动), 2(阴动) 表示
    返回: (上卦名, 下卦名, 动爻列表)
    """
    # 下卦=初二三爻，上卦=四五上爻
    xia_yao = yao_list[:3]
    shang_yao = yao_list[3:]
    
    # 三爻→八卦
    def yao_to_gua(yao):
        gua_map = {
            (1,1,1): '乾', (1,1,0): '兑', (1,0,1): '离', (1,0,0): '震',
            (0,1,1): '巽', (0,1,0): '坎', (0,0,1): '艮', (0,0,0): '坤'
        }
        # 动爻归为静爻查卦
        key = tuple(1 if y in (1,3) else 0 for y in yao)
        return gua_map.get(key, '坤')
    
    shang = yao_to_gua(shang_yao)
    xia = yao_to_gua(xia_yao)
    
    # 动爻位置
    dong = [i+1 for i, y in enumerate(yao_list) if y in (2, 3)]
    
    return shang, xia, dong


# ==================== 装卦 ====================

def zhuang_gua(shang_gua, xia_gua, dong_yao, year, month, day, hour, minute=0, longitude=120.0):
    """
    装卦主函数
    
    参数:
        shang_gua, xia_gua: 上下卦名
        dong_yao: 动爻号(1-6)或列表
        year~longitude: 时间经纬度
    返回:
        dict 完整六爻盘面
    """
    # 1. 真太阳时 & 日月建
    dt = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt)

    # 跨日处理
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt + timedelta(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day

    rz = ri_zhu(act_y, act_m, act_d)
    sz = shi_zhu(rz[0], true_h)

    # 月建（月支）— 用 lunar_python 精确节气确定月柱
    from calendar_utils import yue_zhu
    yz = yue_zhu(act_y, act_m, act_d, true_h, true_m)
    yue_jian = yz[1]  # 月支
    ri_jian = rz[1]   # 日支
    
    # 2. 定卦名
    gua_name = GUA_64.get((shang_gua, xia_gua), f'{shang_gua}{xia_gua}')
    
    # 3. 宫属
    gong = BA_GONG.get(gua_name, '乾')  # 默认乾宫
    gong_wx = BA_GUA_WX[gong]
    
    # 4. 装纳甲
    # 内卦（下卦）用内干，外卦（上卦）用外干
    nei_gan, wai_gan = NA_JIA_GAN[xia_gua]
    nei_zhi = NA_JIA_ZHI[xia_gua][:3]
    wai_zhi = NA_JIA_ZHI[shang_gua][3:]

    # 计算动爻位置列表
    dong_positions = []
    if isinstance(dong_yao, list):
        dong_positions = dong_yao
    else:
        dong_positions = [dong_yao]

    # 计算变卦纳甲地支（用于动爻变支）
    xia_yao = GUA_YAO[xia_gua]
    shang_yao = GUA_YAO[shang_gua]
    all_yao = xia_yao + shang_yao
    bian_yao = all_yao.copy()
    for pos in dong_positions:
        bian_yao[pos - 1] = 1 - bian_yao[pos - 1]
    bian_xia_gua = YAO_GUA.get(tuple(bian_yao[:3]), '坤')
    bian_shang_gua = YAO_GUA.get(tuple(bian_yao[3:]), '坤')
    bian_nei_zhi = NA_JIA_ZHI[bian_xia_gua][:3]
    bian_wai_zhi = NA_JIA_ZHI[bian_shang_gua][3:]

    yao_info = []
    for i in range(6):
        if i < 3:
            # 内卦（初二三爻）
            gan = nei_gan
            zhi = nei_zhi[i]
        else:
            # 外卦（四五上爻）
            gan = wai_gan
            zhi = wai_zhi[i-3]

        liu_qin = get_liu_qin(gong_wx, zhi)

        # 是否动爻
        is_dong = (i + 1) in dong_positions

        # 变支：动爻按变卦重新纳甲
        bian_zhi = None
        if is_dong:
            if i < 3:
                bian_zhi = bian_nei_zhi[i]
            else:
                bian_zhi = bian_wai_zhi[i-3]

        yao_info.append({
            '爻位': i + 1,
            '爻名': ['初','二','三','四','五','上'][i],
            '干支': gan + zhi,
            '六亲': liu_qin,
            '五行': DI_ZHI_WX[zhi],
            '动爻': is_dong,
            '变支': bian_zhi,
        })
    
    # 5. 世应
    sy = SHI_YING.get(gua_name, (6, 3))
    for y in yao_info:
        y['世'] = (y['爻位'] == sy[0])
        y['应'] = (y['爻位'] == sy[1])
    
    # 6. 月破 & 旬空
    yue_po = {'子':'午','午':'子','丑':'未','未':'丑','寅':'申','申':'寅',
              '卯':'酉','酉':'卯','辰':'戌','戌':'辰','巳':'亥','亥':'巳'}[yue_jian]
    kong1, kong2 = xun_kong(rz)
    
    for y in yao_info:
        y['月破'] = (y['干支'][1] == yue_po)
        y['旬空'] = (y['干支'][1] in (kong1, kong2))
    
    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '卦名': gua_name,
        '宫属': f'{gong}宫({gong_wx})',
        '上卦': shang_gua,
        '下卦': xia_gua,
        '月建': yue_jian,
        '日建': ri_jian,
        '日干支': rz,
        '月破地支': yue_po,
        '旬空地支': [kong1, kong2],
        '六爻': yao_info,
    }


# ==================== 便捷函数 ====================

def pa_pan_by_time(year, month, day, hour, minute=0, longitude=120.0):
    """时间起卦法排盘（使用真太阳时确定卦象）"""
    from calendar_utils import true_solar_time
    dt = date(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt)
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt + timedelta(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day
    shang, xia, dong = qi_gua_by_time(act_y, act_m, act_d, true_h, true_m)
    return zhuang_gua(shang, xia, dong, year, month, day, hour, minute, longitude)

def pa_pan_by_numbers(num1, num2, dong=None, year=2024, month=1, day=1, hour=12, minute=0, longitude=120.0):
    """数字起卦法排盘"""
    shang, xia, dong_list = qi_gua_by_numbers(num1, num2, dong)
    return zhuang_gua(shang, xia, dong_list, year, month, day, hour, minute, longitude)

def pa_pan_by_yao(yao_list, year=2024, month=1, day=1, hour=12, minute=0, longitude=120.0):
    """摇卦法排盘"""
    shang, xia, dong = qi_gua_by_yao(yao_list)
    return zhuang_gua(shang, xia, dong, year, month, day, hour, minute, longitude)


if __name__ == '__main__':
    # 时间起卦测试
    result = pa_pan_by_time(2024, 6, 15, 14, 30, longitude=116.4)
    print(f"卦名: {result['卦名']}")
    print(f"宫属: {result['宫属']}")
    print(f"月建: {result['月建']}, 日建: {result['日建']}")
    for y in result['六爻']:
        flag = ''
        if y['动爻']: flag += ' 动→' + (y['变支'] or '')
        if y['世']: flag += ' 世'
        if y['应']: flag += ' 应'
        if y['旬空']: flag += ' 空'
        if y['月破']: flag += ' 破'
        print(f"  {y['爻名']}爻: {y['干支']} {y['六亲']}({y['五行']}){flag}")
