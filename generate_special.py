"""
generate_special.py  v3
────────────────────────
묘수풀이(특수 퍼즐) 자동 생성기

구조:
  - TurnCount = 총 손패 장 수 = StackInfo Stack 개수 (기존 S01~34: TurnCount=3)
  - PlaceableCount = 3 (한 번에 3장 공개, 자유 순서로 1장씩 배치)
  - Normal 칸 1~2개 + Stack 칸들 → cascade로 빈 칸 확보하며 진행
  - 불변식: 보드칩 + 손패칩 = 색별 정확히 10의 배수
  - 수집: 같은 색 연속 정확히 10개 → 제거
  - Merge: HYBRID_02 (배치한 칸 기준, 이웃 2+이면 무조건 배치칸으로)

생성 전략:
  역방향 — 정답 배치 순서를 먼저 설계 → 보드 초기 상태 + 손패 역산
  → 순방향 DFS로 해 검증
"""

import json, random, time
from collections import Counter
from itertools import permutations, combinations
from pathlib import Path

# ── 색상 정의 (app.py와 동일)
COLOR_MAP   = {0:'Blue',1:'Yellow',2:'Red',3:'Green',
               4:'Orange',5:'Purple',6:'White',7:'Black'}
COLOR_NAMES = ['Blue','Yellow','Red','Green','Orange','Purple','White','Black']
MATCH_TARGET = 10  # 수집 기준 (정확히 10)

NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

def get_neighbors(y, x, Y, X):
    offs = NEIGHBORS_EVEN if y%2==0 else NEIGHBORS_ODD
    return [(y+dy,x+dx) for dy,dx in offs if 0<=y+dy<Y and 0<=x+dx<X]


# ══════════════════════════════════════════════════
# 시뮬레이터 (HYBRID_02 merge 모드)
# Stacks[0] = 바닥, Stacks[-1] = 최상단 (top)
# ══════════════════════════════════════════════════

class Board:
    def __init__(self, grid):
        """
        grid[y][x]:
          None        → Blank (보드 외부)
          []          → Normal 빈 칸 (손패 배치 가능)
          [c, c, ...]  → Stack (c=색상코드, [-1]이 top)
        """
        self.Y = len(grid)
        self.X = len(grid[0])
        self.g = [[list(c) if c is not None else None for c in row] for row in grid]

    def clone(self):
        return Board([[list(c) if c is not None else None for c in row] for row in self.g])

    def is_blank(self, y, x):  return self.g[y][x] is None
    def is_empty(self, y, x):  return self.g[y][x] is not None and len(self.g[y][x]) == 0
    def top(self, y, x):
        s = self.g[y][x]
        return s[-1] if s else None  # [-1] = 최상단

    def top_run(self, y, x):
        """최상단 색과 같은 연속 칩 수 (위에서부터)"""
        s = self.g[y][x]
        if not s: return 0
        t = s[-1]; n = 0
        for c in reversed(s):
            if c == t: n += 1
            else: break
        return n

    def place(self, y, x, chips):
        """빈 Normal 칸에 손패 배치 후 cascade. chips[0]=바닥, chips[-1]=top"""
        assert self.is_empty(y, x), f"[{y},{x}] 빈 칸 아님"
        self.g[y][x] = list(chips)
        self._cascade(y, x)

    def _cascade(self, y, x):
        q = [(y, x)]; seen = set()
        while q:
            cy, cx = q.pop(0)
            key = (cy, cx)
            if key in seen: continue
            changed = self._step(cy, cx)
            seen.add(key)
            if changed:
                for ny, nx in get_neighbors(cy, cx, self.Y, self.X):
                    if not self.is_blank(ny, nx) and (ny, nx) not in seen:
                        q.append((ny, nx))

    def _step(self, y, x):
        """HYBRID_02 한 스텝: collect → merge → collect"""
        if self._collect(y, x): return True
        t = self.top(y, x)
        if t is None: return False
        nb = [(ny, nx) for ny, nx in get_neighbors(y, x, self.Y, self.X)
              if not self.is_blank(ny, nx) and self.top(ny, nx) == t]
        if not nb: return False

        if len(nb) >= 2:
            # 이웃 2+: 무조건 (y,x)로 합침
            for ny, nx in nb:
                self._transfer(ny, nx, y, x)
        else:
            ny, nx = nb[0]
            my_run = self.top_run(y, x)
            nb_run = self.top_run(ny, nx)
            if my_run >= nb_run:
                self._transfer(ny, nx, y, x)   # 이웃 → (y,x)
            else:
                self._transfer(y, x, ny, nx)   # (y,x) → 이웃

        self._collect(y, x)
        for ny, nx in nb:
            self._collect(ny, nx)
        return True

    def _transfer(self, sy, sx, dy, dx):
        """src 최상단 동색 칩들을 dst로 이동 (top 유지)"""
        s = self.g[sy][sx]; d = self.g[dy][dx]
        if not s: return
        t = s[-1]; mv = []
        while s and s[-1] == t:
            mv.append(s.pop())
        d.extend(reversed(mv))  # 순서 유지

    def _collect(self, y, x):
        """최상단 색이 정확히 10개 연속이면 수집(제거). True 반환"""
        s = self.g[y][x]
        if not s: return False
        t = s[-1]; n = 0
        for c in reversed(s):
            if c == t: n += 1
            else: break
        if n == MATCH_TARGET:
            del s[-MATCH_TARGET:]
            return True
        return False

    def free_cells(self):
        return [(y, x) for y in range(self.Y) for x in range(self.X)
                if self.is_empty(y, x)]

    def all_clear(self):
        return all(
            self.g[y][x] is None or len(self.g[y][x]) == 0
            for y in range(self.Y) for x in range(self.X)
        )

    def chip_counts(self):
        cnt = Counter()
        for y in range(self.Y):
            for x in range(self.X):
                if self.g[y][x]:
                    for c in self.g[y][x]: cnt[c] += 1
        return cnt

    def to_json_tiles(self, Y, X):
        """현재 보드 상태를 JSON Tiles 포맷으로 반환"""
        tiles = []
        for y in range(Y):
            row = []
            for x in range(X):
                cell = self.g[y][x]
                if cell is None:
                    row.append({'TileType': 1})
                elif len(cell) == 0:
                    row.append({'TileType': 0})
                else:
                    row.append({'TileType': 2, 'Stacks': list(cell)})
            tiles.append(row)
        return tiles


# ══════════════════════════════════════════════════
# 보조 함수
# ══════════════════════════════════════════════════

def _make_layout(Y, X, n_stack, n_normal, rng):
    """연결된 playable 칸 n_stack+n_normal개 반환. 앞 n_stack = Stack 위치"""
    total = n_stack + n_normal
    all_pos = [(y, x) for y in range(Y) for x in range(X)]
    rng.shuffle(all_pos)
    # BFS로 연결된 칸 선택
    start = rng.choice(all_pos)
    chosen = [start]
    frontier = [nb for nb in get_neighbors(*start, Y, X)]
    rng.shuffle(frontier)
    seen_f = set(frontier)
    while len(chosen) < total and frontier:
        nxt = frontier.pop(0)
        if nxt in chosen: continue
        chosen.append(nxt)
        for nb in get_neighbors(*nxt, Y, X):
            if nb not in chosen and nb not in seen_f:
                frontier.append(nb)
                seen_f.add(nb)
    if len(chosen) < total:
        return None
    rng.shuffle(chosen)
    return chosen[:n_stack], chosen[n_stack:total]


def _split(total, n, rng, lo=1, hi=8):
    """total을 n개 [lo,hi] 범위 정수로 분할"""
    if total < n * lo or total > n * hi:
        return None
    parts = [lo] * n
    rem = total - n * lo
    idxs = list(range(n))
    rng.shuffle(idxs)
    for i in idxs:
        add = rng.randint(0, min(rem, hi - lo))
        parts[i] += add
        rem -= add
        if rem <= 0: break
    if rem > 0:
        for i in range(n):
            add = min(rem, hi - parts[i])
            parts[i] += add; rem -= add
            if rem <= 0: break
    return parts if rem == 0 else None


# ══════════════════════════════════════════════════
# 해 탐색 (DFS)
# ══════════════════════════════════════════════════

def _build_board(tiles, Y, X):
    grid = []
    for y in range(Y):
        row = []
        for x in range(X):
            tt = tiles[y][x].get('TileType', 1)
            if   tt == 1: row.append(None)
            elif tt == 0: row.append([])
            elif tt == 2: row.append(list(tiles[y][x]['Stacks']))
            else:          row.append([])
        grid.append(row)
    return grid


def solve(tiles, Y, X, hand_stacks, max_states=100000):
    """
    DFS로 해 탐색.
    hand_stacks: [[색코드,...], ...]  각 원소가 '1장' (배치할 칩 배열)
    Stacks[0]=바닥, Stacks[-1]=top
    반환: 배치 순서 list[dict] or None
    """
    grid = _build_board(tiles, Y, X)
    init = Board(grid)
    n = len(hand_stacks)

    # DFS 스택: (Board, 완료된 장 집합, 배치 이력)
    dfs = [(init, frozenset(), [])]
    visited = 0

    while dfs:
        board, done, history = dfs.pop()
        visited += 1
        if visited > max_states:
            return None

        if len(done) == n:
            if board.all_clear():
                return history
            continue

        free = board.free_cells()
        if not free:
            continue

        remaining = [i for i in range(n) if i not in done]
        # 가지치기: 남은 손패 색과 보드 칩 색이 매치 가능한지 확인
        for hand_idx in remaining:
            for (py, px) in free:
                nb = board.clone()
                nb.place(py, px, hand_stacks[hand_idx])
                new_done = done | {hand_idx}
                new_hist = history + [{'hand_idx': hand_idx,
                                        'pos': (py, px),
                                        'chips': list(hand_stacks[hand_idx])}]
                dfs.append((nb, new_done, new_hist))

    return None


# ══════════════════════════════════════════════════
# 메인 생성 함수
# ══════════════════════════════════════════════════

def generate_special_puzzle(
    puzzle_id: int,
    n_colors: int = 2,
    turn_count: int = 3,
    normal_cells: int = 1,
    seed: int = None,
    max_attempts: int = 500,
):
    """
    특수 퍼즐 1개 생성.

    Parameters
    ----------
    puzzle_id    : S 번호 (예: 35)
    n_colors     : 사용 색 수 (2~3 권장)
    turn_count   : 손패 장 수 = StackInfo Stack 개수 (기존 S01~33: 3, S34: 4)
    normal_cells : 초기 Normal(빈) 칸 수 (1~2)
    seed         : 랜덤 시드 (None이면 puzzle_id 기반)

    Returns
    -------
    dict:
      board_json  : JSON 보드 파일 내용 (dict)
      stack_info  : StackInfo 탭 행 (dict)
      stage_row   : Stage 탭 행 (dict)
      board_chips : Counter — 보드 초기 칩 색별 개수
      hand_chips  : Counter — 손패 칩 색별 개수
      solution    : 검증된 배치 순서 list[dict]
      n_stacks    : 보드 Stack 칸 수
      normal_cells: Normal 칸 수
    """
    base_seed = seed if seed is not None else puzzle_id * 99991
    for attempt in range(max_attempts):
        rng = random.Random(base_seed + attempt * 7919)  # attempt마다 다른 시드
        r = _attempt(puzzle_id, n_colors, turn_count, normal_cells, rng, attempt)
        if r is not None:
            return r
    raise RuntimeError(f"S{puzzle_id:03d}: {max_attempts}회 시도 후 생성 실패")


def _attempt(pid, n_colors, turn_count, normal_cells, rng, attempt):
    """
    역방향 설계:
    ① 각 손패 장이 배치 후 특정 색 수집을 유발하도록 설계
    ② 불변식(색별 합=10) 자동 보장
    ③ 해 검증 (DFS)
    """
    Y, X = 4, 5

    # ── 색상 선택
    colors = rng.sample(range(8), n_colors)

    # ── 역방향: 수집 시퀀스 설계 (각 손패 장이 담당할 색)
    # turn_count=3이므로 3장 × 수집
    collect_seq = (colors * ((turn_count // n_colors) + 1))[:turn_count]
    rng.shuffle(collect_seq)

    # ── 각 장의 손패 구성: collect_seq[i] 색 k개 + 보조 색
    hand_stacks = []
    board_per = {c: 0 for c in colors}
    hand_per  = {c: 0 for c in colors}

    for i, col in enumerate(collect_seq):
        k = rng.randint(1, min(5, MATCH_TARGET - 1))   # 손패에 k개
        board_per[col] += (MATCH_TARGET - k)            # 보드에 10-k개
        hand = [col] * k
        # 나머지 색 보조 칩 (다음 수집 준비, 50% 확률)
        other = [c for c in colors if c != col]
        if other and rng.random() < 0.6:
            ec = rng.choice(other)
            en = rng.randint(1, 3)
            hand.extend([ec] * en)
            board_per[ec] = max(0, board_per.get(ec, 0) - en)
        rng.shuffle(hand)
        hand_stacks.append(hand)
        for c in hand: hand_per[c] = hand_per.get(c, 0) + 1

    # ── 불변식 보정: 각 색 합이 10이 되도록
    for c in colors:
        total = board_per.get(c, 0) + hand_per.get(c, 0)
        diff = MATCH_TARGET - total
        board_per[c] = board_per.get(c, 0) + diff
        if board_per[c] < 0:
            return None

    # ── 보드칩 0인 색 방지 (손패에서 1개 가져옴)
    for c in colors:
        if board_per.get(c, 0) == 0:
            # 손패에서 해당 색 1개를 보드로 이동
            for hs in hand_stacks:
                if c in hs:
                    hs.remove(c)
                    board_per[c] = 1
                    hand_per[c] = hand_per.get(c, 0) - 1
                    break
            if board_per.get(c, 0) == 0:
                return None  # 이동 불가

    board_total = sum(board_per.values())
    if board_total <= 0 or board_total > 30:
        return None

    # ── 보드 Stack 칸 구성
    n_stacks = rng.randint(max(2, n_colors), min(board_total, 7))
    depths = _split(board_total, n_stacks, rng, lo=1, hi=6)
    if depths is None: return None

    # ── 보드 레이아웃
    layout = _make_layout(Y, X, n_stacks, normal_cells, rng)
    if layout is None: return None
    stack_pos, normal_pos = layout

    # ── 보드 칩 배열 (Stacks[0]=바닥, [-1]=top)
    pool = []
    for c, n in board_per.items(): pool.extend([c] * n)
    rng.shuffle(pool)
    board_stacks = []
    idx = 0
    for d in depths:
        board_stacks.append(pool[idx:idx+d])
        idx += d

    # ── 보드 JSON 조립
    tiles = [[{'TileType': 1}] * X for _ in range(Y)]
    for (py, px) in normal_pos:
        tiles[py][px] = {'TileType': 0}
    for i, (py, px) in enumerate(stack_pos):
        tiles[py][px] = {'TileType': 2, 'Stacks': board_stacks[i]}

    # ── 해 검증 (DFS)
    solution = solve(tiles, Y, X, hand_stacks)
    if solution is None: return None

    # ── 결과 조립
    board_json = {
        'Timestamp': int(time.time() * 1000) + pid,
        'GameType':  1,
        'GridOrientation': 0,
        'XCells': X, 'YCells': Y,
        'Tiles': tiles,
    }
    stack_info = {'Id': pid}
    for i, hs in enumerate(hand_stacks):
        stack_info[f'Stack{i+1}'] = ','.join(COLOR_MAP[c] for c in hs)

    # Stage 행 (기존 S01~34와 동일 패턴)
    stage_row = {
        'Id':               1000 + pid,
        'Mode':             'Turn',
        'LevelName':        f'S {pid:02d}',
        'PlaceableCount':   3,
        'IsPreview':        False,
        'TotalAllocation':  turn_count,
        'InitialAvailableColors': None,
        'DistinctColorCount':     None,
        'ColorDuplicationRate':   None,
        'ProgressAddNewColor':    None,
        'NewColorsMilestones':    None,
        'Extra':            pid,
        'TurnCount':        turn_count,
        'IceCount':         0,
        'GrassCount':       0,
        'WoodCount':        0,
        'CameraPictureCount': 0,
    }

    return {
        'board_json':   board_json,
        'stack_info':   stack_info,
        'stage_row':    stage_row,
        'board_chips':  Counter({COLOR_MAP[c]: v for c, v in board_per.items()}),
        'hand_chips':   Counter({COLOR_MAP[c]: v for c, v in hand_per.items()}),
        'solution':     solution,
        'n_stacks':     n_stacks,
        'normal_cells': normal_cells,
        'hand_stacks':  hand_stacks,
    }


# ══════════════════════════════════════════════════
# 난이도 분석
# ══════════════════════════════════════════════════

def analyze_special(result: dict) -> dict:
    """
    특수 퍼즐 난이도 지표 추출.
    반환 dict:
      pressure      : 배치 압박 (normal_cells / turn_count, 낮을수록 어렵)
      color_count   : 색 수
      board_chips   : 보드 초기 칩 총수
      hand_chips    : 손패 칩 총수
      cascade_steps : 정답에서 수집 발생 횟수 (많을수록 복잡)
      score         : 종합 난이도 점수 (0~100)
    """
    nc = result['normal_cells']
    tc = len(result['hand_stacks'])
    colors = len(result['board_chips'])
    bc = sum(result['board_chips'].values())
    hc = sum(result['hand_chips'].values())

    # 배치 압박: 빈 칸이 손패보다 적을수록 높음
    pressure = max(0.0, 1.0 - nc / tc)

    # 손패 혼잡도: 한 장에 여러 색이 섞인 정도
    hand_stacks = result.get('hand_stacks', [])
    mix = sum(len(set(s)) for s in hand_stacks) / max(len(hand_stacks), 1)

    score = round(
        pressure * 40 +        # 배치 압박 (최대 40점)
        (colors - 2) * 15 +    # 색 복잡도 (색당 15점)
        min(bc / 30, 1) * 25 + # 보드 칩 밀도 (최대 25점)
        min(mix / 3, 1) * 20,  # 손패 혼잡도 (최대 20점)
    1)

    return {
        'pressure':    round(pressure, 2),
        'color_count': colors,
        'board_chips': bc,
        'hand_chips':  hc,
        'mix_score':   round(mix, 2),
        'score':       min(100, score),
    }


# ══════════════════════════════════════════════════
# 배치 생성 (범위)
# ══════════════════════════════════════════════════

def generate_range(start: int, end: int, output_dir: str = '.') -> list:
    out = Path(output_dir); out.mkdir(exist_ok=True)
    results = []
    for pid in range(start, end + 1):
        # Stack은 최대 3개(Stack1~Stack3) → TurnCount 항상 3 고정
        if   pid <= 10: n_colors, turn_count, normal_cells = 2, 3, 2
        elif pid <= 20: n_colors, turn_count, normal_cells = 2, 3, 1
        else:            n_colors, turn_count, normal_cells = 3, 3, 1
        try:
            r = generate_special_puzzle(pid, n_colors, turn_count,
                                        normal_cells, seed=pid * 12345)
            p = out / f'S_{pid:03d}.json'
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(r['board_json'], f, ensure_ascii=False, indent=2)
            diff = analyze_special(r)
            total = r['board_chips'] + r['hand_chips']
            ok = all(v % 10 == 0 for v in total.values())
            results.append(r)
            print(f'  S_{pid:03d} [{diff["score"]:4.0f}점] '
                  f'보드={dict(r["board_chips"])} 손패={dict(r["hand_chips"])} '
                  f'{"✓" if ok else "✗"} '
                  f'Stack={r["n_stacks"]} Normal={r["normal_cells"]}')
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
        print('=== S_035 단일 테스트 ===')
        r = generate_special_puzzle(35, n_colors=2, turn_count=3,
                                    normal_cells=1, seed=35*12345)
        total = r['board_chips'] + r['hand_chips']
        diff  = analyze_special(r)
        print(f'보드칩:    {dict(r["board_chips"])}')
        print(f'손패칩:    {dict(r["hand_chips"])}')
        print(f'합계:      {dict(total)}')
        print(f'10배수:    {all(v%10==0 for v in total.values())}')
        print(f'난이도:    {diff}')
        print(f'Stack={r["n_stacks"]}, Normal={r["normal_cells"]}')
        print(f'해 검증:   {"성공" if r["solution"] else "실패"}')
        print()
        print('=== Board JSON ===')
        print(json.dumps(r['board_json'], ensure_ascii=False, indent=2))
        print()
        print('=== StackInfo ===')
        for k, v in r['stack_info'].items(): print(f'  {k}: {v}')
        print()
        print('=== Stage Row ===')
        for k, v in r['stage_row'].items(): print(f'  {k}: {v}')

    elif len(sys.argv) == 3:
        start, end = int(sys.argv[1]), int(sys.argv[2])
        print(f'=== S_{start:03d}~S_{end:03d} 생성 ===')
        results = generate_range(start, end, 'special_puzzles')
        ok = sum(1 for r in results if r)
        print(f'\n완료: {ok}/{end-start+1} 성공')
