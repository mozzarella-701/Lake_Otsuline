#!/usr/bin/env python3
"""manifest.csv に書いたPDFをまとめて取り込み、点検用のサマリを出す。
usage: python tools/batch.py <pdfフォルダ> [manifest.csv] [出力フォルダ]
manifest.csv の列: file,station,direction,day_type  (方面は表の見出しを見て手で書く)
"""
import sys, os, csv, subprocess, collections
pdfdir = sys.argv[1]
manifest = sys.argv[2] if len(sys.argv) > 2 else "manifest.csv"
outdir = sys.argv[3] if len(sys.argv) > 3 else "out"
os.makedirs(outdir, exist_ok=True)
here = os.path.dirname(os.path.abspath(__file__))
merged = []
for r in csv.DictReader(open(manifest, encoding="utf-8-sig")):
    stem = os.path.splitext(r["file"])[0]
    out = os.path.join(outdir, stem + ".csv")
    p = subprocess.run([sys.executable, os.path.join(here, "ocr_timetable.py"), os.path.join(pdfdir, r["file"]),
                        "--out", out, "--station", r["station"], "--direction", r["direction"],
                        "--day-type", r["day_type"], "--debug", os.path.join(outdir, "dbg_" + stem)],
                       capture_output=True, text=True)
    rows = list(csv.DictReader(open(out, encoding="utf-8-sig"))) if os.path.exists(out) else []
    times = [x["depart"] for x in rows]
    problems = []
    if p.stderr.strip(): problems.append(p.stderr.strip())
    if any("?" in t for t in times): problems.append("読めない数字あり")
    if times != sorted(times): problems.append("時刻が昇順でない")
    unk = sorted({x["mark"] for x in rows if x["mark"].startswith("?")})
    if unk: problems.append(f"未知の記号 {len(unk)}件(行単位)")
    print(f'{r["file"]:12} {r["station"]}→{r["direction"]} {r["day_type"]}: {len(rows)}本 '
          f'{times[0] if times else "-"}〜{times[-1] if times else "-"}  ' + (" / ".join(problems) if problems else "OK"))
    merged += rows
with open(os.path.join(outdir, "all.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["station", "day_type", "direction", "depart", "mark", "mark_meaning"])
    w.writeheader(); w.writerows(merged)
print("合計", len(merged), "本 -> all.csv")
