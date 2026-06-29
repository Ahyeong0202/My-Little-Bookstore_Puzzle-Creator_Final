"""
generate_special_v4.py — zip 샘플(인간 제작) 형식 기준 묘수풀이 생성기

핵심 변경 (v3 -> v4):
  1. 좌표계: 열(x) 기준 시프트 헥사 좌표 (board_engine.get_neighbors와 동일).
     실제 게임 좌표계와 다르면 PuzzleActionController.cs 쪽 헥스 인덱싱을
     다시 확인해야 한다 — 이 부분은 zip 샘플 S01/S02/S03/S05/S07의 실제
     해로 교차검증된 것이며, 기존 generate_special.py의 NEIGHBORS_EVEN/ODD
     (행 기준) 와는 다르다.
  2. 매칭 메커니즘: board_engine.Board와 동일.
       - 어떤 칸에 칩을 놓으면(빈칸이든 이미 칩이 있는 칸이든 가능),
         "top 색이 같은 이웃"을 찾는다.
       - 이웃 1개: top 연속 묶음(streak)이 적은 쪽 -> 많은 쪽으로 그 묶음만 이동.
       - 이웃 2개 이상: 모든 이웃의 top 묶음이 무조건 "마지막에 놓은 칸"으로 이동.
       - 도착 칸의 top 연속 개수가 10에 도달하면 그만큼 소멸.
  3. 출력 JSON 포맷: zip 샘플과 동일 (GameType:0, Tiles[[{TileType, Stacks?}]]).
     LockedBelow 등 부가 필드 없음. 보드 크기는 가변(2x2~6x3 수준의 작은 보드).
  4. 색상 규칙:
       - 한 스택 내부: 최대 3가지 색, 색이 바뀌는 전환(transition) 횟수 최대 2회.
         (흰-빨-파 OK / 흰-빨-흰-파 같이 전환이 3회가 되는 것은 불가)
       - 퍼즐 전체(보드+손패) 색상 종류 수:
           난이도 1~3 -> 최대 3색
           난이도 4~5 -> 최대 4색
       - 보드+손패를 합쳐 각 색깔의 총 칩 수가 "정확히 10개"가 되어야 한다
         (10개가 모이면 소멸하는 매칭 규칙과 일치).
  5. 난이도 자동 배정: 15개 패턴을 순환 (목표 비율 1=15%,2=30%,3=25%,4=20%,5=10%에
     가장 가까운 정수 배분을 완전한 지그재그로 배열):
         [2,4,2,3,2,3,2,3,1,4,1,4,3,5,2]
"""

import random
import time
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from board_engine import Board, make_cell, count_solutions, get_neighbors, MATCH_TARGET

COLOR_MAP = {0: 'Blue', 1: 'Yellow', 2: 'Red', 3: 'Green', 4: 'Orange', 5: 'Purple', 6: 'White', 7: 'Black'}

# ── 난이도 자동배정 패턴 (15개 순환, 완전 지그재그, 비율 13.3/33.3/26.7/20/6.7%)
DIFFICULTY_PATTERN = [2, 4, 2, 3, 2, 3, 2, 3, 1, 4, 1, 4, 3, 5, 2]

# 난이도별 설정: 보드 위 스택 개수, normal(빈칸) 개수, 보드 크기 후보
DIFFICULTY_CONFIG = {
    1: {'n_stacks': (3, 3), 'n_normal': (2, 3), 'max_colors': 3, 'sizes': [(3, 3), (2, 2), (3, 2)]},
    2: {'n_stacks': (3, 4), 'n_normal': (1, 2), 'max_colors': 3, 'sizes': [(3, 3), (3, 2), (2, 3), (4, 2)]},
    3: {'n_stacks': (4, 5), 'n_normal': (1, 2), 'max_colors': 3, 'sizes': [(3, 3), (4, 3), (3, 4), (4, 2)]},
    4: {'n_stacks': (5, 6), 'n_normal': (2, 3), 'max_colors': 4, 'sizes': [(4, 3), (5, 3), (4, 4), (5, 2)]},
    5: {'n_stacks': (6, 7), 'n_normal': (2, 3), 'max_colors': 4, 'sizes': [(5, 3), (6, 3), (5, 2), (4, 4)]},
}

MAX_COLORS_PER_STACK = 3   # 스택 내부 최대 색 종류
MAX_TRANSITIONS = 2        # 스택 내부 최대 색 전환 횟수 (예: R-B-Y = 전환 2회)


def difficulty_for_id(pid):
    """1부터 시작하는 puzzle id에 대해 패턴을 순환시켜 난이도(1~5)를 반환."""
    return DIFFICULTY_PATTERN[(pid - 1) % len(DIFFICULTY_PATTERN)]


# ────────────────────────────────────────────────────────────────
# 보드 모양 생성 (zip 샘플처럼 Blank로 모서리를 깎아 다양한 모양을 만든다)
# ────────────────────────────────────────────────────────────────

def _make_layout(Y, X, n_total, rng, max_tries=300):
    """
    랜덤 시작점에서 BFS 확장으로 n_total개의 연결된 칸(좌표)을 고른다.
    (board_engine.get_neighbors 기준 — 열 시프트 좌표계)
    """
    all_pos = [(y, x) for y in range(Y) for x in range(X)]
    for _ in range(max_tries):
        rng.shuffle(all_pos)
        start = all_pos[0]
        chosen = [start]
        chosen_set = {start}
        frontier = list(get_neighbors(*start, Y, X))
        rng.shuffle(frontier)
        seen_f = set(map(tuple, frontier))
        while len(chosen) < n_total and frontier:
            nxt = frontier.pop(0)
            if nxt in chosen_set:
                continue
            chosen.append(nxt)
            chosen_set.add(nxt)
            for nb in get_neighbors(*nxt, Y, X):
                if nb not in chosen_set and nb not in seen_f:
                    frontier.append(nb)
                    seen_f.add(nb)
        if len(chosen) >= n_total:
            rng.shuffle(chosen)
            return chosen[:n_total]
    return None


# ────────────────────────────────────────────────────────────────
# 색 배정 (그래프 컬러링으로 인접 top 충돌 방지)
# ────────────────────────────────────────────────────────────────

def _assign_tops(positions, colors, Y, X, rng, max_tries=300):
    pos_idx = {p: i for i, p in enumerate(positions)}
    n = len(positions)
    for _ in range(max_tries):
        tops = [None] * n
        order = list(range(n))
        rng.shuffle(order)
        ok = True
        for i in order:
            py, px = positions[i]
            used = {tops[pos_idx[nb]]
                    for nb in get_neighbors(py, px, Y, X)
                    if nb in pos_idx and tops[pos_idx[nb]] is not None}
            avail = [c for c in colors if c not in used]
            if not avail:
                ok = False
                break
            tops[i] = rng.choice(avail)
        if ok:
            return tops
    return None


# ────────────────────────────────────────────────────────────────
# 스택 내부 구성 (최대 3색, 전환 최대 2회, 인간 스타일 연속 그룹)
# ────────────────────────────────────────────────────────────────

def _build_stack_from_top(top_color, colors, length, rng):
    """
    top_color로 끝나는(stack[-1] == top_color) 길이 length의 칩 리스트를 만든다.
    제약: 색 종류 <= MAX_COLORS_PER_STACK, 전환 횟수 <= MAX_TRANSITIONS.

    구성 방식: "그룹(연속된 같은 색 묶음)의 나열"로 만든다.
      - 그룹 개수 n_groups = 전환 횟수 + 1 (예: 전환 2회 -> 그룹 3개)
      - 마지막 그룹의 색이 항상 top_color (스택 맨 위 = 배열의 마지막 원소)
      - 인접한 두 그룹은 서로 다른 색이어야 함
    """
    max_extra_colors = min(MAX_COLORS_PER_STACK - 1, len(colors) - 1)
    n_extra = rng.randint(0, max_extra_colors)
    other_colors = [c for c in colors if c != top_color]
    extra_colors = rng.sample(other_colors, min(n_extra, len(other_colors)))
    palette = [top_color] + extra_colors  # 이 스택에서 쓸 색 목록

    max_groups = min(MAX_TRANSITIONS + 1, length)
    n_groups = rng.randint(1, max(1, max_groups))

    # 그룹별 색을 뒤(top)에서부터 채워나간다. 마지막(=배열 끝=top) 그룹은 top_color.
    group_colors = [None] * n_groups
    group_colors[-1] = top_color
    for gi in range(n_groups - 2, -1, -1):
        candidates = [c for c in palette if c != group_colors[gi + 1]]
        if not candidates:
            candidates = palette
        group_colors[gi] = rng.choice(candidates)

    # 길이를 그룹별로 분배 (각 그룹 최소 1)
    sizes = [1] * n_groups
    remaining = length - n_groups
    while remaining > 0:
        gi = rng.randrange(n_groups)
        sizes[gi] += 1
        remaining -= 1

    stack = []
    for color, sz in zip(group_colors, sizes):
        stack.extend([color] * sz)
    return stack


def _verify_stack_rule(stack):
    """색 종류<=3, 전환<=2 인지 검증."""
    colors_used = len(set(stack))
    transitions = sum(1 for i in range(1, len(stack)) if stack[i] != stack[i - 1])
    return colors_used <= MAX_COLORS_PER_STACK and transitions <= MAX_TRANSITIONS


# ────────────────────────────────────────────────────────────────
# 손패 계산: 보드+손패 합산 색깔 총합 = 정확히 10
# ────────────────────────────────────────────────────────────────

def _build_hand(board_counts, colors, rng, n_hand_stacks=3, max_per_hand=8):
    """
    각 색의 (10 - board_count)를 손패에 나눠 담는다.
    board_count가 10을 초과하는 색은 생성 실패로 처리(상위에서 재시도).
    """
    need = {}
    for c in colors:
        b = board_counts.get(c, 0)
        n = MATCH_TARGET - b
        if n < 0:
            return None  # 이미 보드에서 10 초과 -> 실패
        if n > 0:
            need[c] = n

    pool = []
    for c, n in need.items():
        pool.extend([c] * n)
    if not pool:
        return None
    rng.shuffle(pool)

    total = len(pool)
    if total > max_per_hand * n_hand_stacks:
        return None

    # total을 n_hand_stacks장으로 분배 (각 1~max_per_hand)
    for _ in range(200):
        cuts = sorted(rng.sample(range(1, total), min(n_hand_stacks - 1, max(total - 1, 0))) ) if total > 1 else []
        if len(cuts) < n_hand_stacks - 1:
            # total이 너무 작아 n_hand_stacks장을 다 못 채우는 경우, 빈 장 허용
            cuts = sorted(rng.sample(range(0, total + 1), n_hand_stacks - 1)) if total >= n_hand_stacks - 1 else None
            if cuts is None:
                continue
        bounds = [0] + cuts + [total]
        hands = [pool[bounds[i]:bounds[i + 1]] for i in range(n_hand_stacks)]
        if all(0 <= len(h) <= max_per_hand for h in hands) and sum(len(h) for h in hands) == total:
            if any(len(h) > 0 for h in hands):
                return hands
    return None


# ────────────────────────────────────────────────────────────────
# 메인 생성 함수
# ────────────────────────────────────────────────────────────────

def _attempt(pid, difficulty, rng, n_hand_stacks=3, force_n_colors=None):
    cfg = DIFFICULTY_CONFIG[difficulty]
    max_colors = cfg['max_colors']
    n_stacks = rng.randint(*cfg['n_stacks'])
    n_normal = rng.randint(*cfg['n_normal'])
    Y, X = rng.choice(cfg['sizes'])
    n_total = n_stacks + n_normal
    if n_total > Y * X:
        return None

    positions = _make_layout(Y, X, n_total, rng)
    if positions is None:
        return None
    stack_pos = positions[:n_stacks]
    normal_pos = positions[n_stacks:]

    n_colors = force_n_colors if force_n_colors is not None else max_colors
    n_colors = max(2, min(n_colors, 8))
    colors = rng.sample(range(8), n_colors)

    tops = _assign_tops(stack_pos, colors, Y, X, rng)
    if tops is None:
        return None

    # 각 스택 길이: 너무 길지 않게(보드 칩 총량이 10을 넘지 않도록) 상한을 둔다
    stack_chips = []
    for i in range(n_stacks):
        length = rng.randint(2, 6)
        for _try in range(30):
            s = _build_stack_from_top(tops[i], colors, length, rng)
            if _verify_stack_rule(s):
                stack_chips.append(s)
                break
        else:
            return None

    board_counts = Counter(c for s in stack_chips for c in s)
    if any(v > MATCH_TARGET for v in board_counts.values()):
        return None

    hand_stacks = _build_hand(board_counts, colors, rng, n_hand_stacks=n_hand_stacks)
    if hand_stacks is None:
        return None

    # 손패 각 스택도 동일한 색/전환 규칙 적용 + 검증
    for h in hand_stacks:
        if len(set(h)) > MAX_COLORS_PER_STACK:
            return None
        transitions = sum(1 for i in range(1, len(h)) if h[i] != h[i - 1])
        if transitions > MAX_TRANSITIONS:
            # 정렬해서 전환을 최소화 (색끼리 묶기)
            h.sort()

    # ── grid 조립 후 해 존재 검증
    grid = [[None] * X for _ in range(Y)]
    for (py, px) in normal_pos:
        grid[py][px] = make_cell()
    for i, (py, px) in enumerate(stack_pos):
        grid[py][px] = make_cell(chips=stack_chips[i])

    solutions = count_solutions(grid, Y, X, hand_stacks, max_count=4, max_states=25000)
    if not solutions:
        return None
    n_sol = len(solutions)
    if n_sol > 3:
        return None  # 해가 너무 많으면(쉬운 퍼즐) 재시도
    if n_sol == 1:
        forcing = 2  # 해가 정확히 1개 -> 강한 묘수풀이
    elif n_sol == 2:
        forcing = 1
    else:
        forcing = 0  # 해가 3개

    tiles = [[{'TileType': 1} for _ in range(X)] for _ in range(Y)]
    for (py, px) in normal_pos:
        tiles[py][px] = {'TileType': 0}
    for i, (py, px) in enumerate(stack_pos):
        tiles[py][px] = {'TileType': 2, 'Stacks': stack_chips[i]}

    board_json = {
        'Timestamp': int(time.time() * 1000) + pid,
        'GameType': 0,
        'GridOrientation': 0,
        'XCells': X, 'YCells': Y,
        'Tiles': tiles,
    }

    total_counts = Counter(board_counts)
    for h in hand_stacks:
        for c in h:
            total_counts[c] += 1

    stack_info = {'Id': pid}
    for i, hs in enumerate(hand_stacks):
        stack_info[f'Stack{i + 1}'] = ','.join(COLOR_MAP[c] for c in hs) if hs else None

    return {
        'pid': pid,
        'difficulty': difficulty,
        'board_json': board_json,
        'hand_stacks': hand_stacks,
        'stack_chips': stack_chips,
        'stack_pos': stack_pos,
        'normal_pos': normal_pos,
        'board_counts': dict(board_counts),
        'total_counts': dict(total_counts),
        'n_solutions': n_sol,
        'forcing': forcing,
        'solution': solutions[0],
        'stack_info': stack_info,
        'n_colors': n_colors,
    }


def generate_special_puzzle(puzzle_id, difficulty=None, seed=None, max_attempts=400, n_hand_stacks=3):
    """
    puzzle_id: 1부터 시작하는 퍼즐 번호. difficulty가 None이면 패턴에서 자동 결정.
    난이도 4~5는 max_colors(4색)를 먼저 충분히 시도하고, 그래도 안 되면
    한 단계 적은 색(3색)으로 폴백한다.
    """
    if difficulty is None:
        difficulty = difficulty_for_id(puzzle_id)
    cfg = DIFFICULTY_CONFIG[difficulty]
    max_colors = cfg['max_colors']
    base_seed = seed if seed is not None else puzzle_id * 12345

    # 1차: 목표 색상 수(max_colors)로 충분히 시도
    primary_attempts = int(max_attempts * 0.7)
    for attempt in range(primary_attempts):
        rng = random.Random(base_seed + attempt * 7919)
        r = _attempt(puzzle_id, difficulty, rng, n_hand_stacks=n_hand_stacks, force_n_colors=max_colors)
        if r is not None:
            return r

    # 2차: 색상 수를 하나 줄여서 폴백 시도
    fallback_colors = max(2, max_colors - 1)
    for attempt in range(primary_attempts, max_attempts):
        rng = random.Random(base_seed + attempt * 7919)
        r = _attempt(puzzle_id, difficulty, rng, n_hand_stacks=n_hand_stacks, force_n_colors=fallback_colors)
        if r is not None:
            return r

    raise RuntimeError(f"S{puzzle_id:03d}: {max_attempts}회 시도 실패 (난이도 {difficulty})")


def analyze_special(result):
    return {
        'difficulty': result['difficulty'],
        'forcing': result['forcing'],
        'n_solutions': result['n_solutions'],
        'n_stacks': len(result['stack_pos']),
        'n_colors': result['n_colors'],
        'total_counts': result['total_counts'],
    }


if __name__ == '__main__':
    print("=== S01~S30 생성 테스트 (새 generate_special v4) ===")
    ok = fail = 0
    t0 = time.time()
    for pid in range(1, 31):
        diff = difficulty_for_id(pid)
        try:
            r = generate_special_puzzle(pid)
            tc = r['total_counts']
            mod10_ok = all(v == 10 for v in tc.values())
            print(f"S_{pid:02d} 난이도={diff} forcing={r['forcing']} "
                  f"sol={r['n_solutions']} 색={r['n_colors']} "
                  f"합계={tc} {'OK' if mod10_ok else '✗'}")
            ok += 1
        except RuntimeError as e:
            fail += 1
            print(f"S_{pid:02d} 난이도={diff} ✗ 실패: {e}")
    print(f"\n성공:{ok} 실패:{fail} ({time.time()-t0:.1f}초)")
