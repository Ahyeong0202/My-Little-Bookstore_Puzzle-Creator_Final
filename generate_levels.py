"""
generate_levels.py
──────────────────
Streamlit app.py에서 import하여 사용하는 레벨 생성 모듈.

주요 함수:
  generate_level(lv, row)          → 단일 레벨 JSON dict 생성
  generate_range(start, end, df_n) → 범위 레벨 zip bytes 생성
"""

import json, random, math, io, zipfile
import numpy as np
import pandas as pd
from pathlib import Path

# ════════════════════════════════════════
# 난이도 공식
# ════════════════════════════════════════
LOCAL_VAR = [
    -4.18,-10.77,-9.35,0.77,-12.51,-24.5,16.84,7.51,-23.07,-4.67,
    49.59,28.79,-0.01,-7.79,-21.15,0.89,26.65,31.29,18.55,10.54,
    64.81,44.5,-0.6,26.22,18.69,15.97,18.07,48.05,15.12,46.61,
    -0.1,36.66,9.08,-1.83,-10.36,-9.82,16.77,-5.48,-2.13,0.26,
    -35.93,-12.55,-8.93,8.39,23.32,-11.53,3.89,-13.47,8.79,14.44,
    -19.23,-9.61,-6.62,-0.31,-15.68,-45.8,-17.16,8.99,-15.73,6.0,
    -12.44,-5.44,33.37,7.2,2.44,-12.58,-8.38,22.13,-14.12,-6.12,
    -17.77,-24.71,32.97,-11.54,1.42,-8.55,-1.06,-9.44,7.65,-0.38,
    -34.71,-29.79,-21.23,-26.16,2.33,12.95,-16.47,-34.48,5.62,9.64,
    -15.79,-14.75,44.79,5.4,-39.42,-16.52,-20.26,-44.14,1.36,-8.16
]
LOCAL_MEAN = 3.7109

def difficulty(N: int) -> float:
    b = 70 - 52 * math.exp(-N / 90) + LOCAL_MEAN
    return round(float(np.clip(b + LOCAL_VAR[(N - 1) % 100], 0, 100)), 1)

# ════════════════════════════════════════
# 상수
# ════════════════════════════════════════
COLOR_MAP = {'Blue':0,'Yellow':1,'Red':2,'Green':3,
             'Orange':4,'Purple':5,'White':6,'Black':7}
TILETYPE  = {'Normal':0,'Blank':1,'Stack':2,'Lock':3,'Plank':4,
             'Ice':5,'StackLock':6,'Grass':7,'Ads':8}

CHIP_RANGE = {
    'very_easy':(2,5), 'easy':(3,6), 'normal':(4,6),
    'hard':(5,7),      'very_hard':(6,8)
}
UNLOCK_LV = {'StackLock':29,'Ads':49,'Lock':9,'Plank':59,'Ice':179,'Grass':299}

# 전체 그리드 오르내림 패턴 (seed 고정 → 항상 동일)
_rng0 = np.random.default_rng(0)
_base0 = np.sin(np.linspace(0, 4*math.pi, 500)) * (49-15)/3 + (15+49)/2
GRID_COUNTS  = np.clip(np.round(_base0 + _rng0.uniform(-1.5,1.5,500)), 15, 49).astype(int).tolist()

_rng1 = np.random.default_rng(1)
_base1 = np.sin(np.linspace(0, 4*math.pi, 500)) * (7-2)/3 + (2+7)/2
STACK_COUNTS = np.clip(np.round(_base1 + _rng1.uniform(-1.5,1.5,500)), 2, 7).astype(int).tolist()

# ════════════════════════════════════════
# 유틸
# ════════════════════════════════════════
def _grade(d: float) -> str:
    if d < 25:   return 'very_easy'
    elif d < 45: return 'easy'
    elif d < 60: return 'normal'
    elif d < 75: return 'hard'
    else:        return 'very_hard'

def _parse_colors(val) -> list:
    if pd.isna(val): return []
    return [c.strip() for c in str(val).split(',') if c.strip()]

def _make_hex_board(target: int, max_dim: int = 8):
    best_r = 1
    for r in range(1, 8):
        if 3*r*r + 3*r + 1 <= target: best_r = r
        else: break
    r = best_r
    dim = min(2*r+1, max_dim)
    Y, X = dim, dim
    cy, cx = Y//2, X//2
    playable = set()
    for y in range(Y):
        for x in range(X):
            col  = x - (y - (y & 1)) // 2
            cc   = cx - (cy - (cy & 1)) // 2
            dcol = col - cc
            drow = y - cy
            if max(abs(dcol), abs(drow), abs(dcol + drow)) <= r:
                playable.add((y, x))
    tiles = [[{'TileType': 1} for _ in range(X)] for _ in range(Y)]
    for (y, x) in playable:
        tiles[y][x] = {'TileType': 0}
    return X, Y, tiles, playable

# ════════════════════════════════════════
# 핵심: 단일 레벨 JSON 생성
# ════════════════════════════════════════
def generate_level(lv: int, tbl_row: pd.Series) -> dict:
    """
    lv       : 레벨 번호 (1~500)
    tbl_row  : tblStage_500 해당 레벨 행 (pandas Series)
    returns  : LevelData dict (JSON으로 직렬화 가능)
    """
    rng = random.Random(42 + lv)

    diff        = float(tbl_row['DifficultyScore']) if not pd.isna(tbl_row.get('DifficultyScore', float('nan'))) else difficulty(lv)
    g           = _grade(diff)
    chip_lo, chip_hi = CHIP_RANGE[g]
    total_alloc = int(tbl_row['TotalAllocation']) if not pd.isna(tbl_row['TotalAllocation']) else 100

    # 색상 풀
    init_c     = _parse_colors(tbl_row['InitialAvailableColors'])
    new_c      = _parse_colors(tbl_row['NewColorsMilestones'])
    color_pool = list(dict.fromkeys(init_c + new_c))
    color_ints = [COLOR_MAP[c] for c in color_pool if c in COLOR_MAP]

    # 보드
    target = GRID_COUNTS[lv - 1]
    X, Y, tiles, playable = _make_hex_board(target)
    pl = list(playable)
    rng.shuffle(pl)

    n_stacks = STACK_COUNTS[lv - 1]

    # 사용 가능 타입
    avail = ['Normal', 'Stack']
    for t, ul in UNLOCK_LV.items():
        if lv >= ul: avail.append(t)

    stack_pos = pl[:n_stacks]

    # 기믹 배치
    gimmick_types = [t for t in ['Lock','StackLock','Plank','Ice','Grass','Ads'] if t in avail]
    remaining     = [p for p in pl if p not in stack_pos]
    n_gimmick     = min(max(0, int(len(pl) * rng.uniform(0.05, 0.20))), len(remaining))
    gimmick_pos   = [(remaining[j], rng.choice(gimmick_types)) for j in range(n_gimmick)] if gimmick_types else []

    # 스택 타일
    for (y, x) in stack_pos:
        chips = [rng.choice(color_ints) for _ in range(rng.randint(chip_lo, chip_hi))] if color_ints else [0]
        if 'StackLock' in avail and rng.random() < 0.2:
            ul = rng.choice([max(1, int(total_alloc*0.3)),
                             max(1, int(total_alloc*0.5)),
                             max(1, int(total_alloc*0.7))])
            tiles[y][x] = {'TileType': TILETYPE['StackLock'], 'UnlockLevel': ul, 'Stacks': chips}
        else:
            tiles[y][x] = {'TileType': TILETYPE['Stack'], 'Stacks': chips}

    # 기믹 타일
    for (y, x), ttype in gimmick_pos:
        if ttype == 'Lock':
            tiles[y][x] = {'TileType': TILETYPE['Lock'],
                           'Level': max(1, rng.choice([int(total_alloc*0.3), int(total_alloc*0.6)]))}
        elif ttype == 'Plank':
            tiles[y][x] = {'TileType': TILETYPE['Plank'], 'Level': rng.randint(1, 4)}
        elif ttype == 'Ice':
            chips = [rng.choice(color_ints) for _ in range(rng.randint(chip_lo, chip_hi))] if color_ints else [0]
            tiles[y][x] = {'TileType': TILETYPE['Ice'], 'UnlockLevel': rng.randint(1, 3), 'Stacks': chips}
        elif ttype == 'StackLock':
            chips = [rng.choice(color_ints) for _ in range(rng.randint(chip_lo, chip_hi))] if color_ints else [0]
            tiles[y][x] = {'TileType': TILETYPE['StackLock'],
                           'UnlockLevel': max(1, int(total_alloc*0.3)), 'Stacks': chips}
        elif ttype == 'Grass':
            tiles[y][x] = {'TileType': TILETYPE['Grass']}
        elif ttype == 'Ads':
            tiles[y][x] = {'TileType': TILETYPE['Ads']}

    return {
        'Timestamp': 1778220483778 + lv,
        'GameType': 0,
        'GridOrientation': 0,
        'XCells': X,
        'YCells': Y,
        'Tiles': tiles,
    }

# ════════════════════════════════════════
# 범위 생성 → zip bytes 반환
# ════════════════════════════════════════
def generate_range_zip(
    start: int,
    end: int,
    df_n: pd.DataFrame,
    callback=None
) -> bytes:
    """
    start, end : 레벨 범위 (inclusive)
    df_n       : tblStage_500 N 스테이지 DataFrame (0-indexed, lv=index+1)
    callback   : 진행 콜백 fn(lv, total) — Streamlit progress 업데이트용
    returns    : zip 파일 bytes
    """
    buf = io.BytesIO()
    total = end - start + 1

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for lv in range(start, end + 1):
            idx = lv - 1
            if idx < len(df_n):
                row = df_n.iloc[idx]
            else:
                # 범위 초과 시 마지막 행 재사용
                row = df_n.iloc[-1]

            level_data = generate_level(lv, row)
            json_bytes = json.dumps(level_data, ensure_ascii=False, indent=2).encode('utf-8')
            zf.writestr(f"N_{lv:03d}.json", json_bytes)

            if callback:
                callback(lv - start + 1, total)

    return buf.getvalue()
