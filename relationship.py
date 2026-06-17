# -*- coding: utf-8 -*-
"""Relationship compound chart orchestration.

This module builds a structured relationship chart from two natal subjects plus
one current divination time.  The relationship recognizer intentionally uses a
weak-description policy: when the user has not declared the real relation, it
describes relationship signals instead of asserting a social/legal identity.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bazi import get_shi_shen, pa_pan as bazi_pa_pan
from calendar_utils import TIAN_GAN_WX, dz_chong, dz_hai, dz_liu_he, wx_relation
from daliuren import pa_pan as daliuren_pa_pan
from integrate import (
    FINAL_ANSWER_PROMPT,
    LENIENT_MODE_PROMPT,
    NO_THINK_USER_PREFIX,
    _stream_ollama_native,
    _stream_openai_compatible,
)
from hexagram_semantics import get_hexagram_semantics, summarize_hexagram_path
from liuyao import GUA_64, pa_pan_by_numbers as liuyao_pa_pan_num, pa_pan_by_time as liuyao_pa_pan
from meihua import (
    XT2GUA,
    analyze_ti_yong,
    get_bian_gua,
    get_hu_gua,
    gua_to_yao,
    pa_pan as meihua_pa_pan,
)
from qimen import pa_pan as qimen_pa_pan
from ziwei import pa_pan as ziwei_pa_pan


logger = logging.getLogger("sinometa")


GAN_HE = {
    frozenset(("甲", "己")): "甲己合土",
    frozenset(("乙", "庚")): "乙庚合金",
    frozenset(("丙", "辛")): "丙辛合水",
    frozenset(("丁", "壬")): "丁壬合木",
    frozenset(("戊", "癸")): "戊癸合火",
}

SAN_HE_HALF = {
    frozenset(("申", "子")): "申子半合水局",
    frozenset(("子", "辰")): "子辰半合水局",
    frozenset(("亥", "卯")): "亥卯半合木局",
    frozenset(("卯", "未")): "卯未半合木局",
    frozenset(("寅", "午")): "寅午半合火局",
    frozenset(("午", "戌")): "午戌半合火局",
    frozenset(("巳", "酉")): "巳酉半合金局",
    frozenset(("酉", "丑")): "酉丑半合金局",
}

XING_GROUPS = [
    {"寅", "巳", "申"},
    {"丑", "未", "戌"},
    {"子", "卯"},
]

HIGH_RISK_KEYWORDS = {
    "亲缘事实": ["亲生", "血缘", "亲子", "DNA", "dna", "鉴定"],
    "婚恋重大决定": ["离婚", "出轨", "外遇", "复合", "婚姻破裂"],
    "医疗健康": ["手术", "癌", "病", "死亡", "生死", "治疗", "医院"],
    "法律纠纷": ["官司", "诉讼", "犯罪", "坐牢", "判刑", "报警"],
    "投资财务": ["投资", "借钱", "贷款", "破产", "债务"],
}

RELATION_TAXONOMY = {
    "血缘/亲属": [
        "父子", "父女", "母子", "母女", "兄弟", "姐妹", "兄妹", "姐弟",
        "祖孙", "外祖孙", "叔侄", "姑侄", "舅甥", "姨甥", "伯侄",
        "堂表亲", "外甥/外甥女", "侄子/侄女", "继亲", "养亲", "干亲",
    ],
    "婚恋/姻亲": [
        "夫妻", "前夫前妻", "未婚夫妻", "恋人", "同居伴侣", "情人",
        "暧昧对象", "前任", "第三者", "情敌", "岳父母", "婆媳",
        "翁婿", "妯娌", "连襟", "姐夫妹夫", "嫂子弟媳", "儿媳", "女婿",
    ],
    "朋友/同辈": [
        "普通朋友", "密友", "发小", "同学", "同事", "同圈层", "网友",
        "搭子", "旧识", "贵人", "熟人", "泛泛之交",
    ],
    "权责/利益": [
        "合作伙伴", "合伙人", "上下级", "老板员工", "客户供应商",
        "债主债务人", "房东租客", "买卖双方", "投资关系", "委托代理",
        "师徒", "老师学生", "医生病人", "律师客户", "项目伙伴",
    ],
    "冲突/纠葛": [
        "竞争对手", "仇怨对象", "情敌", "诉讼对方", "债务纠纷方",
        "利益冲突方", "消耗关系", "控制关系", "被拖累关系",
    ],
    "照护/依赖": [
        "照顾者/被照顾者", "监护/被监护", "长辈晚辈", "恩人受恩者",
        "依赖关系", "救助关系",
    ],
}


def _taxonomy_summary() -> List[Dict[str, Any]]:
    return [{"大类": category, "细类": values} for category, values in RELATION_TAXONOMY.items()]


def _ranking_strength(ranking: List[Dict[str, Any]], name_part: str) -> float:
    for item in ranking:
        if name_part in item.get("类型", ""):
            return float(item.get("强度", 0.0))
    return 0.0


def _relationship_context_text(payload_or_text: Any) -> str:
    if isinstance(payload_or_text, dict):
        return str(payload_or_text.get("context") or payload_or_text.get("补充信息") or payload_or_text.get("additional_context") or "").strip()
    return str(payload_or_text or "").strip()


def _combined_question_text(question: str, context: str = "") -> str:
    return f"{question or ''}\n{context or ''}".strip()


def _demographic_prior(first: Dict[str, Any], second: Dict[str, Any], context: str = "") -> Dict[str, Any]:
    age_diff = abs((first["出生时间"] - second["出生时间"]).days) / 365.2425
    same_gender = first["性别"] == second["性别"]
    text = context or ""
    context_conflicts = _gendered_relation_conflicts(first, second, text)
    parent_child_words = ["父子", "父女", "母子", "母女", "儿子", "女儿", "孩子", "亲子", "血缘", "父亲", "母亲", "爸爸", "妈妈"]
    partner_words = ["夫妻", "婚恋", "婚姻", "姻缘", "老婆", "老公", "对象", "恋人", "情侣", "男友", "女友", "情人", "暧昧", "伴侣"]
    care_words = ["照顾", "抚养", "监护", "长辈", "晚辈", "赡养", "养育"]
    declared_parent_child = any(word in text for word in parent_child_words) and not context_conflicts
    declared_partner = any(word in text for word in partner_words)
    declared_care = any(word in text for word in care_words)
    long_gap = age_diff >= 18
    generation_gap = age_diff >= 24
    partner_allowed = declared_partner or (not same_gender and age_diff < 18)
    partner_suppressed = not declared_partner and (same_gender or long_gap)
    care_boost = declared_parent_child or declared_care or long_gap
    notes = []
    if generation_gap:
        notes.append(f"年龄差约{age_diff:.1f}年，强烈提示长幼/亲子/照护语境，婚恋暧昧默认降权。")
    elif long_gap:
        notes.append(f"年龄差约{age_diff:.1f}年，优先考虑长幼、照护、权责或师徒上下级语境。")
    elif same_gender:
        notes.append("双方同性；未声明婚恋时，妻财/官鬼不优先翻译为恋爱对象。")
    if declared_parent_child:
        notes.append("补充信息已声明亲子/父母子女语境。")
    if context_conflicts:
        notes.extend(context_conflicts)
    if declared_partner:
        notes.append("补充信息已声明伴侣/婚恋语境。")
    return {
        "年龄差": round(age_diff, 1),
        "同性": same_gender,
        "大年龄差": long_gap,
        "代际年龄差": generation_gap,
        "声明亲子": declared_parent_child,
        "声明伴侣": declared_partner,
        "声明照护": declared_care,
        "允许婚恋优先": partner_allowed,
        "压制婚恋暧昧": partner_suppressed,
        "提升照护长幼": care_boost,
        "上下文冲突": context_conflicts,
        "说明": notes,
    }


def _prior_suppresses_partner(prior: Optional[Dict[str, Any]]) -> bool:
    return bool(prior and prior.get("压制婚恋暧昧") and not prior.get("声明伴侣"))


def _gendered_relation_conflicts(first: Dict[str, Any], second: Dict[str, Any], text: str) -> List[str]:
    text = text or ""
    if not text:
        return []
    _, younger = (first, second) if first["出生时间"] < second["出生时间"] else (second, first)
    younger_gender = younger["性别"]
    conflicts = []
    if any(word in text for word in ["儿子", "父子", "母子"]) and younger_gender != "男":
        conflicts.append("补充信息提到儿子/父子/母子，但较年轻命主为女，疑似上一盘上下文残留")
    if any(word in text for word in ["女儿", "父女", "母女"]) and younger_gender != "女":
        conflicts.append("补充信息提到女儿/父女/母女，但较年轻命主为男，疑似上一盘上下文残留")
    return conflicts
RELATION_TASK_PROFILES = {
    "relationship_identity": {
        "名称": "关系身份/事实类",
        "说明": "用户在问两人是否已经形成某种现实关系或事实状态。",
        "语义主轴": ["事实", "状态", "边界"],
        "time_axis": "present",
        "uncertainty": "medium",
        "weights": {"六爻": 34, "奇门": 18, "大六壬": 18, "八字": 10, "紫微": 10, "关系复合卦": 10, "梅花": 0},
    },
    "relationship_definition": {
        "名称": "关系定义类",
        "说明": "用户在问两人的关系性质，需要把多源信息压缩成关系画像。",
        "语义主轴": ["性质", "状态", "结构"],
        "time_axis": "present",
        "uncertainty": "medium",
        "weights": {"紫微": 22, "八字": 20, "六爻": 20, "奇门": 13, "关系复合卦": 12, "梅花": 8, "大六壬": 5},
    },
    "relationship_state": {
        "名称": "当前状态类",
        "说明": "用户在问现在关系如何、对方态度或当前互动状态。",
        "语义主轴": ["状态", "行为", "趋势"],
        "time_axis": "present",
        "uncertainty": "medium",
        "weights": {"奇门": 28, "六爻": 24, "大六壬": 22, "梅花": 10, "关系复合卦": 6, "紫微": 5, "八字": 5},
    },
    "relationship_future": {
        "名称": "发展趋势类",
        "说明": "用户在问未来能否发展、复合、结婚或关系走向。",
        "语义主轴": ["趋势", "状态", "结构"],
        "time_axis": "future",
        "uncertainty": "high",
        "weights": {"梅花": 26, "奇门": 22, "六爻": 18, "大六壬": 14, "关系复合卦": 10, "紫微": 5, "八字": 5},
    },
    "relationship_timing": {
        "名称": "时间应期类",
        "说明": "用户在问何时发生、何时复合、何时出现结果。",
        "语义主轴": ["时间", "趋势", "状态"],
        "time_axis": "future",
        "uncertainty": "high",
        "weights": {"大六壬": 28, "奇门": 23, "六爻": 23, "梅花": 10, "关系复合卦": 6, "八字": 5, "紫微": 5},
    },
    "relationship_cause": {
        "名称": "因果解释类",
        "说明": "用户在问为什么会这样、为什么反复、问题根源在哪里。",
        "语义主轴": ["因果", "结构", "过程"],
        "time_axis": "past_to_present",
        "uncertainty": "medium",
        "weights": {"大六壬": 26, "八字": 22, "紫微": 18, "关系复合卦": 12, "奇门": 10, "六爻": 8, "梅花": 4},
    },
}


def _has_any(text: str, words: List[str]) -> bool:
    lowered = text.lower()
    return any(word in text or word.lower() in lowered for word in words)


def _classify_relationship_task(question: str, declared_relation: str) -> Dict[str, Any]:
    text = question or ""
    evidence = []
    primary = "relationship_definition"

    if _has_any(text, ["什么时候", "何时", "多久", "哪年", "哪月", "哪天", "几时", "应期"]):
        primary = "relationship_timing"
        evidence.append("问题包含时间/应期词")
    elif _has_any(text, ["为什么", "为何", "原因", "根源", "怎么会", "总是", "反复", "分分合合"]):
        primary = "relationship_cause"
        evidence.append("问题包含因果解释词")
    elif _has_any(text, ["会不会", "能不能", "能否", "是否会", "未来", "以后", "发展", "复合", "结婚", "在一起", "走下去"]):
        primary = "relationship_future"
        evidence.append("问题包含未来/发展趋势词")
    elif _has_any(text, ["现在", "目前", "当下", "态度", "想法", "感觉", "怎么样", "如何", "还爱", "在想"]):
        primary = "relationship_state"
        evidence.append("问题包含当前状态或心理状态词")
    elif _has_any(text, ["是不是", "是否", "有没有", "夫妻", "情侣", "情人", "亲子", "父子", "母女", "合作", "同事", "朋友"]):
        primary = "relationship_identity"
        evidence.append("问题包含身份/事实判断词")
    elif _has_any(text, ["什么关系", "关系是什么", "算算关系", "关系性质"]):
        primary = "relationship_definition"
        evidence.append("问题包含开放关系定义词")
    else:
        evidence.append("未命中特定关系子类，按开放关系定义处理")

    profile = RELATION_TASK_PROFILES[primary]
    declared = _declared_relation_text(declared_relation)
    if declared != "未提供":
        evidence.append("用户已声明现实关系，系统把声明作为解读前提")

    return {
        "domain": "relationship",
        "primary_task": primary,
        "任务名称": profile["名称"],
        "任务说明": profile["说明"],
        "语义主轴": profile["语义主轴"],
        "time_axis": profile["time_axis"],
        "object_type": "human_relation",
        "uncertainty": profile["uncertainty"],
        "识别依据": evidence,
        "现实边界": "关系复合盘只分析两人互动、结构与趋势；未声明关系时不作现实身份、法律身份或血缘事实证明。",
    }


def _relationship_weights_for_task(primary_task: str) -> Dict[str, int]:
    profile = RELATION_TASK_PROFILES.get(primary_task) or RELATION_TASK_PROFILES["relationship_definition"]
    return dict(profile["weights"])


def _weight_rows(weights: Dict[str, int]) -> List[Dict[str, Any]]:
    return [
        {"术数": method, "权重": weight, "说明": _method_role_description(method)}
        for method, weight in sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    ]


def _method_role_description(method: str) -> str:
    return {
        "六爻": "当前事件与事实状态",
        "奇门": "行为路径、主动被动与环境阻力",
        "梅花": "趋势概率与象意补充",
        "大六壬": "过程因果、行为轨迹与后续演化",
        "八字": "长期结构、互补与冲合刑害",
        "紫微": "人生结构、宫位牵动与感情模式",
        "关系复合卦": "双人关系场、对象差异与关系气质校验",
    }.get(method, "")




def _as_int(value: Any, label: str) -> int:
    if value is None or value == "":
        raise ValueError(f"{label}不能为空")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是整数") from exc


def _as_float(value: Any, label: str, default: Optional[float] = None) -> float:
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError(f"{label}不能为空")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc


def _normalize_gender(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if text in {"男", "male", "Male", "M", "m"}:
        return "男"
    if text in {"女", "female", "Female", "F", "f"}:
        return "女"
    raise ValueError(f"{label}性别必须为男或女")


def _validate_datetime(prefix: str, data: Dict[str, Any]) -> datetime:
    year = _as_int(data.get("year"), f"{prefix}年")
    month = _as_int(data.get("month"), f"{prefix}月")
    day = _as_int(data.get("day"), f"{prefix}日")
    hour = _as_int(data.get("hour"), f"{prefix}时")
    minute = _as_int(data.get("minute"), f"{prefix}分")
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError as exc:
        raise ValueError(f"{prefix}时间不合法：{exc}") from exc


def _normalize_subject(raw: Dict[str, Any], label: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label}信息不能为空")
    data = {
        "year": raw.get("birth_year", raw.get("year")),
        "month": raw.get("birth_month", raw.get("month")),
        "day": raw.get("birth_day", raw.get("day")),
        "hour": raw.get("birth_hour", raw.get("hour")),
        "minute": raw.get("birth_minute", raw.get("minute")),
    }
    birth_dt = _validate_datetime(f"{label}出生", data)
    return {
        "称谓": label,
        "性别": _normalize_gender(raw.get("gender"), label),
        "出生时间": birth_dt,
        "出生时间文本": birth_dt.strftime("%Y-%m-%d %H:%M"),
    }


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.exception("Relationship chart subcall failed: %s", getattr(fn, "__name__", fn))
        return {"错误": str(exc)}


def _hexagram_name(shang: str, xia: str) -> str:
    return GUA_64.get((shang, xia), f"{shang}{xia}")


def _branch_pair_relation(a: str, b: str) -> List[str]:
    rel = []
    if a == b:
        rel.append("同支")
    if dz_liu_he(a, b):
        rel.append("六合")
    if dz_chong(a, b):
        rel.append("六冲")
    if dz_hai(a, b):
        rel.append("六害")
    half = SAN_HE_HALF.get(frozenset((a, b)))
    if half:
        rel.append(half)
    if any(a in group and b in group and a != b for group in XING_GROUPS):
        rel.append("刑")
    return rel or ["平常"]


def _gan_pair_relation(a: str, b: str) -> List[str]:
    rel = []
    he = GAN_HE.get(frozenset((a, b)))
    if he:
        rel.append(he)
    rel.append(wx_relation(TIAN_GAN_WX[a], TIAN_GAN_WX[b]))
    return rel


def _top_elements(score: Dict[str, float], reverse: bool = True, count: int = 2) -> List[str]:
    items = sorted(score.items(), key=lambda kv: kv[1], reverse=reverse)
    return [k for k, _ in items[:count]]


def _score_label(score: int) -> str:
    if score >= 75:
        return "强"
    if score >= 60:
        return "中上"
    if score >= 45:
        return "中等"
    return "偏弱"


def _bazi_pair_summary(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    a = first["八字"]
    b = second["八字"]
    if a.get("错误") or b.get("错误"):
        return {"错误": "八字盘存在错误，无法生成合盘摘要", "第一命主": a.get("错误"), "第二命主": b.get("错误")}

    pa = a.get("四柱", {})
    pb = b.get("四柱", {})
    pair_rows = []
    score = 50
    for pos in ["年柱", "月柱", "日柱", "时柱"]:
        ga, gb = pa[pos][0], pb[pos][0]
        za, zb = pa[pos][1], pb[pos][1]
        gan_rel = _gan_pair_relation(ga, gb)
        zhi_rel = _branch_pair_relation(za, zb)
        if "六合" in zhi_rel:
            score += 8 if pos == "日柱" else 4
        if "六冲" in zhi_rel:
            score -= 12 if pos == "日柱" else 6
        if "六害" in zhi_rel or "刑" in zhi_rel:
            score -= 7 if pos == "日柱" else 4
        if GAN_HE.get(frozenset((ga, gb))):
            score += 6 if pos == "日柱" else 3
        pair_rows.append({
            "柱位": pos,
            "第一命主": pa[pos],
            "第二命主": pb[pos],
            "天干关系": gan_rel,
            "地支关系": zhi_rel,
        })

    day_a = pa["日柱"][0]
    day_b = pb["日柱"][0]
    ten_ab = get_shi_shen(day_a, day_b)
    ten_ba = get_shi_shen(day_b, day_a)
    rel_ab = wx_relation(TIAN_GAN_WX[day_a], TIAN_GAN_WX[day_b])
    if "生" in rel_ab:
        score += 4
    if "克" in rel_ab:
        score -= 3

    complement = []
    a_weak = _top_elements(a.get("五行力量", {}), reverse=False)
    b_strong = _top_elements(b.get("五行力量", {}), reverse=True)
    b_weak = _top_elements(b.get("五行力量", {}), reverse=False)
    a_strong = _top_elements(a.get("五行力量", {}), reverse=True)
    if set(a_weak) & set(b_strong):
        score += 6
        complement.append("第二命主较强五行可补第一命主弱项")
    if set(b_weak) & set(a_strong):
        score += 6
        complement.append("第一命主较强五行可补第二命主弱项")
    if not complement:
        complement.append("五行互补不明显，需看问事盘确认")

    score = max(20, min(90, score))
    return {
        "四柱对照": pair_rows,
        "日主关系": {
            "第一命主日主": day_a,
            "第二命主日主": day_b,
            "五行关系": rel_ab,
            "第二命主对第一命主十神": ten_ab,
            "第一命主对第二命主十神": ten_ba,
        },
        "五行互补": complement,
        "关系张力评分": score,
        "关系张力等级": _score_label(score),
    }


def _palace_summary(ziwei: Dict[str, Any], palace_name: str) -> Dict[str, Any]:
    palace = (ziwei.get("十二宫") or {}).get(palace_name, {})
    stars = []
    for group in ("主星", "辅星"):
        for star, strength in (palace.get(group) or {}).items():
            hua = (palace.get("四化") or {}).get(star, "")
            stars.append(f"{star}({strength}{'·' + hua if hua else ''})")
    return {
        "宫名": palace_name,
        "干支": palace.get("干支", ""),
        "地支": palace.get("地支", ""),
        "星曜": stars or ["空宫"],
        "身宫": bool(palace.get("身宫标记")),
    }


def _ziwei_pair_summary(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    a = first["紫微斗数"]
    b = second["紫微斗数"]
    if a.get("错误") or b.get("错误"):
        return {"错误": "紫微盘存在错误，无法生成合盘摘要", "第一命主": a.get("错误"), "第二命主": b.get("错误")}

    key_palaces = ["命宫", "夫妻", "父母", "子女", "福德", "财帛", "官禄"]
    a_palaces = {name: _palace_summary(a, name) for name in key_palaces}
    b_palaces = {name: _palace_summary(b, name) for name in key_palaces}

    signals = []
    score = 50
    if a.get("命宫") == b.get("命宫"):
        score += 8
        signals.append("双方命宫同支，核心性情投射较强")
    if dz_liu_he(a.get("命宫", ""), b.get("命宫", "")):
        score += 8
        signals.append("双方命宫六合，互动有吸引与协作基础")
    if dz_chong(a.get("命宫", ""), b.get("命宫", "")):
        score -= 8
        signals.append("双方命宫相冲，关系中容易出现立场冲突")

    for owner, source, target in [
        ("第一命主", a_palaces, b.get("命宫", "")),
        ("第二命主", b_palaces, a.get("命宫", "")),
    ]:
        if source["夫妻"]["地支"] == target:
            score += 6
            signals.append(f"{owner}夫妻宫牵动对方命宫，亲密关系议题较强")
        if source["子女"]["地支"] == target:
            score += 5
            signals.append(f"{owner}子女宫牵动对方命宫，照护/晚辈/子女议题较强")
        if source["父母"]["地支"] == target:
            score += 5
            signals.append(f"{owner}父母宫牵动对方命宫，长辈/承接/权威议题较强")

    score = max(20, min(90, score))
    return {
        "第一命主重点宫位": a_palaces,
        "第二命主重点宫位": b_palaces,
        "紫微互动线索": signals or ["未见强烈单一宫位牵动，需合参八字与问事盘"],
        "紫微合盘评分": score,
        "紫微合盘等级": _score_label(score),
    }


def _relation_from_question(question: str, first: Dict[str, Any], second: Dict[str, Any], context: str = "") -> Dict[str, Any]:
    text = _combined_question_text(question, context)
    lowered = text.lower()
    evidence = []
    age_diff = abs((first["出生时间"] - second["出生时间"]).days) / 365.2425

    def has_any(words: List[str]) -> bool:
        return any(w in text or w.lower() in lowered for w in words)

    if has_any(["亲生", "亲子", "血缘", "父子", "父女", "母子", "母女", "孩子", "儿子", "女儿"]):
        conflicts = _gendered_relation_conflicts(first, second, text)
        if conflicts:
            evidence.extend(conflicts)
            return {
                "细分": "补充信息与命主性别冲突，疑似上一盘上下文残留",
                "保守层级": "上下文需清理后再判断",
                "置信度": 38,
                "证据": evidence,
            }
        evidence.append("问题包含亲缘/子女关系关键词")
        return {
            "细分": _parent_child_label(first, second, age_diff),
            "保守层级": "直系亲缘/长辈晚辈关系",
            "置信度": 82 if age_diff >= 14 else 68,
            "证据": evidence,
        }
    if age_diff >= 24 and not has_any(["夫妻", "恋", "暧昧", "情侣", "对象", "情人", "伴侣", "男友", "女友"]):
        evidence.append(f"年龄差约{age_diff:.1f}年，未声明婚恋，按长幼/照护方向优先识别")
        return {
            "细分": _parent_child_label(first, second, age_diff),
            "保守层级": "长幼/照护/亲缘候选关系",
            "置信度": 72,
            "证据": evidence,
        }
    if has_any(["夫妻", "婚", "恋", "姻缘", "感情", "复合", "出轨", "老公", "老婆", "男友", "女友"]):
        evidence.append("问题包含婚恋/亲密关系关键词")
        return {"细分": "婚恋/亲密关系", "保守层级": "伴侣或潜在伴侣关系", "置信度": 78, "证据": evidence}
    if has_any(["合作", "合伙", "生意", "项目", "事业", "客户", "投资"]):
        evidence.append("问题包含合作/事业关系关键词")
        return {"细分": "合作/事业关系", "保守层级": "利益协作关系", "置信度": 74, "证据": evidence}
    if has_any(["朋友", "同学", "同事", "兄弟", "姐妹"]):
        evidence.append("问题包含平辈关系关键词")
        return {"细分": "朋友/平辈关系", "保守层级": "平辈互动关系", "置信度": 70, "证据": evidence}
    if has_any(["老师", "师父", "徒弟", "领导", "上级", "下属"]):
        evidence.append("问题包含师徒/上下级关键词")
        return {"细分": "师徒/上下级关系", "保守层级": "权责层级关系", "置信度": 72, "证据": evidence}
    if has_any(["纠纷", "竞争", "仇", "吵架", "官司", "债"]):
        evidence.append("问题包含冲突/纠纷关键词")
        return {"细分": "纠纷/竞争关系", "保守层级": "冲突对立关系", "置信度": 70, "证据": evidence}

    return {
        "细分": "未从问题中明确识别",
        "保守层级": "待盘面辅助描述",
        "置信度": 35,
        "证据": ["问题未提供明确关系关键词"],
    }


def _parent_child_label(first: Dict[str, Any], second: Dict[str, Any], age_diff: float) -> str:
    if age_diff < 14:
        return "亲缘/手足类关系"
    older, younger = (first, second) if first["出生时间"] < second["出生时间"] else (second, first)
    parent = "父" if older["性别"] == "男" else "母"
    child = "子" if younger["性别"] == "男" else "女"
    if older["称谓"] == "第一命主":
        return f"{parent}{child}关系（第一命主为长辈）"
    return f"{parent}{child}关系（第二命主为长辈）"


def _current_relation_signals(current_question: Optional[Dict[str, Any]]) -> Tuple[Dict[str, int], List[str], int]:
    scores = {"亲密": 0, "同辈": 0, "照护": 0, "合作": 0, "冲突": 0, "亲缘": 0}
    evidence = []
    strong_identity_anchors = 0
    if not current_question:
        return scores, evidence, strong_identity_anchors

    liuyao = current_question.get("六爻") or {}
    for yao in liuyao.get("六爻", []):
        liu_qin = yao.get("六亲", "")
        if yao.get("世"):
            evidence.append(f"六爻世爻临{liu_qin}，表示第一命主当前关系切入点")
        if yao.get("应"):
            evidence.append(f"六爻应爻临{liu_qin}，表示第二命主在问事中的落点")
            if liu_qin in {"妻财", "官鬼"}:
                scores["亲密"] += 5
                scores["合作"] += 2
                evidence.append("应爻见财官，只能作亲密/资源/权责牵连象，不能单独断定夫妻或伴侣")
            if liu_qin in {"兄弟", "子孙"}:
                scores["同辈"] += 4
            if liu_qin == "父母":
                scores["照护"] += 4
        if yao.get("动爻"):
            if liu_qin in {"兄弟", "官鬼"}:
                scores["冲突"] += 3
            evidence.append(f"六爻{yao.get('爻名', yao.get('爻位'))}爻发动，临{liu_qin}，为当前关系变化点")

    qimen = current_question.get("奇门遁甲") or {}
    for palace in (qimen.get("九宫") or {}).values():
        if palace.get("八神") == "六合":
            scores["亲密"] += 3
            scores["合作"] += 2
            evidence.append(f"奇门六合临{palace.get('八门', '')}门，表示合和/往来/协作象，不作为婚姻专属证据")
            if palace.get("八门") in {"伤", "惊", "死"}:
                scores["冲突"] += 3
                evidence.append("六合遇凶门，提示关系中有损伤或阻隔")

    dlr = current_question.get("大六壬") or {}
    for label in ("第一命主行年盘", "第二命主行年盘"):
        pan = dlr.get(label) or {}
        for pos in ("初传", "中传", "末传"):
            tian_jiang = ((pan.get("三传") or {}).get(pos) or {}).get("天将", "")
            if tian_jiang == "天后":
                scores["亲密"] += 3
                evidence.append(f"大六壬{label}{pos}见天后，有女性/婚姻/关系收束象，但不能单独断身份")
            if tian_jiang == "六合":
                scores["亲密"] += 3
                scores["合作"] += 2
                evidence.append(f"大六壬{label}{pos}见六合，有合和/关系牵连象")
            if tian_jiang in {"螣蛇", "天空", "白虎"}:
                scores["冲突"] += 2

    return scores, evidence, strong_identity_anchors


def _ziwei_relation_signals(ziwei_pair: Optional[Dict[str, Any]]) -> Tuple[Dict[str, int], List[str], int]:
    scores = {"亲密": 0, "同辈": 0, "照护": 0, "合作": 0, "冲突": 0, "亲缘": 0}
    evidence: List[str] = []
    anchors = 0
    if not ziwei_pair or ziwei_pair.get("错误"):
        return scores, evidence, anchors

    score = int(ziwei_pair.get("紫微合盘评分", 50))
    if score >= 70:
        scores["亲密"] += 4
        scores["合作"] += 2
        evidence.append(f"紫微合盘评分{score}，人生结构互动较强")
    elif score < 50:
        scores["冲突"] += 3
        evidence.append(f"紫微合盘评分{score}，结构支撑偏弱")

    for line in ziwei_pair.get("紫微互动线索", []):
        text = str(line)
        if "夫妻宫" in text:
            scores["亲密"] += 4
            anchors += 1
            evidence.append(f"紫微见夫妻宫牵动：{text}")
        elif "子女宫" in text:
            scores["照护"] += 3
            scores["亲缘"] += 1
            evidence.append(f"紫微见子女宫牵动：{text}")
        elif "父母宫" in text:
            scores["照护"] += 3
            scores["亲缘"] += 2
            evidence.append(f"紫微见父母宫牵动：{text}")
        elif "相冲" in text:
            scores["冲突"] += 3
            evidence.append(f"紫微见宫位冲突：{text}")

    return scores, evidence[:8], anchors


def _compound_relation_signals(compound_hex: Optional[Dict[str, Any]]) -> Tuple[Dict[str, int], List[str], int]:
    scores = {"亲密": 0, "同辈": 0, "照护": 0, "合作": 0, "冲突": 0, "亲缘": 0}
    evidence: List[str] = []
    anchors = 0
    if not compound_hex:
        return scores, evidence, anchors

    ti_yong = compound_hex.get("体用分析") or {}
    relation = ti_yong.get("体用关系", "")
    if relation in {"比和", "用生体"}:
        scores["亲密"] += 3
        scores["合作"] += 2
        evidence.append(f"关系复合卦体用{relation}，关系场有相生或同频象")
    elif relation == "体克用":
        scores["合作"] += 2
        scores["冲突"] += 1
        evidence.append("关系复合卦体克用，主动方可推动但费力")
    elif relation in {"用克体", "体生用"}:
        scores["冲突"] += 3
        evidence.append(f"关系复合卦体用{relation}，关系场有消耗或压力")

    for key in ("本卦", "互卦", "变卦"):
        name = ((compound_hex.get(key) or {}).get("卦名") or "")
        if not name:
            continue
        if any(word in name for word in ["咸", "归妹", "家人", "泰", "同人", "比"]):
            scores["亲密"] += 2
            anchors += 1 if key == "本卦" else 0
            evidence.append(f"关系复合卦{key}为{name}，有亲近/关系牵动象")
        if any(word in name for word in ["睽", "否", "讼", "困", "革", "剥"]):
            scores["冲突"] += 2
            evidence.append(f"关系复合卦{key}为{name}，有阻隔/分歧/变动象")

    return scores, evidence[:8], anchors


def _add_signal(signals: List[Dict[str, Any]], label: str, strength: float, direction: str, evidence: str) -> None:
    strength = max(0.0, min(1.0, float(strength)))
    signals.append({"标签": label, "强度": round(strength, 2), "方向": direction, "依据": evidence})


def _relation_label_scores(signals: List[Dict[str, Any]]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for signal in signals:
        label = str(signal.get("标签", ""))
        if not label:
            continue
        scores[label] = scores.get(label, 0.0) + float(signal.get("强度", 0.0))
    return scores


def _dominant_labels(signals: List[Dict[str, Any]], count: int = 3) -> List[str]:
    scores = _relation_label_scores(signals)
    return [label for label, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:count]]


def _add_hexagram_semantic_signals(
    signals: List[Dict[str, Any]],
    evidence: List[str],
    method_label: str,
    key: str,
    item: Dict[str, Any],
    base_strength: float,
) -> None:
    if not item:
        return
    semantics = get_hexagram_semantics(item.get("卦名"), item.get("上卦"), item.get("下卦"), domain="relationship")
    name = semantics.get("卦名") or item.get("卦名") or ""
    candidates = semantics.get("本题候选义", [])[:2]
    risks = semantics.get("风险标签", [])[:2]
    if not name:
        return
    if candidates:
        evidence.append(f"{method_label}{key}为{name}，关系候选义：{'、'.join(candidates)}")
    text = " ".join(candidates + risks)
    if any(word in text for word in ["吸引", "亲密", "互感", "靠近", "和合", "公开往来", "共同", "聚"]):
        _add_signal(signals, f"{method_label}卦义亲近", base_strength, "合", f"{key}{name}：{'、'.join(candidates)}")
    if any(word in text for word in ["照护", "承接", "滋养", "责任", "规则", "权责", "边界"]):
        _add_signal(signals, f"{method_label}卦义责任", max(0.45, base_strength - 0.1), "中性", f"{key}{name}：{'、'.join(candidates)}")
    if any(word in text for word in ["阻", "隔", "争", "困", "停", "消耗", "冲突", "退缩", "不稳", "冷", "误解"]):
        _add_signal(signals, f"{method_label}卦义阻滞", base_strength, "冲", f"{key}{name}：{'、'.join(candidates + risks)}")
    if any(word in text for word in ["转", "改变", "变", "推进", "回暖", "修复", "明朗"]):
        _add_signal(signals, f"{method_label}卦义变化", max(0.45, base_strength - 0.05), "变", f"{key}{name}：{'、'.join(candidates)}")


def _extract_liuyao_semantics(liuyao: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not liuyao or liuyao.get("错误"):
        return {"术数": "六爻", "语义层": ["事实层", "关系性质层", "趋势概率层"], "标签": signals, "摘要": "六爻盘不可用", "证据": evidence}

    gua_name = str(liuyao.get("卦名", ""))
    _add_hexagram_semantic_signals(signals, evidence, "六爻", "本卦", liuyao, 0.55)
    if any(word in gua_name for word in ["咸", "归妹", "家人", "泰", "同人", "比", "兑"]):
        _add_signal(signals, "亲密牵引", 0.75, "合", f"六爻卦名为{gua_name}，有关系/亲近象")
    if any(word in gua_name for word in ["睽", "否", "讼", "困", "革", "剥"]):
        _add_signal(signals, "关系阻隔", 0.65, "冲", f"六爻卦名为{gua_name}，有分歧/阻隔象")

    for yao in liuyao.get("六爻", []):
        liu_qin = yao.get("六亲", "")
        pos = yao.get("爻名") or yao.get("爻位")
        if yao.get("世"):
            evidence.append(f"世爻临{liu_qin}")
        if yao.get("应"):
            evidence.append(f"应爻临{liu_qin}")
            if liu_qin in {"妻财", "官鬼"}:
                _add_signal(signals, "亲密/权责牵连", 0.8, "合", f"应爻临{liu_qin}，可作亲密、资源或责任牵连象")
            elif liu_qin == "兄弟":
                _add_signal(signals, "同辈竞争", 0.55, "冲", "应爻临兄弟，平辈、竞争或分担象增强")
            elif liu_qin == "父母":
                _add_signal(signals, "照护承接", 0.55, "中性", "应爻临父母，照护、承接或文书规则象增强")
            elif liu_qin == "子孙":
                _add_signal(signals, "轻松互动", 0.5, "合", "应爻临子孙，轻松表达或晚辈照护象增强")
        if yao.get("动爻"):
            direction = "冲" if liu_qin in {"兄弟", "官鬼"} else "变"
            _add_signal(signals, "当前变化点", 0.6, direction, f"六爻{pos}爻发动，临{liu_qin}")

    summary = "当前问事盘提供关系事实与状态快照"
    labels = _dominant_labels(signals)
    if labels:
        summary = "六爻重点提示：" + "、".join(labels)
    return {"术数": "六爻", "语义层": ["事实层", "关系性质层", "趋势概率层"], "标签": signals, "摘要": summary, "证据": evidence}


def _extract_qimen_semantics(qimen: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not qimen or qimen.get("错误"):
        return {"术数": "奇门", "语义层": ["动态行为层", "关系性质层"], "标签": signals, "摘要": "奇门盘不可用", "证据": evidence}

    door_scores = {"开": ("主动推进", 0.65, "合"), "休": ("缓和维持", 0.55, "合"), "生": ("发展生机", 0.7, "合"),
                   "伤": ("互动损伤", 0.65, "冲"), "杜": ("阻隔保留", 0.6, "阻"), "景": ("显化曝光", 0.45, "变"),
                   "死": ("停滞低迷", 0.7, "阻"), "惊": ("不安波动", 0.6, "冲")}
    for gong, palace in (qimen.get("九宫") or {}).items():
        shen = palace.get("八神", "")
        door = palace.get("八门", "")
        star = palace.get("九星", "")
        if shen == "六合":
            _add_signal(signals, "合和往来", 0.75, "合", f"奇门{gong}宫见六合，门为{door}")
        if shen in {"玄武", "螣蛇"}:
            _add_signal(signals, "暗线/疑虑", 0.55, "变", f"奇门{gong}宫见{shen}")
        if shen in {"白虎", "勾陈"}:
            _add_signal(signals, "压力阻力", 0.55, "冲", f"奇门{gong}宫见{shen}")
        if door in door_scores:
            label, strength, direction = door_scores[door]
            if door in {"开", "休", "生", "伤", "杜", "死", "惊"}:
                _add_signal(signals, label, strength, direction, f"奇门{gong}宫八门为{door}，九星为{star}")
                evidence.append(f"{gong}宫：{door}门、{shen}、{star}")

    labels = _dominant_labels(signals)
    summary = "奇门重点提示：" + "、".join(labels) if labels else "奇门未见强烈单一互动路径"
    return {"术数": "奇门", "语义层": ["动态行为层", "关系性质层"], "标签": signals, "摘要": summary, "证据": evidence[:8]}


def _extract_meihua_semantics(meihua: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not meihua or meihua.get("错误"):
        return {"术数": "梅花", "语义层": ["趋势概率层", "关系性质层"], "标签": signals, "摘要": "梅花盘不可用", "证据": evidence}

    ti_yong = meihua.get("体用分析") or {}
    relation = ti_yong.get("体用关系", "")
    if relation in {"比和", "用生体", "体克用"}:
        strength = 0.8 if relation in {"比和", "用生体"} else 0.55
        _add_signal(signals, "趋势向合", strength, "合", f"梅花体用关系为{relation}：{ti_yong.get('断语', '')}")
    elif relation in {"用克体", "体生用"}:
        strength = 0.8 if relation == "用克体" else 0.6
        _add_signal(signals, "趋势消耗", strength, "冲", f"梅花体用关系为{relation}：{ti_yong.get('断语', '')}")

    for key in ("本卦", "互卦", "变卦"):
        name = ((meihua.get(key) or {}).get("卦名") or "")
        _add_hexagram_semantic_signals(signals, evidence, "梅花", key, meihua.get(key) or {}, 0.5)
        if name:
            evidence.append(f"{key}为{name}")
        if any(word in name for word in ["咸", "归妹", "家人", "泰", "同人"]):
            _add_signal(signals, "关系象增强", 0.55, "合", f"梅花{key}为{name}")
        if any(word in name for word in ["睽", "否", "讼", "困"]):
            _add_signal(signals, "分歧阻隔", 0.55, "冲", f"梅花{key}为{name}")

    labels = _dominant_labels(signals)
    summary = "梅花重点提示：" + "、".join(labels) if labels else "梅花主要作趋势象意补充"
    return {"术数": "梅花", "语义层": ["趋势概率层", "关系性质层"], "标签": signals, "摘要": summary, "证据": evidence}


def _extract_compound_hex_semantics(compound_hex: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not compound_hex:
        return {"术数": "关系复合卦", "语义层": ["关系性质层", "结构稳定层", "底层因果层"], "标签": signals, "摘要": "关系复合卦不可用", "证据": evidence}

    ti_yong = compound_hex.get("体用分析") or {}
    relation = ti_yong.get("体用关系", "")
    if relation in {"比和", "用生体", "体克用"}:
        strength = 0.75 if relation in {"比和", "用生体"} else 0.55
        _add_signal(signals, "关系场有牵引", strength, "合", f"复合卦体用关系为{relation}：{ti_yong.get('断语', '')}")
    elif relation in {"用克体", "体生用"}:
        strength = 0.75 if relation == "用克体" else 0.6
        _add_signal(signals, "关系场有消耗", strength, "冲", f"复合卦体用关系为{relation}：{ti_yong.get('断语', '')}")

    for key in ("本卦", "互卦", "变卦"):
        name = ((compound_hex.get(key) or {}).get("卦名") or "")
        _add_hexagram_semantic_signals(signals, evidence, "复合", key, compound_hex.get(key) or {}, 0.55)
        if name:
            evidence.append(f"{key}为{name}")
        if any(word in name for word in ["咸", "归妹", "家人", "泰", "同人", "比"]):
            _add_signal(signals, "关系场亲近", 0.6, "合", f"复合卦{key}为{name}")
        if any(word in name for word in ["睽", "否", "讼", "困", "革", "剥"]):
            _add_signal(signals, "关系场阻隔", 0.6, "冲", f"复合卦{key}为{name}")

    labels = _dominant_labels(signals)
    summary = "关系复合卦提示：" + "、".join(labels) if labels else "关系复合卦主要用于校验双人关系场"
    return {"术数": "关系复合卦", "语义层": ["关系性质层", "结构稳定层", "底层因果层"], "标签": signals, "摘要": summary, "证据": evidence}


def _extract_daliuren_semantics(dlr: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not dlr:
        return {"术数": "大六壬", "语义层": ["底层因果层", "动态行为层", "事实层"], "标签": signals, "摘要": "大六壬盘不可用", "证据": evidence}

    for owner_label, pan in dlr.items():
        if not isinstance(pan, dict) or pan.get("错误"):
            continue
        chuan = pan.get("三传") or {}
        method = chuan.get("起传法", "")
        if method:
            evidence.append(f"{owner_label}起传法为{method}")
        for pos in ("初传", "中传", "末传"):
            item = chuan.get(pos) or {}
            tian_jiang = item.get("天将", "")
            gan_zhi = item.get("干支", "")
            if tian_jiang == "六合":
                _add_signal(signals, "因果牵连", 0.75, "合", f"大六壬{owner_label}{pos}见六合（{gan_zhi}）")
            elif tian_jiang == "天后":
                _add_signal(signals, "亲密/收束象", 0.65, "合", f"大六壬{owner_label}{pos}见天后（{gan_zhi}）")
            elif tian_jiang in {"螣蛇", "天空", "白虎", "勾陈"}:
                _add_signal(signals, "过程阻滞", 0.6, "冲", f"大六壬{owner_label}{pos}见{tian_jiang}（{gan_zhi}）")
            elif tian_jiang in {"青龙", "太常", "太阴", "贵人"}:
                _add_signal(signals, "过程助力", 0.55, "合", f"大六壬{owner_label}{pos}见{tian_jiang}（{gan_zhi}）")

    labels = _dominant_labels(signals)
    summary = "大六壬重点提示：" + "、".join(labels) if labels else "大六壬主要用于观察过程链条"
    return {"术数": "大六壬", "语义层": ["底层因果层", "动态行为层", "事实层"], "标签": signals, "摘要": summary, "证据": evidence[:8]}


def _extract_bazi_semantics(bazi_pair: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not bazi_pair or bazi_pair.get("错误"):
        return {"术数": "八字", "语义层": ["结构稳定层", "底层因果层"], "标签": signals, "摘要": "八字合盘不可用", "证据": evidence}

    score = int(bazi_pair.get("关系张力评分", 50))
    if score >= 70:
        _add_signal(signals, "长期结构较稳", 0.8, "合", f"八字关系张力评分{score}")
    elif score >= 55:
        _add_signal(signals, "长期结构中等", 0.6, "中性", f"八字关系张力评分{score}")
    elif score >= 40:
        _add_signal(signals, "长期结构有波动", 0.65, "冲", f"八字关系张力评分{score}")
    else:
        _add_signal(signals, "长期结构冲克", 0.8, "冲", f"八字关系张力评分{score}")

    for row in bazi_pair.get("四柱对照", []):
        pos = row.get("柱位", "")
        rels = row.get("地支关系", []) + row.get("天干关系", [])
        joined = "、".join(rels)
        if joined:
            evidence.append(f"{pos}：{joined}")
        if any(rel == "六合" or "半合" in rel for rel in rels):
            _add_signal(signals, "结构牵引", 0.55 if pos != "日柱" else 0.75, "合", f"八字{pos}见{joined}")
        if any(rel in {"六冲", "六害", "刑"} for rel in rels):
            _add_signal(signals, "结构张力", 0.55 if pos != "日柱" else 0.8, "冲", f"八字{pos}见{joined}")

    labels = _dominant_labels(signals)
    summary = "八字重点提示：" + "、".join(labels) if labels else "八字主要用于长期结构判断"
    return {"术数": "八字", "语义层": ["结构稳定层", "底层因果层"], "标签": signals, "摘要": summary, "证据": evidence[:8]}


def _extract_ziwei_semantics(ziwei_pair: Dict[str, Any]) -> Dict[str, Any]:
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    if not ziwei_pair or ziwei_pair.get("错误"):
        return {"术数": "紫微", "语义层": ["结构稳定层", "底层因果层", "关系性质层"], "标签": signals, "摘要": "紫微合盘不可用", "证据": evidence}

    score = int(ziwei_pair.get("紫微合盘评分", 50))
    if score >= 70:
        _add_signal(signals, "命盘互动较强", 0.75, "合", f"紫微合盘评分{score}")
    elif score >= 55:
        _add_signal(signals, "命盘互动中等", 0.55, "中性", f"紫微合盘评分{score}")
    else:
        _add_signal(signals, "命盘结构偏弱", 0.65, "冲", f"紫微合盘评分{score}")

    for line in ziwei_pair.get("紫微互动线索", []):
        evidence.append(str(line))
        if "夫妻宫" in str(line):
            _add_signal(signals, "婚恋宫位牵动", 0.75, "合", str(line))
        elif "子女宫" in str(line):
            _add_signal(signals, "照护/晚辈议题", 0.55, "中性", str(line))
        elif "父母宫" in str(line):
            _add_signal(signals, "长辈/承接议题", 0.55, "中性", str(line))
        elif "相冲" in str(line):
            _add_signal(signals, "宫位冲突", 0.65, "冲", str(line))
        elif "六合" in str(line) or "同支" in str(line):
            _add_signal(signals, "宫位吸引", 0.6, "合", str(line))

    labels = _dominant_labels(signals)
    summary = "紫微重点提示：" + "、".join(labels) if labels else "紫微主要用于人生结构与宫位牵动"
    return {"术数": "紫微", "语义层": ["结构稳定层", "底层因果层", "关系性质层"], "标签": signals, "摘要": summary, "证据": evidence[:8]}


def _build_method_semantics(
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    current_question: Dict[str, Any],
    compound_hex: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "六爻": _extract_liuyao_semantics(current_question.get("六爻") or {}),
        "奇门": _extract_qimen_semantics(current_question.get("奇门遁甲") or {}),
        "梅花": _extract_meihua_semantics(current_question.get("梅花易数") or {}),
        "大六壬": _extract_daliuren_semantics(current_question.get("大六壬") or {}),
        "八字": _extract_bazi_semantics(bazi_pair),
        "紫微": _extract_ziwei_semantics(ziwei_pair),
        "关系复合卦": _extract_compound_hex_semantics(compound_hex or {}),
    }


def _weighted_layer_scores(method_semantics: Dict[str, Any], weights: Dict[str, int]) -> Dict[str, Dict[str, float]]:
    layer_scores: Dict[str, Dict[str, float]] = {}
    for method, info in method_semantics.items():
        weight = weights.get(method, 0) / 100.0
        if weight <= 0:
            continue
        for layer in info.get("语义层", []):
            layer_bucket = layer_scores.setdefault(layer, {})
            for signal in info.get("标签", []):
                label = str(signal.get("标签", ""))
                if not label:
                    continue
                value = float(signal.get("强度", 0.0)) * weight
                layer_bucket[label] = layer_bucket.get(label, 0.0) + value
    return layer_scores


def _top_weighted_labels(layer_scores: Dict[str, Dict[str, float]], layer: str, count: int = 3) -> List[str]:
    scores = layer_scores.get(layer, {})
    return [label for label, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:count]]


def _layer_statement(layer: str, labels: List[str]) -> str:
    if not labels:
        return "该层信号不强，需结合其他层判断。"
    joined = "、".join(labels)
    templates = {
        "事实层": f"当前事实/状态层以“{joined}”为主，只说明当下互动象，不等同现实身份证明。",
        "关系性质层": f"关系性质层呈现“{joined}”，适合描述两人的互动类型与关系气质。",
        "结构稳定层": f"长期结构层以“{joined}”为主，用于判断稳定性、适配度与长期张力。",
        "动态行为层": f"动态行为层显示“{joined}”，用于观察谁在推进、阻滞或拉扯。",
        "趋势概率层": f"趋势层偏向“{joined}”，说明未来走向的概率象。",
        "底层因果层": f"因果层重点为“{joined}”，用于解释这段关系为什么呈现当前状态。",
    }
    return templates.get(layer, f"{layer}：{joined}")


def _semantic_layer_summary(layer_scores: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    layers = {}
    for layer in ["事实层", "关系性质层", "结构稳定层", "动态行为层", "趋势概率层", "底层因果层"]:
        labels = _top_weighted_labels(layer_scores, layer)
        layers[layer] = {
            "主要标签": labels,
            "标签分数": {k: round(v, 3) for k, v in sorted((layer_scores.get(layer) or {}).items(), key=lambda kv: kv[1], reverse=True)},
            "解释": _layer_statement(layer, labels),
        }
    return layers


def _relationship_main_definition(layers: Dict[str, Any], identification: Dict[str, Any], declared_relation: str) -> str:
    declared = _declared_relation_text(declared_relation)
    fact_labels = layers.get("事实层", {}).get("主要标签", [])
    type_labels = layers.get("关系性质层", {}).get("主要标签", [])
    structure_labels = layers.get("结构稳定层", {}).get("主要标签", [])

    if declared != "未提供":
        base = f"以用户声明的“{declared}”作为现实关系前提，盘面只分析这段关系的状态、结构和趋势。"
    else:
        base = "用户未声明现实关系，盘面只给关系画像，不把术数象意当作现实身份或法律/血缘证明。"

    type_text = "、".join(type_labels[:2]) if type_labels else identification.get("关系描述", "关系画像不明")
    fact_text = "、".join(fact_labels[:2]) if fact_labels else "当下事实信号不强"
    structure_text = "、".join(structure_labels[:2]) if structure_labels else "长期结构需谨慎判断"
    return f"{base}当前更适合表述为：{type_text}；当下状态见{fact_text}；长期结构见{structure_text}。"


def _build_integrated_explanation(layers: Dict[str, Any], identification: Dict[str, Any], declared_relation: str) -> Dict[str, Any]:
    dynamic_labels = layers.get("动态行为层", {}).get("主要标签", [])
    trend_labels = layers.get("趋势概率层", {}).get("主要标签", [])
    causal_labels = layers.get("底层因果层", {}).get("主要标签", [])
    structure_labels = layers.get("结构稳定层", {}).get("主要标签", [])

    main = _relationship_main_definition(layers, identification, declared_relation)
    structure = "、".join(structure_labels) if structure_labels else "结构层信号不集中"
    dynamic = "、".join(dynamic_labels) if dynamic_labels else "动态层信号不集中"
    trend = "、".join(trend_labels) if trend_labels else "趋势层信号不集中"
    causal = "、".join(causal_labels) if causal_labels else "因果层信号不集中"
    difference = (
        "若短期状态与长期结构不同，应并列解释：六爻/六壬偏当前是否发生，"
        "八字/紫微偏长期能否稳定，奇门/梅花偏过程和走向。"
    )

    return {
        "主关系定义": main,
        "结构描述": f"长期结构：{structure}。",
        "动态描述": f"当前过程：{dynamic}。",
        "趋势描述": f"未来走向：{trend}。",
        "因果描述": f"底层原因：{causal}。",
        "差异说明": difference,
        "身份边界": "除非用户明确声明或现实证据确认，否则不直接断言夫妻、情人、亲子等现实身份。",
    }


def _collect_label_score(
    method_semantics: Dict[str, Any],
    method: str,
    keywords: List[str],
    multiplier: float = 1.0,
    cap: Optional[float] = None,
) -> float:
    info = method_semantics.get(method) or {}
    total = 0.0
    for signal in info.get("标签", []):
        label = str(signal.get("标签", ""))
        evidence = str(signal.get("依据", ""))
        if any(word in label or word in evidence for word in keywords):
            total += float(signal.get("强度", 0.0)) * multiplier
    if cap is not None:
        return min(total, cap)
    return total


def _candidate_level(score: float) -> str:
    if score >= 0.72:
        return "高"
    if score >= 0.45:
        return "中"
    if score >= 0.22:
        return "偏低"
    return "低"


def _relationship_candidate_ranking(
    method_semantics: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    scores = {
        "婚恋/暧昧/亲密牵连": 0.0,
        "朋友/同辈互动": 0.0,
        "合作/利益/权责关系": 0.0,
        "亲缘/照护/长幼关系": 0.0,
        "冲突/竞争/消耗关系": 0.0,
    }
    reasons: Dict[str, List[str]] = {key: [] for key in scores}

    intimate = (
        _collect_label_score(method_semantics, "六爻", ["亲密", "官鬼", "妻财", "关系象"], 1.35, 1.1)
        + _collect_label_score(method_semantics, "奇门", ["合和", "六合"], 0.85, 0.35)
        + _collect_label_score(method_semantics, "梅花", ["向合", "关系象"], 0.8, 0.4)
        + _collect_label_score(method_semantics, "大六壬", ["天后", "六合", "亲密", "牵连"], 0.7, 0.35)
        + _collect_label_score(method_semantics, "紫微", ["夫妻", "婚恋"], 0.9, 0.45)
    )
    scores["婚恋/暧昧/亲密牵连"] += intimate
    if intimate:
        reasons["婚恋/暧昧/亲密牵连"].append("六爻/奇门/梅花或六壬出现亲密、合和、牵连象")

    cooperation = (
        _collect_label_score(method_semantics, "六爻", ["权责", "父母", "官鬼"], 0.8, 0.45)
        + _collect_label_score(method_semantics, "奇门", ["主动推进", "合和往来", "开门"], 0.75, 0.3)
        + _collect_label_score(method_semantics, "大六壬", ["太常", "过程助力"], 0.65, 0.25)
    )
    scores["合作/利益/权责关系"] += cooperation
    if cooperation:
        reasons["合作/利益/权责关系"].append("盘面有权责、协作、现实事务往来信号")

    peer = _collect_label_score(method_semantics, "六爻", ["同辈", "兄弟"], 1.0, 0.7)
    scores["朋友/同辈互动"] += peer
    if peer:
        reasons["朋友/同辈互动"].append("六爻见同辈或兄弟象")

    care = (
        _collect_label_score(method_semantics, "六爻", ["照护", "父母", "子孙"], 1.0, 0.55)
        + _collect_label_score(method_semantics, "紫微", ["照护", "晚辈", "长辈", "承接"], 0.8, 0.45)
    )
    scores["亲缘/照护/长幼关系"] += care
    if care:
        reasons["亲缘/照护/长幼关系"].append("盘面有照护、承接、父母子女类象")

    conflict = (
        _collect_label_score(method_semantics, "八字", ["结构张力", "冲克", "六冲", "六害"], 1.25, 0.9)
        + _collect_label_score(method_semantics, "奇门", ["损伤", "阻隔", "压力", "不安", "停滞"], 0.7, 0.35)
        + _collect_label_score(method_semantics, "大六壬", ["阻滞", "白虎", "天空", "勾陈"], 0.7, 0.25)
        + _collect_label_score(method_semantics, "梅花", ["消耗", "分歧", "阻隔"], 0.6, 0.2)
    )
    scores["冲突/竞争/消耗关系"] += conflict
    if conflict:
        reasons["冲突/竞争/消耗关系"].append("八字冲害与问事盘阻滞信号显示关系张力")

    bazi_score = int(bazi_pair.get("关系张力评分", 50)) if isinstance(bazi_pair, dict) else 50
    ziwei_score = int(ziwei_pair.get("紫微合盘评分", 50)) if isinstance(ziwei_pair, dict) else 50
    if bazi_score < 45:
        scores["冲突/竞争/消耗关系"] += 0.35
        reasons["冲突/竞争/消耗关系"].append(f"八字关系张力评分{bazi_score}，长期结构偏弱")
    if ziwei_score < 55:
        scores["婚恋/暧昧/亲密牵连"] -= 0.08
        reasons["婚恋/暧昧/亲密牵连"].append(f"紫微合盘评分{ziwei_score}，不支持直接锁定稳定婚姻结构")

    if prior:
        age_diff = prior.get("年龄差")
        if prior.get("声明伴侣"):
            scores["婚恋/暧昧/亲密牵连"] += 0.38
            reasons["婚恋/暧昧/亲密牵连"].append("补充信息已声明伴侣/婚恋语境，婚恋候选保留优先级")
        if prior.get("声明亲子"):
            scores["亲缘/照护/长幼关系"] += 1.25
            scores["婚恋/暧昧/亲密牵连"] -= 1.2
            reasons["亲缘/照护/长幼关系"].append("补充信息已声明亲子/父母子女语境")
            reasons["婚恋/暧昧/亲密牵连"].append("已声明亲子语境，妻财/官鬼优先解释为资源、责任或照护")
        elif prior.get("代际年龄差"):
            scores["亲缘/照护/长幼关系"] += 1.05
            scores["合作/利益/权责关系"] += 0.25
            scores["婚恋/暧昧/亲密牵连"] -= 0.85
            reasons["亲缘/照护/长幼关系"].append(f"年龄差约{age_diff}年，强烈提示长幼、亲子或照护语境")
            reasons["婚恋/暧昧/亲密牵连"].append("大年龄差且未声明婚恋，婚恋/暧昧默认降权")
        elif prior.get("大年龄差"):
            scores["亲缘/照护/长幼关系"] += 0.65
            scores["合作/利益/权责关系"] += 0.2
            scores["婚恋/暧昧/亲密牵连"] -= 0.45
            reasons["亲缘/照护/长幼关系"].append(f"年龄差约{age_diff}年，长幼/照护/权责候选增强")
            reasons["婚恋/暧昧/亲密牵连"].append("年龄差较大且未声明婚恋，不能把合和象直接翻成暧昧")
        if prior.get("同性") and not prior.get("声明伴侣"):
            scores["朋友/同辈互动"] += 0.25
            scores["合作/利益/权责关系"] += 0.2
            scores["婚恋/暧昧/亲密牵连"] -= 0.55
            reasons["朋友/同辈互动"].append("双方同性且未声明婚恋，平辈/社交或亲缘方向需优先消歧")
            reasons["婚恋/暧昧/亲密牵连"].append("双方同性且未声明婚恋，妻财/官鬼不优先翻译为恋爱对象")

    ranked = []
    denominators = {
        "婚恋/暧昧/亲密牵连": 2.2,
        "合作/利益/权责关系": 2.8,
        "朋友/同辈互动": 1.6,
        "亲缘/照护/长幼关系": 1.8,
        "冲突/竞争/消耗关系": 3.0,
    }
    for name, score in scores.items():
        normalized = max(0.0, min(1.0, score / denominators.get(name, 2.2)))
        ranked.append({
            "类型": name,
            "强度": round(normalized, 2),
            "等级": _candidate_level(normalized),
            "依据": reasons[name] or ["该类型信号不明显"],
        })
    return sorted(ranked, key=lambda item: item["强度"], reverse=True)


def _relationship_not_like(ranking: List[Dict[str, Any]]) -> List[str]:
    weak = [item["类型"] for item in ranking if item["强度"] <= 0.25]
    return weak[:2]


def _has_hex_name(method_semantics: Dict[str, Any], names: List[str]) -> bool:
    for method in ("六爻", "梅花", "关系复合卦"):
        info = method_semantics.get(method) or {}
        text = " ".join(str(x) for x in info.get("证据", []))
        text += " " + " ".join(str(s.get("依据", "")) for s in info.get("标签", []))
        if any(name in text for name in names):
            return True
    return False


def _subtype_strengths(
    ranking: List[Dict[str, Any]],
    method_semantics: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    intimate = _ranking_strength(ranking, "婚恋") + _ranking_strength(ranking, "亲密")
    conflict = _ranking_strength(ranking, "冲突")
    care = _ranking_strength(ranking, "照护") + _ranking_strength(ranking, "亲缘")
    cooperation = _ranking_strength(ranking, "合作") + _ranking_strength(ranking, "权责")
    peer = _ranking_strength(ranking, "朋友") + _ranking_strength(ranking, "同辈")
    bazi_score = int(bazi_pair.get("关系张力评分", 50)) if isinstance(bazi_pair, dict) else 50
    ziwei_score = int(ziwei_pair.get("紫微合盘评分", 50)) if isinstance(ziwei_pair, dict) else 50

    day_row = next((row for row in bazi_pair.get("四柱对照", []) if row.get("柱位") == "日柱"), {}) if isinstance(bazi_pair, dict) else {}
    day_rels = (day_row.get("天干关系", []) or []) + (day_row.get("地支关系", []) or [])
    has_day_union = any(rel == "六合" or "半合" in str(rel) for rel in day_rels)
    has_day_conflict = any(rel in {"六冲", "六害", "刑"} for rel in day_rels)
    has_spouse = _collect_label_score(method_semantics, "紫微", ["夫妻", "婚恋"], 1.0, 1.0)
    has_child = _collect_label_score(method_semantics, "紫微", ["子女", "晚辈", "照护"], 1.0, 1.0)
    current_change = _collect_label_score(method_semantics, "六爻", ["当前变化点", "动爻"], 1.0, 1.0)
    current_stable = 0.25 if _has_hex_name(method_semantics, ["恒", "家人"]) else 0.0
    encounter = 0.35 if _has_hex_name(method_semantics, ["姤"]) else 0.0
    blocked = 0.25 if _has_hex_name(method_semantics, ["否", "讼", "困", "睽"]) else 0.0

    strengths = {
        "已成关系框架": max(0.0, intimate * 0.55 + has_spouse * 0.35 + current_stable + (0.18 if has_day_conflict else 0.0) - encounter * 0.35),
        "未定型吸引框架": max(0.0, intimate * 0.45 + encounter + (0.22 if has_day_union else 0.0) + current_change * 0.18 - has_spouse * 0.15),
        "责任照护框架": max(0.0, care * 0.55 + has_child * 0.35 + cooperation * 0.2),
        "合作权责框架": max(0.0, cooperation * 0.65 + _collect_label_score(method_semantics, "六爻", ["权责", "父母", "官鬼"], 0.25, 0.3)),
        "冲突纠葛框架": max(0.0, conflict * 0.65 + blocked + (0.22 if bazi_score < 45 else 0.0) + (0.15 if ziwei_score < 50 else 0.0)),
        "朋友同辈框架": max(0.0, peer * 0.8 - intimate * 0.2),
    }
    if prior:
        if prior.get("声明伴侣"):
            strengths["已成关系框架"] += 0.28
            strengths["未定型吸引框架"] += 0.12
        if prior.get("声明亲子"):
            strengths["责任照护框架"] += 0.75
            strengths["合作权责框架"] += 0.12
            strengths["已成关系框架"] *= 0.45
            strengths["未定型吸引框架"] *= 0.25
        elif prior.get("代际年龄差"):
            strengths["责任照护框架"] += 0.55
            strengths["合作权责框架"] += 0.12
            strengths["已成关系框架"] *= 0.55
            strengths["未定型吸引框架"] *= 0.35
        elif prior.get("大年龄差"):
            strengths["责任照护框架"] += 0.35
            strengths["未定型吸引框架"] *= 0.55
        if prior.get("同性") and not prior.get("声明伴侣"):
            strengths["朋友同辈框架"] += 0.18
            strengths["未定型吸引框架"] *= 0.55
    return strengths


def _relationship_framework(
    ranking: List[Dict[str, Any]],
    method_semantics: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    strengths = _subtype_strengths(ranking, method_semantics, bazi_pair, ziwei_pair, prior)
    ordered = sorted(strengths.items(), key=lambda kv: kv[1], reverse=True)
    primary_name, primary_score = ordered[0]
    secondary = [name for name, score in ordered[1:3] if score >= 0.28]
    descriptions = {
        "已成关系框架": "更像已经形成现实关系框架或长期绑定的亲密关系，重点看责任、磨合和维系质量。",
        "未定型吸引框架": "更像有吸引、有牵引，但身份或现实框架尚未完全坐实的关系。",
        "责任照护框架": "更像由照护、家庭、子女、长幼或依赖议题牵动的关系。",
        "合作权责框架": "更像由现实事务、资源、合作、规则或权责牵动的关系。",
        "冲突纠葛框架": "更像由冲突、竞争、消耗、旧问题或争执牵动的关系。",
        "朋友同辈框架": "更像同辈、朋友、同圈层或一般社交互动关系。",
    }
    return {
        "主框架": primary_name,
        "说明": descriptions.get(primary_name, ""),
        "强度": round(min(1.0, primary_score), 2),
        "辅助框架": secondary,
        "框架评分": {name: round(min(1.0, score), 2) for name, score in ordered},
    }


def _relationship_motives(
    layers: Dict[str, Any],
    method_semantics: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> List[str]:
    label_text = " ".join(
        label
        for layer in layers.values()
        for label in layer.get("主要标签", [])
    )
    all_text = label_text + " " + json.dumps(method_semantics, ensure_ascii=False, default=str)
    motives = []
    checks = [
        ("吸引牵引", ["亲密", "向合", "关系场亲近", "结构牵引", "婚恋宫位"]),
        ("责任权责", ["权责", "官鬼", "父母", "现实事务", "规则"]),
        ("照护依赖", ["照护", "子女", "晚辈", "长辈", "承接"]),
        ("冲突消耗", ["冲突", "阻隔", "消耗", "损伤", "六冲", "六害", "讼"]),
        ("暗线疑虑", ["暗线", "疑虑", "玄武", "天空", "保留"]),
        ("停滞反复", ["停滞", "阻滞", "伏吟", "勾陈", "旬空"]),
    ]
    for name, words in checks:
        if any(word in all_text for word in words):
            motives.append(name)
    if prior:
        if prior.get("声明亲子") or prior.get("代际年龄差"):
            motives = [m for m in motives if m != "吸引牵引"]
            motives.insert(0, "照护依赖")
        elif prior.get("大年龄差"):
            motives.insert(0, "责任权责")
        if prior.get("声明伴侣") and "吸引牵引" not in motives:
            motives.insert(0, "吸引牵引")
    deduped = []
    for motive in motives:
        if motive not in deduped:
            deduped.append(motive)
    return deduped[:2] or ["关系动力不集中"]


def _relationship_info_gaps(
    framework: Dict[str, Any],
    ranking: List[Dict[str, Any]],
    motives: List[str],
    declared_relation: str,
    prior: Optional[Dict[str, Any]] = None,
) -> List[str]:
    gaps = []
    declared = _declared_relation_text(declared_relation)
    if declared == "未提供":
        if prior and (prior.get("代际年龄差") or prior.get("声明亲子")):
            gaps.append("用户未声明现实关系，需确认是否为亲子、长幼照护或师徒上下级等现实框架。")
        else:
            gaps.append("用户未声明现实关系，盘面不能证明两人是否已经公开坐实身份。")
    if prior and prior.get("压制婚恋暧昧") and not prior.get("声明伴侣"):
        gaps.append("人口学先验不支持默认婚恋解读；需先确认财官象指向资源责任、照护还是合作。")
    if framework.get("强度", 0) < 0.55:
        gaps.append("主框架强度不高，需要追问关系是感情、责任还是现实事务主导。")
    top = ranking[0] if ranking else {}
    second = ranking[1] if len(ranking) > 1 else {}
    if second and abs(float(top.get("强度", 0)) - float(second.get("强度", 0))) <= 0.18:
        gaps.append(f"候选关系接近：{top.get('类型')} 与 {second.get('类型')} 需要消歧。")
    if any("暗线" in motive or "停滞" in motive for motive in motives):
        gaps.append("盘面有暗线或停滞，需确认阻力来自对方态度、第三方还是现实条件。")
    return gaps[:3] or ["当前信息足以给出关系画像，若要确认现实身份仍需用户补充事实。"]


def _followup_questions(
    framework: Dict[str, Any],
    gaps: List[str],
    motives: List[str],
    prior: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    questions = []
    if prior and (prior.get("声明亲子") or prior.get("代际年龄差")):
        questions.append({
            "问题": "这段关系的现实框架更接近亲子长幼、照护责任，还是师徒/上下级权责？",
            "用途": "优先消解大年龄差下的亲缘、照护与权责框架。",
        })
    elif prior and prior.get("压制婚恋暧昧") and not prior.get("声明伴侣"):
        questions.append({
            "问题": "这段关系现实中是亲属、朋友同辈、合作权责，还是另有特殊情感背景？",
            "用途": "避免把财官或合和象机械解释为恋爱。",
        })
    else:
        questions.append({
            "问题": "这段关系是否已经进入现实伴侣或固定关系框架？",
            "用途": "区分已成关系与未定型吸引。",
        })
    if any("责任" in motive or "照护" in motive for motive in motives):
        questions.append({
            "问题": "这段关系的核心纽带更偏感情吸引，还是责任照护/现实事务？",
            "用途": "区分婚恋牵引、照护责任和权责合作。",
        })
    if any("暗线" in gap or "阻力" in gap or "停滞" in gap for gap in gaps):
        questions.append({
            "问题": "当前阻滞主要来自对方态度、第三方因素，还是现实条件？",
            "用途": "定位关系卡点。",
        })
    if framework.get("主框架") == "冲突纠葛框架":
        questions.append({
            "问题": "这段关系未来三个月是缓和、继续停滞，还是进入争执？",
            "用途": "判断近期走向。",
        })
    return questions[:3]


def _brief_from_labels(labels: List[str], fallback: str) -> str:
    if not labels:
        return fallback
    return "、".join(labels[:2])


def _build_identity_layer(declared_relation: str) -> str:
    declared = _declared_relation_text(declared_relation)
    if declared == "未提供":
        return "未声明现实身份；本盘只输出关系画像，不证明或否认夫妻、亲子、法律身份。"
    return f"用户已声明为“{declared}”；本盘接受该现实前提，只分析状态、质量、风险与趋势。"


def _build_emotional_state_layer(
    ranking: List[Dict[str, Any]],
    motives: List[str],
    prior: Optional[Dict[str, Any]] = None,
) -> str:
    intimate_strength = _ranking_strength(ranking, "婚恋")
    care_strength = _ranking_strength(ranking, "照护") + _ranking_strength(ranking, "亲缘")
    cooperation_strength = _ranking_strength(ranking, "合作") + _ranking_strength(ranking, "权责")
    conflict_strength = _ranking_strength(ranking, "冲突")
    suppressed = bool(prior and prior.get("压制婚恋暧昧") and not prior.get("声明伴侣"))

    if suppressed and care_strength >= max(intimate_strength, 0.35):
        primary = "情感不按男女暧昧优先解释，主要看照护、责任、依赖或长幼牵连。"
    elif intimate_strength >= 0.65:
        primary = "亲密牵连明显，有吸引、暧昧、伴侣式靠近或强情感投入信号。"
    elif intimate_strength >= 0.38:
        primary = "有一定亲密或吸引信号，但不足以单凭盘面坐实婚恋身份。"
    elif care_strength >= 0.45:
        primary = "情感表达偏照护、承接、依赖或责任牵挂，不是单纯暧昧热度。"
    elif cooperation_strength >= 0.4:
        primary = "情感热度不算主轴，更偏现实事务、合作、资源或权责往来。"
    else:
        primary = "情感信号不集中，需要结合现实互动确认。"

    if conflict_strength >= 0.45 and "冲突消耗" in motives:
        primary += " 同时伴随冲突或消耗，不能只看亲密一面。"
    return primary


def _build_quality_layer(framework: Dict[str, Any], stability: str, motives: List[str]) -> str:
    framework_name = framework.get("主框架", "关系画像不明")
    auxiliary = framework.get("辅助框架") or []
    aux_text = f"，辅见{'、'.join(auxiliary[:2])}" if auxiliary else ""
    motive_text = "、".join(motives[:2]) if motives else "关系动力不集中"
    return f"{framework_name}{aux_text}；关系动力以{motive_text}为主；长期稳定性{stability}。"


def _build_user_facing_conclusion(
    layers: Dict[str, Any],
    identification: Dict[str, Any],
    declared_relation: str,
    method_semantics: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ranking = _relationship_candidate_ranking(method_semantics, bazi_pair, ziwei_pair, prior)
    top = ranking[0] if ranking else {"类型": "关系画像不明", "等级": "低", "强度": 0}
    second = ranking[1] if len(ranking) > 1 else None
    framework = _relationship_framework(ranking, method_semantics, bazi_pair, ziwei_pair, prior)
    motives = _relationship_motives(layers, method_semantics, prior)
    gaps = _relationship_info_gaps(framework, ranking, motives, declared_relation, prior)
    followups = _followup_questions(framework, gaps, motives, prior)
    not_like = _relationship_not_like(ranking)

    fact = _brief_from_labels(layers.get("事实层", {}).get("主要标签", []), "当前事实信号不够集中")
    structure = _brief_from_labels(layers.get("结构稳定层", {}).get("主要标签", []), "长期结构需要谨慎观察")
    dynamic = _brief_from_labels(layers.get("动态行为层", {}).get("主要标签", []), "互动过程信号不集中")
    trend = _brief_from_labels(layers.get("趋势概率层", {}).get("主要标签", []), "趋势暂不明朗")

    declared = _declared_relation_text(declared_relation)
    boundary = "这是盘面关系画像，只说明关系状态与质量，不用于证明或否认现实身份。"
    if declared != "未提供":
        boundary = f"用户已声明“{declared}”，以下结论是在该现实前提下判断状态和质量。"

    top_type = top["类型"]
    second_text = f"，其次带有“{second['类型']}”信号" if second and second["强度"] >= 0.35 else ""
    not_like_text = "；不像" + "、".join(not_like) if not_like else ""
    direct_map = {
        "已成关系框架": "更像已经成形的关系框架，重点是维系质量与现实责任。",
        "未定型吸引框架": "更像有吸引和牵引，但身份或现实框架尚未坐实。",
        "责任照护框架": "更像由照护、家庭或责任议题牵动的关系。",
        "合作权责框架": "更像由现实事务、权责或合作牵动的关系。",
        "冲突纠葛框架": "更像由冲突、旧问题或消耗牵动的关系。",
        "朋友同辈框架": "更像同辈或社交互动关系。",
    }
    user_answer = direct_map.get(framework["主框架"], "关系性质暂时只能给出大致画像。")

    stability = "偏低"
    bazi_score = int(bazi_pair.get("关系张力评分", 50)) if isinstance(bazi_pair, dict) else 50
    ziwei_score = int(ziwei_pair.get("紫微合盘评分", 50)) if isinstance(ziwei_pair, dict) else 50
    if bazi_score >= 65 and ziwei_score >= 60:
        stability = "较高"
    elif bazi_score >= 50 and ziwei_score >= 50:
        stability = "中等"
    elif bazi_score >= 40:
        stability = "偏低"
    else:
        stability = "低"

    identity_layer = _build_identity_layer(declared_relation)
    emotional_layer = _build_emotional_state_layer(ranking, motives, prior)
    quality_layer = _build_quality_layer(framework, stability, motives)
    one_sentence = f"现实身份层：{identity_layer} 情感状态层：{emotional_layer} 关系质量层：{quality_layer}{second_text}{not_like_text}"

    return {
        "一句话结论": one_sentence,
        "直接回答": user_answer,
        "现实身份层": identity_layer,
        "情感状态层": emotional_layer,
        "关系质量层": quality_layer,
        "最像关系": top,
        "主框架": framework,
        "动力": motives,
        "信息缺口": gaps,
        "推荐追问": followups,
        "候选关系排行": ranking,
        "不像关系": not_like,
        "当前状态": f"{fact}；过程上见{dynamic}。",
        "长期稳定性": f"{stability}。结构层主要是{structure}。",
        "发展趋势": f"{trend}。",
        "关键依据": [
            "六爻/六壬优先看当前是否有互动与牵连",
            "八字/紫微优先看长期结构和稳定性",
            "奇门/梅花优先看行为路径与后续趋势",
        ],
        "现实边界": boundary,
    }


def _build_relationship_meta_interpreter(
    question: str,
    declared_relation: str,
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    current_question: Dict[str, Any],
    compound_hex: Dict[str, Any],
    identification: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task = _classify_relationship_task(question, declared_relation)
    weights = _relationship_weights_for_task(task["primary_task"])
    method_semantics = _build_method_semantics(bazi_pair, ziwei_pair, current_question, compound_hex)
    layer_scores = _weighted_layer_scores(method_semantics, weights)
    layers = _semantic_layer_summary(layer_scores)
    integrated = _build_integrated_explanation(layers, identification, declared_relation)
    user_conclusion = _build_user_facing_conclusion(
        layers,
        identification,
        declared_relation,
        method_semantics,
        bazi_pair,
        ziwei_pair,
        prior,
    )

    return {
        "问题识别": task,
        "权重调度": {
            "原则": "权重不是谁更准，而是谁更适合回答本题。",
            "权重表": _weight_rows(weights),
        },
        "用户结论": user_conclusion,
        "关系先验": prior or {},
        "各术数语义标签": method_semantics,
        "任务语义汇总": layers,
        "综合断语": integrated,
        "显示建议": [
            "先展示问题识别与权重调度，让用户知道本题谁主谁辅。",
            "再逐术数展示独立分析，避免六术互相抢结论。",
            "最后展示语义汇总与综合断语，把当前状态、长期结构、动态趋势分开说。",
        ],
    }


def _format_yao_brief(yao: Dict[str, Any]) -> str:
    if not yao:
        return "未见"
    flags = []
    if yao.get("世"):
        flags.append("世")
    if yao.get("应"):
        flags.append("应")
    if yao.get("动爻"):
        flags.append(f"动化{yao.get('变支') or ''}".rstrip())
    if yao.get("旬空"):
        flags.append("旬空")
    if yao.get("月破"):
        flags.append("月破")
    flag_text = "，".join(flags)
    return f"{yao.get('爻名', yao.get('爻位'))}爻 {yao.get('干支', '')} {yao.get('六亲', '')}{'（' + flag_text + '）' if flag_text else ''}"


def _raw_liuyao_points(liuyao: Dict[str, Any]) -> Dict[str, Any]:
    if not liuyao or liuyao.get("错误"):
        return {"可用": False, "错误": liuyao.get("错误") if isinstance(liuyao, dict) else "六爻盘缺失"}
    yaos = liuyao.get("六爻", [])
    shi = next((y for y in yaos if y.get("世")), {})
    ying = next((y for y in yaos if y.get("应")), {})
    moving = [y for y in yaos if y.get("动爻")]
    empties = [f"{y.get('爻名', y.get('爻位'))}爻{y.get('六亲', '')}{y.get('干支', '')}" for y in yaos if y.get("旬空")]
    return {
        "可用": True,
        "卦名": liuyao.get("卦名", ""),
        "宫属": liuyao.get("宫属", ""),
        "月建": liuyao.get("月建", ""),
        "日建": liuyao.get("日建", ""),
        "旬空": liuyao.get("旬空地支", []),
        "世爻": _format_yao_brief(shi),
        "应爻": _format_yao_brief(ying),
        "动爻": [_format_yao_brief(y) for y in moving] or ["无动爻"],
        "落空爻": empties or ["无"],
        "判读锚点": ["世应关系", "动爻", "旬空/月破", "六亲主线"],
        "六十四卦语义": summarize_hexagram_path({"本卦": {"卦名": liuyao.get("卦名", ""), "上卦": liuyao.get("上卦", ""), "下卦": liuyao.get("下卦", "")}}, domain="relationship"),
    }


def _raw_bazi_points(bazi_pair: Dict[str, Any]) -> Dict[str, Any]:
    if not bazi_pair or bazi_pair.get("错误"):
        return {"可用": False, "错误": bazi_pair.get("错误") if isinstance(bazi_pair, dict) else "八字合盘缺失"}
    rows = []
    for row in bazi_pair.get("四柱对照", []):
        rels = row.get("天干关系", []) + row.get("地支关系", [])
        rows.append({
            "柱位": row.get("柱位", ""),
            "第一命主": row.get("第一命主", ""),
            "第二命主": row.get("第二命主", ""),
            "关系": rels,
        })
    return {
        "可用": True,
        "关系张力评分": bazi_pair.get("关系张力评分"),
        "关系张力等级": bazi_pair.get("关系张力等级"),
        "日主关系": bazi_pair.get("日主关系", {}),
        "四柱对照": rows,
        "五行互补": bazi_pair.get("五行互补", []),
        "判读锚点": ["日柱", "月柱", "冲合刑害", "五行互补"],
    }


def _raw_ziwei_points(ziwei_pair: Dict[str, Any]) -> Dict[str, Any]:
    if not ziwei_pair or ziwei_pair.get("错误"):
        return {"可用": False, "错误": ziwei_pair.get("错误") if isinstance(ziwei_pair, dict) else "紫微合盘缺失"}
    return {
        "可用": True,
        "紫微合盘评分": ziwei_pair.get("紫微合盘评分"),
        "紫微合盘等级": ziwei_pair.get("紫微合盘等级"),
        "互动线索": ziwei_pair.get("紫微互动线索", []),
        "第一命主命宫": (ziwei_pair.get("第一命主重点宫位", {}).get("命宫") or {}),
        "第一命主夫妻宫": (ziwei_pair.get("第一命主重点宫位", {}).get("夫妻") or {}),
        "第二命主命宫": (ziwei_pair.get("第二命主重点宫位", {}).get("命宫") or {}),
        "第二命主夫妻宫": (ziwei_pair.get("第二命主重点宫位", {}).get("夫妻") or {}),
        "判读锚点": ["命宫", "夫妻宫", "宫位牵动", "四化/星曜"],
    }


def _raw_qimen_points(qimen: Dict[str, Any]) -> Dict[str, Any]:
    if not qimen or qimen.get("错误"):
        return {"可用": False, "错误": qimen.get("错误") if isinstance(qimen, dict) else "奇门盘缺失"}
    highlights = []
    for gong, palace in (qimen.get("九宫") or {}).items():
        if palace.get("八神") in {"六合", "玄武", "白虎", "螣蛇", "值符"} or palace.get("八门") in {"开", "生", "死", "伤", "杜", "惊"}:
            highlights.append({
                "宫": gong,
                "方位": palace.get("方位", ""),
                "天盘": palace.get("天盘", ""),
                "地盘": palace.get("地盘", ""),
                "九星": palace.get("九星", ""),
                "八门": palace.get("八门", ""),
                "八神": palace.get("八神", ""),
            })
    return {
        "可用": True,
        "遁型": qimen.get("遁型", ""),
        "局数": qimen.get("局数", ""),
        "值符星": qimen.get("值符星", ""),
        "值使门": qimen.get("值使门", ""),
        "旬空": qimen.get("旬空", []),
        "关键宫": highlights[:8],
        "判读锚点": ["值符值使", "六合/玄武/白虎", "八门", "关键宫位"],
    }


def _raw_meihua_points(meihua: Dict[str, Any]) -> Dict[str, Any]:
    if not meihua or meihua.get("错误"):
        return {"可用": False, "错误": meihua.get("错误") if isinstance(meihua, dict) else "梅花盘缺失"}
    payload = {
        "可用": True,
        "本卦": meihua.get("本卦", {}),
        "互卦": meihua.get("互卦", {}),
        "变卦": meihua.get("变卦", {}),
        "动爻": meihua.get("动爻", ""),
        "体用分析": meihua.get("体用分析", {}),
        "判读锚点": ["本卦", "互卦", "变卦", "体用", "动爻"],
    }
    payload["六十四卦语义"] = summarize_hexagram_path(
        {
            "本卦": meihua.get("本卦", {}),
            "互卦": meihua.get("互卦", {}),
            "变卦": meihua.get("变卦", {}),
        },
        domain="relationship",
    )
    return payload


def _raw_daliuren_points(dlr: Dict[str, Any]) -> Dict[str, Any]:
    if not dlr:
        return {"可用": False, "错误": "大六壬盘缺失"}
    result = {"可用": True, "判读锚点": ["四课", "三传", "天将", "空亡", "行年"]}
    for label in ("第一命主行年盘", "第二命主行年盘"):
        pan = dlr.get(label) or {}
        if not pan or pan.get("错误"):
            result[label] = {"可用": False, "错误": pan.get("错误", "盘缺失") if isinstance(pan, dict) else "盘缺失"}
            continue
        chuan = pan.get("三传", {})
        result[label] = {
            "可用": True,
            "日干支": pan.get("日干支", ""),
            "时干支": pan.get("时干支", ""),
            "起传法": chuan.get("起传法", ""),
            "初传": chuan.get("初传", {}),
            "中传": chuan.get("中传", {}),
            "末传": chuan.get("末传", {}),
            "空亡落传": (pan.get("神煞") or {}).get("空亡落传", []),
            "本命": pan.get("本命", ""),
            "行年": pan.get("行年", ""),
        }
    return result


def _raw_compound_hex_points(compound_hex: Dict[str, Any]) -> Dict[str, Any]:
    if not compound_hex:
        return {"可用": False, "错误": "关系复合卦缺失"}
    payload = {
        "可用": True,
        "本卦": compound_hex.get("本卦", {}),
        "互卦": compound_hex.get("互卦", {}),
        "变卦": compound_hex.get("变卦", {}),
        "动爻": compound_hex.get("动爻", ""),
        "体用分析": compound_hex.get("体用分析", {}),
        "判读锚点": ["本卦", "互卦", "变卦", "体用", "动爻"],
    }
    payload["六十四卦语义"] = summarize_hexagram_path(
        {
            "本卦": compound_hex.get("本卦", {}),
            "互卦": compound_hex.get("互卦", {}),
            "变卦": compound_hex.get("变卦", {}),
        },
        domain="relationship",
    )
    return payload


def _birth_fingerprint(first: Dict[str, Any], second: Dict[str, Any], q_dt: datetime, payload: Dict[str, Any]) -> str:
    data = {
        "first": {
            "gender": first["性别"],
            "birth": first["出生时间文本"],
        },
        "second": {
            "gender": second["性别"],
            "birth": second["出生时间文本"],
        },
        "question_time": q_dt.strftime("%Y-%m-%d %H:%M"),
        "longitude": payload.get("longitude"),
        "liuyao_nums": payload.get("liuyao_nums") or [],
        "meihua_nums": payload.get("meihua_nums") or [],
        "numbers": payload.get("numbers") or [],
        "azimuth": payload.get("azimuth"),
    }
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _pillars_brief(chart: Dict[str, Any]) -> str:
    pillars = ((chart.get("八字") or {}).get("四柱") or {})
    return " ".join(str(pillars.get(pos, "")) for pos in ("年柱", "月柱", "日柱", "时柱")).strip()


def _palace_branch(chart: Dict[str, Any], palace: str) -> str:
    ziwei = chart.get("紫微斗数") or {}
    key = palace if palace.endswith("宫") else f"{palace}宫"
    data = (ziwei.get("十二宫") or {}).get(key) or (ziwei.get("宫位详情") or {}).get(key) or {}
    return str(data.get("地支", ""))


def _build_change_diagnostics(
    first: Dict[str, Any],
    second: Dict[str, Any],
    first_chart: Dict[str, Any],
    second_chart: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    current_question: Dict[str, Any],
    compound_hex: Dict[str, Any],
    q_dt: datetime,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "请求指纹": _birth_fingerprint(first, second, q_dt, payload),
        "第一命主": {
            "性别": first["性别"],
            "出生时间": first["出生时间文本"],
            "四柱": _pillars_brief(first_chart),
            "紫微命宫": _palace_branch(first_chart, "命"),
            "紫微夫妻宫": _palace_branch(first_chart, "夫妻"),
        },
        "第二命主": {
            "性别": second["性别"],
            "出生时间": second["出生时间文本"],
            "四柱": _pillars_brief(second_chart),
            "紫微命宫": _palace_branch(second_chart, "命"),
            "紫微夫妻宫": _palace_branch(second_chart, "夫妻"),
        },
        "随命主变化": {
            "八字合盘日柱": next((row for row in bazi_pair.get("四柱对照", []) if row.get("柱位") == "日柱"), {}),
            "紫微合盘评分": ziwei_pair.get("紫微合盘评分"),
            "紫微互动线索": ziwei_pair.get("紫微互动线索", [])[:5],
            "关系复合卦": {
                "本卦": (compound_hex.get("本卦") or {}).get("卦名", ""),
                "互卦": (compound_hex.get("互卦") or {}).get("卦名", ""),
                "变卦": (compound_hex.get("变卦") or {}).get("卦名", ""),
                "第二命主数": compound_hex.get("第二命主数"),
            },
            "大六壬第二行年": ((current_question.get("大六壬") or {}).get("第二命主行年盘") or {}).get("行年", ""),
        },
        "随起卦变化": {
            "说明": "六爻、奇门、梅花默认是当前问事盘，主要随起卦时间、数字、方位和经度变化；只换第二命主生日时不必然变化。",
            "六爻": (current_question.get("六爻") or {}).get("卦名", ""),
            "奇门": f"{(current_question.get('奇门遁甲') or {}).get('遁型', '')}{(current_question.get('奇门遁甲') or {}).get('局数', '')}局",
            "梅花": ((current_question.get("梅花易数") or {}).get("本卦") or {}).get("卦名", ""),
        },
    }


def _build_raw_chart_points(
    bazi_pair: Dict[str, Any],
    ziwei_pair: Dict[str, Any],
    current_question: Dict[str, Any],
    compound_hex: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "八字合盘": _raw_bazi_points(bazi_pair),
        "紫微合盘": _raw_ziwei_points(ziwei_pair),
        "六爻": _raw_liuyao_points(current_question.get("六爻") or {}),
        "奇门遁甲": _raw_qimen_points(current_question.get("奇门遁甲") or {}),
        "梅花易数": _raw_meihua_points(current_question.get("梅花易数") or {}),
        "大六壬": _raw_daliuren_points(current_question.get("大六壬") or {}),
        "关系复合卦": _raw_compound_hex_points(compound_hex),
        "说明": "此字段是解读主依据。元解释器只用于任务调度和权重提示；若摘要与原始盘要点冲突，以本字段和完整排盘为准。",
    }


def _relation_from_charts(
    first: Dict[str, Any],
    second: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Optional[Dict[str, Any]] = None,
    current_question: Optional[Dict[str, Any]] = None,
    compound_hex: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if bazi_pair.get("错误"):
        return {"细分": "盘面识别不足", "保守层级": "待判断", "置信度": 30, "证据": ["八字合盘不可用"]}

    age_diff = abs((first["出生时间"] - second["出生时间"]).days) / 365.2425
    ten_ab = bazi_pair["日主关系"]["第二命主对第一命主十神"]
    ten_ba = bazi_pair["日主关系"]["第一命主对第二命主十神"]
    evidence = [
        f"第二命主对第一命主为{ten_ab}",
        f"第一命主对第二命主为{ten_ba}",
        f"年龄差约{age_diff:.1f}年",
    ]
    scores = {"亲密": 0, "同辈": 0, "照护": 0, "合作": 0, "冲突": 0, "亲缘": 0}
    strong_identity_anchors = 0

    if first["性别"] != second["性别"]:
        scores["亲密"] += 2
        evidence.append("双方为异性：只作为可能亲密/合作互动背景，不作为身份判断")
    if age_diff <= 12:
        scores["同辈"] += 5
        evidence.append("年龄差处于同代互动范围，可对应朋友、同事、伴侣等多种关系")
    elif age_diff >= 14:
        scores["照护"] += 5
        scores["亲缘"] += 3
        evidence.append("年龄差较大，长幼/照护/权威关系象增强")

    if ten_ab in {"正印", "偏印"} or ten_ba in {"正印", "偏印"}:
        scores["照护"] += 5
        evidence.append("十神见印，带照护、依赖、承接或庇护色彩")
    if ten_ab in {"食神", "伤官"} or ten_ba in {"食神", "伤官"}:
        scores["照护"] += 3
        scores["同辈"] += 2
        evidence.append("十神见食伤，带表达、付出、欣赏或晚辈互动色彩")
    if ten_ab in {"正财", "偏财", "正官", "七杀"} or ten_ba in {"正财", "偏财", "正官", "七杀"}:
        scores["合作"] += 5
        scores["亲密"] += 2
        evidence.append("十神见财官，存在现实资源、责任、规则或亲密吸引象")

    day_row = next((row for row in bazi_pair.get("四柱对照", []) if row.get("柱位") == "日柱"), {})
    month_row = next((row for row in bazi_pair.get("四柱对照", []) if row.get("柱位") == "月柱"), {})
    day_zhi_rel = day_row.get("地支关系", [])
    month_zhi_rel = month_row.get("地支关系", [])
    if any(rel in day_zhi_rel for rel in {"六合", "六冲", "六害", "刑"}):
        scores["亲密"] += 4
        if any(rel in day_zhi_rel for rel in {"六冲", "六害", "刑"}):
            scores["冲突"] += 4
        evidence.append(f"双方日支有强互动：{','.join(day_zhi_rel)}；此为关系张力，不直接等同身份")
    if any("半合" in rel or rel == "六合" for rel in day_zhi_rel):
        scores["亲密"] += 3
        evidence.append(f"日支合象：{','.join(day_zhi_rel)}，说明有牵引或共鸣")
    if any(rel in month_zhi_rel for rel in {"六合", "六冲", "六害", "刑"}):
        scores["同辈"] += 2
        scores["冲突"] += 2 if any(rel in month_zhi_rel for rel in {"六冲", "六害", "刑"}) else 0
        evidence.append(f"月支互动为{','.join(month_zhi_rel)}，显示生活背景或相处模式有牵连")

    current_scores, current_evidence, current_anchors = _current_relation_signals(current_question)
    for key, value in current_scores.items():
        scores[key] += value
    evidence.extend(current_evidence)
    strong_identity_anchors += current_anchors

    ziwei_scores, ziwei_evidence, ziwei_anchors = _ziwei_relation_signals(ziwei_pair)
    for key, value in ziwei_scores.items():
        scores[key] += value
    evidence.extend(ziwei_evidence)
    strong_identity_anchors += ziwei_anchors

    compound_scores, compound_evidence, compound_anchors = _compound_relation_signals(compound_hex)
    for key, value in compound_scores.items():
        scores[key] += value
    evidence.extend(compound_evidence)
    strong_identity_anchors += compound_anchors

    top_key, top_score = max(scores.items(), key=lambda kv: kv[1])
    confidence = min(62, 42 + top_score)
    descriptions = {
        "亲密": "亲密牵引较明显，但不足以单独断定现实身份",
        "同辈": "平辈/社交/同圈层互动较明显",
        "照护": "照护、承接、长幼或依赖色彩较明显",
        "合作": "合作、资源、权责或现实事务牵连较明显",
        "冲突": "关系中摩擦、竞争或压力信号较明显",
        "亲缘": "亲缘/长幼方向有提示，但需现实证据确认",
    }

    if strong_identity_anchors >= 3 and top_key == "亲密":
        fine = "伴侣/婚恋象较强，但仍需用户声明或现实关系确认"
        confidence = 68
    else:
        fine = descriptions[top_key]

    return {
        "细分": fine,
        "保守层级": "关系画像描述，不作现实身份断言",
        "置信度": confidence,
        "证据": evidence,
        "候选评分": scores,
    }


def _declared_relation_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "自动识别":
        return "未提供"
    return text


def _relation_identification(
    question: str,
    declared_relation: str,
    first: Dict[str, Any],
    second: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    ziwei_pair: Optional[Dict[str, Any]] = None,
    current_question: Optional[Dict[str, Any]] = None,
    compound_hex: Optional[Dict[str, Any]] = None,
    context: str = "",
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    semantic = _relation_from_question(question, first, second, context)
    chart = _relation_from_charts(first, second, bazi_pair, ziwei_pair, current_question, compound_hex)
    declared = _declared_relation_text(declared_relation)

    if prior and _prior_suppresses_partner(prior):
        scores = chart.get("候选评分") or {}
        if scores.get("亲密", 0) > scores.get("照护", 0):
            scores["照护"] = scores.get("照护", 0) + (6 if prior.get("代际年龄差") else 3)
            scores["合作"] = scores.get("合作", 0) + 2
            scores["亲密"] = max(0, scores.get("亲密", 0) - (6 if prior.get("代际年龄差") else 3))
            chart["候选评分"] = scores
            chart["证据"] = (chart.get("证据") or []) + [
                "人口学先验压制婚恋默认翻译，财官/合和象优先读作资源、责任、照护或权责牵连"
            ]
            if scores.get("照护", 0) >= scores.get("亲密", 0):
                chart["细分"] = "照护、承接、长幼或依赖色彩较明显"
                chart["置信度"] = max(chart.get("置信度", 0), 58)

    context_conflicts = (prior or {}).get("上下文冲突") or []

    if context_conflicts:
        fine = "补充信息与命主资料冲突，疑似上一盘上下文残留"
        coarse = "需清理补充事实/声明关系后重新判断"
        confidence = 40
        source = "上下文冲突检测"
    elif declared != "未提供":
        fine = declared
        coarse = "用户声明关系"
        confidence = max(65, chart["置信度"])
        source = "用户声明+盘面描述"
    elif semantic["置信度"] >= 65:
        fine = semantic["细分"]
        coarse = semantic["保守层级"]
        confidence = semantic["置信度"]
        source = "问题语义"
    else:
        fine = chart["细分"]
        coarse = chart["保守层级"]
        confidence = chart["置信度"]
        source = "盘面关系画像"

    consistency = "用户未声明关系，系统只输出盘面关系画像；除非证据极强，不作现实身份断言"
    if context_conflicts:
        consistency = "补充事实与当前命主资料冲突，系统已停止沿用该补充事实，需清理上一盘上下文"
    elif declared != "未提供":
        consistency = "用户已声明关系，系统以声明为现实关系前提，盘面只作状态与互动描述"

    return {
        "用户声明关系": declared,
        "问题语义倾向": semantic,
        "盘面识别倾向": chart,
        "细粒度推断": f"{fine}（{confidence}%）",
        "关系描述": fine,
        "保守层级": f"{coarse}（置信度 {confidence}%）",
        "主要来源": source,
        "一致性": consistency,
        "用途边界": "关系识别盘只作为合盘参考条件，不作为现实身份、血缘、法律或医学事实证明。",
    }


def _relationship_hexagram(
    first: Dict[str, Any],
    second: Dict[str, Any],
    divination_dt: datetime,
    numbers: Optional[List[int]] = None,
    azimuth: Optional[float] = None,
) -> Dict[str, Any]:
    a_dt = first["出生时间"]
    b_dt = second["出生时间"]
    a_num = a_dt.year + a_dt.month + a_dt.day + a_dt.hour + a_dt.minute
    b_num = b_dt.year + b_dt.month + b_dt.day + b_dt.hour + b_dt.minute
    q_num = divination_dt.year + divination_dt.month + divination_dt.day + divination_dt.hour + divination_dt.minute
    extra = sum(int(n) for n in (numbers or []) if n is not None)
    if azimuth is not None:
        extra += int(round(float(azimuth)))

    shang = XT2GUA[a_num % 8 or 8]
    xia = XT2GUA[b_num % 8 or 8]
    dong = (q_num + extra) % 6 or 6
    bian_shang, bian_xia = get_bian_gua(shang, xia, dong)
    hu_shang, hu_xia = get_hu_gua(gua_to_yao(shang), gua_to_yao(xia))

    return {
        "算法说明": "系统关系专用复合卦：第一命主出生数定上卦，第二命主出生数定下卦，起卦时间及可选数字/方位定动爻。此为产品内合参算法，不冒充传统固定流派。",
        "第一命主数": a_num,
        "第二命主数": b_num,
        "起卦动爻数": q_num + extra,
        "本卦": {"上卦": shang, "下卦": xia, "卦名": _hexagram_name(shang, xia)},
        "互卦": {"上卦": hu_shang, "下卦": hu_xia, "卦名": _hexagram_name(hu_shang, hu_xia)},
        "变卦": {"上卦": bian_shang, "下卦": bian_xia, "卦名": _hexagram_name(bian_shang, bian_xia)},
        "动爻": dong,
        "体用分析": analyze_ti_yong(shang, xia, dong),
    }


def _detect_high_risk(question: str) -> Dict[str, Any]:
    hits = []
    for category, words in HIGH_RISK_KEYWORDS.items():
        if any(word in question for word in words):
            hits.append(category)
    if not hits:
        return {"命中类别": [], "提示": "常规关系问题，仍需提示术数结论仅供参考。"}
    return {
        "命中类别": hits,
        "提示": "本问题涉及重大现实后果。术数可给出倾向判断，但不能替代亲子鉴定、医疗诊断、法律意见、投资建议或其他专业证据。",
    }


def _build_subject_chart(subject: Dict[str, Any], longitude: float) -> Dict[str, Any]:
    dt = subject["出生时间"]
    return {
        "性别": subject["性别"],
        "出生时间": subject["出生时间文本"],
        "八字": _safe_call(bazi_pa_pan, dt.year, dt.month, dt.day, dt.hour, dt.minute, longitude, subject["性别"]),
        "紫微斗数": _safe_call(ziwei_pa_pan, dt.year, dt.month, dt.day, dt.hour, dt.minute, longitude, subject["性别"]),
    }


def relationship_divination(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a complete relationship compound chart from request-like data."""
    question = str(payload.get("event") or payload.get("问题") or "").strip()
    if not question:
        raise ValueError("所问问题不能为空")
    context = _relationship_context_text(payload)

    first_raw = payload.get("first_subject") or payload.get("第一命主")
    second_raw = payload.get("second_subject") or payload.get("第二命主")
    first = _normalize_subject(first_raw, "第一命主")
    second = _normalize_subject(second_raw, "第二命主")

    q_dt = _validate_datetime("起卦", {
        "year": payload.get("year"),
        "month": payload.get("month"),
        "day": payload.get("day"),
        "hour": payload.get("hour"),
        "minute": payload.get("minute"),
    })
    longitude = _as_float(payload.get("longitude"), "经度", 120.0)
    latitude = _as_float(payload.get("latitude"), "纬度", 30.0)
    declared_relation = payload.get("declared_relation") or payload.get("relation_type") or payload.get("用户声明关系") or ""
    prior_context = _combined_question_text(question, _combined_question_text(str(declared_relation or ""), context))

    liuyao_nums = payload.get("liuyao_nums") or []
    meihua_nums = payload.get("meihua_nums") or []
    compound_nums = payload.get("numbers") or []
    azimuth = payload.get("azimuth")
    azimuth_val = None if azimuth in (None, "") else float(azimuth)

    first_chart = _build_subject_chart(first, longitude)
    second_chart = _build_subject_chart(second, longitude)
    bazi_pair = _bazi_pair_summary(first_chart, second_chart)
    ziwei_pair = _ziwei_pair_summary(first_chart, second_chart)
    prior = _demographic_prior(first, second, prior_context)

    if liuyao_nums and len(liuyao_nums) >= 2:
        liuyao_chart = _safe_call(
            liuyao_pa_pan_num,
            int(liuyao_nums[0]),
            int(liuyao_nums[1]),
            year=q_dt.year,
            month=q_dt.month,
            day=q_dt.day,
            hour=q_dt.hour,
            minute=q_dt.minute,
            longitude=longitude,
        )
    else:
        liuyao_chart = _safe_call(liuyao_pa_pan, q_dt.year, q_dt.month, q_dt.day, q_dt.hour, q_dt.minute, longitude)

    if meihua_nums and len(meihua_nums) >= 2:
        meihua_chart = _safe_call(
            meihua_pa_pan,
            q_dt.year,
            q_dt.month,
            q_dt.day,
            q_dt.hour,
            q_dt.minute,
            longitude,
            method="number",
            num1=int(meihua_nums[0]),
            num2=int(meihua_nums[1]),
        )
    elif azimuth_val is not None:
        meihua_chart = _safe_call(
            meihua_pa_pan,
            q_dt.year,
            q_dt.month,
            q_dt.day,
            q_dt.hour,
            q_dt.minute,
            longitude,
            method="fangwei",
            azimuth=azimuth_val,
        )
    else:
        meihua_chart = _safe_call(meihua_pa_pan, q_dt.year, q_dt.month, q_dt.day, q_dt.hour, q_dt.minute, longitude)

    current_question = {
        "六爻": liuyao_chart,
        "奇门遁甲": _safe_call(qimen_pa_pan, q_dt.year, q_dt.month, q_dt.day, q_dt.hour, q_dt.minute, longitude),
        "梅花易数": meihua_chart,
        "大六壬": {
            "第一命主行年盘": _safe_call(
                daliuren_pa_pan,
                q_dt.year,
                q_dt.month,
                q_dt.day,
                q_dt.hour,
                q_dt.minute,
                longitude,
                first["出生时间"].year,
                first["性别"],
            ),
            "第二命主行年盘": _safe_call(
                daliuren_pa_pan,
                q_dt.year,
                q_dt.month,
                q_dt.day,
                q_dt.hour,
                q_dt.minute,
                longitude,
                second["出生时间"].year,
                second["性别"],
            ),
        },
    }

    compound_hex = _relationship_hexagram(
        first,
        second,
        q_dt,
        numbers=[*liuyao_nums, *meihua_nums, *compound_nums],
        azimuth=azimuth_val,
    )
    identification = _relation_identification(
        question,
        declared_relation,
        first,
        second,
        bazi_pair,
        ziwei_pair,
        current_question,
        compound_hex,
        context,
        prior,
    )
    logger.info(
        "REL identify selected=%s layer=%s scores=%s",
        identification.get("细粒度推断"),
        identification.get("主要来源"),
        (identification.get("盘面识别倾向") or {}).get("候选评分", {}),
    )
    meta_interpreter = _build_relationship_meta_interpreter(
        question,
        declared_relation,
        bazi_pair,
        ziwei_pair,
        current_question,
        compound_hex,
        identification,
        prior,
    )
    raw_chart_points = _build_raw_chart_points(bazi_pair, ziwei_pair, current_question, compound_hex)
    change_diagnostics = _build_change_diagnostics(
        first,
        second,
        first_chart,
        second_chart,
        bazi_pair,
        ziwei_pair,
        current_question,
        compound_hex,
        q_dt,
        payload,
    )
    high_risk = _detect_high_risk(question)

    return {
        "问题": question,
        "补充信息": context,
        "用户声明关系": _declared_relation_text(declared_relation),
        "时空坐标": {
            "起卦时间": q_dt.strftime("%Y-%m-%d %H:%M"),
            "经度": longitude,
            "纬度": latitude,
            "城市估算": "",
        },
        "第一命主": first_chart,
        "第二命主": second_chart,
        "双人本命合盘": {
            "八字合盘": bazi_pair,
            "紫微合盘": ziwei_pair,
        },
        "关系识别盘": identification,
        "元解释器": meta_interpreter,
        "原始盘要点": raw_chart_points,
        "排盘变化校验": change_diagnostics,
        "当前问事盘": current_question,
        "关系复合卦": compound_hex,
        "综合验证": {
            "高风险主题": high_risk,
            "合参顺序": [
                "先读取原始盘面，确认八字、紫微、六爻、奇门、梅花、大六壬、关系复合卦的实际字段",
                "再由元解释器识别关系子任务与语义主轴，并给出动态权重",
                "再按任务权重决定六术在本题中的主辅地位",
                "各术数只在自身擅长层面给出语义标签；若摘要与原盘冲突，以原盘为准",
                "最后把当前状态、长期结构、动态趋势、底层因果分层汇总",
                "关系复合卦作为双人关系场的补充校验",
            ],
            "免责声明": "所有结论均为民俗术数研究与娱乐参考，不能替代现实证据、亲子鉴定、医疗诊断、法律意见或其他专业判断。",
        },
    }



def _format_method_signals(meta):
    """Extract the key signals from each method into concise text lines for the prompt."""
    semantics = meta.get("各术数语义标签", {})
    method_order = ["六爻", "八字", "紫微", "奇门", "梅花", "大六壬", "关系复合卦"]
    lines = []
    for method in method_order:
        info = semantics.get(method, {})
        labels = info.get("标签", [])
        if not labels:
            lines.append(f"{method}：盘面不可用或信号不集中")
            continue
        top = sorted(labels, key=lambda s: s.get("强度", 0), reverse=True)[:3]
        parts = [f"{s['标签']}({s['方向']})" for s in top]
        lines.append(f"{method}：{' / '.join(parts)}")
    return "\n".join(lines)


def _method_section_template(method: str, summary: str, evidence: List[str], conclusion: str) -> str:
    evidence_text = "\n".join(f"- {item}" for item in (evidence or [])[:4]) or "- 证据不集中"
    return (
        f"### {method}\n"
        f"**内容**：{summary or '信号不集中'}\n"
        f"**证据**：\n{evidence_text}\n"
        f"**论断**：**{conclusion or '暂无明确结论'}**\n"
    )

def generate_relationship_prompt(compound_result):
    result_text = json.dumps(compound_result, ensure_ascii=False, indent=2, default=str)
    question = compound_result.get('问题', '')
    meta = compound_result.get('元解释器', {})
    raw_points = compound_result.get('原始盘要点', {})
    risk = compound_result.get('综合验证', {}).get('高风险主题', {})
    task = meta.get('问题识别', {})
    user_conc = meta.get('用户结论', {})
    layers = meta.get('任务语义汇总', {})
    prior = meta.get('关系先验', {})
    context = compound_result.get('补充信息', '')

    top_relation = user_conc.get('最像关系', {})
    ranking = user_conc.get('候选关系排行', [])
    not_like = user_conc.get('不像关系', [])
    direct_answer = user_conc.get('直接回答', '')
    current_state = user_conc.get('当前状态', '')
    stability = user_conc.get('长期稳定性', '')
    trend = user_conc.get('发展趋势', '')
    identity_layer = user_conc.get('现实身份层', '')
    emotional_layer = user_conc.get('情感状态层', '')
    quality_layer = user_conc.get('关系质量层', '')

    ranking_text = ''
    if ranking:
        ranking_lines = []
        for i, r in enumerate(ranking[:3]):
            evidence_text = '；'.join(r.get('依据', [])[:2])
            ranking_lines.append(
                '  %d. %s（%s，强度%s）—— %s' % (i + 1, r['类型'], r['等级'], r['强度'], evidence_text)
            )
        ranking_text = '\n'.join(ranking_lines)

    layer_text = ''
    for layer_name in ['事实层', '关系性质层', '结构稳定层', '动态行为层', '趋势概率层', '底层因果层']:
        l = layers.get(layer_name, {})
        tags = '、'.join(l.get('主要标签', [])[:3]) or '信号不集中'
        layer_text += '  %s：%s\n' % (layer_name, tags)

    risk_hits = risk.get('命中类别', [])
    risk_note = ''
    if risk_hits:
        risk_note = '⚠ 本问题涉及' + '、'.join(risk_hits) + '，需提示用户以现实证据为准。'

    not_like_text = '、'.join(not_like) if not_like else '无明显排除项'
    task_name = task.get('任务名称', '')
    task_desc = task.get('任务说明', '')
    top_type = top_relation.get('类型', '')
    top_level = top_relation.get('等级', '')
    top_strength = top_relation.get('强度', '')

    prompt = '你是一位传统术数关系合盘解读助手。请做全息解盘：先从八字、紫微、六爻、奇门、梅花、大六壬、关系复合卦逐层展开，最后再给综合结论。\n'
    prompt += '\n'
    prompt += '# 用户问题\n'
    prompt += question + '\n'
    if context:
        prompt += '补充事实/追问回答：' + context + '\n'
    prompt += '\n'
    prompt += '# 系统任务摘要（只作导航，必须用原始盘核验）\n'
    prompt += '问题类型：' + task_name + '（' + task_desc + '）\n'
    prompt += '关系判断：' + top_type + '（可信度等级：' + top_level + '，强度：' + str(top_strength) + '）\n'
    prompt += '不像关系：' + not_like_text + '\n'
    prompt += '直接回答：' + direct_answer + '\n'
    prompt += '现实身份层：' + identity_layer + '\n'
    prompt += '情感状态层：' + emotional_layer + '\n'
    prompt += '关系质量层：' + quality_layer + '\n'
    prompt += '当前状态：' + current_state + '\n'
    prompt += '长期稳定性：' + stability + '\n'
    prompt += '发展趋势：' + trend + '\n'
    prompt += '关系先验：' + json.dumps(prior, ensure_ascii=False, default=str) + '\n'
    prompt += '注意：以上摘要不是最终判词。若换第二命主后八字、紫微、复合卦、大六壬行年出现差异，必须围绕这些差异重判，不得套用上一盘或固定模板。\n'
    prompt += '\n'
    prompt += '# 原始盘要点（解读主依据，必须优先读取）\n'
    prompt += json.dumps(raw_points, ensure_ascii=False, indent=2, default=str) + '\n'
    prompt += '\n'
    prompt += '# 候选关系排行\n'
    prompt += ranking_text + '\n'
    prompt += '\n'
    prompt += '# 主框架与关系库参考\n'
    prompt += json.dumps(meta.get('用户结论', {}).get('主框架', {}), ensure_ascii=False, indent=2, default=str) + '\n'
    prompt += json.dumps(_taxonomy_summary(), ensure_ascii=False, indent=2, default=str) + '\n'
    prompt += '\n'
    prompt += '# 信息缺口与追问建议\n'
    prompt += json.dumps(meta.get('用户结论', {}).get('信息缺口', []), ensure_ascii=False, indent=2, default=str) + '\n'
    prompt += json.dumps(meta.get('用户结论', {}).get('推荐追问', []), ensure_ascii=False, indent=2, default=str) + '\n'
    prompt += '\n'
    prompt += '# 六层语义标签\n'
    prompt += layer_text
    prompt += '\n'
    prompt += '# 各术数关键信号\n'
    prompt += _format_method_signals(meta) + '\n'
    prompt += '\n'
    prompt += '# 完整排盘数据\n'
    prompt += result_text + '\n'
    prompt += '\n'
    prompt += risk_note + '\n'
    prompt += '\n'
    prompt += '# 硬性规则\n'
    prompt += '1. 不要开头先给最终结论；先逐盘解读，最后集中给综合结论。\n'
    prompt += '2. 原始盘要点和完整排盘是最高优先级；元解释器只作任务调度和权重参考，不能压过原始盘差异。\n'
    prompt += '3. 如果元解释器摘要与原始排盘冲突，必须以原始排盘为准，并说明“按原盘看应修正为……”。\n'
    prompt += '4. 禁止编造原盘没有的字段：不得写错四柱、日主、卦名、世应、动爻、三传、复合卦。\n'
    prompt += '5. 未声明现实关系时，只能说“盘面关系画像”，不能证明现实身份；但也不能反向否定现实身份，例如不能写“不是夫妻/不是公开伴侣”。\n'
    prompt += '6. 每一行结论最多给两个判断，不要一串标签。\n'
    prompt += '7. 八字、紫微、六爻、奇门、梅花、大六壬、关系复合卦都要单独成段分析。\n'
    prompt += '8. 专业术语可以出现，但每个术语后要翻译成人话。\n'
    prompt += '9. 如果短期状态与长期结构不一致，直接说“当前如何、长期如何”，不要和稀泥。\n'
    prompt += '10. 输出要信息充分，建议 1200-2000 字；不要只写三小段。\n'
    prompt += '11. 六爻、奇门、梅花属于当前问事盘；只换第二命主生日时，它们不变不能证明两段关系一样。关系性质必须重点核验八字合盘、紫微合盘、关系复合卦和大六壬第二命主行年。\n'
    prompt += '12. 最终结论必须分成三层：“现实身份层 / 情感状态层 / 关系质量层”。关系质量标签不得覆盖现实身份标签；冲突、消耗、阻滞只能说明质量，不能写成“不是夫妻/不是伴侣”。\n'
    prompt += '13. 如果身份、责任来源或阻滞来源不能确认，必须列出信息缺口和一个定向追问卦问题；追问卦只用于消歧，不能反客为主推翻原盘结构。\n'
    prompt += '14. 若关系先验显示“大年龄差/代际年龄差/同性且未声明婚恋/声明亲子”，六爻妻财、官鬼、六合、天后等象必须优先翻译为资源、责任、照护、管束、依赖、权责或往来；除非补充事实明确声明婚恋，不得默认写成暧昧、恋人、男女朋友。\n'
    prompt += '15. 若补充事实或用户声明已经给出现实关系（如儿子、夫妻、同事），不得用盘面反向否定现实身份；只分析这段关系的状态、质量、问题和趋势。\n'
    prompt += '16. 若补充事实与命主性别或年龄顺序冲突，优先判定为上一盘上下文残留或输入未清理，不得继续沿用冲突的亲缘/性别称谓。\n'
    prompt += '17. 原始盘要点中的“六十四卦语义”是候选义筛选器：必须结合问事类型、世应/体用/动爻和其他术数，只取 2-3 个最强解释，不得机械照抄全部候选义。\n'
    prompt += '18. 未声明现实关系时，也必须自动判断情感情况：明确写“亲密牵连明显/有一定吸引/情感弱而事务强/偏照护责任”等，不得只写冲突或结构。\n'
    prompt += '19. 用户问题原文不得改写、净化或替换；即使表达粗俗，也按原文识别并直接回答，但结论必须保留双方自愿、现实边界和风险提示。\n'
    prompt += '20. 输出格式必须稳定：每段只用“## 标题 / **内容：** / **论断：**”三层写；不要再混用【标题】；“论断”必须加粗，且每段不超过 2 个结论句。\n'
    prompt += '\n'
    prompt += '# 输出\n'
    prompt += '## 问题识别\n**内容：** 简要说明本题问的是什么，不超过两行。\n**论断：** **只给任务类型和判定边界。**\n'
    prompt += '## 八字合盘\n**内容：** 长期结构、冲合刑害、稳定性。\n**论断：** **写清主象与辅象，不要只报术语。**\n'
    prompt += '## 紫微合盘\n**内容：** 命宫/夫妻宫牵动、人生结构和关系质量。\n**论断：** **优先说明宫位牵动和关系轴心。**\n'
    prompt += '## 六爻\n**内容：** 当前事实状态、谁主动、谁保留、关系是否有变化。\n**论断：** **直接给当前层的判断。**\n'
    prompt += '## 奇门遁甲\n**内容：** 行为路径、阻力、暗线、主动被动。\n**论断：** **说明卡点和推进方向。**\n'
    prompt += '## 梅花易数\n**内容：** 趋势概率、关系是否向合或需变革。\n**论断：** **说明趋势，不要泛泛而谈。**\n'
    prompt += '## 大六壬\n**内容：** 过程因果、起因-发展-结果链条。\n**论断：** **突出过程线而不是术语堆叠。**\n'
    prompt += '## 关系复合卦\n**内容：** 双人关系场校验。\n**论断：** **说明关系场是增益、阻滞还是消耗。**\n'
    prompt += '## 综合验证\n**内容：** 把各术数合在一起，说明哪些是主象、哪些是辅象、哪些是风险。\n**论断：** **只保留最关键的合参结论。**\n'
    prompt += '## 最终结论\n**内容：** 必须分行写：现实身份层、情感状态层、关系质量层、当前状态、长期稳定性、趋势。\n**论断：** **用一句话给最终主判断，再用一句话给现实边界。**\n'
    prompt += '## 信息缺口与追问\n**内容：** 如果仍有歧义，列出需要补证的点和推荐追问卦问题。\n**论断：** **只给最必要的追问。**\n'
    prompt += '## 建议\n**内容：** 给 3-5 条具体建议。\n**论断：** **建议要短、具体、可执行。**\n'
    return prompt


def generate_relationship_followup_prompt(
    compound_result: Dict[str, Any],
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    message = str(message or "").strip()
    history = history or []
    prompt = '你是一位传统术数关系合盘解读助手。现在用户在同一张关系复合盘下继续追问或补充事实。\n\n'
    prompt += '# 本轮追问/补充事实\n'
    prompt += message + '\n\n'
    if history:
        prompt += '# 已有追问记录\n'
        prompt += json.dumps(history[-6:], ensure_ascii=False, indent=2, default=str) + '\n\n'
    prompt += '# 原始关系复合盘\n'
    prompt += json.dumps(compound_result, ensure_ascii=False, indent=2, default=str) + '\n\n'
    prompt += '# 硬性规则\n'
    prompt += '1. 本轮是“沿用原盘继续解读”，不得重新起卦，不得改变原盘中的起卦时间、六爻卦名、世应、动爻、奇门局、梅花卦、大六壬三传和关系复合卦。\n'
    prompt += '2. 用户补充事实优先用于修正现实语境；不能用盘面反向否定用户已说明的现实关系。\n'
    prompt += '3. 若追问只是补充身份、背景、阻力来源或对方态度，必须在原盘各术数信号内解释，不要要求用户重新起盘。\n'
    prompt += '4. 只有用户明确提出新的独立时效问题，例如“未来三个月会不会复合/是否结婚/是否联系”，才提醒可另起追问卦；本轮仍先按原盘给可回答部分。\n'
    prompt += '5. 大年龄差、同性未声明婚恋、亲子或照护语境下，妻财、官鬼、六合、天后优先解释为资源、责任、照护、管束、依赖、权责或往来，不默认写成暧昧/恋人。\n'
    prompt += '6. 输出要短于完整解盘，重点回答用户本轮问题；如补充事实改变了关系画像，需要给出“修正后的最终判断”。\n'
    prompt += '7. 用户追问原文不得改写、净化或替换；即使表达粗俗，也按原文识别并直接回答，但涉及亲密/性关系时必须保留双方自愿、边界和风险提示。\n'
    prompt += '8. 若用户补充“这是夫妻/亲子/同事”等现实关系，只能把它作为现实身份层前提；不得用冲突、阻滞、消耗等质量标签反向否定身份，也不得抹掉原盘中的亲密/照护/权责信号。\n'
    prompt += '9. 修正结论必须分成三层：“现实身份层 / 情感状态层 / 关系质量层”。\n'
    prompt += '10. 若原盘带有“六十四卦语义”，只可把它当作候选义筛选器，必须结合本轮补充事实与原盘选出 2-3 个最强解释，不可重新起义或机械抄全量候选义。\n'
    prompt += '11. 输出格式必须稳定：每段都按“## 标题 / **内容：** / **论断：**”写；论断必须加粗。\n\n'
    prompt += '# 输出格式\n'
    prompt += '## 追问识别\n**内容：** 说明本轮是补充事实、同盘追问，还是建议另起追问卦。\n**论断：** **一句话说明是否沿用原盘。**\n'
    prompt += '## 同盘回答\n**内容：** 直接回答用户本轮问题，保留用户追问原意，不替换用户问题。\n**论断：** **给出本轮最关键判断。**\n'
    prompt += '## 原盘依据\n**内容：** 列出 3-6 条对应的原盘证据。\n**论断：** **说明这些证据共同指向什么。**\n'
    prompt += '## 修正结论\n**内容：** 必须分行写：现实身份层、情感状态层、关系质量层；如未改变关系画像，则说明原结论保持。\n**论断：** **给出修正或维持后的最终判断。**\n'
    prompt += '## 下一步\n**内容：** 只给 1-3 条具体建议或下一追问方向。\n**论断：** **点明下一步最该做什么。**\n'
    return prompt


def stream_relationship_followup(
    compound_result: Dict[str, Any],
    message: str,
    history: Optional[List[Dict[str, Any]]],
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str = "",
    provider_type: str = "openai_compatible",
    lenient_mode: bool = False,
):
    system_msg = system_prompt or "你是一位严谨、客观的传统术数关系合盘分析顾问。"
    system_msg = f"{system_msg.rstrip()}\n\n{FINAL_ANSWER_PROMPT.strip()}"
    if lenient_mode:
        system_msg = f"{system_msg.rstrip()}\n\n{LENIENT_MODE_PROMPT.strip()}"
    messages = [
        {"role": "system", "content": system_msg},
        {
            "role": "user",
            "content": f"{NO_THINK_USER_PREFIX}\n{generate_relationship_followup_prompt(compound_result, message, history)}",
        },
    ]
    if provider_type == "ollama_native":
        yield from _stream_ollama_native(messages, api_key, base_url, model)
    else:
        yield from _stream_openai_compatible(messages, api_key, base_url, model)


def build_relationship_messages(
    compound_result: Dict[str, Any],
    system_prompt: str = "",
    lenient_mode: bool = False,
) -> List[Dict[str, str]]:
    system_msg = system_prompt or "你是一位严谨、客观的传统术数关系合盘分析顾问。"
    system_msg = f"{system_msg.rstrip()}\n\n{FINAL_ANSWER_PROMPT.strip()}"
    if lenient_mode:
        system_msg = f"{system_msg.rstrip()}\n\n{LENIENT_MODE_PROMPT.strip()}"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"{NO_THINK_USER_PREFIX}\n{generate_relationship_prompt(compound_result)}"},
    ]


def stream_relationship_interpret(
    compound_result: Dict[str, Any],
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str = "",
    provider_type: str = "openai_compatible",
    lenient_mode: bool = False,
):
    messages = build_relationship_messages(compound_result, system_prompt, lenient_mode)
    if provider_type == "ollama_native":
        yield from _stream_ollama_native(messages, api_key, base_url, model)
    else:
        yield from _stream_openai_compatible(messages, api_key, base_url, model)
