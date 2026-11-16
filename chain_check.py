#!/usr/bin/env python3
"""隣り合う駅の発車時刻を突き合わせ、列車ごとの所要時間が揃うかを確認する。
usage: chain_check.py <outdir> 駅コード:駅名 駅コード:駅名 ...   (列車の進行順)
"""
import csv, sys, os, statistics as st
d = sys.argv[1]
def load(code):
    return [(int(r['depart'][:2]) * 60 + int(r['depart'][3:]), r['mark']) for r in csv.DictReader(open(os.path.join(d, code + '.csv'), encoding='utf-8-sig'))]
order = [a.split(':') for a in sys.argv[2:]]
def fmt(l): return ', '.join(f"{t//60}:{t%60:02d}{m}" for t, m in l)
for (ca, na), (cb, nb) in zip(order, order[1:]):
    A, B = load(ca), load(cb)
    # 1回目: ゆるく突き合わせて所要時間の中央値を出す
    diffs = []; used = set()
    for t, m in A:
        c = [x for x, _ in B if 1 <= x - t <= 6 and x not in used]
        if c: x = min(c); used.add(x); diffs.append(x - t)
    med = st.median(diffs)
    # 2回目: 中央値±1分で厳密に突き合わせ、両側の余りを出す
    usedB = set(); endA = []
    for t, m in A:
        c = [x for x, _ in B if abs(x - t - med) <= 1 and x not in usedB]
        if c: usedB.add(min(c, key=lambda x: abs(x - t - med)))
        else: endA.append((t, m))
    startB = [(x, m) for x, m in B if x not in usedB]
    print(f"{na}→{nb}: 所要{med}分 / {na}で終点となる列車 {len(endA)}本 [{fmt(endA)}] / {nb}が始発の列車 {len(startB)}本 [{fmt(startB)}]")
