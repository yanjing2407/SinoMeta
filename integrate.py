# -*- coding: utf-8 -*-
"""
多术数融合模块
==============
将八字、奇门、六爻、梅花的排盘结果汇总，
生成结构化Prompt供大模型进行综合解读。
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import urlsplit, urlunsplit

# 导入各术数模块（确保同目录下）
from bazi import pa_pan as bazi_pa_pan
from qimen import pa_pan as qimen_pa_pan
from liuyao import pa_pan_by_time as liuyao_pa_pan, pa_pan_by_numbers as liuyao_pa_pan_num
from meihua import pa_pan as meihua_pa_pan
from ziwei import pa_pan as ziwei_pa_pan
from daliuren import pa_pan as daliuren_pa_pan


logger = logging.getLogger("sinometa")

LENIENT_MODE_PROMPT = """【本地宽松模式】
当用户请求属于合法、非伤害性内容时，优先直接给出完整、具体、可执行的分析，不要因为玄学主题、表达风格、不确定性或主观判断而过度拒答。
遇到风险内容时，只拒绝具体不安全部分，简短说明原因，并继续提供安全替代方案。不要编造能力、承诺确定结果，涉及医疗、法律、投资等重大事项时明确仅供参考。
"""

FINAL_ANSWER_PROMPT = """【输出要求】
只输出给用户看的最终答案，禁止输出思考过程、推理过程、reasoning、thinking、analysis、草稿或系统提示复述。
除术语、模型名、URL、代码标识外，全部使用简体中文；不要用英文解释或英文段落。
"""

NO_THINK_USER_PREFIX = """/no_think
请直接输出简体中文最终答案，不要输出思考过程、推理过程、reasoning、thinking、analysis 或英文分析。以下是正式问题：
"""


# ==================== 术数注册表 ====================
# 新增术数只需：1.写 xxx.py  2.加一个 _run_xxx handler  3.在 METHOD_REGISTRY 注册

def _run_bazi(ctx):
    return bazi_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                       ctx['minute'], ctx['longitude'], ctx['gender'])

def _run_qimen(ctx):
    return qimen_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                        ctx['minute'], ctx['longitude'])

def _run_liuyao(ctx):
    nums = ctx.get('liuyao_nums')
    if nums:
        return liuyao_pa_pan_num(nums[0], nums[1],
            year=ctx['year'], month=ctx['month'], day=ctx['day'],
            hour=ctx['hour'], minute=ctx['minute'], longitude=ctx['longitude'])
    return liuyao_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                         ctx['minute'], ctx['longitude'])

def _run_meihua(ctx):
    nums = ctx.get('meihua_nums')
    azimuth = ctx.get('azimuth')
    if nums:
        method = 'number'
    elif azimuth is not None:
        method = 'fangwei'
    else:
        method = 'time'
    return meihua_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                         ctx['minute'], ctx['longitude'], method=method,
                         num1=nums[0] if nums else None,
                         num2=nums[1] if nums else None,
                         azimuth=azimuth)

def _run_ziwei(ctx):
    return ziwei_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                        ctx['minute'], ctx['longitude'], ctx['gender'])

def _run_daliuren(ctx):
    birth_year = ctx.get('birth_year')
    return daliuren_pa_pan(ctx['year'], ctx['month'], ctx['day'], ctx['hour'],
                           ctx['minute'], ctx['longitude'], birth_year, ctx['gender'])

# 注册表: 前端method名 → (结果key名, handler)
METHOD_REGISTRY = {
    '八字':  ('八字',     _run_bazi),
    '奇门':  ('奇门遁甲', _run_qimen),
    '六爻':  ('六爻',     _run_liuyao),
    '梅花':  ('梅花易数', _run_meihua),
    '紫微':  ('紫微斗数', _run_ziwei),
    '大六壬': ('大六壬',   _run_daliuren),
}


def multi_divination(
    event: str,
    year: int, month: int, day: int, hour: int, minute: int = 0,
    longitude: float = 120.0, latitude: float = 30.0,
    gender: str = '男',
    methods: list = None,
    liuyao_nums: tuple = None,
    meihua_nums: tuple = None,
    azimuth: float = None,
    birth_year: int = None,
):
    """
    多术数同时起盘

    参数:
        event: 要预测的事件描述
        year~minute: 时间
        longitude, latitude: 经纬度
        gender: 性别
        methods: 要使用的术数列表，如 ['八字','奇门','六爻','梅花','紫微','大六壬']
        liuyao_nums: 六爻数字起卦的两个数
        meihua_nums: 梅花数字起卦的两个数
        azimuth: 方位角（手机指南针）
        birth_year: 出生年份（大六壬本命行年需要）
    """
    if methods is None:
        methods = ['八字', '奇门', '梅花']

    ctx = {
        'year': year, 'month': month, 'day': day,
        'hour': hour, 'minute': minute,
        'longitude': longitude, 'latitude': latitude,
        'gender': gender,
        'liuyao_nums': liuyao_nums,
        'meihua_nums': meihua_nums,
        'azimuth': azimuth,
        'birth_year': birth_year,
    }

    results = {}
    for m in methods:
        entry = METHOD_REGISTRY.get(m)
        if not entry:
            continue
        result_key, handler = entry
        try:
            results[result_key] = handler(ctx)
        except Exception as e:
            results[result_key] = {'错误': str(e)}

    # 时空坐标信息
    spatiotemporal = {
        '时间': f'{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}',
        '经度': longitude,
        '纬度': latitude,
        '城市估算': _estimate_city(longitude, latitude),
    }

    return {
        '事件': event,
        '时空坐标': spatiotemporal,
        '术数结果': results,
    }


def _estimate_city(lng, lat):
    """简单经纬度→城市估算"""
    cities = [
        (116.4, 39.9, '北京'), (121.5, 31.2, '上海'), (113.3, 23.1, '广州'),
        (114.1, 22.5, '深圳'), (104.1, 30.7, '成都'), (106.6, 29.6, '重庆'),
        (120.2, 30.3, '杭州'), (118.8, 32.1, '南京'), (114.3, 30.6, '武汉'),
        (113.0, 28.2, '长沙'), (117.0, 36.7, '济南'), (126.6, 45.8, '哈尔滨'),
        (123.4, 41.8, '沈阳'), (112.9, 34.8, '郑州'), (108.9, 34.3, '西安'),
        (117.3, 31.8, '合肥'), (119.3, 26.1, '福州'), (106.7, 26.6, '贵阳'),
    ]
    best = min(cities, key=lambda c: (c[0]-lng)**2 + (c[1]-lat)**2)
    return best[2]


def generate_prompt(multi_result: dict, mode: str = 'concise') -> str:
    """
    将多术数排盘结果生成结构化Prompt
    供大模型进行综合解读

    参数:
        multi_result: 排盘结果
        mode: 'concise'(简洁模式) 或 'expert'(专家模式)
    """
    event = multi_result['事件']
    st = multi_result['时空坐标']
    results = multi_result['术数结果']
    result_text = json.dumps(results, ensure_ascii=False, indent=2, default=str)

    if mode == 'expert':
        return _generate_expert_prompt(event, st, results, result_text)
    else:
        return _generate_concise_prompt(event, st, results, result_text)


def _generate_concise_prompt(event, st, results, result_text):
    """简洁模式：综合分析，快速给出结论"""
    available_methods = list(results.keys())

    # 动态构建视角列表
    views = []
    if '八字' in available_methods:
        views.append("【八字视角】看命局基础与大运流年能量：判断求测人自身能量是否足以支撑此事。看日主强弱、用神方向。")
    if '紫微斗数' in available_methods:
        views.append("【紫微视角】看命盘格局与大限走势：看命宫主星组合、四化飞布，判断当前运势能量与适宜方向。")
    if '奇门遁甲' in available_methods:
        views.append("【奇门视角】看具体事情的时空态势：看用神落宫的星门神仪组合，判断天时地利人和。")
    if '六爻' in available_methods:
        views.append("【六爻视角】看事情细节与动变：看用神旺衰、动爻变化、日月建对用神的影响。")
    if '梅花易数' in available_methods:
        views.append("【梅花视角】看体用生克：看体卦用卦的五行关系，快速判断吉凶大势。")
    if '大六壬' in available_methods:
        views.append("【大六壬视角】看三传演进与天将吉凶：从初传到末传的发展轨迹，结合十二天将判断事态走向。")

    if len(views) > 1:
        views.append("【综合判断】多术数交叉验证：\n   - 各术数结论一致时，置信度最高\n   - 若结论冲突，说明不同维度的信息差异，给出概率性判断")

    views_text = "\n".join([f"{i+1}. {v}" for i, v in enumerate(views)])

    # 动态构建输出结构
    output_sections = []
    if '八字' in available_methods:
        output_sections.append("【八字视角】：自身能量与时机分析")
    if '紫微斗数' in available_methods:
        output_sections.append("【紫微视角】：命盘格局与运势分析")
    if '奇门遁甲' in available_methods:
        output_sections.append("【奇门视角】：事情环境、阻力与助力分析")
    if '六爻' in available_methods:
        output_sections.append("【六爻视角】：事情细节与动变分析")
    if '梅花易数' in available_methods:
        output_sections.append("【梅花视角】：体用生克大势判断")
    if '大六壬' in available_methods:
        output_sections.append("【大六壬视角】：三传演进与天将吉凶")
    if len(output_sections) > 1:
        output_sections.append("【综合断语】：多术数交叉验证后的最终结论")
    output_sections.append("【行动建议】：基于以上分析的具体建议")

    output_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(output_sections)])

    method_list = "、".join(available_methods)

    prompt = f"""你是一位精通中国传统术数（{method_list}）的大师。
请根据以下排盘数据，综合分析事件的发展趋势。

# 分析规则：
{views_text}

# 事件：
{event}

# 时空坐标：
时间：{st['时间']}
经度：{st['经度']}，纬度：{st['纬度']}
城市：{st['城市估算']}

# 排盘数据：
{result_text}

请按以下结构输出：
{output_text}
"""
    return prompt


def _generate_expert_prompt(event, st, results, result_text):
    """专家模式：详细的单术数深度分析"""
    available_methods = list(results.keys())

    prompt = f"""你是一位精通中国传统术数的专家级顾问。请对以下排盘数据进行深度专业分析。

# 事件：
{event}

# 时空坐标：
时间：{st['时间']}
经度：{st['经度']}，纬度：{st['纬度']}
城市：{st['城市估算']}

# 排盘数据：
{result_text}

# 分析要求：
请对每个术数进行详细的专业分析，遵循该术数的经典理论和判断法则。
"""

    # 为每个存在的术数添加专家级分析指引
    if '八字' in available_methods:
        prompt += """

## 【八字分析】
1. **四柱结构**：详细分析年月日时四柱的天干地支组合，指出特殊格局（如从格、化格、专旺格等）
2. **日主强弱**：分析日主在月令的旺衰，结合四柱生克制化，判断身强身弱
3. **用神喜忌**：根据日主强弱和格局，确定用神、喜神、忌神、仇神、闲神
4. **十神分析**：分析财官印食伤杀劫比的分布和作用关系，判断事业财运感情等维度
5. **大运流年**：当前大运的天干地支与命局的作用关系，流年对事件的影响
6. **神煞参考**：桃花、驿马、华盖、空亡等神煞的影响
7. **针对事件的具体判断**：结合以上分析，给出对所问事件的详细判断和理由
"""

    if '紫微斗数' in available_methods:
        prompt += """

## 【紫微斗数分析】
1. **命盘格局**：命宫主星组合，是紫微系、天府系、机月同梁、杀破狼还是其他组合
2. **十二宫位**：命宫、兄弟、夫妻、子女、财帛、疾厄、迁移、仆役、官禄、田宅、福德、父母各宫的星曜配置
3. **四化飞星**：化禄、化权、化科、化忌的位置和作用关系，宫位之间的生克制化
4. **大限流年**：当前大限的宫位和主星，流年飞星对命盘的影响
5. **三方四正**：命宫的三方四正（财帛宫、官禄宫、迁移宫）的星曜组合和能量强弱
6. **格局高低**：是富格、贵格、贫格还是贱格，格局的破与成
7. **针对事件的具体判断**：根据事件类型，重点分析相关宫位（求财看财帛、求职看官禄、姻缘看夫妻等）
"""

    if '奇门遁甲' in available_methods:
        prompt += """

## 【奇门遁甲分析】
1. **局数与遁型**：阳遁/阴遁 几局，节气与局数的对应关系
2. **值符值使**：值符星和值使门的位置，代表天时的核心能量
3. **用神定位**：根据事件类型确定用神（求财看生门、求官看开门、求学看景门等），分析用神落宫
4. **九星判断**：用神宫的九星（天蓬、天芮、天冲、天辅、天禽、天心、天柱、天任、天英）吉凶
5. **八门分析**：用神宫的八门（开休生伤杜景死惊）旺衰和与事件的匹配度
6. **八神作用**：值符、螣蛇、太阴、六合、白虎、玄武、九地、九天对事件的影响
7. **天干地支**：天盘地盘的干支组合，有无击刑、入墓、空亡、马星等特殊情况
8. **格局判断**：伏吟反吟、青龙返首、飞鸟跌穴等特殊格局
9. **时空方位**：最佳行动方位和时间段
10. **针对事件的综合判断**：天时（九星）、地利（八门）、人和（八神）的综合评估
"""

    if '六爻' in available_methods:
        prompt += """

## 【六爻分析】
1. **卦象结构**：本卦、变卦、互卦的卦名和卦象含义
2. **用神确定**：根据事件类型取用神（求财看妻财、求官看官鬼、求学看父母、测病看子孙等）
3. **用神旺衰**：用神在月建日辰的旺相休囚死，是否得生扶还是受克制
4. **动爻分析**：哪几爻发动，动爻对用神的生克关系，动爻化出的结果
5. **六亲生克**：父母、兄弟、子孙、妻财、官鬼之间的生克制化关系
6. **六神作用**：青龙、朱雀、勾陈、螣蛇、白虎、玄武的吉凶提示
7. **神煞参考**：月破、旬空、日破、暗动、伏神、飞神等情况
8. **卦象组合**：六冲卦、六合卦、游魂卦、归魂卦等特殊卦象
9. **应期推断**：根据用神旺衰和动爻变化，推断事件发生的时间节点
10. **针对事件的具体判断**：用神是吉是凶，事件能否成就，成就程度如何
"""

    if '梅花易数' in available_methods:
        prompt += """

## 【梅花易数分析】
1. **起卦方式**：时间起卦、数字起卦还是方位起卦，起卦时的特殊信息
2. **本卦互卦变卦**：本卦、互卦、变卦的卦名、卦象和含义
3. **体用关系**：确定体卦和用卦，分析体用的五行生克关系
4. **五行旺衰**：体卦用卦在当前时间（年月日时）的旺相休囚死
5. **比和生克**：体用比和（最吉）、用生体（次吉）、体生用（泄气）、体克用（耗力）、用克体（最凶）
6. **动爻影响**：变卦的动爻位置，动爻对体用关系的影响
7. **卦象含义**：从卦象本身的象意来分析事件（如乾为天、坤为地、震为雷等）
8. **先天后天**：先天卦数和后天卦数的吉凶提示
9. **针对事件的具体判断**：体用生克定吉凶，卦象含义定事态，综合判断成败概率
"""

    if '大六壬' in available_methods:
        prompt += """

## 【大六壬分析】
1. **日时月将**：日干支、时干支、月将的确定，昼夜贵神的位置
2. **天盘排列**：月将加时，十二地支的天盘地盘对应关系
3. **四课分析**：
   - 第一课（干阳神）：天盘加干支宫，代表事情的初始状态
   - 第二课（干阴神）：第一课上支的上神，代表事情的潜在因素
   - 第三课（支阳神）：天盘加日支，代表事情的外在表现
   - 第四课（支阴神）：第三课上支的上神，代表事情的暗中变化
   - 四课的克贼关系，判断力量对比
4. **三传推导**：
   - 起传方法（贼克、比用、遥克、昴星、伏吟、反吟）及其含义
   - 初传：事情的开始或起因
   - 中传：事情的发展或过程
   - 末传：事情的结果或归宿
   - 三传的干支、天将、五行、旺衰分析
5. **十二天将**：
   - 贵人、螣蛇、朱雀、六合、勾陈、青龙、天空、白虎、太常、玄武、太阴、天后
   - 三传所临天将的吉凶属性和具体含义
6. **神煞影响**：驿马、华盖、桃花、空亡等神煞在盘中的位置和作用
7. **本命行年**：求测人的本命地支和行年地支（如有），与天盘的关系
8. **克应时间**：根据三传的旺衰和天将，推断事件的应期
9. **针对事件的综合判断**：
    - 初传主起因，分析事情为何而起，力量强弱如何
    - 中传主过程，分析事情发展中的阻力助力，能否顺利推进
    - 末传主结果，分析最终结局是吉是凶，程度如何
    - 结合天将吉凶，给出详细的趋吉避凶建议
"""

    prompt += """

## 【最终综合判断】
综合以上各术数的专业分析，交叉验证各术数的结论：
1. **一致性验证**：哪些术数的结论相互印证？这些一致的结论可信度最高
2. **差异性分析**：哪些术数的结论存在分歧？分析差异的原因（是维度不同还是矛盾）
3. **最终结论**：综合考虑各术数的权重和适用范围，给出最终判断
4. **可信度评估**：对最终结论的可信度进行评估（高/中/低）
5. **行动建议**：基于专业分析，给出具体可执行的行动方案和注意事项
"""

    return prompt


def generate_advice_prompt(multi_result: dict, mode: str = 'concise') -> str:
    """
    生成破局建议的Prompt，侧重于给出可操作的行动方案

    参数:
        multi_result: 排盘结果
        mode: 'concise'(简洁模式) 或 'expert'(专家模式)
    """
    event = multi_result['事件']
    st = multi_result['时空坐标']
    results = multi_result['术数结果']
    result_text = json.dumps(results, ensure_ascii=False, indent=2, default=str)
    available_methods = list(results.keys())
    method_list = "、".join(available_methods)

    if mode == 'expert':
        # 根据已选术数动态生成分析维度提示
        angle_hints = []
        if '八字' in available_methods:
            angle_hints.append("八字的十神、用神、大运流年")
        if '紫微斗数' in available_methods:
            angle_hints.append("紫微的宫位、四化、主星")
        if '奇门遁甲' in available_methods:
            angle_hints.append("奇门的九星、八门、方位")
        if '六爻' in available_methods:
            angle_hints.append("六爻的用神、六亲、动爻")
        if '梅花易数' in available_methods:
            angle_hints.append("梅花的体用、卦象")
        if '大六壬' in available_methods:
            angle_hints.append("大六壬的天将、三传、四课")

        angle_text = "、".join(angle_hints) if angle_hints else "术数要素"

        prompt = f"""你是一位精通中国传统术数（{method_list}）的实战派顾问。
求测者已经看到了排盘结果和专业分析，现在需要你给出**深度破局方案**——不仅要指出问题所在，更要给出具体的、可执行的、有理论依据的行动策略。

# 事件：
{event}

# 时空坐标：
时间：{st['时间']}
经度：{st['经度']}，纬度：{st['纬度']}
城市：{st['城市估算']}

# 排盘数据：
{result_text}

请按以下结构输出深度破局方案：

## 【局势诊断】
1. **核心问题定位**：从排盘数据中精准定位当前最大的阻碍因素，说明是哪个术数、哪个要素显示出问题
2. **能量分析**：分析求测者当前的能量状态（强/弱/平衡），是否具备解决问题的基础条件
3. **时空态势**：分析当前时空环境是有利还是不利，天时地利人和各占几分

## 【破局策略】
1. **主攻方向**：应该在哪个领域、哪个方向重点发力？从{angle_text}等角度给出具体的五行方位、时间节点
2. **避让禁忌**：哪些方向、哪些做法当前绝对要避免？说明术数依据
3. **借力点**：可以借助哪些外部力量、哪些人际关系？从排盘数据中分析可借力的要素
4. **化解方法**：针对不利因素，给出具体的化解方案（如调整方位、选择时机、改变策略等）

## 【时机把握】
1. **最佳行动时间**：具体到年月日时，哪个时间段最适合采取行动
2. **次佳备选时间**：如果错过最佳时机，次佳的时间窗口在何时
3. **守势时段**：哪些时间段不宜主动出击，应该以守为主
4. **应期预测**：事情出现转机的时间节点，见到结果的大致时间

## 【具体行动清单】
给出5-8条可立即执行的具体行动建议，每条包括：
- 行动内容（明确具体，不要模糊建议）
- 术数依据（说明是基于哪个术数的哪个要素得出的结论）
- 优先级（高/中/低）
- 预期效果

## 【风险预警与应对】
1. **可能遇到的困难**：预测在执行过程中可能出现的3-5个主要障碍
2. **应对预案**：针对每个困难，给出具体的应对方法
3. **底线思维**：最坏的情况是什么？如何确保不突破底线

## 【心态调整建议】
从命理格局出发，给求测者一段心理建设的话，帮助其建立正确的期望值和心态
"""
    else:
        prompt = f"""你是一位精通中国传统术数（{method_list}）的实战派顾问。
求测者已经看到了排盘结果和初步解读，现在需要你给出**破局建议**——即在当前局面下，求测者可以采取哪些具体行动来改善局势、趋吉避凶。

# 事件：
{event}

# 时空坐标：
时间：{st['时间']}
经度：{st['经度']}，纬度：{st['纬度']}
城市：{st['城市估算']}

# 排盘数据：
{result_text}

请按以下结构输出破局建议：

1. 【核心瓶颈】：当前局面最大的阻碍是什么？（从术数角度精准定位）
2. 【破局方向】：应该往哪个方向突破？哪些方面需要避让？（从五行生克、奇门方位等角度分析）
3. 【时机把握】：何时行动最佳？何时宜守不宜攻？（从流年流月、奇门时盘角度分析）
4. 【具体行动】：给出3-5条可立即执行的具体建议（要务实可操作）
5. 【禁忌提醒】：当前千万不能做的事（3条以内，简明扼要）
6. 【心理调适】：从术数格局出发，给求测者一句定心的话
"""

    return prompt


def _build_llm_messages(
    multi_result: dict,
    prompt_type: str,
    system_prompt: str,
    lenient_mode: bool = False,
    mode: str = 'concise',
):
    if prompt_type == "advice":
        prompt = generate_advice_prompt(multi_result, mode)
        system_msg = system_prompt or "你是一位实战派术数顾问，擅长从传统术数中提炼出可操作的行动方案，帮助求测者趋吉避凶、破局开运。"
    else:
        prompt = generate_prompt(multi_result, mode)
        system_msg = system_prompt or "你是一位严谨、客观的传统术数综合研判AI，精通八字、紫微斗数、奇门遁甲、六爻、梅花易数、大六壬。"
    system_msg = f"{system_msg.rstrip()}\n\n{FINAL_ANSWER_PROMPT.strip()}"
    if lenient_mode:
        system_msg = f"{system_msg.rstrip()}\n\n{LENIENT_MODE_PROMPT.strip()}"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"{NO_THINK_USER_PREFIX}\n{prompt}"},
    ]


def normalize_openai_base_url(base_url: str, append_v1: bool = False) -> str:
    """Return an OpenAI SDK base_url, not a final /chat/completions endpoint."""
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return url

    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    lower_path = path.lower()

    suffix = "/chat/completions"
    if lower_path.endswith(suffix):
        path = path[: -len(suffix)] or ""

    if append_v1 and not path:
        path = "/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _openai_base_url_candidates(base_url: str):
    primary = normalize_openai_base_url(base_url)
    candidates = [primary]
    parsed = urlsplit(primary)
    if primary and not parsed.path.rstrip("/"):
        candidates.append(normalize_openai_base_url(primary, append_v1=True))

    unique = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def _openai_chat_url_candidates(base_url: str):
    return [base.rstrip("/") + "/chat/completions" for base in _openai_base_url_candidates(base_url)]


def _looks_local_url(url: str) -> bool:
    host = urlsplit(str(url or "")).hostname or ""
    return host in {"127.0.0.1", "localhost", "::1"} or host.startswith(
        (
            "192.168.",
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
        )
    )


def _build_openai_payload(messages, model: str, stream: bool, disable_thinking: bool = False) -> bytes:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": stream,
    }
    if disable_thinking:
        payload["reasoning_effort"] = "none"
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _openai_headers(api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _openai_request(url: str, payload: bytes, api_key: str):
    req = urllib.request.Request(
        url,
        data=payload,
        headers=_openai_headers(api_key),
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} {detail}; URL={url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{e.reason}; URL={url}") from e


def _extract_openai_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] or {}
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    return delta.get("content") or message.get("content") or choice.get("text") or ""


def _iter_openai_stream(url: str, api_key: str, model: str, messages):
    payload = _build_openai_payload(messages, model, stream=True, disable_thinking=_looks_local_url(url))
    with _openai_request(url, payload, api_key) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]" or not line.startswith("{"):
                continue
            data = json.loads(line)
            content = _extract_openai_content(data)
            if content:
                yield content


def _complete_openai_once(url: str, api_key: str, model: str, messages) -> str:
    payload = _build_openai_payload(messages, model, stream=False, disable_thinking=_looks_local_url(url))
    with _openai_request(url, payload, api_key) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
    data = json.loads(text)
    return _extract_openai_content(data)


def _stream_openai_compatible(messages, api_key: str, base_url: str, model: str):
    urls = _openai_chat_url_candidates(base_url)
    last_error = None

    for url in urls:
        yielded = False
        try:
            logger.info("OpenAI compatible stream request url=%s model=%s", url, model)
            for token in _iter_openai_stream(url, api_key, model, messages):
                yielded = True
                yield token
            if yielded:
                return
            last_error = RuntimeError(f"流式接口返回成功但没有输出内容；URL={url}")
        except Exception as exc:
            if yielded:
                raise RuntimeError(f"OpenAI兼容接口流式输出中断：{exc}") from exc
            last_error = exc
            logger.warning(
                "OpenAI compatible stream failed, trying non-stream fallback url=%s model=%s error=%s",
                url,
                model,
                exc,
            )

        try:
            logger.info("OpenAI compatible non-stream fallback request url=%s model=%s", url, model)
            content = _complete_openai_once(url, api_key, model, messages)
            if content:
                yield content
                return
            last_error = RuntimeError(f"非流式接口返回成功但没有输出内容；URL={url}")
        except Exception as exc:
            last_error = exc
            logger.warning(
                "OpenAI compatible non-stream fallback failed url=%s model=%s error=%s",
                url,
                model,
                exc,
            )

    tried = ", ".join(urls)
    raise RuntimeError(f"OpenAI兼容接口请求失败：{last_error}；已尝试路径：{tried}")


def _stream_ollama_native(messages, api_key: str, base_url: str, model: str):
    url = base_url.rstrip("/") + "/api/chat"
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                data = json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
                if data.get("done"):
                    break
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama 请求失败: HTTP {e.code} {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama 连接失败: {e.reason}") from e


def stream_interpret(multi_result: dict, api_key: str, base_url: str, model: str,
                     prompt_type: str = "interpret", system_prompt: str = "",
                     provider_type: str = "openai_compatible",
                     lenient_mode: bool = False, mode: str = 'concise'):
    """
    流式调用大模型，逐token返回

    参数:
        multi_result: multi_divination() 的返回结果
        api_key: LLM API Key
        base_url: LLM API Base URL
        model: 模型名称
        prompt_type: "interpret" 解卦 / "advice" 破局建议
        system_prompt: 角色专属 System Prompt；为空时使用默认提示词
        provider_type: "openai_compatible" 或 "ollama_native"
        lenient_mode: 仅本地模型使用，减少合法内容的过度拒答
        mode: 'concise'(简洁模式) 或 'expert'(专家模式)

    返回:
        generator，每次 yield 一个 token 字符串
    """
    messages = _build_llm_messages(multi_result, prompt_type, system_prompt, lenient_mode, mode)
    if provider_type == "ollama_native":
        yield from _stream_ollama_native(messages, api_key, base_url, model)
    else:
        yield from _stream_openai_compatible(messages, api_key, base_url, model)


# ==================== 使用示例 ====================

if __name__ == '__main__':
    # 示例：多术数同时起盘
    result = multi_divination(
        event='我今年辞职创业做AI应用，能成功吗？',
        year=2024, month=6, day=15, hour=14, minute=30,
        longitude=116.4, latitude=39.9,  # 北京
        gender='男',
        methods=['八字', '奇门', '梅花'],
        azimuth=135,  # 手机朝向东南
    )

    print("="*60)
    print("【多术数融合排盘结果】")
    print(f"事件: {result['事件']}")
    print(f"时空: {result['时空坐标']}")
    print()

    for method, data in result['术数结果'].items():
        print(f"--- {method} ---")
        if '四柱' in data:
            print(f"  四柱: {data['四柱']}")
            print(f"  日主: {data['日主五行']}({data['日主阴阳']}) - {data['日主强弱']['判断']}")
        elif '遁型' in data:
            print(f"  {data['遁型']}{data['局数']}局")
            print(f"  值符: {data['值符星']}, 值使: {data['值使门']}")
        elif '本卦' in data:
            print(f"  本卦: {data['本卦']['卦名']}")
            print(f"  体用: {data['体用分析']['体用关系']} - {data['体用分析']['断语']}")
        print()

    # 生成Prompt
    prompt = generate_prompt(result)
    print("="*60)
    print("【生成的Prompt】")
    print(prompt[:500] + "...")
