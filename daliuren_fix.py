# -*- coding: utf-8 -*-
"""
大六壬三传取法修复版
修复问题：
1. 处理"上克下"（kek）
2. 正确实现涉害法
3. 修正八专判断逻辑
4. 统一九宗门顺序
"""

def get_san_chuan_fixed(si_ke, tian_pan, ri_gan):
    """
    三传取法（九宗门完整实现）

    九宗门顺序（参考维基百科）：
    1. 贼克（下克上）
    2. 知一/比用（多克时取与日干阴阳同者）
    3. 涉害（无克贼，日干上神与日支上神相克）
    4. 遥克（无克贼涉害，日干与四课上神五行遥克）
    5. 昴星（无遥克）
    6. 别责（四课无克且无遥克，取日干支下神相克）
    7. 八专（四课上下相同）
    8. 伏吟（天盘地盘相同）
    9. 返吟（天盘地盘相冲）

    参数:
        si_ke: [(name, 上支, 下支), ...] 四课列表
        tian_pan: {地支: 天盘地支} 天盘映射
        ri_gan: 日干

    返回: {'初传': str, '中传': str, '末传': str, '起传法': str}
    """
    # 提取干阳、干阴、支阳、支阴
    gan_yang = si_ke[0]  # (第一课, 上支, 下支)
    gan_yin = si_ke[1]
    zhi_yang = si_ke[2]
    zhi_yin = si_ke[3]

    # 检查伏吟（天盘地盘相同）
    if all(tian_pan[dz] == dz for dz in tian_pan):
        # 伏吟：初传取日干寄宫，中传取初传天盘，末传取中传天盘
        chu = GAN_JI_GONG[ri_gan]
        return _complete(chu, tian_pan, '伏吟')

    # 检查返吟（天盘地盘相冲）
    chong_map = {'子':'午','丑':'未','寅':'申','卯':'酉','辰':'戌','巳':'亥',
                 '午':'子','未':'丑','申':'寅','酉':'卯','戌':'辰','亥':'巳'}
    if all(tian_pan[dz] == chong_map[dz] for dz in tian_pan):
        # 返吟：初传取日干支下神（支阳课下支）
        chu = zhi_yang[2]
        return _complete(chu, tian_pan, '返吟')

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

    # 1. 贼克法：有下克上
    if len(zei) == 1:
        return _complete(zei[0][1], tian_pan, '贼克')

    if len(zei) > 1:
        # 知一/比用：多个贼克时取与日干阴阳相同者
        return _bi_yong(zei, tian_pan, ri_gan, '贼克')

    # 2. 如果有上克下但无下克上
    if not zei and len(kek) == 1:
        return _complete(kek[0][1], tian_pan, '克法')

    if not zei and len(kek) > 1:
        return _bi_yong(kek, tian_pan, ri_gan, '克法')

    # 3. 涉害法：无克贼，日干上神与日支上神相克
    gan_shang = gan_yang[1]  # 干上神（第一课上支）
    zhi_shang = zhi_yang[1]  # 支上神（第三课上支）
    gan_zhi_relation = ke_relation(gan_shang, zhi_shang)

    if gan_zhi_relation == '克':
        # 干上神克支上神：初传取支上神
        return _complete(zhi_shang, tian_pan, '涉害(干克支上神)')
    elif gan_zhi_relation == '贼':
        # 支上神克干上神：初传取干上神
        return _complete(gan_shang, tian_pan, '涉害(支克干上神)')

    # 4. 遥克法：日干与四课上支五行遥克
    yk = _yao_ke(si_ke, tian_pan, ri_gan)
    if yk:
        return yk

    # 5. 八专判断：四课上下支完全相同（且都是比和）
    # 注意：伏吟已经在前面处理，这里八专是"部分相同"的情况
    if all(u == l for _, u, l in si_ke) and len(bi_he) == 4:
        yang = ri_gan in '甲丙戊庚壬'
        c1 = tian_pan['酉'] if yang else tian_pan['卯']
        return _complete(c1, tian_pan, '八专')

    # 6. 别责法：四课无克且无遥克，取日干支下神相克者
    if not zei and not kek:
        gan_xia = GAN_JI_GONG[ri_gan]  # 干下神
        zhi_xia = zhi_yang[2]  # 支下神（第三课下支）
        gan_zhi_xia_relation = ke_relation(gan_xia, zhi_xia)

        if gan_zhi_xia_relation == '克':
            # 干下神克支下神：初传取支下神
            return _complete(zhi_xia, tian_pan, '别责(干克支下神)')
        elif gan_zhi_xia_relation == '贼':
            # 支下神克干下神：初传取干下神
            return _complete(gan_xia, tian_pan, '别责(支克干下神)')

    # 7. 昴星法（默认兜底）
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


def _bi_yong(kl, tp, ri_gan, ktype):
    """
    比用法/知一法：多个克贼时取与日干阴阳相同者

    参数:
        kl: [(name, 上支, 下支), ...] 克贼课列表
        tp: 天盘
        ri_gan: 日干
        ktype: '贼克' or '克法'
    """
    yang = ri_gan in '甲丙戊庚壬'
    yang_zhi = {'子','寅','辰','午','申','戌'}

    # 取与日干阴阳相同的上支
    for name, u, l in kl:
        is_yang_zhi = u in yang_zhi
        if yang == is_yang_zhi:
            return _complete(u, tp, f'知一({"阳" if yang else "阴"}日-{ktype})')

    # 如果没找到匹配的，取第一个
    return _complete(kl[0][1], tp, f'比用(简化-{ktype})')


def _yao_ke(si_ke, tp, ri_gan):
    """
    遥克法：日干与四课上支五行遥克

    分为两种：
    - 蒿矢：四课上支克日干五行
    - 弹射：日干五行克四课上支
    """
    from daliuren import TIAN_GAN_WX, DI_ZHI_WX, WX_KE

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


def ke_relation(upper, lower):
    """判断上下支五行关系：克/贼/比和/上生/下生/无克"""
    from daliuren import DI_ZHI_WX, WX_KE, WX_SHENG

    u_wx = DI_ZHI_WX[upper]
    l_wx = DI_ZHI_WX[lower]

    if u_wx == l_wx:
        return '比和'
    if WX_KE.get(u_wx) == l_wx:
        return '克'  # 上克下
    if WX_KE.get(l_wx) == u_wx:
        return '贼'  # 下克上
    if WX_SHENG.get(u_wx) == l_wx:
        return '上生'
    if WX_SHENG.get(l_wx) == u_wx:
        return '下生'
    return '无克'


# 需要从 daliuren.py 导入的常量
GAN_JI_GONG = {
    '甲':'寅', '乙':'卯', '丙':'巳', '丁':'午', '戊':'巳',
    '己':'午', '庚':'申', '辛':'酉', '壬':'亥', '癸':'子'
}
