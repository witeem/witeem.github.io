#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双色球预测脚本
功能：
1. 从 datachart.500.com 抓取最近 200 期开奖记录
2. 统计每个球出现的频次（美化卡片展示，按频次排序）
3. 使用5种预测算法（热号恒热、冷号反弹、冷热号混合、加权随机、随机）各模拟50000次
4. 每种算法取得分最高的3组号码
5. 将上一期预测与最新开奖结果对比，计算准确率
6. 生成以日期命名的 Hugo Markdown 文件（content/ssq/YYYY-MM-DD.md）
7. 同时更新 content/ssq/_index.md 历史列表入口页
"""

import os
import re
import sys
import json
import math
import random
import datetime
import urllib.request
import urllib.error
from collections import Counter

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
FETCH_URL   = "https://datachart.500.com/ssq/history/newinc/history.php?limit=200&expect=0"
SSQ_DIR     = os.path.join(os.path.dirname(__file__), "..", "content", "ssq")
CACHE_FILE  = os.path.join(os.path.dirname(__file__), "ssq_last_prediction.json")
RED_COUNT   = 6          # 每期红球数量
BLUE_COUNT  = 1          # 每期蓝球数量
RED_RANGE   = range(1, 34)   # 红球范围 1-33
BLUE_RANGE  = range(1, 17)   # 蓝球范围 1-16
SIMULATE    = 50000      # 每种算法模拟次数
TOP_N       = 3          # 取前 N 组


# ──────────────────────────────────────────────
# 1. 抓取开奖数据
# ──────────────────────────────────────────────
def fetch_history(limit: int = 200):
    """从 datachart.500.com 抓取最近 limit 期开奖记录"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://datachart.500.com/ssq/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    url = f"https://datachart.500.com/ssq/history/newinc/history.php?limit={limit}&expect=0"
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gb2312", errors="replace")
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        sys.exit(1)

    records = []
    # 匹配表格行: <tr class="..."> ... </tr>
    row_pattern = re.compile(r'<tr[^>]*?class=["\'][^"\']*t_tr[^"\']*["\'][^>]*>(.*?)</tr>', re.S)
    td_pattern  = re.compile(r'<td[^>]*?>(.*?)</td>', re.S)
    num_pattern = re.compile(r'[\d]+')
    
    for row_m in row_pattern.finditer(raw):
        cells = td_pattern.findall(row_m.group(1))
        if len(cells) < 9:
            continue
        # 清理 HTML 标签
        clean = lambda s: re.sub(r'<[^>]+>', '', s).strip()
        period   = clean(cells[1])
        date_str = clean(cells[-1])
        
        # 红球 index 2-7, 蓝球 index 8
        reds = []
        for i in range(2, 8):
            m = num_pattern.search(clean(cells[i]))
            if m:
                reds.append(int(m.group()))
        
        blue_raw = clean(cells[8])
        bm = num_pattern.search(blue_raw)
        blue = int(bm.group()) if bm else 0
        
        if len(reds) == 6 and 0 < blue <= 16:
            records.append({
                "period": period,
                "date":   date_str,
                "reds":   sorted(reds),
                "blue":   blue
            })

    if not records:
        print("[ERROR] 未能解析到任何开奖记录，页面结构可能已变化。")
        print("[DEBUG] 页面前2000字符:")
        print(raw[:2000])
        sys.exit(1)

    print(f"[INFO] 共抓取 {len(records)} 期记录，最新一期: {records[0]['period']}")
    return records


# ──────────────────────────────────────────────
# 2. 统计频次
# ──────────────────────────────────────────────
def calc_frequency(records):
    """统计红球和蓝球出现的频次"""
    red_counter  = Counter()
    blue_counter = Counter()
    for r in records:
        red_counter.update(r["reds"])
        blue_counter[r["blue"]] += 1
    return red_counter, blue_counter


# ──────────────────────────────────────────────
# 3. 预测算法
# ──────────────────────────────────────────────

# ── 评分权重配置 ──
W_FREQ      = 0.50   # 频次权重叠加（核心）
W_MATCH_HOT = 0.20   # 与 TOP10 热号的匹配度
W_ODD_EVEN  = 0.15   # 奇偶比合理性
W_SUM_RANGE = 0.15   # 和值区间合理性

# 双色球红球和值统计上，历史和值集中在 [60, 150] 区间
SUM_MIN, SUM_MAX     = 60, 150
# 奇偶比合理范围：2:4 ~ 4:2（即奇数个数 2-4 个）
ODD_MIN, ODD_MAX     = 2, 4


def _score_combo_advanced(combo, blue, red_counter, blue_counter, total, top10_hot):
    """
    多维综合评分（满分 1.0）：
      - 频次权重叠加  (50%)：每个球历史频次之和 / 理论最大值
      - 热号匹配度    (20%)：与 TOP10 热号的重合个数 / 6
      - 奇偶合理性    (15%)：奇数个数落在 [ODD_MIN, ODD_MAX] 得满分，否则线性递减
      - 和值合理性    (15%)：红球之和落在 [SUM_MIN, SUM_MAX] 得满分，否则线性递减
    蓝球频次单独计入（附加分，不影响红球各维度满分）
    """
    combo = list(combo)

    # 1) 频次权重叠加
    max_possible_red  = max(red_counter.values()) * 6 if red_counter else 1
    freq_sum = sum(red_counter.get(n, 0) for n in combo)
    s_freq = freq_sum / max_possible_red

    # 2) 热号匹配度
    match_cnt = sum(1 for n in combo if n in top10_hot)
    s_match = match_cnt / 6

    # 3) 奇偶合理性
    odd_cnt = sum(1 for n in combo if n % 2 == 1)
    if ODD_MIN <= odd_cnt <= ODD_MAX:
        s_odd = 1.0
    else:
        deviation = min(abs(odd_cnt - ODD_MIN), abs(odd_cnt - ODD_MAX))
        s_odd = max(0.0, 1.0 - deviation * 0.4)

    # 4) 和值合理性
    red_sum = sum(combo)
    if SUM_MIN <= red_sum <= SUM_MAX:
        s_sum = 1.0
    else:
        mid  = (SUM_MIN + SUM_MAX) / 2
        span = (SUM_MAX - SUM_MIN) / 2 + 50   # 容忍带
        s_sum = max(0.0, 1.0 - abs(red_sum - mid) / span)

    # 红球综合得分
    red_score = (W_FREQ * s_freq + W_MATCH_HOT * s_match
                 + W_ODD_EVEN * s_odd + W_SUM_RANGE * s_sum)

    # 蓝球频次附加（满分 0.1）
    max_blue = max(blue_counter.values()) if blue_counter else 1
    blue_score = 0.1 * blue_counter.get(blue, 0) / max_blue

    return round(red_score + blue_score, 6)

def _score_full_random(combo, blue):
    """
    全随机评分机制 (红球 0.9 + 蓝球 0.1)
    完全不依赖历史频次，只看组合形态的数学合理性
    """
    combo = sorted(list(combo))
    score = 0.0

    # === 红球评分 (共 0.9) ===
    
    # 1. 奇偶比 (0.25)
    odds = sum(1 for n in combo if n % 2 != 0)
    odd_even_map = {3: 1.0, 2: 0.8, 4: 0.8, 1: 0.3, 5: 0.3, 0: 0.1, 6: 0.1}
    score += 0.25 * odd_even_map.get(odds, 0)
    
    # 2. 跨度 (0.2) - 理想跨度 22-30
    span = combo[-1] - combo[0]
    if 22 <= span <= 30:
        score += 0.2
    else:
        # 偏离理想区间越远得分越低
        score += 0.2 * max(0, (1 - abs(span - 26) / 20))

    # 3. AC值 (0.15) - 随机性指标
    diffs = set()
    for i in range(len(combo)):
        for j in range(i + 1, len(combo)):
            diffs.add(combo[j] - combo[i])
    ac_value = len(diffs) - 5
    score += 0.15 * (min(ac_value, 10) / 10) # AC值越高越随机

    # 4. 连号形态 (0.15)
    con_groups = sum(1 for i in range(len(combo)-1) if combo[i+1]-combo[i]==1)
    if con_groups == 0: score += 0.15
    elif con_groups == 1: score += 0.12 # 允许1组二连号
    else: score += 0.05 # 连号过多降分

    # 5. 三区分布 (0.15) - 避免号码过于堆积
    z1 = sum(1 for n in combo if n <= 11)
    z2 = sum(1 for n in combo if 12 <= n <= 22)
    z3 = sum(1 for n in combo if n >= 23)
    dist = sorted([z1, z2, z3])
    if dist == [2, 2, 2]: score += 0.15
    elif dist == [1, 2, 3]: score += 0.12
    else: score += 0.05

    # === 蓝球评分 (共 0.1) ===
    
    blue_score = 0.0
    # 1. 奇偶均衡 (0.05)
    # 2. 质合分布 (0.05) - 2,3,5,7,11,13 为质数
    primes = {2, 3, 5, 7, 11, 13}
    if blue in primes:
        blue_score += 0.05
    else:
        blue_score += 0.03 # 理论上合数更多，给个基础分
    
    # 加上蓝球的大小均衡判断（可选）
    if 4 <= blue <= 13: # 避开极端的 1,2,3 或 14,15,16
        blue_score += 0.05
    else:
        blue_score += 0.02

    return round(score + blue_score, 4)

def _build_top10(red_counter):
    """返回 TOP10 高频红球集合"""
    return set(k for k, _ in red_counter.most_common(10))


def _top_unique(results, top=TOP_N):
    """从结果中取分数最高的 top 组（去重）"""
    seen   = set()
    ranked = []
    for combo, blue, score in sorted(results, key=lambda x: -x[2]):
        key = (combo, blue)
        if key not in seen:
            seen.add(key)
            ranked.append((combo, blue, score))
        if len(ranked) >= top:
            break
    return ranked


def _build_decay_weights(records, all_reds, half_life: int = 30):
    """
    指数衰减频次权重：越近期出现的号码权重越高。
    weight(r, t) = exp(-λ * t)，λ = ln2 / half_life
    t = 距今期数(0 = 最新一期）
    """
    import math as _math
    lam = _math.log(2) / half_life
    decay_w = {r: 0.0 for r in all_reds}
    for t, rec in enumerate(records):          # records[0] 最新
        w = _math.exp(-lam * t)
        for r in rec["reds"]:
            if r in decay_w:
                decay_w[r] += w
    # 归一化到 [0.1, 1] 避免零权重
    max_w = max(decay_w.values()) or 1.0
    return {r: max(0.1, decay_w[r] / max_w) for r in all_reds}


def _build_cooccurrence(records, all_reds):
    """
    构建二阶共现矩阵：co[a][b] = 号码 a 和 b 在同一期同时出现的次数。
    用于条件抽样：已选 a 时，更新 b 的权重 += co[a][b]。
    """
    co = {r: {s: 0 for s in all_reds} for r in all_reds}
    for rec in records:
        reds = rec["reds"]
        for i in range(len(reds)):
            for j in range(i + 1, len(reds)):
                a, b = reds[i], reds[j]
                co[a][b] += 1
                co[b][a] += 1
    return co


def algo_hot(red_counter, blue_counter, total, n=SIMULATE, records=None):
    """
    算法1：热号恒热

    Step1 - 指数衰减权重（滑动窗口效应）：
            近期出现的号码权重更高，半衰期 30 期；
            比简单累计频次更能捕捉"最近热"趋势。

    Step2 - 条件抽样（二阶相关矩阵）：
            选出第 k 个球后，实时将已选球与剩余球的
            历史共现次数叠加到剩余球权重上，
            让"经常同框"的热号组合更易被整体选中。

    Step3 - 蓝球同样采用指数衰减权重。
    """
    top10_hot = _build_top10(red_counter)
    all_reds  = list(RED_RANGE)
    all_blues = list(BLUE_RANGE)

    # ── Step1: 衰减权重（需要 records）──
    if records:
        decay_w = _build_decay_weights(records, all_reds, half_life=30)
        # 指数放大热号优势：decay²
        base_weights = {r: decay_w[r] ** 2 for r in all_reds}

        # 蓝球衰减
        import math as _math
        lam = _math.log(2) / 30
        blue_decay = {b: 0.0 for b in all_blues}
        for t, rec in enumerate(records):
            w = _math.exp(-lam * t)
            b = rec["blue"]
            if b in blue_decay:
                blue_decay[b] += w
        max_bw = max(blue_decay.values()) or 1.0
        blue_weights = [max(0.1, blue_decay[b] / max_bw) ** 2 for b in all_blues]
    else:
        # 无 records 时退化为原始 freq² 权重
        base_weights = {r: red_counter.get(r, 0.1) ** 2 for r in all_reds}
        blue_weights = [blue_counter.get(b, 0.1) ** 2 for b in all_blues]

    # ── Step2: 预构建共现矩阵 ──
    co = _build_cooccurrence(records, all_reds) if records else None

    results = []
    for _ in range(n):
        # 条件抽样：每选一个球，更新剩余球权重
        remaining = list(all_reds)
        rem_weights = [base_weights[r] for r in remaining]
        selected = []

        for _ in range(6):
            # 归一化后抽样
            pick = random.choices(remaining, weights=rem_weights, k=1)[0]
            selected.append(pick)
            idx = remaining.index(pick)
            remaining.pop(idx)
            rem_weights.pop(idx)

            # 根据已选球更新剩余球权重（共现叠加）
            if co:
                for j, r in enumerate(remaining):
                    rem_weights[j] = max(
                        0.01,
                        rem_weights[j] + co[pick][r] * 0.5   # 共现加成系数
                    )

        combo = tuple(sorted(selected))
        blue  = random.choices(all_blues, weights=blue_weights, k=1)[0]
        score = _score_combo_advanced(combo, blue, red_counter, blue_counter,
                                      total, top10_hot)
        results.append((combo, blue, score))

    return _top_unique(results)


def algo_cold_rebound(red_counter, blue_counter, total, n=SIMULATE, records=None):
    """
    算法2：冷号反弹
    综合4个维度计算动态权重，逻辑更严谨：

    Step1 - 遗漏期数权重：统计每个号码距今已多少期未出现，
            遗漏越长权重指数上升（反映"欠债"积累效应）。
    Step2 - 频次反转权重：历史频率越高权重越小，频率越低权重越大
            （全量反转排序，高频号处于劣势，冷号天然占优）。
    Step3 - 动态冷热比例过滤：每注必须包含 3~5 个冷号
           （遗漏 > 阈值）+ 1~3 个次热号（所有非冷号，权重同样反转），
            强化冷号主导、避免极端全冷组合。
    Step4 - 关联性修正：若同一注中两个冷号曾频繁同框，
            视为"关联热"，适当替换以增加组合多样性。
    """
    top10_hot  = _build_top10(red_counter)
    all_reds   = list(RED_RANGE)
    all_blues  = list(BLUE_RANGE)
    total_draws = total

    # ── Step 1: 遗漏期数估算 ──
    avg_freq = (total_draws * 6) / 33          # 红球理论均值
    absence = {}
    for r in all_reds:
        freq = red_counter.get(r, 0)
        if freq == 0:
            absence[r] = total_draws
        else:
            avg_interval = total_draws / freq
            absence[r] = avg_interval * max(1.0, avg_freq / max(freq, 0.1))

    max_absence = max(absence.values()) or 1

    # ── Step 2: 频次反转权重（全量，频次越高权重越小）──
    max_freq = max((red_counter.get(r, 0) for r in all_reds), default=1) + 1
    def inv_freq_weight(r):
        """频次反转：最高频号权重最小，冷号权重最大"""
        freq = red_counter.get(r, 0)
        return max_freq - freq   # 差值越大 = 频次越低 = 权重越高

    # 偏离标准差（辅助冷号内部排序）
    freqs  = [red_counter.get(r, 0) for r in all_reds]
    mean_f = sum(freqs) / len(freqs)
    std_f  = (sum((f - mean_f) ** 2 for f in freqs) / len(freqs)) ** 0.5 or 1
    dev_weight = {r: max(0.0, (mean_f - red_counter.get(r, 0)) / std_f + 1.0)
                  for r in all_reds}

    # ── Step 3: 冷热分区 ──
    # 冷号：遗漏超过平均间隔 1.5 倍
    cold_threshold = (total_draws / max(avg_freq, 1)) * 1.5
    cold_set = {r for r in all_reds if absence[r] >= cold_threshold}

    # 次热号 = 所有非冷号（不再排除高频号，依靠反转权重压制高频号）
    warm_set = {r for r in all_reds if r not in cold_set}

    # 保底：冷号不足 3 个时取遗漏最长的前 8 个
    if len(cold_set) < 3:
        cold_set = set(sorted(all_reds, key=lambda x: -absence[x])[:8])
        warm_set = {r for r in all_reds if r not in cold_set}

    # 次热号至少 1 个（极端情况兜底）
    if len(warm_set) < 1:
        warm_set = {sorted(all_reds, key=lambda x: red_counter.get(x, 0))[0]}

    # ── Step 4: 关联性修正（冷号对共现惩罚）──
    def pair_penalty(a, b):
        """两冷号频次越高（说明并非真冷），惩罚越大"""
        fa = red_counter.get(a, 0) / total_draws
        fb = red_counter.get(b, 0) / total_draws
        return fa * fb * 100

    # ── 综合权重（遗漏 × 偏离 × 反转频次）──
    def cold_weight(r):
        w_abs = absence[r] / max_absence                     # [0,1]
        w_dev = min(dev_weight[r], 2.0) / 2.0               # [0,1]
        w_inv = inv_freq_weight(r) / max_freq                # [0,1]
        return w_abs * 0.5 + w_dev * 0.3 + w_inv * 0.2

    # 次热号权重同样采用频次反转（高频号在次热池里权重最小）
    def warm_weight(r):
        return inv_freq_weight(r)

    cold_list = sorted(cold_set, key=lambda x: -cold_weight(x))
    warm_list = sorted(warm_set, key=lambda x: -warm_weight(x))  # 反转：低频优先

    cold_weights_list = [cold_weight(r) for r in cold_list]
    warm_weights_list = [warm_weight(r) for r in warm_list]

    # 蓝球：反转频次权重
    max_blue_freq = max(blue_counter.values()) if blue_counter else 1
    blue_weights  = [1.0 / (blue_counter.get(b, 0.1) / max_blue_freq + 0.05)
                     for b in all_blues]

    results = []
    for _ in range(n):
        # 每注抽 3~5 个冷号 + 补足到 6 个次热号
        n_cold = random.choices([3, 4, 5], weights=[0.4, 0.4, 0.2])[0]
        n_cold = min(n_cold, len(cold_list))   # 不超过冷号池大小
        n_warm = 6 - n_cold

        # 冷号加权无放回抽样
        cold_picked = set()
        cw = list(cold_weights_list)
        cl = list(cold_list)
        while len(cold_picked) < n_cold and cl:
            pick = random.choices(cl, weights=cw, k=1)[0]
            idx  = cl.index(pick)
            cold_picked.add(pick)
            cl.pop(idx); cw.pop(idx)

        # 关联性修正：若两个冷号之间惩罚高，有概率替换其中一个
        cold_picked = list(cold_picked)
        if len(cold_picked) >= 2:
            penalty = pair_penalty(cold_picked[0], cold_picked[1])
            if random.random() < penalty:
                cold_picked.pop(0)
                extra = [r for r in cold_list if r not in cold_picked]
                if extra:
                    ew = [cold_weight(r) for r in extra]
                    cold_picked.append(random.choices(extra, weights=ew, k=1)[0])
        cold_picked = set(cold_picked)

        # 次热号补足（反转权重抽样，低频优先）
        warm_avail = [r for r in warm_list if r not in cold_picked]
        ww = [warm_weight(r) for r in warm_avail]
        warm_picked = set()
        while len(warm_picked) < n_warm and warm_avail:
            pick = random.choices(warm_avail, weights=ww, k=1)[0]
            idx  = warm_avail.index(pick)
            warm_picked.add(pick)
            warm_avail.pop(idx); ww.pop(idx)

        combo = tuple(sorted(cold_picked | warm_picked))
        if len(combo) != 6:
            continue

        blue  = random.choices(all_blues, weights=blue_weights, k=1)[0]
        score = _score_combo_advanced(combo, blue, red_counter, blue_counter,
                                      total, top10_hot)
        results.append((combo, blue, score))

    return _top_unique(results)


def algo_cold_hot(red_counter, blue_counter, total, n=SIMULATE):
    """
    算法3：冷热混合
    固定取 TOP12 热号中 4 个 + 末12冷号中 2 个，兼顾频率均衡。
    """
    top10_hot    = _build_top10(red_counter)
    sorted_reds  = [k for k, _ in red_counter.most_common()]
    sorted_blues = [k for k, _ in blue_counter.most_common()]
    hot_reds  = sorted_reds[:12]
    cold_reds = sorted_reds[-12:]
    blue_pool = sorted_blues[:10]

    results = []
    for _ in range(n):
        hot_sel  = random.sample(hot_reds, 4)
        cold_sel = random.sample(cold_reds, 2)
        combo    = tuple(sorted(hot_sel + cold_sel))
        blue     = random.choice(blue_pool)
        score    = _score_combo_advanced(combo, blue, red_counter, blue_counter, total, top10_hot)
        results.append((combo, blue, score))
    return _top_unique(results)


def algo_random(red_counter, blue_counter, total, n=SIMULATE):
    """
    算法4：纯随机
    完全等概率从全域抽取，不受历史数据偏向影响，
    依然通过多维评分筛选出形态最优的组合。
    """
    results = []
    for _ in range(n):
        combo = tuple(sorted(random.sample(list(RED_RANGE), 6)))
        blue  = random.randint(1, 16)
        score = _score_full_random(combo, blue)
        results.append((combo, blue, score))
    return _top_unique(results)


def algo_weighted_random(red_counter, blue_counter, total, n=SIMULATE):
    """
    算法5：加权随机
    以历史频率为线性权重进行加权随机抽样（介于热号恒热与纯随机之间），
    每个球被选中的概率与其历史出现频次成正比，
    再经多维评分筛选形态最优的组合。
    """
    top10_hot    = _build_top10(red_counter)
    all_reds     = list(RED_RANGE)
    all_blues    = list(BLUE_RANGE)
    red_weights  = [red_counter.get(r, 0.1) for r in all_reds]    # 线性权重
    blue_weights = [blue_counter.get(b, 0.1) for b in all_blues]

    results = []
    for _ in range(n):
        selected = set()
        while len(selected) < 6:
            pick = random.choices(all_reds, weights=red_weights, k=1)[0]
            selected.add(pick)
        combo = tuple(sorted(selected))
        blue  = random.choices(all_blues, weights=blue_weights, k=1)[0]
        score = _score_combo_advanced(combo, blue, red_counter, blue_counter, total, top10_hot)
        results.append((combo, blue, score))
    return _top_unique(results)


# ──────────────────────────────────────────────
# 4. 计算准确率（与上一期预测对比）
# ──────────────────────────────────────────────
def load_last_prediction():
    """读取上一次保存的预测结果"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_prediction(predictions, latest_period):
    """保存本次预测结果供下次对比"""
    data = {
        "period": latest_period,
        "predictions": predictions
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calc_accuracy(predicted_reds, predicted_blue, actual_reds, actual_blue):
    """计算单组预测与实际结果的匹配情况"""
    hit_reds = len(set(predicted_reds) & set(actual_reds))
    hit_blue = 1 if predicted_blue == actual_blue else 0
    return hit_reds, hit_blue


def prize_level(hit_reds, hit_blue):
    """根据命中数判断奖级"""
    table = {
        (6, 1): "一等奖 🏆",
        (6, 0): "二等奖 🥈",
        (5, 1): "三等奖 🥉",
        (5, 0): "四等奖",
        (4, 1): "四等奖",
        (4, 0): "五等奖",
        (3, 1): "五等奖",
        (2, 1): "六等奖",
        (1, 1): "六等奖",
        (0, 1): "六等奖",
    }
    return table.get((hit_reds, hit_blue), "未中奖")


# ──────────────────────────────────────────────
# 5. 生成 Markdown
# ──────────────────────────────────────────────
def fmt_ball(num, is_blue=False):
    """格式化单个球为 Markdown HTML span"""
    cls = "ball-blue" if is_blue else "ball-red"
    return f'<span class="{cls}">{num:02d}</span>'


def _donate_block() -> list:
    """
    打赏模块 HTML 片段（复用于预测和验证两个 tab）。
    二维码图片放在 /images/donate-wechat.jpg 和 /images/donate-alipay.jpg。
    """
    return [
        '<div class="ssq-donate">',
        '  <div class="donate-title">☕ 觉得有用？请作者喝杯咖啡</div>',
        '  <p class="donate-desc">内容完全免费，如果对你有帮助，欢迎打赏支持持续更新 🙏</p>',
        '  <div class="donate-qrcodes">',
        '    <div class="donate-item">',
        '      <img src="/images/donate-wechat.jpg" alt="微信赞赏码" class="donate-qr" />',
        '      <span class="donate-label">💚 微信</span>',
        '    </div>',
        '    <div class="donate-item">',
        '      <img src="/images/donate-alipay.jpg" alt="支付宝收款码" class="donate-qr" />',
        '      <span class="donate-label">💙 支付宝</span>',
        '    </div>',
        '  </div>',
        '</div>',
    ]


def fmt_combo(reds, blue):
    """格式化一组号码"""
    balls = " ".join(fmt_ball(r) for r in sorted(reds))
    balls += " " + fmt_ball(blue, is_blue=True)
    return balls



def generate_markdown(records, red_counter, blue_counter, all_predictions, last_pred, update_time):
    """生成完整的 Markdown 文件内容"""
    now_str   = update_time.strftime("%Y-%m-%d %H:%M:%S")
    date_str  = update_time.strftime("%Y-%m-%d")
    latest    = records[0]
    total     = len(records)

    # ── 频次排名数据准备 ──
    max_red_freq    = max(red_counter.values()) if red_counter else 1
    max_blue_freq   = max(blue_counter.values()) if blue_counter else 1
    sorted_red_rank  = [k for k, _ in red_counter.most_common()]   # 按频次从高到低
    sorted_blue_rank = [k for k, _ in blue_counter.most_common()]

    # 红球按频次降序排列（前3高亮）
    red_sorted_nums  = sorted(range(1, 34), key=lambda x: -red_counter.get(x, 0))
    blue_sorted_nums = sorted(range(1, 17), key=lambda x: -blue_counter.get(x, 0))

    lines = []

    # ── Front Matter ──
    lines += [
        "---",
        f'title: "🎱 双色球预测 {date_str}"',
        f'description: "双色球 {date_str} 开奖历史、频次分析与智能预测"',
        f'date: "{update_time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}"',
        f'slug: "{date_str}"',
        'layout: "ssq"',
        "---",
        "",
    ]

    # ── 更新时间 ──
    lines += [
        f'<p class="ssq-update-time">🕐 数据更新：{now_str}　·　基于最近 <strong>{total}</strong> 期记录　·　最新一期：<strong>{latest["period"]}</strong></p>',
        "",
    ]

    # ── Tab 切换 ──
    lines += [
        '<div class="ssq-tabs">',
        '  <button class="ssq-tab active" onclick="showTab(\'history\')">📋 开奖历史</button>',
        '  <button class="ssq-tab" onclick="showTab(\'freq\')">📊 频次统计</button>',
        '  <button class="ssq-tab" onclick="showTab(\'predict\')">🔮 智能预测</button>',
        '  <button class="ssq-tab" onclick="showTab(\'accuracy\')">🎯 预测验证</button>',
        '</div>',
        "",
    ]

    # ══════════════════════════════════════════
    # Tab 1: 最近10期开奖历史
    # ══════════════════════════════════════════
    lines += [
        '<div id="tab-history" class="ssq-tab-content active">',
        "",
        "## 📋 最近 10 期开奖历史",
        "",
        '<div class="ssq-history-table">',
        "",
        "| 期号 | 开奖日期 | 红球 | 蓝球 |",
        "|------|----------|------|------|",
    ]
    for r in records[:10]:
        red_balls = " ".join(fmt_ball(n) for n in r["reds"])
        blue_ball = fmt_ball(r["blue"], is_blue=True)
        lines.append(f'| {r["period"]} | {r["date"]} | {red_balls} | {blue_ball} |')

    lines += [
        "",
        "</div>",
        "",
        "</div>",
        "",
    ]

    # ══════════════════════════════════════════
    # Tab 2: 频次统计（美化版）
    # ══════════════════════════════════════════
    lines += [
        '<div id="tab-freq" class="ssq-tab-content">',
        "",
        f"## 📊 号码频次统计（近 {total} 期）",
        "",
    ]

    # ── 热号/冷号快览条 ──
    top5_hot_red   = [k for k, _ in red_counter.most_common(5)]
    top5_cold_red  = sorted(range(1, 34), key=lambda x: red_counter.get(x, 0))[:5]
    top3_hot_blue  = [k for k, _ in blue_counter.most_common(3)]
    top3_cold_blue = sorted(range(1, 17), key=lambda x: blue_counter.get(x, 0))[:3]

    lines += [
        '<div class="ssq-hot-cold">',
        '  <div class="hot-cold-item"><span class="hc-label">🔥 红球热号 TOP5</span>'
        + "".join(fmt_ball(n) for n in top5_hot_red) + "</div>",
        '  <div class="hot-cold-item"><span class="hc-label">❄️ 红球冷号 TOP5</span>'
        + "".join(fmt_ball(n) for n in top5_cold_red) + "</div>",
        '  <div class="hot-cold-item"><span class="hc-label">🔥 蓝球热号 TOP3</span>'
        + "".join(fmt_ball(n, True) for n in top3_hot_blue) + "</div>",
        '  <div class="hot-cold-item"><span class="hc-label">❄️ 蓝球冷号 TOP3</span>'
        + "".join(fmt_ball(n, True) for n in top3_cold_blue) + "</div>",
        "</div>",
        "",
    ]

    # ── 红球频次卡片（按频次降序） ──
    lines += [
        "### � 红球出现频次排行（1–33，按频次降序）",
        "",
        '<div class="ssq-freq-cards">',
    ]
    for rank_i, num in enumerate(red_sorted_nums, 1):
        freq = red_counter.get(num, 0)
        pct  = round(freq / max_red_freq * 100)
        avg  = round(total * 6 / 33, 1)   # 理论平均出现次数
        diff = freq - avg
        diff_cls  = "freq-above" if diff >= 0 else "freq-below"
        diff_sign = "+" if diff >= 0 else ""
        medal = ""
        card_cls = "freq-card"
        if rank_i == 1:   medal = "🥇"; card_cls += " rank-gold"
        elif rank_i == 2: medal = "🥈"; card_cls += " rank-silver"
        elif rank_i == 3: medal = "🥉"; card_cls += " rank-bronze"
        elif rank_i <= 10: card_cls += " rank-hot"
        elif rank_i >= 30: card_cls += " rank-cold"

        lines.append(
            f'<div class="{card_cls}">'
            f'  <div class="fc-rank">{medal or f"#{rank_i}"}</div>'
            f'  {fmt_ball(num)}'
            f'  <div class="fc-bar-wrap"><div class="fc-bar" style="width:{pct}%"></div></div>'
            f'  <div class="fc-stats">'
            f'    <span class="fc-count">{freq} 次</span>'
            f'    <span class="fc-diff {diff_cls}">{diff_sign}{diff:.1f}</span>'
            f'  </div>'
            f'</div>'
        )
    lines += [
        "</div>",
        "",
    ]

    # ── 蓝球频次卡片（按频次降序） ──
    lines += [
        "### 🔵 蓝球出现频次排行（1–16，按频次降序）",
        "",
        '<div class="ssq-freq-cards ssq-freq-cards--blue">',
    ]
    for rank_i, num in enumerate(blue_sorted_nums, 1):
        freq = blue_counter.get(num, 0)
        pct  = round(freq / max_blue_freq * 100)
        avg  = round(total / 16, 1)
        diff = freq - avg
        diff_cls  = "freq-above" if diff >= 0 else "freq-below"
        diff_sign = "+" if diff >= 0 else ""
        medal = ""
        card_cls = "freq-card freq-card--blue"
        if rank_i == 1:   medal = "🥇"; card_cls += " rank-gold"
        elif rank_i == 2: medal = "🥈"; card_cls += " rank-silver"
        elif rank_i == 3: medal = "🥉"; card_cls += " rank-bronze"
        elif rank_i <= 5:  card_cls += " rank-hot"
        elif rank_i >= 14: card_cls += " rank-cold"

        lines.append(
            f'<div class="{card_cls}">'
            f'  <div class="fc-rank">{medal or f"#{rank_i}"}</div>'
            f'  {fmt_ball(num, is_blue=True)}'
            f'  <div class="fc-bar-wrap"><div class="fc-bar fc-bar--blue" style="width:{pct}%"></div></div>'
            f'  <div class="fc-stats">'
            f'    <span class="fc-count">{freq} 次</span>'
            f'    <span class="fc-diff {diff_cls}">{diff_sign}{diff:.1f}</span>'
            f'  </div>'
            f'</div>'
        )
    lines += [
        "</div>",
        "",
        "</div>",
        "",
    ]

    # ══════════════════════════════════════════
    # Tab 3: 智能预测
    # ══════════════════════════════════════════
    algo_names = {
        "hot":              ("🔥 热号恒热",  "指数衰减近期热度（半衰期30期）+ 条件抽样"),
        "cold_rebound":     ("❄️ 冷号反弹",  "频率越低权重越大（1/freq），统计回归角度看冷号有补偿倾向"),
        "cold_hot":         ("🌡️ 冷热混合",  "固定取 TOP12 热号 4 个 + 末尾冷号 2 个，兼顾频率均衡"),
        "weighted_random":  ("⚖️ 加权随机",  "以历史频率为线性权重抽样，概率与频次正比，多维评分筛优"),
        "random":           ("🎲 纯随机",    "等概率全域抽取，以多维评分筛选形态最优组合"),
    }

    lines += [
        '<div id="tab-predict" class="ssq-tab-content">',
        "",
        f"## 🔮 智能预测（各算法模拟 {SIMULATE:,} 次）",
        "",
        f'<p class="ssq-predict-note">📅 预测期号：<strong>{latest["period"]} 之后的下一期</strong></p>',
        "",
        '<div class="ssq-score-legend">',
        '  <span class="score-legend-title">📐 综合评分维度：</span>',
        '  <span class="score-dim">🔴 频次叠加 50%</span>',
        '  <span class="score-dim">🎯 热号匹配 20%</span>',
        '  <span class="score-dim">⚖️ 奇偶合理 15%</span>',
        '  <span class="score-dim">➕ 和值区间 15%</span>',
        '  <span class="score-dim">🔵 蓝球附加 0.1</span>',
        '</div>',
        "",
    ]

    save_data = {}
    for algo_key, (algo_title, algo_desc) in algo_names.items():
        preds = all_predictions[algo_key]
        lines += [
            '<div class="ssq-algo-block">',
            f'<h3 class="ssq-algo-title">{algo_title}</h3>',
            f'<p class="ssq-algo-desc">{algo_desc}</p>',
            '<div class="ssq-pred-list">',
        ]
        save_data[algo_key] = []
        for i, (combo, blue, score) in enumerate(preds, 1):
            combo_list = list(combo)
            lines += [
                '<div class="ssq-pred-item">',
                f'  <span class="pred-rank">第 {i} 组</span>',
                f'  <span class="pred-balls">{fmt_combo(combo_list, blue)}</span>',
                f'  <span class="pred-score">得分: {score:.4f}</span>',
                '</div>',
            ]
            save_data[algo_key].append({
                "reds": combo_list,
                "blue": blue,
                "score": score
            })
        lines += [
            "</div>",
            "</div>",
            "",
        ]

    lines += [
        '<p class="ssq-disclaimer">⚠️ 以上预测仅供娱乐参考，彩票具有随机性，请理性购彩。</p>',
        "",
    ]
    lines += _donate_block()
    lines += [
        "",
        "</div>",
        "",
    ]

    # ══════════════════════════════════════════
    # Tab 4: 预测验证
    # ══════════════════════════════════════════
    lines += [
        '<div id="tab-accuracy" class="ssq-tab-content">',
        "",
        "## 🎯 上期预测验证",
        "",
    ]

    if last_pred is None:
        lines += [
            '<div class="ssq-no-data">',
            "  <p>📭 暂无上期预测数据，下次运行后将自动生成对比结果。</p>",
            "</div>",
            "",
        ]
    else:
        pred_period  = latest["period"]
        pred_preds   = last_pred.get("predictions", {})

        actual_record = None
        for r in records:
            if r["period"] == pred_period:
                actual_record = r
                break
        if actual_record is None:
            for r in reversed(records):
                if r["period"] > pred_period:
                    actual_record = r
                    break
        if actual_record is None:
            actual_record = records[0]

        actual_reds = actual_record["reds"]
        actual_blue = actual_record["blue"]

        lines += [
            '<div class="ssq-accuracy-header">',
            f'  <p>📌 上期预测期号：<strong>{pred_period}</strong></p>',
            f'  <p>🎰 实际开奖（{actual_record["period"]} 期）：'
            + fmt_combo(actual_reds, actual_blue) + '</p>',
            '</div>',
            "",
        ]

        for algo_key, (algo_title, _) in algo_names.items():
            preds_list = pred_preds.get(algo_key, [])
            if not preds_list:
                continue
            lines += [
                '<div class="ssq-algo-block">',
                f'<h3 class="ssq-algo-title">{algo_title} 验证结果</h3>',
                '<div class="ssq-pred-list">',
            ]
            for i, pred in enumerate(preds_list, 1):
                pr = pred["reds"]
                pb = pred["blue"]
                hr, hb = calc_accuracy(pr, pb, actual_reds, actual_blue)
                level = prize_level(hr, hb)
                hit_class = "hit-prize" if "奖" in level and "未" not in level else "no-prize"
                lines += [
                    f'<div class="ssq-pred-item {hit_class}">',
                    f'  <span class="pred-rank">第 {i} 组</span>',
                    f'  <span class="pred-balls">{fmt_combo(pr, pb)}</span>',
                    f'  <span class="pred-result">红球命中 {hr}/6 ｜ 蓝球{"✅" if hb else "❌"} ｜ {level}</span>',
                    '</div>',
                ]
            lines += [
                "</div>",
                "</div>",
                "",
            ]

    lines += _donate_block()
    lines += [
        "",
        "</div>",
        "",
    ]

    # ── Tab JS ──
    lines += [
        "<script>",
        "function showTab(name) {",
        "  document.querySelectorAll('.ssq-tab-content').forEach(el => el.classList.remove('active'));",
        "  document.querySelectorAll('.ssq-tab').forEach(el => el.classList.remove('active'));",
        "  document.getElementById('tab-' + name).classList.add('active');",
        "  event.currentTarget.classList.add('active');",
        "}",
        "</script>",
        "",
    ]

    return "\n".join(lines), save_data


# ──────────────────────────────────────────────
# 6. 更新历史列表页 (_index.md)
# ──────────────────────────────────────────────
def update_index_page(ssq_dir):
    """扫描 ssq/ 目录下的日期命名文件，重新生成 _index.md 列表页"""
    # 收集所有日期命名的 md 文件
    entries = []
    for fname in os.listdir(ssq_dir):
        if re.match(r'^\d{4}-\d{2}-\d{2}\.md$', fname):
            date_key = fname[:-3]   # 去掉 .md
            entries.append(date_key)
    entries.sort(reverse=True)   # 最新在前

    lines = [
        "---",
        'title: "🎱 双色球预测历史"',
        'description: "双色球历史预测记录，每日更新"',
        'layout: "ssq-list"',
        'menu:',
        '  main:',
        '    identifier: "ssq"',
        '    name: "🎱 双色球"',
        '    weight: 6',
        "---",
        "",
        '<div class="ssq-history-list">',
        "",
        "## 📅 历史预测记录",
        "",
    ]

    if not entries:
        lines += [
            '<div class="ssq-no-data"><p>📭 暂无历史记录</p></div>',
        ]
    else:
        lines += ['<ul class="ssq-entry-list">']
        for d in entries:
            lines.append(
                f'<li><a href="/ssq/{d}/">📋 {d} 预测报告</a></li>'
            )
        lines += ['</ul>']

    lines += [
        "",
        "</div>",
    ]

    index_path = os.path.join(ssq_dir, "_index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[INFO] 历史列表页已更新: {index_path}")


# ──────────────────────────────────────────────
# 7. 清理旧 MD 文件（仅保留最近 N 期）
# ──────────────────────────────────────────────
KEEP_MD_COUNT = 20   # 保留最近期数


def cleanup_old_md(ssq_dir: str, keep: int = KEEP_MD_COUNT):
    """
    扫描 ssq/ 目录下所有 YYYY-MM-DD.md 文件，
    按日期降序排列后，删除超出 keep 数量的旧文件。
    """
    dated_files = []
    for fname in os.listdir(ssq_dir):
        if re.match(r'^\d{4}-\d{2}-\d{2}\.md$', fname):
            dated_files.append(fname)

    dated_files.sort(reverse=True)   # 最新在前

    to_delete = dated_files[keep:]   # 超出保留数量的文件
    if not to_delete:
        print(f"[INFO] MD 文件共 {len(dated_files)} 个，无需清理（保留上限 {keep}）。")
        return

    for fname in to_delete:
        fpath = os.path.join(ssq_dir, fname)
        try:
            os.remove(fpath)
            print(f"[CLEAN] 已删除旧文件: {fname}")
        except OSError as e:
            print(f"[WARN] 删除失败 {fname}: {e}")

    print(f"[INFO] 清理完成，删除 {len(to_delete)} 个旧文件，保留最新 {keep} 个。")


# ──────────────────────────────────────────────
# 0. 开奖日判断
# ──────────────────────────────────────────────
# 双色球每周二（1）、四（3）、日（6）开奖（weekday：周一=0，周日=6）
SSQ_DRAW_WEEKDAYS = {1, 3, 6}


def _beijing_today() -> datetime.date:
    """返回北京时间（UTC+8）的今日日期，避免 GitHub Actions UTC 时区干扰"""
    tz_cst = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz=tz_cst).date()


def is_yesterday_draw_day(force: bool = False) -> bool:
    """
    判断昨天（北京时间）是否为双色球开奖日（周二/四/日）。
    若命令行传入 --force 参数则跳过检查，强制执行。
    """
    if force:
        return True
    yesterday = _beijing_today() - datetime.timedelta(days=1)
    return yesterday.weekday() in SSQ_DRAW_WEEKDAYS


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  双色球预测脚本 v1.0")
    print("=" * 50)

    # 0. 开奖日检查（昨天北京时间是否为开奖日：周二/四/日）
    force = "--force" in sys.argv
    # weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    # yesterday = _beijing_today() - datetime.timedelta(days=1)
    # if not is_yesterday_draw_day(force):
    #     print(
    #         f"[SKIP] 昨天（{yesterday} {weekday_names[yesterday.weekday()]}）不是开奖日，"
    #         "本次跳过执行。"
    #     )
    #     print("       双色球开奖日为每周二、四、日。")
    #     print("       如需强制运行，请添加 --force 参数。")
    #     sys.exit(0)

    # print(f"[INFO] 昨天（{yesterday} {weekday_names[yesterday.weekday()]}）为开奖日，开始执行...")

    # 1. 抓取数据
    records = fetch_history(500)
    red_counter, blue_counter = calc_frequency(records)
    total = len(records)

    print(f"[INFO] 红球频次统计完成，共 {len(red_counter)} 个号码")
    print(f"[INFO] 蓝球频次统计完成，共 {len(blue_counter)} 个号码")

    # 2. 读取上次预测
    last_pred = load_last_prediction()
    if last_pred:
        print(f"[INFO] 读取到上次预测记录，期号: {last_pred.get('period')}")
    else:
        print("[INFO] 未找到上次预测记录（首次运行）")

    # 2.5 期号重复检查：若最新一期与缓存期号相同，说明尚未开新奖，跳过
    latest_period = records[0]["period"]
    cached_period = last_pred.get("period") if last_pred else None
    if not force and cached_period and latest_period == cached_period:
        print(f"[SKIP] 最新期号（{latest_period}）与上次运行一致，本期尚未开新奖，跳过执行。")
        print("       如需强制重新生成，请添加 --force 参数。")
        sys.exit(0)
    print(f"[INFO] 检测到新期号：{latest_period}（上次：{cached_period or '无'}），继续执行...")

    # 3. 运行预测算法
    print("[INFO] 正在运行预测算法（共5种，各50000次）...")
    all_predictions = {}
    algos = [
        ("hot",             algo_hot),
        ("cold_rebound",    algo_cold_rebound),
        ("cold_hot",        algo_cold_hot),
        ("weighted_random", algo_weighted_random),
        ("random",          algo_random),
    ]
    for key, func in algos:
        print(f"  → {key} ...")
        if key == "hot":
            # 热号恒热需要传入 records 以构建衰减权重和共现矩阵
            all_predictions[key] = func(red_counter, blue_counter, total, records=records)
        else:
            all_predictions[key] = func(red_counter, blue_counter, total)

    # 4. 生成 Markdown
    update_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str    = update_time.strftime("%Y-%m-%d")
    md_content, save_data = generate_markdown(
        records, red_counter, blue_counter, all_predictions, last_pred, update_time
    )

    # 5. 写入以日期命名的文件（如 content/ssq/2026-03-19.md）
    os.makedirs(SSQ_DIR, exist_ok=True)
    md_path = os.path.join(SSQ_DIR, f"{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[INFO] Markdown 已生成: {md_path}")

    # 6. 更新历史列表页
    update_index_page(SSQ_DIR)

    # 6.5 清理旧 MD 文件，仅保留最近 KEEP_MD_COUNT 期
    cleanup_old_md(SSQ_DIR)

    # 7. 保存本次预测供下次对比
    save_prediction(save_data, records[0]["period"])
    print(f"[INFO] 预测数据已保存: {CACHE_FILE}")

    print("[DONE] 全部完成！")


if __name__ == "__main__":
    main()
