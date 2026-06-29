"""
generate_special_v3.py — 인간 퍼즐 규칙 기반 묘수풀이 생성기

핵심 수정:
  1. 보드+손패 색별 칩 수 = 짝수 (수집 가능 조건)
  2. top 색을 그래프 컬러링으로 배정 → 인접 동색 원천 차단
  3. 스택 내부는 인간 스타일(연속 그룹)로 구성
"""

import random, time, copy
from collections import Counter

COLOR_MAP = {0:'Blue',1:'Yellow',2:'Red',3:'Green',4:'Orange',5:'Purple',6:'White',7:'Black'}
BOARD_Y, BOARD_X = 4, 5
MATCH_TARGET = 10

NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

DIFFICULTY_LEVELS = {
    'D8':  {'empt':4,'pre':2,'n_colors':2,'label':'D8', 'score':8},
    'D12': {'empt':3,'pre':3,'n_colors':2,'label':'D12','score':12},
    'D34': {'empt':2,'pre':4,'n_colors':3,'label':'D34','score':34},
    'D48': {'empt':2,'pre':5,'n_colors':3,'label':'D48','score':48},
    'D52': {'empt':2,'pre':6,'n_colors':4,'label':'D52','score':52},
}


def get_neighbors(y, x, Y, X):
    offs = NEIGHBORS_EVEN if y%2==0 else NEIGHBORS_ODD
    return [(y+dy,x+dx) for dy,dx in offs if 0<=y+dy<Y and 0<=x+dx<X]


class Board:
    def __init__(self, grid):
        self.Y = len(grid); self.X = len(grid[0])
        self.g = copy.deepcopy(grid)

    def top(self, y, x):
        c = self.g[y][x]
        if c is None or not c['chips']: return None
        return c['chips'][-1]

    def is_empty(self, y, x):
        c = self.g[y][x]
        return c is not None and len(c['chips']) == 0

    def place(self, y, x, stack):
        assert self.is_empty(y, x)
        self.g[y][x]['chips'] = list(stack)
        changed = True
        while changed:
            changed = False
            for ry in range(self.Y):
                for rx in range(self.X):
                    if self.g[ry][rx] is None: continue
                    t = self.top(ry, rx)
                    if t is None: continue
                    for ny, nx in get_neighbors(ry, rx, self.Y, self.X):
                        if self.top(ny, nx) == t:
                            if self.top(ry, rx) == t and self.top(ny, nx) == t:
                                self.g[ry][rx]['chips'].pop()
                                self.g[ny][nx]['chips'].pop()
                                changed = True; break
                    if changed: break
                if changed: break

    def free_cells(self):
        return [(y,x) for y in range(self.Y) for x in range(self.X) if self.is_empty(y,x)]

    def all_clear(self):
        return all(
            self.g[y][x] is None or not self.g[y][x]['chips']
            for y in range(self.Y) for x in range(self.X)
        )


def make_cell(chips=None):
    return {'chips': list(chips) if chips else [], 'locked_below': 0}


def _make_layout(Y, X, n_total, rng):
    all_pos = [(y,x) for y in range(Y) for x in range(X)]
    rng.shuffle(all_pos)
    start = all_pos[0]
    chosen = [start]
    frontier = list(get_neighbors(*start, Y, X))
    rng.shuffle(frontier)
    seen_f = set(map(tuple, frontier))
    while len(chosen) < n_total and frontier:
        nxt = frontier.pop(0)
        if tuple(nxt) in set(map(tuple, chosen)): continue
        chosen.append(nxt)
        for nb in get_neighbors(*nxt, Y, X):
            t = tuple(nb)
            if t not in set(map(tuple, chosen)) and t not in seen_f:
                frontier.append(nb); seen_f.add(t)
    if len(chosen) < n_total: return None
    rng.shuffle(chosen)
    return chosen[:n_total]


def _assign_tops(positions, colors, Y, X, rng, max_tries=200):
    """그래프 컬러링: 인접 스택 top 색 충돌 방지"""
    pos_idx = {tuple(p):i for i,p in enumerate(positions)}
    n = len(positions)
    for _ in range(max_tries):
        tops = [None]*n
        order = list(range(n)); rng.shuffle(order)
        ok = True
        for i in order:
            py,px = positions[i]
            used = {tops[pos_idx[tuple(nb)]]
                    for nb in get_neighbors(py,px,Y,X)
                    if tuple(nb) in pos_idx and tops[pos_idx[tuple(nb)]] is not None}
            avail = [c for c in colors if c not in used]
            if not avail: ok=False; break
            tops[i] = rng.choice(avail)
        if ok: return tops
    return None


def _build_stack_from_top(top_color, colors, rng, n_chips_range=(2,7)):
    """
    top 색을 고정하고 아래쪽을 인간 스타일(연속 그룹)로 채움
    stack[-1] = top (맨 위)
    """
    n_chips = rng.randint(*n_chips_range)
    
    # 아래쪽 그룹들 (top 제외)
    stack = []
    remaining = n_chips - 1  # top 1개 예약
    prev = top_color
    while remaining > 0:
        avail = [c for c in colors if c != prev]
        if not avail: avail = colors
        c = rng.choice(avail)
        sz = rng.randint(1, min(3, remaining))
        stack.extend([c]*sz)
        remaining -= sz
        prev = c
    
    # top 추가 (맨 위)
    stack.append(top_color)
    return stack


def count_solutions(grid, Y, X, hand_stacks, max_count=20, max_states=150000):
    init = Board(grid)
    n = len(hand_stacks)
    dfs = [(init, frozenset(), [])]
    solutions = []
    visited = 0
    while dfs and len(solutions) < max_count:
        board, used, path = dfs.pop()
        visited += 1
        if visited > max_states: break
        free = board.free_cells()
        remaining = [i for i in range(n) if i not in used]
        if not remaining:
            if board.all_clear(): solutions.append(path)
            continue
        for hi in remaining:
            for (py, px) in free:
                nb = Board(board.g)
                nb.place(py, px, hand_stacks[hi])
                dfs.append((nb, used|{hi}, path+[{'hand_idx':hi,'pos':(py,px),'chips':hand_stacks[hi]}]))
    return solutions


def _attempt(pid, cfg, rng):
    empt=cfg['empt']; n_pre=cfg['pre']; n_colors=cfg['n_colors']
    Y,X = BOARD_Y, BOARD_X
    n_total = empt + n_pre
    if n_total > Y*X: return None

    positions = _make_layout(Y, X, n_total, rng)
    if positions is None: return None
    pre_pos = positions[:n_pre]
    normal_pos = positions[n_pre:]

    colors = rng.sample(range(8), n_colors)

    # 1. top 색 그래프 컬러링으로 배정 → 인접 동색 원천 차단
    tops = _assign_tops(pre_pos, colors, Y, X, rng)
    if tops is None: return None

    # 2. 각 스택 칩 구성 (top 고정, 아래는 인간 스타일)
    pre_chips = [_build_stack_from_top(tops[i], colors, rng) for i in range(n_pre)]

    # 3. 보드 색별 칩 수 파악
    board_cnt = Counter(c for chips in pre_chips for c in chips)

    # 4. 손패를 짝수 조건 맞춰서 생성
    # 각 색의 보드 칩 수가 홀수면 손패에서 홀수개 추가 → 전체 짝수
    # 짝수면 손패에서 짝수개 추가
    hand_pool = []
    for c in colors:
        board_n = board_cnt.get(c, 0)
        # 추가할 양: 1~4개, 단 전체 합이 짝수되도록
        add = rng.randint(1, 4)
        if (board_n + add) % 2 != 0:
            add += 1  # 홀수면 1 더해서 짝수로
        hand_pool.extend([c] * add)

    if len(hand_pool) < 3: return None
    rng.shuffle(hand_pool)

    # 3장으로 분배 (각 장 최소 1칩)
    total_h = len(hand_pool)
    if total_h < 3: return None
    cuts = sorted(rng.sample(range(1, total_h), 2))
    hand_stacks = [hand_pool[:cuts[0]], hand_pool[cuts[0]:cuts[1]], hand_pool[cuts[1]:]]
    if any(len(h) == 0 for h in hand_stacks): return None

    # 5. grid 생성
    grid = [[None]*X for _ in range(Y)]
    for py,px in normal_pos: grid[py][px] = make_cell()
    for i,(py,px) in enumerate(pre_pos): grid[py][px] = make_cell(chips=pre_chips[i])

    # 6. 해 탐색
    solutions = count_solutions(grid, Y, X, hand_stacks, max_count=20)
    if not solutions: return None

    n_sol = len(solutions)
    if n_sol >= 12: forcing=0
    elif n_sol >= 5: forcing=1
    elif n_sol >= 2: forcing=2
    else: forcing=3

    # 7. JSON 조립
    tiles = [[{'TileType':1}]*X for _ in range(Y)]
    for py,px in normal_pos: tiles[py][px] = {'TileType':0}
    for i,(py,px) in enumerate(pre_pos):
        tiles[py][px] = {'TileType':2,'Stacks':pre_chips[i],'LockedBelow':0}

    board_json = {'Timestamp':int(time.time()*1000)+pid,'GameType':1,
                  'GridOrientation':0,'XCells':X,'YCells':Y,'Tiles':tiles}
    stack_info = {'Id':pid}
    for i,hs in enumerate(hand_stacks):
        stack_info[f'Stack{i+1}'] = ','.join(COLOR_MAP[c] for c in hs)
    stage_row = {'Id':1000+pid,'LevelName':f'S {pid:02d}','TurnCount':len(hand_stacks),'Mode':'Turn'}

    return {
        'board_json':board_json,'hand_stacks':hand_stacks,
        'pre_pos':pre_pos,'normal_pos':normal_pos,'pre_chips':pre_chips,
        'solution':solutions[0],'n_solutions':n_sol,'forcing':forcing,
        'board_chips':Counter(c for ch in pre_chips for c in ch),
        'hand_chips':Counter(c for h in hand_stacks for c in h),
        'stack_info':stack_info,'stage_row':stage_row,
        'normal_cells':empt,'n_stacks':n_pre,'n_colors':n_colors,
        'difficulty':cfg['label'],'diff_score':cfg['score'],
    }


def generate_special_puzzle(puzzle_id, difficulty='D34', n_colors=None, seed=None, max_attempts=1500):
    cfg = dict(DIFFICULTY_LEVELS[difficulty])
    if n_colors is not None: cfg['n_colors'] = n_colors
    base_seed = seed if seed is not None else puzzle_id*12345
    for attempt in range(max_attempts):
        rng = random.Random(base_seed + attempt*7919)
        r = _attempt(puzzle_id, cfg, rng)
        if r is not None: return r
    raise RuntimeError(f"S{puzzle_id:03d}: {max_attempts}회 실패 ({difficulty})")


def analyze_special(result):
    return {'difficulty':result['difficulty'],'diff_score':result['diff_score'],
            'forcing':result['forcing'],'n_solutions':result['n_solutions'],
            'normal_cells':result['normal_cells'],'n_pre':result['n_stacks']}

def solve(result): return result.get('solution')


if __name__ == '__main__':
    import time as _t
    pattern = ['D12','D34','D12','D48','D34','D8','D34','D48','D34','D52']
    print("=== S01~S40 테스트 ===")
    ok=fail=conflict=0; t0=_t.time()
    for pid in range(1, 41):
        diff = pattern[(pid-1)%10]
        try:
            r = generate_special_puzzle(pid, difficulty=diff, seed=pid*12345)
            tiles = r['board_json']['Tiles']
            Y,X = r['board_json']['YCells'],r['board_json']['XCells']
            tops = {(y,x):t['Stacks'][-1] for y in range(Y) for x in range(X)
                    if (t:=tiles[y][x]).get('TileType')==2 and t.get('Stacks')}
            adj = any(tops.get(tuple(nb))==top for (y,x),top in tops.items()
                      for nb in get_neighbors(y,x,Y,X) if tuple(nb) in tops)
            if adj: conflict+=1; print(f"S_{pid:02d} {diff} ⚠️ 동색인접!")
            else: ok+=1; print(f"S_{pid:02d} {diff} ✓ forcing={r['forcing']} sol={r['n_solutions']}")
        except Exception as e: fail+=1; print(f"S_{pid:02d} {diff} ✗ {e}")
    print(f"\n성공:{ok} 실패:{fail} 동색충돌:{conflict} ({_t.time()-t0:.1f}초)")
