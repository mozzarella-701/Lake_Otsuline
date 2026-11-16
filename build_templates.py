#!/usr/bin/env python3
"""正解CSV(目視確認済み)から数字・記号の見本を作る。初回セットアップ用。
usage: build_templates.py <pdf> <verified.csv> <direction> [--marks '5:13=市,...']
"""
import sys, os, csv, cv2, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_timetable as t

ap = argparse.ArgumentParser()
ap.add_argument("pdf"); ap.add_argument("csv"); ap.add_argument("direction")
ap.add_argument("--marks", default="", help="例: 05:13=市,10:02=四")
a = ap.parse_args()
gt = [r for r in csv.DictReader(open(a.csv, encoding="utf-8-sig")) if r["direction"] == a.direction]
segs, _ = t.segment(t.render(a.pdf))
times = [(h, d, m) for h, items in segs for d, m in items]
assert len(times) == len(gt), (len(times), len(gt))
os.makedirs(t.DIGIT_DIR, exist_ok=True); os.makedirs(t.MARK_DIR, exist_ok=True)
seen = {}
for (h, digits, mark), row in zip(times, gt):
    mm = row["depart"].split(":")[1].lstrip("0") or "0"
    assert int(row["depart"][:2]) == h
    assert len(mm) == len(digits), (row["depart"], len(digits))
    for ch, d in zip(mm, digits): seen.setdefault(ch, d)
for ch, d in seen.items():
    cv2.imwrite(os.path.join(t.DIGIT_DIR, f"{ch}.png"), d)
mk = dict(x.split("=") for x in a.marks.split(",") if x)
for (h, digits, mark), row in zip(times, gt):
    if mark is not None and row["depart"] in mk:
        cv2.imwrite(os.path.join(t.MARK_DIR, f"{mk[row['depart']]}.png"), mark)
print("digits:", sorted(seen), "marks:", sorted(os.listdir(t.MARK_DIR)))
