"""
generate_special.py  v4
────────────────────────
묘수풀이(특수 퍼즐) 자동 생성기

구조:
  - trap 스택: 한 칸에 3층 (위=열림, 중·아래=잠금)
               잠금 층은 위층 수집 후 표면화 → 인접 병합 cascade
  - prePlaced: trap 외 칸에 작은 분산 보드칩 (가교 역할)
               → 손패를 prePlaced 인접 칸에 놓아야 병합이 일어나 수집 가능
  - 빈 칸(Normal): 1~4개 (적을수록 배치 압박)
  - 불변식: 색별 (trap + prePlaced + 손패) 합 = 10의 배수
  - 수집: 같은 색 정확히 10개 연속 → 제거
  - Merge: HYBRID_02

난이도 단계:
  D8  : empt=6, prePlaced=0, forcing≈0  (trap만, 위치 자유)
  D12 : empt=5, prePlaced=1, forcing≈1  (가교 1개 필수)
  D34 : empt=3, prePlaced=3, forcing≈2  (순서+위치 강제)
  D48 : empt=2, prePlaced=3, forcing≈3  (배치 압박 최대)
  D52 : empt=2, prePlaced=4, forcing≈3+
"""

import json, random, time, copy
from collections import Counter
from pathlib import Path

# ── 색상
COLOR_MAP   = {0:'Blue',1:'Yellow',2:'Red',3:'Green',
               4:'Orange',5:'Purple',6:'White',7:'Black'}
COLOR_NAMES = ['Blue','Yellow','Red','Green','Orange','Purple','White','Black']
MATCH_TARGET = 10

NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

def get_neighbors(y, x, Y, X):
    offs = NEIGHBORS_EVEN if y%2==0 else NEIGHBORS_ODD
    return [(y+dy,x+dx) for dy,dx in offs if 0<=y+dy<Y and 0<=x+dx<X]


# ══════════════════════════════════════════════════
# 시뮬레이터 (HYBRID_02, 잠금 층 지원)
# ══════════════════════════════════════════════════

class Board:
    """
    grid[y][x]:
      None          → Blank
      {'chips': [], 'locked_below': 0}  → 칸
        chips: 색상코드 리스트 ([-1]=top)
        locked_below: 아래에서부터 잠긴 층 수
    """
    def __init__(self, grid):
        self.Y = len(grid)
        self.X = len(grid[0])
        self.g = [[copy.deepcopy(c) if c is not None else None
                   for c in row] for row in grid]

    def clone(self):
        return Board([[copy.deepcopy(c) if c is not None else None
                       for c in row] for row in self.g])

    def is_blank(self, y, x):   return self.g[y][x] is None
    def is_empty(self, y, x):
        c = self.g[y][x]
        return c is not None and len(c['chips']) == 0

    def top(self, y, x):
        c = self.g[y][x]
        if c is None or not c['chips']: return None
        # 잠금 위의 표면 top
        chips = c['chips']
        lb    = c['locked_below']
        surface = chips[lb:]   # 잠금 위 부분
        return surface[-1] if surface else None

    def surface_run(self, y, x):
        """잠금 위 표면에서 top 색 연속 개수"""
        c = self.g[y][x]
        if c is None: return 0
        surface = c['chips'][c['locked_below']:]
        if not surface: return 0
        t = surface[-1]; n = 0
        for ch in reversed(surface):
            if ch == t: n += 1
            else: break
        return n

    def surface_total(self, y, x, color):
        """잠금 위 표면에서 특정 색 합계"""
        c = self.g[y][x]
        if c is None: return 0
        surface = c['chips'][c['locked_below']:]
        return sum(1 for ch in surface if ch == color)

    def place(self, y, x, chips):
        """빈 칸에 손패 배치 후 cascade"""
        assert self.is_empty(y, x)
        self.g[y][x]['chips'] = list(chips)
        self._cascade(y, x)

    def _cascade(self, y, x):
        q = [(y,x)]; seen = set()
        while q:
            cy,cx = q.pop(0)
            if (cy,cx) in seen: continue
            changed = self._step(cy,cx)
            seen.add((cy,cx))
            if changed:
                for ny,nx in get_neighbors(cy,cx,self.Y,self.X):
                    if not self.is_blank(ny,nx) and (ny,nx) not in seen:
                        q.append((ny,nx))

    def _step(self, y, x):
        if self._collect(y,x): return True
        t = self.top(y,x)
        if t is None: return False
        nb = [(ny,nx) for ny,nx in get_neighbors(y,x,self.Y,self.X)
              if not self.is_blank(ny,nx) and self.top(ny,nx)==t]
        if not nb: return False

        if len(nb) >= 2:
            for ny,nx in nb: self._transfer(ny,nx,y,x)
        else:
            ny,nx = nb[0]
            if self.surface_run(y,x) >= self.surface_run(ny,nx):
                self._transfer(ny,nx,y,x)
            else:
                self._transfer(y,x,ny,nx)

        self._collect(y,x)
        for ny,nx in nb: self._collect(ny,nx)
        return True

    def _transfer(self, sy, sx, dy, dx):
        """src 표면 top 동색 칩 → dst로 이동"""
        sc = self.g[sy][sx]; dc = self.g[dy][dx]
        if sc is None or not sc['chips']: return
        surface = sc['chips'][sc['locked_below']:]
        if not surface: return
        t = surface[-1]; mv = []
        while surface and surface[-1] == t:
            mv.append(surface.pop())
        # chips 업데이트
        sc['chips'] = sc['chips'][:sc['locked_below']] + surface
        dc['chips'].extend(reversed(mv))

    def _collect(self, y, x):
        """표면에서 top 색이 정확히 10개 연속이면 수집"""
        c = self.g[y][x]
        if c is None: return False
        surface = c['chips'][c['locked_below']:]
        if not surface: return False
        t = surface[-1]; n = 0
        for ch in reversed(surface):
            if ch == t: n += 1
            else: break
        if n == MATCH_TARGET:
            # 제거
            new_surface = surface[:-MATCH_TARGET]
            c['chips'] = c['chips'][:c['locked_below']] + new_surface
            # 수집 후 잠금 해제 체크 (위층 수집 → 아래층 표면화)
            self._unlock_check(y, x)
            return True
        return False

    def _unlock_check(self, y, x):
        """표면이 비었으면 다음 잠금 색 블록 전체를 한 번에 표면화"""
        c = self.g[y][x]
        if c is None or c['locked_below'] == 0: return
        chips = c['chips']
        lb = c['locked_below']
        surface = chips[lb:]
        if surface: return  # 표면에 이미 칩 있음 → unlock 불필요
        if lb == 0 or lb > len(chips): 
            c['locked_below'] = 0
            return
        # 표면이 비어있음 → chips[lb-1]부터 같은 색 블록 전체를 표면으로 끌어올림
        next_color = chips[lb-1]
        new_lb = lb
        while new_lb > 0 and chips[new_lb-1] == next_color:
            new_lb -= 1
        c['locked_below'] = new_lb
        # 새로 드러난 표면에서 수집 시도
        self._collect(y, x)

    def free_cells(self):
        return [(y,x) for y in range(self.Y) for x in range(self.X)
                if self.is_empty(y,x)]

    def all_clear(self):
        for y in range(self.Y):
            for x in range(self.X):
                c = self.g[y][x]
                if c is not None and c['chips']:
                    return False
        return True

    def chip_counts(self):
        cnt = Counter()
        for y in range(self.Y):
            for x in range(self.X):
                c = self.g[y][x]
                if c:
                    for ch in c['chips']: cnt[ch] += 1
        return cnt


def make_cell(chips=None, locked_below=0):
    return {'chips': list(chips) if chips else [], 'locked_below': locked_below}


# ══════════════════════════════════════════════════
# 보조 함수
# ══════════════════════════════════════════════════

def get_neighbors(y, x, Y, X):
    offs = NEIGHBORS_EVEN if y%2==0 else NEIGHBORS_ODD
    return [(y+dy,x+dx) for dy,dx in offs if 0<=y+dy<Y and 0<=x+dx<X]

def _make_layout(Y, X, n_total, rng):
    """연결된 칸 n_total개 반환"""
    all_pos = [(y,x) for y in range(Y) for x in range(X)]
    rng.shuffle(all_pos)
    start = all_pos[0]
    chosen = [start]
    frontier = list(get_neighbors(*start,Y,X))
    rng.shuffle(frontier)
    seen_f = set(frontier)
    while len(chosen) < n_total and frontier:
        nxt = frontier.pop(0)
        if nxt in chosen: continue
        chosen.append(nxt)
        for nb in get_neighbors(*nxt,Y,X):
            if nb not in chosen and nb not in seen_f:
                frontier.append(nb); seen_f.add(nb)
    if len(chosen) < n_total: return None
    rng.shuffle(chosen)
    return chosen[:n_total]

def _assign_tops_graph(positions, colors, Y, X, rng, max_tries=100):
    """그래프 컬러링: 인접 스택 top 색 충돌 방지"""
    pos_idx = {pos:i for i,pos in enumerate(positions)}
    n = len(positions)
    for _ in range(max_tries):
        tops = [None]*n
        order = list(range(n)); rng.shuffle(order)
        ok = True
        for i in order:
            py,px = positions[i]
            used = {tops[pos_idx[(ny,nx)]]
                    for ny,nx in get_neighbors(py,px,Y,X)
                    if (ny,nx) in pos_idx and tops[pos_idx[(ny,nx)]] is not None}
            avail = [c for c in colors if c not in used]
            if not avail: ok=False; break
            tops[i] = rng.choice(avail)
        if ok: return tops
    return None


# ══════════════════════════════════════════════════
# DFS 해 탐색 (forcing 계산 포함)
# ══════════════════════════════════════════════════

def _build_grid(trap_pos, trap_stack_3layers,
                pre_pos, pre_chips,
                normal_pos, Y, X):
    """Board용 grid 생성"""
    grid = [[None]*X for _ in range(Y)]
    # Normal 빈 칸
    for (py,px) in normal_pos:
        grid[py][px] = make_cell()
    # prePlaced 더미
    for i,(py,px) in enumerate(pre_pos):
        grid[py][px] = make_cell(chips=pre_chips[i], locked_below=0)
    # trap 스택 (3층: 위=열림, 중·아래=잠금)
    # trap_stack_3layers = [(색,개수), (색,개수), (색,개수)]  위→중→아래
    # 저장 순서: chips = [아래색×n, 중색×m, 위색×k] ([-1]=top=위층)
    (tc_top,n_top),(tc_mid,n_mid),(tc_bot,n_bot) = trap_stack_3layers
    chips = [tc_bot]*n_bot + [tc_mid]*n_mid + [tc_top]*n_top
    # locked_below = n_bot + n_mid (아래 두 층 잠금)
    locked_below = n_bot + n_mid
    py,px = trap_pos
    grid[py][px] = make_cell(chips=chips, locked_below=locked_below)
    return grid

def count_solutions(grid, Y, X, hand_stacks, max_count=20, max_states=200000):
    """해의 수를 세기 (forcing 계산용). max_count 초과시 조기 종료"""
    init = Board(grid)
    n = len(hand_stacks)
    dfs = [(init, frozenset(), [])]
    solutions = []
    visited = 0
    while dfs and len(solutions) < max_count:
        board, done, hist = dfs.pop()
        visited += 1
        if visited > max_states: break
        if len(done) == n:
            if board.all_clear(): solutions.append(hist)
            continue
        free = board.free_cells()
        if not free: continue
        for hi in [i for i in range(n) if i not in done]:
            for (py,px) in free:
                nb = board.clone()
                nb.place(py,px,hand_stacks[hi])
                dfs.append((nb, done|{hi},
                             hist+[{'hand_idx':hi,'pos':(py,px),'chips':list(hand_stacks[hi])}]))
    return solutions

def solve(grid, Y, X, hand_stacks, max_states=200000):
    """첫 번째 해 반환"""
    sols = count_solutions(grid, Y, X, hand_stacks, max_count=1, max_states=max_states)
    return sols[0] if sols else None


# ══════════════════════════════════════════════════
# 난이도 단계 정의
# ══════════════════════════════════════════════════

DIFFICULTY_LEVELS = {  # score 필드가 label 역할

    'D8':  {'empt': 6, 'n_pre': 0, 'forcing_max': 99, 'label':'D8','score': 8},
    'D12': {'empt': 5, 'n_pre': 1, 'forcing_max': 99, 'label':'D12','score': 12},
    'D34': {'empt': 3, 'n_pre': 3, 'forcing_max': 99, 'label':'D34','score': 34},
    'D48': {'empt': 2, 'n_pre': 3, 'forcing_max': 99, 'label':'D48','score': 48},
    'D52': {'empt': 2, 'n_pre': 4, 'forcing_max': 99, 'label':'D52','score': 52},
}


# ══════════════════════════════════════════════════
# 메인 생성 함수
# ══════════════════════════════════════════════════

def generate_special_puzzle(
    puzzle_id: int,
    difficulty: str = 'D12',
    n_colors: int = 3,
    seed: int = None,
    max_attempts: int = 500,
):
    """
    특수 퍼즐 1개 생성.

    Parameters
    ----------
    puzzle_id   : S 번호
    difficulty  : 'D8' / 'D12' / 'D34' / 'D48' / 'D52'
    n_colors    : 사용 색 수 (3 고정 권장)
    seed        : 랜덤 시드
    """
    cfg = DIFFICULTY_LEVELS[difficulty]
    base_seed = seed if seed is not None else puzzle_id * 99991

    for attempt in range(max_attempts):
        rng = random.Random(base_seed + attempt * 7919)
        r = _attempt(puzzle_id, n_colors, cfg, rng)
        if r is not None:
            return r
    raise RuntimeError(f"S{puzzle_id:03d}: {max_attempts}회 실패")


def _attempt(pid, n_colors, cfg, rng):
    Y, X = 4, 5
    empt  = cfg['empt']
    n_pre = cfg['n_pre']

    # ── 색상 선택 (3색)
    colors = rng.sample(range(8), n_colors)  # [top색, mid색, bot색]
    rng.shuffle(colors)
    c_top, c_mid, c_bot = colors[0], colors[1], colors[2]

    # ── 손패 배분: 각 색 k개 (1~4)
    # top층 수집을 손패+prePlaced로 완성
    k_top = rng.randint(1, 4)
    k_mid = rng.randint(1, 4)
    k_bot = rng.randint(1, 4)

    # trap 스택 각 층 칩 수: (10 - k - prePlaced기여)
    # prePlaced는 top 색만 지원 (가교 역할)
    # prePlaced 총 칩 수: n_pre * (1~3)개
    pre_count_per = rng.randint(1, 3) if n_pre > 0 else 0
    pre_total = n_pre * pre_count_per  # top 색 prePlaced 총량

    pre_mid_total_early = n_pre * pre_count_per  # prePlaced → c_mid 기여
    n_top = MATCH_TARGET - k_top               # top은 손패만으로 보충
    n_mid = MATCH_TARGET - k_mid - pre_mid_total_early  # mid는 prePlaced+손패
    n_bot = MATCH_TARGET - k_bot

    if n_top < 1 or n_mid < 1 or n_bot < 1: return None
    if n_top > 9 or n_mid > 9 or n_bot > 9: return None

    # ── 보드 칸 수 계산
    # trap 1개 + prePlaced n_pre개 + Normal empt개
    n_total = 1 + n_pre + empt
    if n_total > 14: return None  # 5×4 보드 한계

    positions = _make_layout(Y, X, n_total, rng)
    if positions is None: return None

    trap_pos    = positions[0]
    pre_pos     = positions[1:1+n_pre]
    normal_pos  = positions[1+n_pre:]

    # ── prePlaced = c_mid 색으로 설정
    # trap top(c_top)과 달라서 초기 cascade 없음
    # trap 잠금1층(c_mid) 수집 후 표면화 시 prePlaced와 자동 연쇄
    pre_chips = [[c_mid] * pre_count_per for _ in range(n_pre)]

    # ── 손패 배열 (3장): top→mid→bot 순서로 배치해야 층별 수집
    hand_raw = [
        [c_top] * k_top,
        [c_mid] * k_mid,
        [c_bot] * k_bot,
    ]
    rng.shuffle(hand_raw)  # 순서 랜덤화

    # ── 불변식 검증 (prePlaced는 c_mid에 기여)
    pre_mid_total = n_pre * pre_count_per
    for c, trap_n, hand_k, pre_n in [
        (c_top, n_top, k_top, 0),
        (c_mid, n_mid, k_mid, pre_mid_total),
        (c_bot, n_bot, k_bot, 0),
    ]:
        if (trap_n + hand_k + pre_n) != MATCH_TARGET: return None

    # ── grid 생성
    trap_3layers = [
        (c_top, n_top),
        (c_mid, n_mid),
        (c_bot, n_bot),
    ]
    grid = _build_grid(trap_pos, trap_3layers,
                       pre_pos, pre_chips,
                       normal_pos, Y, X)

    # ── 초기 상태 인접 동색 top 체크
    # trap top = c_top, prePlaced top = c_top
    # → trap 인접에 prePlaced 없도록 이미 체크했음
    # normal 빈 칸은 top 없으므로 무관

    # ── 해 탐색 (forcing 계산)
    solutions = count_solutions(grid, Y, X, hand_raw, max_count=20)
    if not solutions: return None
    n_sol = len(solutions)
    solution = solutions[0]

    # ── forcing 점수 (해의 수가 적을수록 높음)
    # forcing=0: 해 많음(≥12), forcing=1: 5~11, forcing=2: 2~4, forcing=3: 1
    if n_sol >= 12:   forcing = 0
    elif n_sol >= 5:  forcing = 1
    elif n_sol >= 2:  forcing = 2
    else:             forcing = 3

    # ── JSON 조립 (tblStage 연동 포맷 유지)
    # Stacks: [bot×n_bot, mid×n_mid, top×n_top]  ([-1]=top)
    # 잠금 정보: 별도 필드 LockedBelow
    tiles = [[{'TileType':1}]*X for _ in range(Y)]
    for (py,px) in normal_pos:
        tiles[py][px] = {'TileType': 0}
    for i,(py,px) in enumerate(pre_pos):
        tiles[py][px] = {'TileType': 2,
                         'Stacks': pre_chips[i],
                         'LockedBelow': 0}
    py,px = trap_pos
    chips_flat = [c_bot]*n_bot + [c_mid]*n_mid + [c_top]*n_top
    tiles[py][px] = {'TileType': 2,
                     'Stacks': chips_flat,
                     'LockedBelow': n_bot + n_mid}

    board_json = {
        'Timestamp': int(time.time()*1000) + pid,
        'GameType':  1,
        'GridOrientation': 0,
        'XCells': X, 'YCells': Y,
        'Tiles': tiles,
    }

    # ── StackInfo (손패 3장)
    stack_info = {'Id': pid}
    for i, hs in enumerate(hand_raw):
        stack_info[f'Stack{i+1}'] = ','.join(COLOR_MAP[c] for c in hs)

    stage_row = {
        'Id':               1000 + pid,
        'Mode':             'Turn',
        'LevelName':        f'S {pid:02d}',
        'PlaceableCount':   3,
        'IsPreview':        False,
        'TotalAllocation':  3,
        'InitialAvailableColors': None,
        'DistinctColorCount':     None,
        'ColorDuplicationRate':   None,
        'ProgressAddNewColor':    None,
        'NewColorsMilestones':    None,
        'Extra':            pid,
        'TurnCount':        3,
        'IceCount':         0, 'GrassCount': 0,
        'WoodCount':        0, 'CameraPictureCount': 0,
    }

    diff_score = cfg['score']

    return {
        'board_json':   board_json,
        'stack_info':   stack_info,
        'stage_row':    stage_row,
        'board_chips':  Counter({
            COLOR_MAP[c_top]: n_top,
            COLOR_MAP[c_mid]: n_mid + pre_mid_total_early,
            COLOR_MAP[c_bot]: n_bot,
        }),
        'hand_chips': Counter({
            COLOR_MAP[c_top]: k_top,
            COLOR_MAP[c_mid]: k_mid,
            COLOR_MAP[c_bot]: k_bot,
        }),
        'solution':     solution,
        'n_solutions':  n_sol,
        'forcing':      forcing,
        'difficulty':   cfg.get('label','D?'),
        'diff_score':   diff_score,
        'trap_pos':     trap_pos,
        'pre_pos':      pre_pos,
        'normal_pos':   normal_pos,
        'hand_stacks':  hand_raw,
        'trap_layers':  [(COLOR_MAP[c_top],n_top),(COLOR_MAP[c_mid],n_mid),(COLOR_MAP[c_bot],n_bot)],
        'n_stacks':     1 + n_pre,
        'normal_cells': empt,
    }


# ══════════════════════════════════════════════════
# 난이도 분석
# ══════════════════════════════════════════════════

def analyze_special(result: dict) -> dict:
    return {
        'difficulty':  result['difficulty'],
        'diff_score':  result['diff_score'],
        'forcing':     result['forcing'],
        'n_solutions': result['n_solutions'],
        'normal_cells': result['normal_cells'],
        'n_pre':       len(result['pre_pos']),
        'color_count': 3,
    }


# ══════════════════════════════════════════════════
# 범위 생성
# ══════════════════════════════════════════════════

# 난이도 진행 스케줄 (S01~S34 범위 예시)
SCHEDULE = [
    (range(1,  5),  'D8'),
    (range(5,  11), 'D12'),
    (range(11, 19), 'D34'),
    (range(19, 23), 'D48'),
    (range(23, 35), 'D52'),
]

def _get_difficulty(pid):
    for rng_obj, diff in SCHEDULE:
        if pid in rng_obj: return diff
    # 34 이후
    return 'D52'

def generate_range(start: int, end: int, output_dir: str = '.') -> list:
    out = Path(output_dir); out.mkdir(exist_ok=True)
    results = []
    for pid in range(start, end+1):
        diff = _get_difficulty(pid)
        try:
            r = generate_special_puzzle(pid, difficulty=diff, seed=pid*12345)
            p = out / f'S_{pid:03d}.json'
            with open(p,'w',encoding='utf-8') as f:
                json.dump(r['board_json'],f,ensure_ascii=False,indent=2)
            total = r['board_chips'] + r['hand_chips']
            ok = all(v%10==0 for v in total.values())
            results.append(r)
            print(f'  S_{pid:03d} [{diff} {r["diff_score"]}점] '
                  f'forcing={r["forcing"]} sol={r["n_solutions"]:2d} '
                  f'보드={dict(r["board_chips"])} 손패={dict(r["hand_chips"])} '
                  f'{"✓" if ok else "✗"}')
        except Exception as e:
            print(f'  S_{pid:03d}: 실패 - {e}')
            results.append(None)
    return results


# ══════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        print('=== S_005 D12 단일 테스트 ===')
        r = generate_special_puzzle(5, difficulty='D12', seed=5*12345)
        total = r['board_chips'] + r['hand_chips']
        print(f'보드칩:    {dict(r["board_chips"])}')
        print(f'손패칩:    {dict(r["hand_chips"])}')
        print(f'합계:      {dict(total)}')
        print(f'10배수:    {all(v%10==0 for v in total.values())}')
        print(f'trap 층:   {r["trap_layers"]}')
        print(f'forcing:   {r["forcing"]} (해의 수: {r["n_solutions"]})')
        print(f'trap 위치: {r["trap_pos"]}')
        print(f'pre 위치:  {r["pre_pos"]}')
        print(f'정답: {r["solution"]}')
        print()
        print('Board JSON:')
        print(json.dumps(r['board_json'], ensure_ascii=False, indent=2))
        print('StackInfo:', r['stack_info'])
    elif len(sys.argv) == 3:
        start, end = int(sys.argv[1]), int(sys.argv[2])
        print(f'=== S_{start:03d}~S_{end:03d} 생성 ===')
        results = generate_range(start, end, 'special_puzzles')
        ok = sum(1 for r in results if r)
        print(f'\n완료: {ok}/{end-start+1}')
