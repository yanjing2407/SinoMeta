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


logger = logging.getLogger("sinometa")


def multi_divination(
    event: str,
    year: int, month: int, day: int, hour: int, minute: int = 0,
    longitude: float = 120.0, latitude: float = 30.0,
    gender: str = '男',
    methods: list = None,
    liuyao_nums: tuple = None,
    meihua_nums: tuple = None,
    azimuth: float = None,
):
    """
    多术数同时起盘

    参数:
        event: 要预测的事件描述
        year~minute: 时间
        longitude, latitude: 经纬度
        gender: 性别
        methods: 要使用的术数列表，如 ['八字','奇门','六爻','梅花']
        liuyao_nums: 六爻数字起卦的两个数
        meihua_nums: 梅花数字起卦的两个数
        azimuth: 方位角（手机指南针）
    """
    if methods is None:
        methods = ['八字', '奇门', '梅花']

    results = {}

    if '八字' in methods:
        try:
            results['八字'] = bazi_pa_pan(year, month, day, hour, minute, longitude, gender)
        except Exception as e:
            results['八字'] = {'错误': str(e)}

    if '奇门' in methods:
        try:
            results['奇门遁甲'] = qimen_pa_pan(year, month, day, hour, minute, longitude)
        except Exception as e:
            results['奇门遁甲'] = {'错误': str(e)}

    if '六爻' in methods:
        try:
            if liuyao_nums:
                results['六爻'] = liuyao_pa_pan_num(
                    liuyao_nums[0], liuyao_nums[1],
                    year=year, month=month, day=day, hour=hour, minute=minute, longitude=longitude)
            else:
                results['六爻'] = liuyao_pa_pan(year, month, day, hour, minute, longitude)
        except Exception as e:
            results['六爻'] = {'错误': str(e)}

    if '梅花' in methods:
        try:
            if meihua_nums:
                mh_method = 'number'
            elif azimuth is not None:
                mh_method = 'fangwei'
            else:
                mh_method = 'time'
            results['梅花易数'] = meihua_pa_pan(
                year, month, day, hour, minute, longitude,
                method=mh_method,
                num1=meihua_nums[0] if meihua_nums else None,
                num2=meihua_nums[1] if meihua_nums else None,
                azimuth=azimuth)
        except Exception as e:
            results['梅花易数'] = {'错误': str(e)}

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


def generate_prompt(multi_result: dict) -> str:
    """
    将多术数排盘结果生成结构化Prompt
    供大模型进行综合解读
    """
    event = multi_result['事件']
    st = multi_result['时空坐标']
    results = multi_result['术数结果']

    # 将结果序列化为易读文本
    result_text = json.dumps(results, ensure_ascii=False, indent=2, default=str)

    prompt = f"""你是一位精通中国传统术数（八字、奇门遁甲、六爻、梅花易数）的大师。
请根据以下多维度排盘数据，综合分析事件的发展趋势。

# 分析规则：
1. 【八字视角】看命局基础与大运流年能量：判断求测人自身能量是否足以支撑此事。看日主强弱、用神方向。
2. 【奇门视角】看具体事情的时空态势：看用神落宫的星门神仪组合，判断天时地利人和。
3. 【六爻视角】看事情细节与动变：看用神旺衰、动爻变化、日月建对用神的影响。
4. 【梅花视角】看体用生克：看体卦用卦的五行关系，快速判断吉凶大势。
5. 【综合判断】多术数交叉验证：
   - 各术数结论一致时，置信度最高
   - 八字看长期底色，奇门看时空机遇，六爻看事件细节，梅花看大势方向
   - 若结论冲突，说明不同维度的信息差异，给出概率性判断

# 事件：
{event}

# 时空坐标：
时间：{st['时间']}
经度：{st['经度']}，纬度：{st['纬度']}
城市：{st['城市估算']}

# 排盘数据：
{result_text}

请按以下结构输出：
1. 【八字视角】：自身能量与时机分析（200字）
2. 【奇门视角】：事情环境、阻力与助力分析（200字）
3. 【六爻视角】：事情细节与动变分析（200字）
4. 【梅花视角】：体用生克大势判断（100字）
5. 【综合断语】：多术数交叉验证后的最终结论（200字）
6. 【行动建议】：基于以上分析的具体建议（100字）
"""
    return prompt


def generate_advice_prompt(multi_result: dict) -> str:
    """
    生成破局建议的Prompt，侧重于给出可操作的行动方案
    """
    event = multi_result['事件']
    st = multi_result['时空坐标']
    results = multi_result['术数结果']
    result_text = json.dumps(results, ensure_ascii=False, indent=2, default=str)

    prompt = f"""你是一位精通中国传统术数（八字、奇门遁甲、六爻、梅花易数）的实战派顾问。
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

1. 【核心瓶颈】：当前局面最大的阻碍是什么？（从术数角度精准定位，50字）
2. 【破局方向】：应该往哪个方向突破？哪些方面需要避让？（从五行生克、奇门方位等角度分析，150字）
3. 【时机把握】：何时行动最佳？何时宜守不宜攻？（从流年流月、奇门时盘角度分析，100字）
4. 【具体行动】：给出3-5条可立即执行的具体建议（每条30字以内，要务实可操作）
5. 【禁忌提醒】：当前千万不能做的事（3条以内，简明扼要）
6. 【心理调适】：从术数格局出发，给求测者一句定心的话（30字以内）
"""
    return prompt


def _build_llm_messages(multi_result: dict, prompt_type: str, system_prompt: str):
    if prompt_type == "advice":
        prompt = generate_advice_prompt(multi_result)
        system_msg = system_prompt or "你是一位实战派术数顾问，擅长从传统术数中提炼出可操作的行动方案，帮助求测者趋吉避凶、破局开运。"
    else:
        prompt = generate_prompt(multi_result)
        system_msg = system_prompt or "你是一位严谨、客观的传统术数综合研判AI，精通八字、奇门遁甲、六爻、梅花易数。"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
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


def _build_openai_payload(messages, model: str, stream: bool) -> bytes:
    return json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "stream": stream,
        },
        ensure_ascii=False,
    ).encode("utf-8")


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
    payload = _build_openai_payload(messages, model, stream=True)
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
    payload = _build_openai_payload(messages, model, stream=False)
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
                     provider_type: str = "openai_compatible"):
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

    返回:
        generator，每次 yield 一个 token 字符串
    """
    messages = _build_llm_messages(multi_result, prompt_type, system_prompt)
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
