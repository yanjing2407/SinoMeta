# -*- coding: utf-8 -*-
"""
梅花易数起盘模块
==============
规则说明:
  梅花易数是邵雍所创，最大特点是"万物皆可起卦"。
  核心是体用关系：不动为体，动为用。用生体、比和则吉；用克体则凶。
  
  排盘步骤:
    1. 起卦（数字法/时间法/方位法/声音法/字数法）
    2. 定体用（动爻所在卦为用卦，另一卦为体卦）
    3. 列互卦（234爻为下互，345爻为上互）
    4. 列变卦（动爻变后的卦）
    5. 分析体用五行生克关系
"""

from calendar_utils import (
    DI_ZHI, BA_GUA, BA_GUA_WX, XIAN_TIAN, LUO_SHU,
    true_solar_time, nian_zhu, get_jie_qi_month, shi_chen_idx, ri_zhu
)

# 先天数→八卦
XT2GUA = {1:'乾',2:'兑',3:'离',4:'震',5:'巽',6:'坎',7:'艮',8:'坤'}
GUA2XT = {v:k for k,v in XT2GUA.items()}

# 八卦象意（用于解读）
GUA_XIANG = {
    '乾': {'象':'天','性':'健','五行':'金','人物':'父/君','身体':'首','动物':'马','方位':'西北'},
    '兑': {'象':'泽','性':'悦','五行':'金','人物':'少女','身体':'口','动物':'羊','方位':'西'},
    '离': {'象':'火','性':'丽','五行':'火','人物':'中女','身体':'目','动物':'雉','方位':'南'},
    '震': {'象':'雷','性':'动','五行':'木','人物':'长男','身体':'足','动物':'龙','方位':'东'},
    '巽': {'象':'风','性':'入','五行':'木','人物':'长女','身体':'股','动物':'鸡','方位':'东南'},
    '坎': {'象':'水','性':'陷','五行':'水','人物':'中男','身体':'耳','动物':'猪','方位':'北'},
    '艮': {'象':'山','性':'止','五行':'土','人物':'少男','身体':'手','动物':'狗','方位':'东北'},
    '坤': {'象':'地','性':'顺','五行':'土','人物':'母','身体':'腹','动物':'牛','方位':'西南'},
}

# 体用关系断语
TI_YONG_DUAN = {
    '用生体': '大吉，有助力，事可成',
    '用克体': '凶，有阻力，事难成',
    '体生用': '泄气，费力不讨好',
    '体克用': '小吉，费力可成',
    '比和':   '吉，势均力敌，顺利',
}

# ==================== 起卦方法 ====================

def qi_gua_by_time(year, month, day, hour, minute=0):
    """
    时间起卦法
    规则: 
      上卦 = (年支序+月+日) % 8 → 先天数
      下卦 = (年支序+月+日+时辰序) % 8 → 先天数
      动爻 = (年支序+月+日+时辰序) % 6 + 1
    """
    nz = nian_zhu(year, month, day, hour, minute)
    nian_idx = DI_ZHI.index(nz[1]) + 1
    mnum = get_jie_qi_month(year, month, day, hour, minute)
    shi_idx = shi_chen_idx(hour) + 1
    
    n1 = nian_idx + mnum + day
    n2 = n1 + shi_idx
    
    shang = n1 % 8 or 8
    xia = n2 % 8 or 8
    dong = n2 % 6 or 6
    
    return XT2GUA[shang], XT2GUA[xia], dong


def qi_gua_by_numbers(a, b, dong=None):
    """
    数字起卦法
    a → 上卦 = a % 8
    b → 下卦 = b % 8
    动爻 = (a+b) % 6，或指定
    """
    shang = a % 8 or 8
    xia = b % 8 or 8
    if dong is None:
        dong = (a + b) % 6 or 6
    return XT2GUA[shang], XT2GUA[xia], dong


def qi_gua_by_fangwei(azimuth):
    """
    方位起卦法（手机指南针）
    azimuth: 0-360度方位角
    上卦 = 方位角/45°取整 + 1 → 后天八卦序
    下卦 = 用当前时辰
    """
    # 后天八卦方位角
    # 北0, 东北45, 东90, 东南135, 南180, 西南225, 西270, 西北315
    idx = int(azimuth / 45) % 8
    fangwei_gua = ['坎','艮','震','巽','离','坤','兑','乾'][idx]
    
    return fangwei_gua  # 仅返回方位卦，需配合时间组成上下卦


def qi_gua_by_text(text):
    """
    字数起卦法
    规则: 
      字数分两半，前半为上卦，后半为下卦
      单数时前多半
      动爻 = 总字数 % 6
    """
    n = len(text)
    half = (n + 1) // 2
    a = half
    b = n - half
    dong = n % 6 or 6
    
    shang = a % 8 or 8
    xia = b % 8 or 8
    return XT2GUA[shang], XT2GUA[xia], dong


# ==================== 卦象操作 ====================

def gua_to_yao(gua_name):
    """八卦名 → 三爻(从下到上，1=阳，0=阴)"""
    yao_map = {
        '乾':[1,1,1], '兑':[1,1,0], '离':[1,0,1], '震':[1,0,0],
        '巽':[0,1,1], '坎':[0,1,0], '艮':[0,0,1], '坤':[0,0,0]
    }
    return yao_map.get(gua_name, [0,0,0])


def yao_to_gua(yao):
    """三爻 → 八卦名"""
    gua_map = {
        (1,1,1):'乾',(1,1,0):'兑',(1,0,1):'离',(1,0,0):'震',
        (0,1,1):'巽',(0,1,0):'坎',(0,0,1):'艮',(0,0,0):'坤'
    }
    return gua_map.get(tuple(yao), '坤')


def get_hu_gua(shang_yao, xia_yao):
    """
    互卦: 取234爻为下互，345爻为上互
    """
    all_yao = xia_yao + shang_yao  # 初到上
    hu_xia = [all_yao[1], all_yao[2], all_yao[3]]  # 234爻
    hu_shang = [all_yao[2], all_yao[3], all_yao[4]]  # 345爻
    return yao_to_gua(hu_shang), yao_to_gua(hu_xia)


def get_bian_gua(shang_gua, xia_gua, dong_yao):
    """
    变卦: 动爻变（阳变阴，阴变阳）
    """
    xia_yao = gua_to_yao(xia_gua)
    shang_yao = gua_to_yao(shang_gua)
    all_yao = xia_yao + shang_yao
    
    bian_yao = all_yao.copy()
    idx = dong_yao - 1
    bian_yao[idx] = 1 - bian_yao[idx]  # 0→1, 1→0
    
    bian_shang = yao_to_gua(bian_yao[3:6])
    bian_xia = yao_to_gua(bian_yao[0:3])
    return bian_shang, bian_xia


# ==================== 体用分析 ====================

def analyze_ti_yong(shang_gua, xia_gua, dong_yao):
    """
    体用分析
    规则:
      动爻在上卦 → 下卦为体，上卦为用
      动爻在下卦 → 上卦为体，下卦为用
    """
    if dong_yao >= 4:
        # 动爻在上卦
        ti_gua = xia_gua  # 下卦为体
        yong_gua = shang_gua  # 上卦为用
    else:
        # 动爻在下卦
        ti_gua = shang_gua
        yong_gua = xia_gua
    
    ti_wx = BA_GUA_WX[ti_gua]
    yong_wx = BA_GUA_WX[yong_gua]
    
    from calendar_utils import WX_SHENG, WX_KE
    if ti_wx == yong_wx:
        relation = '比和'
    elif WX_SHENG.get(yong_wx) == ti_wx:
        relation = '用生体'
    elif WX_KE.get(yong_wx) == ti_wx:
        relation = '用克体'
    elif WX_SHENG.get(ti_wx) == yong_wx:
        relation = '体生用'
    elif WX_KE.get(ti_wx) == yong_wx:
        relation = '体克用'
    else:
        relation = '未知'
    
    return {
        '体卦': ti_gua,
        '用卦': yong_gua,
        '体五行': ti_wx,
        '用五行': yong_wx,
        '体用关系': relation,
        '断语': TI_YONG_DUAN.get(relation, ''),
    }


# ==================== 主函数 ====================

def pa_pan(year, month, day, hour, minute=0, longitude=120.0,
           method='time', num1=None, num2=None, text=None, azimuth=None):
    """
    梅花易数起盘

    参数:
        method: 'time'(时间起卦) / 'number'(数字起卦) / 'text'(字数起卦)
        num1, num2: 数字起卦时的两个数
        text: 字数起卦时的文字
        azimuth: 方位角（手机指南针）
    """
    from datetime import date as dt_cls, timedelta as td_cls

    # 真太阳时修正（用于时间/方位起卦）
    dt_obj = dt_cls(year, month, day)
    true_h, true_m, day_offset = true_solar_time(longitude, hour, minute, date_obj=dt_obj)
    act_y, act_m, act_d = year, month, day
    if day_offset != 0:
        dt2 = dt_obj + td_cls(days=day_offset)
        act_y, act_m, act_d = dt2.year, dt2.month, dt2.day

    # 起卦
    if method == 'number' and num1 is not None and num2 is not None:
        shang, xia, dong = qi_gua_by_numbers(num1, num2)
    elif method == 'text' and text:
        shang, xia, dong = qi_gua_by_text(text)
    elif method == 'fangwei' and azimuth is not None:
        fw_gua = qi_gua_by_fangwei(azimuth)
        nz = nian_zhu(act_y, act_m, act_d)
        shi_idx = shi_chen_idx(true_h) + 1
        xia = XT2GUA[shi_idx % 8 or 8]
        shang = fw_gua
        dong = shi_idx % 6 or 6
    else:
        # 默认时间起卦（使用真太阳时修正后的日期和时辰）
        shang, xia, dong = qi_gua_by_time(act_y, act_m, act_d, true_h, true_m)
    
    # 互卦
    shang_yao = gua_to_yao(shang)
    xia_yao = gua_to_yao(xia)
    hu_shang, hu_xia = get_hu_gua(shang_yao, xia_yao)
    
    # 变卦
    bian_shang, bian_xia = get_bian_gua(shang, xia, dong)
    
    # 体用分析
    ti_yong = analyze_ti_yong(shang, xia, dong)

    return {
        '公历': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '真太阳时': f'{true_h:02d}:{true_m:02d}',
        '经度': longitude,
        '本卦': {
            '上卦': shang, '下卦': xia,
            '卦名': f'{shang}{xia}',
            '上卦象': GUA_XIANG[shang],
            '下卦象': GUA_XIANG[xia],
        },
        '互卦': {
            '上卦': hu_shang, '下卦': hu_xia,
            '卦名': f'{hu_shang}{hu_xia}',
        },
        '变卦': {
            '上卦': bian_shang, '下卦': bian_xia,
            '卦名': f'{bian_shang}{bian_xia}',
        },
        '动爻': dong,
        '体用分析': ti_yong,
    }


if __name__ == '__main__':
    # 时间起卦
    result = pa_pan(2024, 6, 15, 14, 30, longitude=116.4)
    print(f"本卦: {result['本卦']['卦名']}")
    print(f"互卦: {result['互卦']['卦名']}")
    print(f"变卦: {result['变卦']['卦名']}")
    print(f"动爻: {result['动爻']}")
    print(f"体用: 体={result['体用分析']['体卦']}({result['体用分析']['体五行']}) "
          f"用={result['体用分析']['用卦']}({result['体用分析']['用五行']}) "
          f"→ {result['体用分析']['体用关系']}：{result['体用分析']['断语']}")
    
    # 数字起卦
    print("\n--- 数字起卦 ---")
    result2 = pa_pan(2024,1,1,12, method='number', num1=3, num2=7)
    print(f"数字3,7起卦: {result2['本卦']['卦名']}, 动{result2['动爻']}爻")
    
    # 方位起卦
    print("\n--- 方位起卦 ---")
    result3 = pa_pan(2024,6,15,14, method='fangwei', azimuth=135)
    print(f"东南方(135°)起卦: {result3['本卦']['卦名']}")
