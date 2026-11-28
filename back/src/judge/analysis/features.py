"""「と」専用の特徴量（筆跡解析エンジン）。

座標はキャンバスの長辺で割った単位（0〜1）で扱い、キャンバスの大きさに依存しないようにする。
"""

from __future__ import annotations

import math

import numpy as np

from ..geometry import match
from ..geometry.normalize import normalize_xy, resample, smooth
from ..refs import TARGET, load_references
from .strokes import InputStrokes, stroke_length

_EPS = 1e-9


def _speeds(a: np.ndarray) -> np.ndarray:
    seg = np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)
    dt = np.diff(a[:, 2])
    ok = dt > 0
    return seg[ok] / dt[ok] if ok.any() else np.zeros(0)


def _turn_angles(p: np.ndarray) -> np.ndarray:
    v = np.diff(p, axis=0)
    ang = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
    return np.diff(ang)


def _circle_radius(p: np.ndarray) -> float:
    """点列に円を当てはめた半径（最小二乗）。直線に近いほど大きい。"""
    if len(p) < 3:
        return math.inf
    x, y = p[:, 0], p[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    try:
        c, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return math.inf
    cx, cy = c[0] / 2, c[1] / 2
    r2 = c[2] + cx ** 2 + cy ** 2
    return float(math.sqrt(r2)) if r2 > 0 else math.inf


def _polygon_area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def _principal_angle(p: np.ndarray) -> float:
    c = p - p.mean(axis=0)
    w, v = np.linalg.eigh(c.T @ c)
    major = v[:, int(np.argmax(w))]
    ang = math.degrees(math.atan2(major[0], major[1]))  # 縦方向からの角度
    return (ang + 90) % 180 - 90


def match_to_reference(inp: InputStrokes) -> tuple[dict[int, int], list[np.ndarray], list[np.ndarray]]:
    """ユーザーの画を「と」のお手本の画に対応付ける。返り値: (ref_index -> user_index, 正規化済みユーザー画, 正規化済みお手本画)"""
    ref = load_references(TARGET)[0]
    user_n = [smooth(resample(s)) for s in normalize_xy([a[:, :2] for a in inp.kept])]
    ref_n = [smooth(resample(s)) for s in normalize_xy(ref.strokes)]
    asg = match.assign(user_n, ref_n)
    return {j: i for i, j in asg.pairs}, user_n, ref_n


def compute(inp: InputStrokes, endings_detected: list[str] | None = None) -> dict[str, float | None]:
    """特徴量16個（一部は該当しないと None）。"""
    W, H = inp.canvas
    unit = max(W, H) or 1.0
    strokes = [np.column_stack([a[:, 0] / unit, a[:, 1] / unit, a[:, 2] / 1000.0, a[:, 3]]) for a in inp.kept]
    allxy = np.concatenate([s[:, :2] for s in strokes])
    lo, hi = allxy.min(axis=0), allxy.max(axis=0)
    bw, bh = float(hi[0] - lo[0]), float(hi[1] - lo[1])
    char_h = max(bh, _EPS)
    char_size = max(bw, bh, _EPS)

    ref_of, user_n, ref_n = match_to_reference(inp)
    s1 = ref_of.get(0)
    s2 = ref_of.get(1)

    # --- A 慎重さ ---
    pen_time = sum(max(s[-1, 2] - s[0, 2], 0.0) for s in strokes)
    total_len = sum(stroke_length(s) for s in strokes)
    speed = total_len / pen_time if pen_time > _EPS else None
    t0 = min(s[0, 2] for s in strokes)
    t1 = max(s[-1, 2] for s in strokes)
    duration = t1 - t0 if t1 > t0 else None
    tome_rate = None
    if endings_detected:
        judged = [e for e in endings_detected if e in ("tome", "hane", "harai")]
        if judged:
            tome_rate = sum(e == "tome" for e in judged) / len(judged)
    sloppiness = float(len(inp.ignored) + max(len(strokes) - 2, 0))

    # --- B 運筆の流れ ---
    cvs, pauses = [], 0
    for s in strokes:
        v = _speeds(s)
        if len(v) >= 6:
            core = v[len(v) // 10: len(v) - len(v) // 10 or None]
            if len(core) >= 3 and core.mean() > _EPS:
                cvs.append(float(core.std() / core.mean()))
                med = float(np.median(core))
                pauses += int(np.sum(np.diff((core < med * 0.15).astype(int)) == 1))
    speed_cv = float(np.mean(cvs)) if cvs else None
    jit = []
    for s in strokes:
        L = stroke_length(s)
        if L < char_size * 0.1:
            continue
        n = max(int(L / (char_size * 0.03)), 6)
        turn = _turn_angles(resample(s[:, :2], n))
        if len(turn) >= 3:
            jit.append(float(np.abs(np.diff(turn)).mean()))
    jitter = float(np.mean(jit)) if jit else None
    gap_time = None
    if s1 is not None and s2 is not None:
        g = strokes[s2][0, 2] - strokes[s1][-1, 2]
        gap_time = float(g) if g >= 0 else None

    # --- C 形の丸み（2画目） ---
    turn_radius = corners = straight_ratio = None
    if s2 is not None:
        p = user_n[s2]
        k = int(np.argmin(p[:, 0]))  # 最も左の点＝折り返し
        win = p[max(k - 8, 0): k + 9]
        r = _circle_radius(win)
        turn_radius = float(min(r, 2.0))
        ta = _turn_angles(p)
        if len(ta) >= 4:
            local = np.abs(np.convolve(ta, np.ones(3), mode="valid"))
            corners = float(np.sum(np.diff((local > math.radians(45)).astype(int)) == 1))
            straight_ratio = float(np.mean(np.abs(ta) < math.radians(2.5)))
    stroke1_angle = stroke1_len = None
    if s1 is not None:
        a = strokes[s1][:, :2]
        d = a[-1] - a[0]
        stroke1_angle = float(math.degrees(math.atan2(d[0], d[1])))  # 縦からの角度（右下がりで正）
        stroke1_len = float(np.linalg.norm(d) / char_h)

    # --- D 広がり ---
    aspect = bw / char_h
    pocket = None
    if s2 is not None:
        p = user_n[s2]
        pocket = _polygon_area(p)  # 正規化座標（字の長辺 = 1）での面積
    gap12 = None
    if s1 is not None and s2 is not None:
        end1 = strokes[s1][-1, :2]
        gap12 = float(np.min(np.linalg.norm(strokes[s2][:, :2] - end1, axis=1)) / char_size)

    # --- E 大胆さ ---
    ref_angle = _principal_angle(np.concatenate(ref_n))
    tilt = abs(_principal_angle(np.concatenate(user_n)) - ref_angle)
    placement = None
    pairs = [(i, j) for j, i in ref_of.items()]
    if pairs:
        placement = float(np.mean([np.linalg.norm(user_n[i].mean(axis=0) - ref_n[j].mean(axis=0)) for i, j in pairs]))
    size = char_size  # キャンバス長辺に対する比
    prs = np.concatenate([s[:, 3] for s in strokes])
    prs = prs[~np.isnan(prs)]
    pressure = float(prs.mean()) if len(prs) and any(t == "pen" for t in inp.pointer_types) else None

    return {
        "speed": speed, "duration": duration, "tome_rate": tome_rate, "sloppiness": sloppiness,
        "speed_cv": speed_cv, "pauses": float(pauses), "jitter": jitter, "gap_time": gap_time,
        "turn_radius": turn_radius, "corners": corners, "straight_ratio": straight_ratio,
        "stroke1_angle": stroke1_angle, "stroke1_len": stroke1_len,
        "aspect": aspect, "pocket": pocket, "gap12": gap12,
        "tilt": tilt, "placement": placement, "size": size, "pressure": pressure,
    }
