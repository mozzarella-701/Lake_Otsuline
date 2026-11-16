#!/usr/bin/env python3
"""時刻表と遅延投稿から、①いま列車がどこにいるか ②駅のリアルタイム時刻表 を計算する試作。

usage:
  python tools/position.py build trains --time 10:00 [--line ishiyama-sakamoto]
  python tools/position.py build board  --station 近江神宮前 --time 10:00
  遅延の投稿を重ねる: --delay 列車ID:駅(日本語名かid):遅れ分  （例: --delay 160:京阪大津京:4）
遅延モデル: 投稿された駅から先の全停車駅に同じ遅れを引き継ぐ（--recover で1駅ごとに回復する分を指定）。
"""
import csv, sys, os, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import network as N

ID2NAME = {v: k for k, v in N.STATIONS.items()}
def hm(sec): m = round(sec / 60); return f"{m // 60}:{m % 60:02d}"

class Timetable:
    def __init__(self, d):
        self.trips = {}
        for r in csv.DictReader(open(os.path.join(d, 'trips.csv'), encoding='utf-8')):
            self.trips[int(r['id'])] = dict(r, id=int(r['id']), stops=[])
        for r in csv.DictReader(open(os.path.join(d, 'stop_times.csv'), encoding='utf-8')):
            a = int(float(r['arrival_sec'])); dp = int(float(r['departure_sec'])) if r['departure_sec'] else None
            self.trips[int(r['trip_id'])]['stops'].append((r['station_id'], a, dp))
        for t in self.trips.values(): t['stops'].sort(key=lambda s: s[1])

def parse_delays(items):
    """'列車ID:駅:遅れ分' を [(列車ID, 駅id, 遅れ秒)] に。駅は日本語名でもid でもよい。"""
    out = []
    for x in items or []:
        tid, stn, mn = x.split(':')
        out.append((int(tid), N.STATIONS.get(stn, stn), float(mn) * 60))
    return out

def delay_at(trip, k, reports, recover_sec):
    """停車 k での遅れ(秒)。報告のある駅から先に引き継ぐ。"""
    d = 0.0
    for tid, stn, sec in reports:
        if tid != trip['id']: continue
        idx = next((i for i, s in enumerate(trip['stops']) if s[0] == stn), None)
        if idx is not None and k >= idx: d = max(d, max(0.0, sec - recover_sec * (k - idx)))
    return d

def locate(trip, t, reports=(), recover_sec=0.0):
    st = trip['stops']; n = len(st)
    eff = [(s[1] + delay_at(trip, k, reports, recover_sec), (s[2] if s[2] is not None else s[1]) + delay_at(trip, k, reports, recover_sec))
           for k, s in enumerate(st)]
    if t < st[0][2] : return None                                 # まだ出ていない
    if t >= eff[-1][0]: return None                               # 到着済み
    if t < eff[0][1]: return dict(state='発車待ち', k=0, frac=0.0, delay=eff[0][1] - st[0][2])
    for k in range(n - 1):
        if eff[k][1] <= t < eff[k + 1][0]:
            span = eff[k + 1][0] - eff[k][1]
            return dict(state='走行中', k=k, frac=(t - eff[k][1]) / span if span else 0.0,
                        delay=eff[k][1] - (st[k][2]), eta=eff[k + 1][0], eta_sched=st[k + 1][1])
    return None

def cmd_trains(tt, a, reports, rec):
    t = a.t
    rows = collections.defaultdict(list)
    for tr in tt.trips.values():
        if a.line and tr['line_id'] != a.line: continue
        p = locate(tr, t, reports, rec)
        if p: rows[(tr['line_id'], tr['direction'])].append((tr, p))
    for key in sorted(rows):
        print(f"\n■ {N.LINES[key[0]][0]} / {key[1]}  ({len(rows[key])}本)")
        for tr, p in sorted(rows[key], key=lambda x: (x[1]['k'] + x[1]['frac'])):
            s = tr['stops']; here = ID2NAME[s[p['k']][0]]
            if p['state'] == '発車待ち': pos = f"{here} で発車待ち（{p['delay']/60:+.0f}分）"
            else:
                nxt = ID2NAME[s[p['k'] + 1][0]]
                pos = f"{here}→{nxt} {p['frac']*100:3.0f}%  {nxt}着 {hm(p['eta'])}" + (f"（遅れ{p['delay']/60:+.0f}分）" if abs(p['delay']) >= 30 else '')
            print(f"  #{tr['id']:<4}{tr['headsign']}行  {pos}")

def cmd_board(tt, a, reports, rec):
    sid = N.STATIONS.get(a.station, a.station); t = a.t
    print(f"■ {ID2NAME[sid]} 駅  {hm(t)} 現在")
    by = collections.defaultdict(list)
    for tr in tt.trips.values():
        for k, s in enumerate(tr['stops']):
            if s[0] == sid and s[2] is not None:
                d = delay_at(tr, k, reports, rec); eff = s[2] + d
                if eff >= t: by[(tr['line_id'], tr['direction'])].append((eff, s[2], d, tr))
    for key in sorted(by):
        print(f"  {N.LINES[key[0]][0]} {key[1]}")
        for eff, sch, d, tr in sorted(by[key], key=lambda x: x[0])[:a.n]:
            print(f"    {hm(eff)} 発  {tr['headsign']}行  (時刻表 {hm(sch)}" + (f"、遅れ{d/60:+.0f}分" if d >= 30 else '') + f")  #{tr['id']}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('build'); ap.add_argument('cmd', choices=['trains', 'board'])
    ap.add_argument('--time', required=True); ap.add_argument('--line'); ap.add_argument('--station'); ap.add_argument('-n', type=int, default=3)
    ap.add_argument('--delay', action='append'); ap.add_argument('--recover', type=float, default=0.0, help='1駅ごとに回復する遅れ(分)')
    a = ap.parse_args(); h, m = a.time.split(':'); a.t = (int(h) * 60 + int(m)) * 60
    reports = parse_delays(a.delay); tt = Timetable(a.build); rec = a.recover * 60
    {'trains': cmd_trains, 'board': cmd_board}[a.cmd](tt, a, reports, rec)

if __name__ == '__main__': main()
