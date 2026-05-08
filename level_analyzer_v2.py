import json
import csv
from pathlib import Path

# ── TileType 매핑
TILE = {
    0: 'Normal', 1: 'Blank',  2: 'Stack',   3: 'Lock',
    4: 'Plank',  5: 'Ice',    6: 'StackLock',7: 'Grass',
    8: 'Ads',    9: 'CameraPicture',
}

# ── 헥사 이웃 오프셋 (Horizontal orientation)
NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

def open_sides(y, x, tiles, Y, X):
    """해당 셀의 열린 변 수 (이웃이 Blank가 아니고 보드 안인 변)"""
    offsets = NEIGHBORS_EVEN if y % 2 == 0 else NEIGHBORS_ODD
    count = 0
    for dy, dx in offsets:
        ny, nx = y+dy, x+dx
        if 0 <= ny < Y and 0 <= nx < X:
            if tiles[ny][nx].get('TileType', 1) != 1:  # Blank(1) 아니면 열린 변
                count += 1
        # 보드 밖 = 닫힌 변
    return count

def color_changes(stacks: list) -> int:
    """인접한 칩 색이 바뀌는 횟수"""
    return sum(1 for i in range(1, len(stacks)) if stacks[i] != stacks[i-1])

def analyze_level(data: dict) -> dict:
    Y = data['YCells']
    X = data['XCells']
    tiles = data['Tiles']

    # 타입별 분류
    groups = {t: [] for t in TILE.values()}
    for y in range(Y):
        for x in range(X):
            t = tiles[y][x]
            tt = t.get('TileType', 0)
            groups[TILE[tt]].append((y, x, t))

    def side_sum(cell_list):
        return sum(open_sides(y, x, tiles, Y, X) for y, x, _ in cell_list)

    # Stack + StackLock 합산
    stacks_all = groups['Stack'] + groups['StackLock']

    # H1-1: XCells × YCells 전체
    H1_1 = X * Y

    # H1-2: Normal 열린 변 합 (낮을수록 어려움)
    H1_2 = side_sum(groups['Normal'])

    # H1-3: Normal 개수 (적을수록 어려움)
    H1_3 = len(groups['Normal'])

    # H1-4: Stack+StackLock 열린 변 합 (낮을수록 어려움)
    H1_4 = side_sum(stacks_all)

    # H1-5: Stack+StackLock 개수 (많을수록 어려움)
    H1_5 = len(stacks_all)

    # H1-6: 타일 색 총합 (많을수록 어려움)
    H1_6 = sum(len(t.get('Stacks', [])) for _, _, t in stacks_all)

    # H1-7: 색 변화 복잡도 (많을수록 어려움)
    H1_7 = sum(color_changes(t.get('Stacks', [])) for _, _, t in stacks_all)

    # H1-8: Lock 열린 변 합 (많을수록 어려움 — 잠겨있으므로)
    H1_8 = side_sum(groups['Lock'])

    # H1-9: Lock 개수 (많을수록 어려움)
    H1_9 = len(groups['Lock'])

    # H1-10: StackLock 열린 변 합 (많을수록 어려움 — 잠겨있으므로)
    H1_10 = side_sum(groups['StackLock'])

    # H1-11: StackLock 개수 (많을수록 어려움)
    H1_11 = len(groups['StackLock'])

    # H1-12: 잠금 해제 기준 합
    #   Lock + Plank → Level
    #   StackLock + Ice → UnlockLevel
    H1_12 = (sum(t.get('Level', 0) for _, _, t in groups['Lock'] + groups['Plank']) +
              sum(t.get('UnlockLevel', 0) for _, _, t in groups['StackLock'] + groups['Ice']))

    # H1-13: Ads 열린 변 합 (낮을수록 어려움 — 광고 접근 어려움)
    H1_13 = side_sum(groups['Ads'])

    # H1-14: Ads 개수 (많을수록 쉬움 — 광고 무조건 본다는 가정, 최대 3개 반영)
    H1_14 = min(len(groups['Ads']), 3)

    # H1-15: 기타 기믹 위치 열린 변 합 (낮을수록 어려움)
    gimmicks = groups['Plank'] + groups['Ice'] + groups['Grass'] + groups['CameraPicture']
    H1_15 = side_sum(gimmicks)

    return {
        'XCells': X, 'YCells': Y,
        'H1_1':  H1_1,
        'H1_2':  H1_2,
        'H1_3':  H1_3,
        'H1_4':  H1_4,
        'H1_5':  H1_5,
        'H1_6':  H1_6,
        'H1_7':  H1_7,
        'H1_8':  H1_8,
        'H1_9':  H1_9,
        'H1_10': H1_10,
        'H1_11': H1_11,
        'H1_12': H1_12,
        'H1_13': H1_13,
        'H1_14': H1_14,
        'H1_15': H1_15,
        'tile_counts': {k: len(v) for k, v in groups.items()},
    }

def analyze_file(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    r = analyze_level(data)
    r['file'] = Path(path).stem
    return r

def analyze_directory(dir_path: str) -> list:
    results = []
    for p in sorted(Path(dir_path).glob('*.json')):
        try:
            results.append(analyze_file(str(p)))
        except Exception as e:
            print(f"  오류 {p.name}: {e}")
    return results

FIELD_NAMES = [
    'file','XCells','YCells',
    'H1_1','H1_2','H1_3','H1_4','H1_5','H1_6','H1_7',
    'H1_8','H1_9','H1_10','H1_11','H1_12','H1_13','H1_14','H1_15'
]

def to_csv(results: list, output_path: str):
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV 저장 완료: {output_path} ({len(results)}개)")

def print_result(r: dict):
    print(f"\n{'─'*52}")
    print(f"파일: {r.get('file','')}   보드: {r['XCells']}×{r['YCells']} = {r['H1_1']}칸")
    print(f"  타일 구성: {r['tile_counts']}")
    rows = [
        ("H1-1",  "전체 그리드 수",       r['H1_1'],  "많을수록 쉬움"),
        ("H1-2",  "빈 그리드 열린 변 합", r['H1_2'],  "낮을수록 어려움"),
        ("H1-3",  "순수 빈 칸 수",        r['H1_3'],  "적을수록 어려움"),
        ("H1-4",  "스택 열린 변 합",      r['H1_4'],  "낮을수록 어려움"),
        ("H1-5",  "스택 개수",            r['H1_5'],  "많을수록 어려움"),
        ("H1-6",  "타일 색 총합",         r['H1_6'],  "많을수록 어려움"),
        ("H1-7",  "색 변화 복잡도",       r['H1_7'],  "많을수록 어려움"),
        ("H1-8",  "잠금 그리드 열린 변",  r['H1_8'],  "많을수록 어려움"),
        ("H1-9",  "잠금 그리드 개수",     r['H1_9'],  "많을수록 어려움"),
        ("H1-10", "잠금 스택 열린 변",    r['H1_10'], "많을수록 어려움"),
        ("H1-11", "잠금 스택 개수",       r['H1_11'], "많을수록 어려움"),
        ("H1-12", "잠금 해제 기준 합",    r['H1_12'], "클수록 어려움"),
        ("H1-13", "광고 열린 변 합",      r['H1_13'], "낮을수록 어려움"),
        ("H1-14", "광고 수 (최대 3)",     r['H1_14'], "많을수록 쉬움"),
        ("H1-15", "기믹 열린 변 합",      r['H1_15'], "낮을수록 어려움"),
    ]
    for code, name, val, direction in rows:
        print(f"  {code:6s} {name:20s} {val:5}   ({direction})")

# ── 샘플 테스트
if __name__ == '__main__':
    import sys

    if len(sys.argv) == 1:
        # 샘플 JSON으로 테스트
        sample = {
          "Timestamp": 1778220483778,
          "GameType": 0, "GridOrientation": 0,
          "XCells": 7, "YCells": 7,
          "Tiles": [
            [{"TileType":0},{"TileType":1},{"TileType":0},{"TileType":0},{"TileType":7},{"TileType":0},{"TileType":1}],
            [{"UnlockLevel":50,"Stacks":[3,6,0],"TileType":6},{"TileType":0},{"TileType":0},{"Stacks":[0,1,2,3,4,5,6,7],"TileType":2},{"TileType":0},{"TileType":0},{"TileType":8}],
            [{"TileType":8},{"TileType":1},{"TileType":0},{"TileType":0},{"TileType":1},{"TileType":0},{"UnlockLevel":15,"Stacks":[0,0,0],"TileType":6}],
            [{"TileType":0},{"TileType":0},{"UnlockLevel":2,"Stacks":[],"TileType":5},{"TileType":0},{"Level":20,"TileType":3},{"TileType":0},{"TileType":0}],
            [{"Level":1,"TileType":4},{"TileType":7},{"TileType":0},{"TileType":0},{"TileType":0},{"TileType":0},{"UnlockLevel":1,"Stacks":[],"TileType":5}],
            [{"TileType":0},{"TileType":0},{"TileType":1},{"TileType":8},{"TileType":0},{"TileType":1},{"TileType":0}],
            [{"TileType":0},{"TileType":0},{"TileType":0},{"TileType":0},{"TileType":0},{"TileType":0},{"TileType":0}]
          ]
        }
        r = analyze_level(sample)
        r['file'] = 'sample'
        print_result(r)

    elif len(sys.argv) == 2:
        path = sys.argv[1]
        if path.endswith('.json'):
            r = analyze_file(path)
            print_result(r)
        else:
            results = analyze_directory(path)
            for r in results: print_result(r)

    elif len(sys.argv) == 3:
        results = analyze_directory(sys.argv[1])
        to_csv(results, sys.argv[2])
        for r in results: print_result(r)
