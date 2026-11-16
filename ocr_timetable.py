#!/usr/bin/env python3
"""京阪 駅時刻表PDF(文字アウトライン化・1ページ)から発車時刻を抽出する。

使い方:
  python tools/ocr_timetable.py <pdf> [--out out.csv] [--debug dir]
        [--station 上栄町] [--direction 太秦天神川方面] [--day-type 土休日]

- 時間行(5〜24時)は左端の黒いラベル箱から検出
- 分の数字は tools/digits/ の見本(同じ書体)との形状照合で判定
- 右肩の記号(市/御/四/▽ …)は tools/marks/ の見本と照合。見本に無い記号は
  `?N` として出力し、--debug に切り出し画像を保存する(見本に追加して再実行)
- 駅・方面・ダイヤ種別は PDF の Title メタデータから取るが、方面などが
  実際の表と食い違うPDFがあるため、必ず --direction などで上書きして確認すること
"""
import argparse, csv, os, re, subprocess, sys, glob
import cv2, numpy as np, json

DPI = 200
HERE = os.path.dirname(os.path.abspath(__file__))
DIGIT_DIR = os.path.join(HERE, "digits")
MARK_DIR = os.path.join(HERE, "marks")
DSIZE = (20, 28)   # digit 正規化サイズ (w,h)
MSIZE = (24, 24)   # mark 正規化サイズ

# ---------- 画像処理 ----------
def pdf_title(pdf):
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    m = re.search(r"^Title:\s*(.+)$", out, re.M)
    return m.group(1).strip() if m else os.path.splitext(os.path.basename(pdf))[0]

def render(pdf):
    base = "/tmp/_tt_page"
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", "-singlefile", pdf, base], check=True, stderr=subprocess.DEVNULL)
    return cv2.imread(base + ".png", 0)

def find_rows(img):
    H, W = img.shape
    strip = img[int(H * .15):int(H * .85)]
    xs = np.where((strip < 100).mean(axis=0) > .4)[0]
    left = xs.min()
    dark = (img[:, left + 6:left + 12] < 100).mean(axis=1)
    rows, s = [], None
    for y, v in enumerate(dark):
        if v > .8 and s is None: s = y
        if v <= .8 and s is not None:
            if y - s > 30: rows.append((s, y))
            s = None
    line = img[rows[0][0] + 6, left:] < 100
    right = left + int(np.argmax(~line))
    return rows, left, right

def norm(mask, size):
    ys, xs = np.where(mask > 0)
    if len(ys) == 0: return None
    c = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return cv2.resize(c, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 255

def corr(a, b):
    a, b = a.flatten() - a.mean(), b.flatten() - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def split_blob(mask, templates=None):
    """くっついた数字(例: 44)を分割する。
    見本があれば、左右それぞれの形の一致度の合計が最大になる位置で切る。無ければ縦投影の最小位置。"""
    h, w = mask.shape
    k = int(round(w / (0.72 * h)))
    if k < 2: return [mask]
    if templates and k == 2:
        best, bc = -9, w // 2
        for c in range(int(w * .3), int(w * .7)):
            l, r = mask[:, :c], mask[:, c:]
            if l.sum() == 0 or r.sum() == 0: continue
            sc = classify(l, templates, DSIZE, -1)[1] + classify(r, templates, DSIZE, -1)[1]
            if sc > best: best, bc = sc, c
        return [mask[:, :bc], mask[:, bc:]]
    cols = (mask > 0).sum(axis=0)
    cuts, step = [0], w / k
    for i in range(1, k):
        c = int(step * i); lo, hi = max(1, int(c - step * .25)), min(w - 1, int(c + step * .25))
        cuts.append(lo + int(np.argmin(cols[lo:hi + 1])))
    cuts.append(w)
    return [mask[:, a:b] for a, b in zip(cuts, cuts[1:])]

def find_legend(img):
    """右下の「備考」欄(枠線でつながった濃い塊)の左端x・上端yを返す。無ければ (W, H)。"""
    H, W = img.shape
    x0, y0 = int(W * .5), int(H * .7)
    dark = (img[y0:, x0:] < 100).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, 8)
    best = None
    for j in range(1, n):
        x, y, w, h, a = st[j]
        if w > W * .12 and h < H * .4:   # 備考欄は枠線でつながった大きな塊になる
            if best is None or w * h > best[2] * best[3]: best = (x, y, w, h)
    return (x0 + best[0], y0 + best[1]) if best else (W, H)

def segment(img, digit_templates=None):
    """各時間行を [(hour, [ (digit_masks, mark_mask or None), ... ])] に分解。"""
    H, W = img.shape
    rows, left, right = find_rows(img)
    leg_x, leg_y = find_legend(img)
    out = []
    for i, (y0, y1) in enumerate(rows):
        xmax = (leg_x - 12) if y1 > leg_y else int(W * .965)   # 備考欄と重なる行だけ手前で止める
        crop = img[y0 + 4:y1 - 4, right + 12:xmax]
        bw = (crop < 120).astype(np.uint8) * 255
        n, lab, st, _ = cv2.connectedComponentsWithStats(bw, 8)
        comps = [(st[j][0], st[j][1], st[j][2], st[j][3], j) for j in range(1, n) if st[j][4] > 12]
        items = []
        if comps:
            big_h = max(c[3] for c in comps)
            big = sorted([c for c in comps if c[3] > big_h * .6], key=lambda c: c[0])
            small = [c for c in comps if c[3] <= big_h * .6]
            groups, cur = [], [big[0]]
            for c in big[1:]:
                if c[0] - (cur[-1][0] + cur[-1][2]) > big_h * .45: groups.append(cur); cur = [c]
                else: cur.append(c)
            groups.append(cur)
            for gi, g in enumerate(groups):
                x1 = max(c[0] + c[2] for c in g)
                nxt = min(c[0] for c in groups[gi + 1]) if gi + 1 < len(groups) else None
                digits = []
                for c in g:
                    m = ((lab == c[4]).astype(np.uint8) * 255)[c[1]:c[1] + c[3], c[0]:c[0] + c[2]]
                    digits += split_blob(m, digit_templates) if c[2] > 1.15 * c[3] else [m]
                ms = [c for c in small if x1 - 4 <= c[0] <= (nxt - 4 if nxt else x1 + big_h)]
                mark = None
                if ms:
                    mx0 = min(c[0] for c in ms); mx1 = max(c[0] + c[2] for c in ms)
                    my0 = min(c[1] for c in ms); my1 = max(c[1] + c[3] for c in ms)
                    mark = bw[my0:my1, mx0:mx1]
                items.append((digits, mark))
        out.append((5 + i, items))
    return out, len(rows)

# ---------- 見本 ----------
def load_templates(d, size):
    t = {}
    for p in glob.glob(os.path.join(d, "*.png")):
        t[os.path.splitext(os.path.basename(p))[0]] = norm(cv2.imread(p, 0), size)
    return t

def classify(mask, templates, size, thr):
    sig = norm(mask, size)
    if sig is None or not templates: return None, 0
    ar = mask.shape[1] / mask.shape[0]
    best, bs = None, -9
    for k, t in templates.items():
        s = corr(sig, t)
        if s > bs: best, bs = k, s
    return (best.split('~')[0] if (best is not None and bs >= thr) else None), bs

def split_marks(mask, digit_h):
    """上下に重なった複数の記号(例: ◇の下に近)を、投影が最小の行で分ける。"""
    h = mask.shape[0]
    if h <= 0.75 * digit_h: return [mask]
    rows = (mask > 0).sum(axis=1)
    lo, hi = int(h * .3), int(h * .7)
    cut = lo + int(np.argmin(rows[lo:hi + 1]))
    top, bot = mask[:cut], mask[cut:]
    return [m for m in (top, bot) if m.sum() > 0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("--out"); ap.add_argument("--debug")
    ap.add_argument("--station"); ap.add_argument("--direction"); ap.add_argument("--day-type")
    a = ap.parse_args()
    parts = (pdf_title(a.pdf).split("_") + ["", "", ""])[:3]
    station = a.station or parts[0]; direction = a.direction or parts[1]; daytype = a.day_type or parts[2]
    lp = os.path.join(MARK_DIR, "legend.json")
    legend = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    digits_t = load_templates(DIGIT_DIR, DSIZE); marks_t = load_templates(MARK_DIR, MSIZE)
    segs, nrows = segment(render(a.pdf), digits_t)
    if nrows != 20: print(f"WARN: 時間行が{nrows}行(想定20)", file=sys.stderr)
    out = a.out or os.path.splitext(a.pdf)[0] + ".csv"
    unknown, bad, total = [], 0, 0
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["station", "day_type", "direction", "depart", "mark", "mark_meaning"])
        for hour, items in segs:
            for digits, markmask in items:
                chars = []
                for d in digits:
                    k, s = classify(d, digits_t, DSIZE, .75); chars.append(k if k else "?")
                txt = "".join(chars)
                mark = ""
                if markmask is not None:
                    labels = []
                    for part in split_marks(markmask, digits[0].shape[0]):
                        k, sc = classify(part, marks_t, MSIZE, .80)
                        if k is None:
                            unknown.append((hour, txt, part)); labels.append(f"?{len(unknown)}")
                        else: labels.append(k)
                    mark = "".join(labels)
                ok = txt.isdigit() and 0 <= int(txt) < 60
                bad += (not ok); total += 1
                w.writerow([station, daytype, direction, f"{hour:02d}:{int(txt):02d}" if ok else f"{hour:02d}:{txt}", mark, "／".join(legend[c] for c in mark if c in legend)])
    if a.debug:
        os.makedirs(a.debug, exist_ok=True)
        for i, (h, t, m) in enumerate(unknown, 1):
            cv2.imwrite(os.path.join(a.debug, f"unknown{i}_{h}h{t}.png"), m)
    print(f"{station}/{direction}/{daytype}: {total}本, 数字の判定不能{bad}, 未知の記号{len(unknown)} -> {out}")

if __name__ == "__main__":
    main()
