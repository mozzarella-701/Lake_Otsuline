"""大津線の路線定義。駅の並びは時刻表の所要時間（隣駅1〜4分で全区間一致）で確認済み。"""
# 駅名 -> (id, 英語名) 。id は PDF の英語表記から作った
STATIONS = {
 '御陵': 'misasagi', '京阪山科': 'keihan-yamashina', '四宮': 'shinomiya', '追分': 'oiwake', '大谷': 'otani',
 '上栄町': 'kamisakaemachi', 'びわ湖浜大津': 'biwako-hamaotsu',
 '石山寺': 'ishiyamadera', '唐橋前': 'karahashi-mae', '京阪石山': 'keihan-ishiyama', '粟津': 'awazu',
 '瓦ヶ浜': 'kawaragahama', '中ノ庄': 'nakanosho', '膳所本町': 'zeze-hommachi', '錦': 'nishiki',
 '京阪膳所': 'keihan-zeze', '石場': 'ishiba', '島ノ関': 'shimanoseki',
 '三井寺': 'miidera', '大津市役所前': 'otsu-shiyakusho-mae', '京阪大津京': 'keihan-otsukyo',
 '近江神宮前': 'omi-jingu-mae', '南滋賀': 'minami-shiga', '滋賀里': 'shigasato', '穴太': 'anoo',
 '松ノ馬場': 'matsunobamba', '坂本比叡山口': 'sakamoto-hieizanguchi',
}
LINES = {
 'keishin': ('京津線', ['御陵', '京阪山科', '四宮', '追分', '大谷', '上栄町', 'びわ湖浜大津']),
 'ishiyama-sakamoto': ('石山坂本線', ['石山寺', '唐橋前', '京阪石山', '粟津', '瓦ヶ浜', '中ノ庄', '膳所本町', '錦', '京阪膳所',
                                    '石場', '島ノ関', 'びわ湖浜大津', '三井寺', '大津市役所前', '京阪大津京', '近江神宮前',
                                    '南滋賀', '滋賀里', '穴太', '松ノ馬場', '坂本比叡山口']),
}
# (路線, 方向) -> 進行順の駅リスト
def order(line, d):
    geo = LINES[line][1]
    return geo[::-1] if d in ('up', 'to_ishiyama') else geo

def classify(direction):
    """時刻表の見出し(方面)から (路線, 方向) を決める。"""
    if '太秦天神川方面' in direction: return 'keishin', 'up'            # 浜大津→御陵
    if direction == 'びわ湖浜大津方面': return 'keishin', 'down'          # 御陵→浜大津
    if '坂本比叡山口方面' in direction: return 'ishiyama-sakamoto', 'to_sakamoto'
    if '石山寺方面' in direction: return 'ishiyama-sakamoto', 'to_ishiyama'
    raise ValueError(direction)

DEST_MARKS = {'近': '近江神宮前', '四': '四宮', '市': '京都市役所前', '御': '御陵'}
CONN_MARKS = {'○': '太秦天神川', '△': '京都市役所前', '□': '御陵', '◇': '四宮'}  # びわ湖浜大津で京津線に連絡
