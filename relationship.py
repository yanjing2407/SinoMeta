# -*- coding: utf-8 -*-
"""Relationship compound chart orchestration.

This module builds a structured relationship chart from two natal subjects plus
one current divination time.  The relationship recognizer intentionally uses a
weak-description policy: when the user has not declared the real relation, it
describes relationship signals instead of asserting a social/legal identity.
"""

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


def _relation_from_question(question: str, first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    text = question or ""
    lowered = text.lower()
    evidence = []
    age_diff = abs((first["出生时间"] - second["出生时间"]).days) / 365.2425

    def has_any(words: List[str]) -> bool:
        return any(w in text or w.lower() in lowered for w in words)

    if has_any(["亲生", "亲子", "血缘", "父子", "父女", "母子", "母女", "孩子", "儿子", "女儿"]):
        evidence.append("问题包含亲缘/子女关系关键词")
        return {
            "细分": _parent_child_label(first, second, age_diff),
            "保守层级": "直系亲缘/长辈晚辈关系",
            "置信度": 82 if age_diff >= 14 else 68,
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


def _relation_from_charts(
    first: Dict[str, Any],
    second: Dict[str, Any],
    bazi_pair: Dict[str, Any],
    current_question: Optional[Dict[str, Any]] = None,
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
    current_question: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    semantic = _relation_from_question(question, first, second)
    chart = _relation_from_charts(first, second, bazi_pair, current_question)
    declared = _declared_relation_text(declared_relation)

    if declared != "未提供":
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
    if declared != "未提供":
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

    liuyao_nums = payload.get("liuyao_nums") or []
    meihua_nums = payload.get("meihua_nums") or []
    compound_nums = payload.get("numbers") or []
    azimuth = payload.get("azimuth")
    azimuth_val = None if azimuth in (None, "") else float(azimuth)

    first_chart = _build_subject_chart(first, longitude)
    second_chart = _build_subject_chart(second, longitude)
    bazi_pair = _bazi_pair_summary(first_chart, second_chart)
    ziwei_pair = _ziwei_pair_summary(first_chart, second_chart)

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

    identification = _relation_identification(question, declared_relation, first, second, bazi_pair, current_question)
    logger.info(
        "REL identify selected=%s layer=%s scores=%s",
        identification.get("细粒度推断"),
        identification.get("主要来源"),
        (identification.get("盘面识别倾向") or {}).get("候选评分", {}),
    )

    compound_hex = _relationship_hexagram(
        first,
        second,
        q_dt,
        numbers=[*liuyao_nums, *meihua_nums, *compound_nums],
        azimuth=azimuth_val,
    )
    high_risk = _detect_high_risk(question)

    return {
        "问题": question,
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
        "当前问事盘": current_question,
        "关系复合卦": compound_hex,
        "综合验证": {
            "高风险主题": high_risk,
            "合参顺序": [
                "先看用户声明与问题语义，确认是否已有现实关系前提",
                "再看两位个体命盘，判断长期结构",
                "再看八字合盘与紫微合盘，判断关系底层牵引",
                "再看六爻、奇门、梅花、大六壬，判断当前互动状态",
                "最后用关系复合卦作为双人关系场的校验",
            ],
            "免责声明": "所有结论均为民俗术数研究与娱乐参考，不能替代现实证据、亲子鉴定、医疗诊断、法律意见或其他专业判断。",
        },
    }


def generate_relationship_prompt(compound_result: Dict[str, Any]) -> str:
    result_text = json.dumps(compound_result, ensure_ascii=False, indent=2, default=str)
    question = compound_result.get("问题", "")
    relation = compound_result.get("关系识别盘", {})
    risk = compound_result.get("综合验证", {}).get("高风险主题", {})
    return f"""你是一位严谨、克制的传统术数关系合盘分析顾问。本次只使用专家模式：必须逐项分析，但不要把术数象意说成现实事实。

# 用户问题
{question}

# 关系识别摘要
{json.dumps(relation, ensure_ascii=False, indent=2, default=str)}

# 风险边界
{json.dumps(risk, ensure_ascii=False, indent=2, default=str)}

硬性规则：
1. 关系识别采用弱描述策略。用户未声明现实关系时，必须描述关系象，不要直接断言“就是夫妻/情人/同事/亲子”等现实身份。
2. 只有当用户明确声明关系，或多个独立盘面给出极强且一致的身份锚点时，才可说“较可能为某类关系”；仍需注明“术数倾向，不是现实证明”。
3. 六爻财官、奇门六合、天后、姤卦、咸卦、归妹、家人等都只能作为关系象或亲密象，不能单独作为夫妻、婚外情或法律婚姻证明。
4. 涉及亲生/血缘/医疗/法律/投资时，必须提示以正规鉴定、专业机构或现实证据为准。
5. 不输出思考过程，不输出英文段落；使用简体中文。

# 完整排盘数据
{result_text}

# 必须按以下章节输出
1. 【问题与关系识别】
2. 【第一命主个体盘】
3. 【第二命主个体盘】
4. 【八字合盘】
5. 【紫微合盘】
6. 【关系识别盘】
7. 【当前问事盘：六爻】
8. 【当前问事盘：奇门遁甲】
9. 【当前问事盘：梅花易数】
10. 【当前问事盘：大六壬】
11. 【关系复合卦】
12. 【交叉验证】
13. 【最终判断】
14. 【置信度】
15. 【行动建议】

最终判断必须直接回答用户问题，但在关系未声明时，优先给出“关系画像/互动状态”，不要过度身份断言。"""


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
