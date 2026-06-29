"""
generate_special_v2.py  — trap 없는 인간 방식 묘수풀이 생성기

핵심 설계 (S01~S34 분석 기반):
  - 모든 스택 prePlaced (LockedBelow=0), trap 없음
  - 동색 top 인접 금지
  - 손패 3장을 빈칸에 배치 → 인접 동색 연쇄 수집 → 보드 클리어
  - 해가 반드시 존재해야 함
"""

import random, time, copy
from collections import Counter

COLOR_MAP = {0:'Blue',1:'Yellow',2:'Red',3:'Green',4:'Orange',5:'Purple',6:'White',7:'Black'}
BOARD_Y, BOARD_X = 4, 5
MATCH_TARGET = 10  # 호환용

NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

DIFFICULTY_LEVELS = {
    'D8':  {'empt':4,'pre':2,'n_colors':2,'label':'D8', 'score':8,  'name':'아주 쉬움'},
    'D12': {'empt':3,'pre':3,'n_colors':2,'label':'D12','score':12, 'name':'쉬움'},
    'D34': {'empt':2,'pre':4,'n_colors':3,'label':'D34','score':34, 'name':'보통'},
    'D48': {'empt':2,'pre':5,'n_colors':3,'label':'D48','score':48, 'name':'어려움'},
    'D52': {'empt':2,'pre':6,'n_colors':4,'label':'D52','score':52, 'name':'아주 어려움'},
}


def get_neighbors(y, x, Y, X):
    offs = NEIGHBORS_EVEN if y%2==0 else NEIGHBORS_ODD
    return [(y+dy,x+dx) for dy,dx in offs if 0<=y+dy<Y and 0<=x+dx<X]


# ══════════════════════════════════════════════════
# Board
# ══════════════════════════════════════════════════
class Board:
    def __init__(self, grid):
        self.Y = len(grid)
        self.X = len(grid[0])
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
                                changed = True
                                break
                    if changed: break
                if changed: break

    def free_cells(self):
        return [(y,x) for y in range(self.Y) for x in range(self.X)
                if self.is_empty(y,x)]

    def all_clear(self):
        for y in range(self.Y):
            for x in range(self.X):
                c = self.g[y][x]
                if c is not None and c['chips']: return False
        return True


def make_cell(chips=None):
    return {'chips': list(chips) if chips else [], 'locked_below': 0}


# ══════════════════════════════════════════════════
# 레이아웃
# ══════════════════════════════════════════════════
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
            if t not in set(map(tuple,chosen)) and t not in seen_f:
                frontier.append(nb); seen_f.add(t)
    if len(chosen) < n_total: return None
    rng.shuffle(chosen)
    return chosen[:n_total]


# ══════════════════════════════════════════════════
# 해 탐색
# ══════════════════════════════════════════════════
def count_solutions(grid, Y, X, hand_stacks, max_count=20, max_states=200000):
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
            if board.all_clear():
                solutions.append(path)
            continue
        for hi in remaining:
            for (py, px) in free:
                nb = Board(board.g)
                nb.place(py, px, hand_stacks[hi])
                dfs.append((nb, used | {hi},
                            path + [{'hand_idx':hi,'pos':(py,px),'chips':hand_stacks[hi]}]))
    return solutions


# ══════════════════════════════════════════════════
# 핵심: 역방향 설계 (해를 먼저 정하고 보드 구성)
# ══════════════════════════════════════════════════
def _attempt(pid, cfg, rng):
    """
    역방향 설계:
    1. 빈칸 위치와 손패 배치 순서를 먼저 정함
    2. 각 배치 시 수집될 칩을 prePlaced에서 역산
    3. 동색 top 인접 없도록 조정
    """
    empt     = cfg['empt']
    n_pre    = cfg['pre']
    n_colors = cfg['n_colors']
    Y, X     = BOARD_Y, BOARD_X
    n_total  = empt + n_pre

    if n_total > Y * X: return None

    # 1. 위치 배정
    positions = _make_layout(Y, X, n_total, rng)
    if positions is None: return None

    pre_pos    = positions[:n_pre]
    normal_pos = positions[n_pre:]

    # 2. 색 선택
    colors = rng.sample(range(8), n_colors)

    # 3. 손패 3장 구성 — 각 장은 1~2가지 색, 1~6칩
    def make_hand_stacks():
        hands = []
        for _ in range(3):
            nc = rng.randint(1, min(2, n_colors))
            hand_colors = rng.sample(colors, nc)
            chips = []
            for hc in hand_colors:
                chips.extend([hc] * rng.randint(1, 3))
            rng.shuffle(chips)
            if not chips: return None
            hands.append(chips)
        return hands

    hand_stacks = make_hand_stacks()
    if hand_stacks is None: return None

    # 4. prePlaced 스택 구성
    #    각 색별 총 칩 = 손패의 해당 색 수 + prePlaced의 해당 색 수
    #    → prePlaced에서 각 색을 일정량 배분
    hand_color_cnt = Counter(c for h in hand_stacks for c in h)

    # 각 색에 prePlaced 칩 추가 (손패와 합쳐서 수집 가능하도록)
    # 간단 전략: 각 색을 rng.randint(1,6)개씩 prePlaced에 넣고 섞어 배치
    pre_chip_pool = []
    for c in colors:
        cnt = rng.randint(2, 8)
        pre_chip_pool.extend([c] * cnt)
    rng.shuffle(pre_chip_pool)

    # n_pre개 스택에 배분
    if len(pre_chip_pool) < n_pre: return None
    stack_sizes = []
    remaining = len(pre_chip_pool)
    for i in range(n_pre):
        left = n_pre - i - 1
        lo = max(1, remaining - left * 8)
        hi = min(8, remaining - left)
        if lo > hi: return None
        sz = rng.randint(lo, hi)
        stack_sizes.append(sz)
        remaining -= sz
    if remaining != 0: return None

    pre_chips = []
    idx = 0
    for sz in stack_sizes:
        stack = pre_chip_pool[idx:idx+sz]
        rng.shuffle(stack)
        pre_chips.append(stack)
        idx += sz

    # 5. 동색 top 인접 금지 체크
    pre_top_map = {tuple(pp): chips[-1] for pp, chips in zip(pre_pos, pre_chips) if chips}
    for pp in pre_pos:
        top = pre_top_map.get(tuple(pp))
        if top is None: continue
        for nb in get_neighbors(*pp, Y, X):
            if pre_top_map.get(tuple(nb)) == top:
                return None

    # 6. grid 생성
    grid = [[None]*X for _ in range(Y)]
    for py, px in normal_pos:
        grid[py][px] = make_cell()
    for i, (py, px) in enumerate(pre_pos):
        grid[py][px] = make_cell(chips=pre_chips[i])

    # 7. 해 탐색
    solutions = count_solutions(grid, Y, X, hand_stacks, max_count=20)
    if not solutions: return None

    n_sol = len(solutions)
    if n_sol >= 12:   forcing = 0
    elif n_sol >= 5:  forcing = 1
    elif n_sol >= 2:  forcing = 2
    else:             forcing = 3

    # 8. JSON 조립
    tiles = [[{'TileType':1}]*X for _ in range(Y)]
    for py, px in normal_pos:
        tiles[py][px] = {'TileType': 0}
    for i, (py, px) in enumerate(pre_pos):
        tiles[py][px] = {'TileType': 2, 'Stacks': pre_chips[i], 'LockedBelow': 0}

    board_json = {
        'Timestamp': int(time.time()*1000) + pid,
        'GameType': 1, 'GridOrientation': 0,
        'XCells': X, 'YCells': Y, 'Tiles': tiles,
    }

    stack_info = {'Id': pid}
    for i, hs in enumerate(hand_stacks):
        stack_info[f'Stack{i+1}'] = ','.join(COLOR_MAP[c] for c in hs)

    board_chips = Counter(c for chips in pre_chips for c in chips)
    hand_chips  = Counter(c for h in hand_stacks for c in h)

    stage_row = {
        'Id': 1000+pid, 'LevelName': f'S {pid:02d}',
        'TurnCount': len(hand_stacks), 'Mode': 'Turn',
    }

    return {
        'board_json':   board_json,
        'hand_stacks':  hand_stacks,
        'pre_pos':      pre_pos,
        'normal_pos':   normal_pos,
        'pre_chips':    pre_chips,
        'solution':     solutions[0],
        'n_solutions':  n_sol,
        'forcing':      forcing,
        'board_chips':  board_chips,
        'hand_chips':   hand_chips,
        'stack_info':   stack_info,
        'stage_row':    stage_row,
        'normal_cells': empt,
        'n_stacks':     n_pre,
        'n_colors':     n_colors,
        'difficulty':   cfg['label'],
        'diff_score':   cfg['score'],
    }


# ══════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════
def generate_special_puzzle(puzzle_id, difficulty='D34', n_colors=None, seed=None, max_attempts=1500):
    cfg = dict(DIFFICULTY_LEVELS[difficulty])
    if n_colors is not None:
        cfg['n_colors'] = n_colors
    base_seed = seed if seed is not None else puzzle_id * 12345
    for attempt in range(max_attempts):
        rng = random.Random(base_seed + attempt * 7919)
        r = _attempt(puzzle_id, cfg, rng)
        if r is not None:
            return r
    raise RuntimeError(f"S{puzzle_id:03d}: {max_attempts}회 실패 ({difficulty})")


def analyze_special(result):
    return {
        'difficulty':   result['difficulty'],
        'diff_score':   result['diff_score'],
        'forcing':      result['forcing'],
        'n_solutions':  result['n_solutions'],
        'normal_cells': result['normal_cells'],
        'n_pre':        result['n_stacks'],
    }


def solve(result):
    return result.get('solution')


# ══════════════════════════════════════════════════
# 테스트
# ══════════════════════════════════════════════════
if __name__ == '__main__':
    import time as _t
    pattern = ['D12','D34','D12','D48','D34','D8','D34','D48','D34','D52']
    print("=== S01~S30 생성 테스트 ===")
    ok = fail = conflict = 0
    t0 = _t.time()
    for pid in range(1, 31):
        diff = pattern[(pid-1)%10]
        try:
            r = generate_special_puzzle(pid, difficulty=diff, seed=pid*12345)
            tiles = r['board_json']['Tiles']
            Y, X = r['board_json']['YCells'], r['board_json']['XCells']
            tops = {}
            for y in range(Y):
                for x in range(X):
                    t = tiles[y][x]
                    if t.get('TileType')==2 and t.get('Stacks'):
                        tops[(y,x)] = t['Stacks'][-1]
            adj = any(
                tops.get(tuple(nb)) == top
                for (y,x),top in tops.items()
                for nb in get_neighbors(y,x,Y,X)
                if tuple(nb) in tops
            )
            if adj:
                conflict += 1
                print(f"S_{pid:02d} {diff} ⚠️  동색 인접!")
            else:
                ok += 1
                print(f"S_{pid:02d} {diff} ✓  pre={r['n_stacks']} empt={r['normal_cells']} forcing={r['forcing']} sol={r['n_solutions']}")
        except Exception as e:
            fail += 1
            print(f"S_{pid:02d} {diff} ✗  {e}")
    elapsed = _t.time() - t0
    print(f"\n성공:{ok} 실패:{fail} 동색충돌:{conflict} ({elapsed:.1f}초)")
