#!/usr/bin/env python3
"""駅ごとの発車時刻CSVから、列車1本ごとの全駅の時刻(trips / stop_times)を組み立てる。

usage: python tools/assemble_trips.py data/otsu_holiday_all.csv build [--day-type holiday]
出力(build/): lines.csv stations.csv line_stations.csv trips.csv stop_times.csv turnbacks.csv
前提: 隣の駅どうしの所要時間はほぼ一定で、同じ駅を2分以内に2本が出ることはない。
"""
import csv, sys, os, statistics as st, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import network as N

def mins(s): h, m = s.split(':'); return int(h) * 60 + int(m)

def load(path):
    deps = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(path, encoding='utf-8-sig')):
        line, d = N.classify(r['direction'])
        deps[(line, d)][r['station']].append((mins(r['depart']), r['mark'], r['mark_meaning']))
    for k in deps:
        for s in deps[k]: deps[k][s].sort()
    return deps

def assemble(order, dep):
    """進行順 order の各駅の発車リスト dep から列車を組み立てる。"""
    trips, active, pair_runs = [], [], {}
    for i, stn in enumerate(order):
        B = dep.get(stn)
        if B is None:
            if i != len(order) - 1: raise SystemExit(f'途中の駅の時刻表がありません: {stn}')
            break
        if i == 0:
            for b in B:
                t = {'stops': [(i, b[0], b[1])]}; trips.append(t); active.append(t)
            continue
        # 所要時間の中央値（ゆるく突き合わせて推定）
        used, diffs = set(), []
        for t in sorted(active, key=lambda x: x['stops'][-1][1]):
            lt = t['stops'][-1][1]
            c = [(b[0] - lt, j) for j, b in enumerate(B) if j not in used and 1 <= b[0] - lt <= 8]
            if c: d, j = min(c); used.add(j); diffs.append(d)
        med = st.median(diffs); pair_runs[(order[i - 1], stn)] = med
        # 中央値±1分で厳密に突き合わせ
        used, nxt = set(), []
        for t in sorted(active, key=lambda x: x['stops'][-1][1]):
            lt = t['stops'][-1][1]
            c = [(abs(b[0] - lt - med), j) for j, b in enumerate(B) if j not in used and abs(b[0] - lt - med) <= 1]
            if c:
                _, j = min(c); used.add(j); t['stops'].append((i, B[j][0], B[j][1])); nxt.append(t)
        for j, b in enumerate(B):
            if j not in used:
                t = {'stops': [(i, b[0], b[1])]}; trips.append(t); nxt.append(t)
        active = nxt
    return trips, pair_runs

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('out'); ap.add_argument('--day-type', default='holiday')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deps = load(a.csv)
    built, runs = {}, collections.defaultdict(list)
    for (line, d), dep in deps.items():
        order = N.order(line, d)
        trips, pr = assemble(order, dep)
        built[(line, d)] = (order, trips)
        for (x, y), m in pr.items(): runs[(line, frozenset((x, y)))].append(m)
    run = {k: st.mean(v) for k, v in runs.items()}   # 駅間の所要時間（上り下りの平均）

    rows_trip, rows_stop, report = [], [], collections.defaultdict(int)
    tid = 0; allt = []
    for (line, d), (order, trips) in sorted(built.items()):
        for t in sorted(trips, key=lambda t: t['stops'][0][1]):
            tid += 1
            idxs = [s[0] for s in t['stops']]; last = idxs[-1]
            endi = last + 1 if last + 1 < len(order) else last
            marks = set(''.join(s[2] for s in t['stops']))
            dm = [m for m in N.DEST_MARKS if m in marks]
            # 行先
            if (line, d) == ('keishin', 'up'):
                head = N.DEST_MARKS[dm[0]] if dm and dm[0] != '近' else '太秦天神川'
            elif (line, d) == ('keishin', 'down'): head = 'びわ湖浜大津'
            else:
                head = '近江神宮前' if '近' in marks else ('坂本比叡山口' if d == 'to_sakamoto' else '石山寺')
            # 検算: 行先の記号と終着駅が合っているか
            expect = {'近': '近江神宮前', '四': '四宮'}
            for m, stn in expect.items():
                if m in marks and order[endi] != stn: report['記号と終着駅が不一致'] += 1
            if len(dm) > 1: report['行先記号が複数'] += 1
            # 各駅の記号が途中で変わるか（行先記号のみ判定）
            seen = {frozenset(c for c in s[2] if c in N.DEST_MARKS) for s in t['stops']}
            if len(seen) > 1: report['行先記号が途中で変化'] += 1
            conn = sorted({N.CONN_MARKS[c] for c in marks if c in N.CONN_MARKS})
            note = ('びわ湖浜大津で京津線 ' + '・'.join(conn) + 'ゆきに連絡') if conn else ''
            arr_end = t['stops'][-1][1] + run.get((line, frozenset((order[last], order[endi]))), 2) if endi != last else None
            rows_trip.append([tid, line, a.day_type, d, head, '', note])
            for k, (i, tm, mk) in enumerate(t['stops']):
                rows_stop.append([tid, k + 1, N.STATIONS[order[i]], tm * 60, tm * 60])
            if arr_end is not None:
                rows_stop.append([tid, len(t['stops']) + 1, N.STATIONS[order[endi]], round(arr_end * 60), ''])
            allt.append(dict(id=tid, line=line, dir=d, order=order, first=t['stops'][0], last_i=last, endi=endi,
                             arr=arr_end, head=head))
    # 折り返しの推定（運用の連結）: 路線内で終着駅=始発駅の列車を、待ち時間が最短になるように結ぶ
    links, TB = [], collections.defaultdict(list)
    for t in allt:
        if t['endi'] == t['last_i']: continue
        endst = t['order'][t['endi']]
        if t['line'] == 'keishin' and t['dir'] == 'up' and t['head'] != '御陵': continue   # 地下鉄へ直通
        TB[(t['line'], endst)].append(t)
    starts = collections.defaultdict(list)
    for t in allt:
        starts[(t['line'], t['order'][t['first'][0]])].append(t)
    for (line, stn), ends in TB.items():
        free = sorted([s for s in starts[(line, stn)] if s['first'][1] is not None], key=lambda s: s['first'][1])
        for e in sorted(ends, key=lambda x: x['arr']):
            c = [s for s in free if s['dir'] != e['dir'] and 2 <= s['first'][1] - e['arr'] <= 30]
            if c:
                s = c[0]; free.remove(s); links.append([e['id'], s['id'], N.STATIONS[stn], round(s['first'][1] - e['arr'], 1)])
            else: report['折り返し先が見つからない'] += 1
    w = lambda name, head, rows: csv.writer(open(os.path.join(a.out, name), 'w', newline='', encoding='utf-8')).writerows([head] + rows)
    w('lines.csv', ['id', 'name', 'operator'], [[k, v[0], '京阪電気鉄道'] for k, v in N.LINES.items()])
    w('stations.csv', ['id', 'name'], [[v, k] for k, v in N.STATIONS.items()])
    w('line_stations.csv', ['line_id', 'station_id', 'seq'], [[k, N.STATIONS[s], i + 1] for k, v in N.LINES.items() for i, s in enumerate(v[1])])
    w('trips.csv', ['id', 'line_id', 'day_type_id', 'direction', 'headsign', 'kind', 'note'], rows_trip)
    w('stop_times.csv', ['trip_id', 'seq', 'station_id', 'arrival_sec', 'departure_sec'], rows_stop)
    w('turnbacks.csv', ['from_trip', 'to_trip', 'station_id', 'wait_min'], links)
    # レポート
    print(f'列車 {len(rows_trip)}本 / 停車 {len(rows_stop)}行 / 折り返し連結 {len(links)}件')
    per = collections.Counter((t['line'], t['dir']) for t in allt)
    for k, v in sorted(per.items()): print('  ', k, v, '本')
    print('検算:', dict(report) if report else 'すべて一致')
    waits = [l[3] for l in links]
    if waits: print(f'折り返し待ち時間: 中央値{st.median(waits)}分 最小{min(waits)} 最大{max(waits)}')

if __name__ == '__main__': main()
