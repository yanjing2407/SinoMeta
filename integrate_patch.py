# -*- coding: utf-8 -*-
"""
历史命例检测函数补丁
"""

def determine_subject_status(multi_result: dict, subject_status: str = None) -> str:
    """
    判断命主状态：在世/历史命例/仅看格局

    自动判断规则：
    - birth_year 距今超过 120 年：历史命例
    - 当前年龄超过 110 岁：历史命例
    - 用户明确指定：使用用户指定值
    """
    if subject_status and subject_status != 'auto':
        return subject_status

    # 尝试从术数结果中提取出生年份
    birth_year = None
    results = multi_result.get('术数结果', {})

    if '八字' in results:
        try:
            year_pillar = results['八字'].get('四柱', {}).get('年柱', '')
            # 八字结果中可能包含公历年份信息
            birth_year = results['八字'].get('公历', {}).get('year')
        except:
            pass

    if '紫微斗数' in results:
        try:
            birth_year = results['紫微斗数'].get('出生年份')
        except:
            pass

    # 从时空坐标中提取出生时间
    st = multi_result.get('时空坐标', {})
    birth_time_str = st.get('出生时间')
    if birth_time_str:
        try:
            birth_year = int(birth_time_str.split('-')[0])
        except:
            pass

    if birth_year:
        from datetime import datetime
        current_year = datetime.now().year
        age = current_year - birth_year

        # 超过 120 年或年龄超过 110 岁，判定为历史命例
        if current_year - birth_year > 120 or age > 110:
            return 'historical'

    # 默认为在世人物
    return 'living'


# 测试
if __name__ == '__main__':
    # 测试历史命例
    test_historical = {
        '事件': '测试',
        '时空坐标': {
            '起卦时间': '2026-01-01 10:00',
            '出生时间': '1893-12-26 08:00',
        },
        '术数结果': {}
    }

    result = determine_subject_status(test_historical)
    print(f'Historical test: {result}')
    assert result == 'historical', f'Expected historical, got {result}'

    # 测试在世人物
    test_living = {
        '事件': '测试',
        '时空坐标': {
            '起卦时间': '2026-01-01 10:00',
            '出生时间': '1990-01-01 10:00',
        },
        '术数结果': {}
    }

    result = determine_subject_status(test_living)
    print(f'Living test: {result}')
    assert result == 'living', f'Expected living, got {result}'

    print('All tests passed!')
