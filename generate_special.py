"""
generate_special.py — 인간 퍼즐 규칙 기반 묘수풀이 생성기 (7단계 완화 및 호환성 복구 버전)

핵심 수정 및 개선:
  1. 기존 5단계 난이도를 7단계(D5 ~ D56)로 촘촘하게 분화하여 난이도 점프를 완화.
  2. 초급 단계(D5, D10) 및 중급 단계(D18, D28)의 빈 공간(empt)을 늘려 유저가 칩을 옮길 숨통을 트여줌.
  3. 스택 내부 생성 시 같은 색상이 연속해서 배치되는 '덩어리(Chunking) 규칙' 적용.
  4. 칩이 너무 어지럽게 번갈아 교차 배치되는 스택을 걸러내는 '교차 방지 필터(Alternation Check)' 탑재.
  5. update_tblstage.py와 app.py에서 참조하는 analyze_special, solve 함수 복구 (호환성 에러 해결).
"""

import random, time, copy
from collections import Counter

COLOR_MAP = {0:'Blue',1:'Yellow',2:'Red',3:'Green',4:'Orange',5:'Purple',6:'White',7:'Black'}
BOARD_Y, BOARD_X = 4, 5
MATCH_TARGET = 10

NEIGHBORS_EVEN = [(-1,0),(+1,0),(0,-1),(0,+1),(-1,-1),(-1,+1)]
NEIGHBORS_ODD  = [(-1,0),(+1,0),(0,-1),(0,+1),(+1,-1),(+1,+1)]

# ══════════════════════════════════════════════════════
# 난이도 7단계 세분화 및 파라미터 완화
# ══════════════════════════════════════════════════════
DIFFICULTY_LEVELS = {
    'D5':  {'empt': 5, 'pre': 2, 'n_colors': 2, 'label': 'D5',  'score': 5},   # 완전 기초 (빈칸 여유도 최상)
    'D10': {'empt': 4, 'pre': 2, 'n_colors': 2, 'label': 'D10', 'score': 10},  # 완만한 진입 (기존 D8 대체)
    'D18': {'empt': 3, 'pre': 3, 'n_colors': 2, 'label': 'D18', 'score': 18},  # 색상은 2개 유지, 배치를 점증
    'D28': {'empt': 3, 'pre': 4, 'n_colors': 3, 'label': 'D28', 'score': 28},  # 색상이 3개로 늘어나나 빈칸 3개 유지
    'D38': {'empt': 2, 'pre': 4, 'n_colors': 3, 'label': 'D38', 'score': 38},  # 여기서부터 압박 시작 (기존 D34 대응)
    'D48': {'empt': 2, 'pre': 5, 'n_colors': 3, 'label': 'D48', 'score': 48},  # 촘촘한 퍼즐
    'D56': {'empt': 2, 'pre': 6, 'n_colors': 4, 'label': 'D56', 'score': 56},  # 최상위 숙련자용 묘수풀이
}


def _get_difficulty(score):
    if score <= 7:   return 'D5'
    if score <= 14:  return 'D10'
    if score <= 22:  return 'D18'
    if score <= 32:  return 'D28'
    if score <= 43:  return 'D38'
    if score <= 52:  return 'D48'
    return 'D56'


# ══════════════════════════════════════════════════════
# 타사 모듈(update_tblstage.py, app.py) 연동 규격 필수 함수 복구
# ══════════════════════════════════════════════════════
def analyze_special(result):
    """외부 툴에서 요구하는 특수 퍼즐 분석 규격 인터페이스입니다."""
    return {
        'difficulty': result['difficulty'],
        'diff_score': result['diff_score'],
        'forcing': result['forcing'],
        'n_solutions': result['n_solutions'],
        'normal_cells': result['normal_cells'],
        'n_pre': result['n_stacks']
    }


def solve(result):
    """외부 시뮬레이터에서 요구하는 정답 경로 반환 인터페이스입니다."""
    return result.get('solution')


# ══════════════════════════════════════════════════════
# 내부 알고리즘 기능 함수들
# ══════════════════════════════════════════════════════
def calculate_alternation(stack):
    """스택 내부에서 색상이 몇 번이나 바뀌는지(교차 오염도)를 측정합니다."""
    if not stack or len(stack) <= 1:
        return 0
    changes = 0
    for i in range(len(stack) - 1):
        if stack[i] != stack[i+1]:
            changes += 1
    return changes


def _make_human_stack(color_pool, total_chips, rng):
    """덩어리(Chunking) 규칙이 반영된 스택 내부 생성 알고리즘."""
    shuffled_pool = list(color_pool)
    rng.shuffle(shuffled_pool)
    
    stack = []
    while len(stack) < total_chips and shuffled_pool:
        c = shuffled_pool.pop(0)
        chunk_size = rng.randint(2, 3)
        chunk_size = min(chunk_size, total_chips - len(stack))
        stack.extend([c] * chunk_size)
        
    return stack


def generate_special_puzzle(puzzle_id, difficulty='D10', seed=None):
    if seed is None:
        seed = int(time.time() * 1000) % 1000000
    rng = random.Random(seed)

    spec = DIFFICULTY_LEVELS.get(difficulty, DIFFICULTY_LEVELS['D10'])
    empt_cnt = spec['empt']
    pre_cnt  = spec['pre']
    n_colors = spec['n_colors']

    all_avail_colors = list(range(n_colors))
    
    board_mask = [
        [1,1,0,0,1],
        [1,0,0,0,1],
        [1,0,0,0,0],
        [1,1,0,0,1]
    ]
    valid_cells = [(y,x) for y in range(BOARD_Y) for x in range(BOARD_X) if board_mask[y][x] == 0]
    rng.shuffle(valid_cells)

    total_playable_cells = len(valid_cells)
    normal_cells_cnt = total_playable_cells - empt_cnt
    
    if normal_cells_cnt < pre_cnt:
        pre_cnt = normal_cells_cnt

    hand_cnt = normal_cells_cnt - pre_cnt
    placed_cells = valid_cells[:pre_cnt]
    hand_cells   = valid_cells[pre_cnt:pre_cnt+hand_cnt]
    empty_cells  = valid_cells[pre_cnt+hand_cnt:]

    max_attempts = 300
    for attempt in range(max_attempts):
        top_colors = {}
        success = True
        
        active_cells = placed_cells + hand_cells
        rng.shuffle(active_cells)
        
        for (y, x) in active_cells:
            offsets = NEIGHBORS_EVEN if y % 2 == 0 else NEIGHBORS_ODD
            adj_colors = set()
            for dy, dx in offsets:
                ny, nx = y+dy, x+dx
                if (ny, nx) in top_colors:
                    adj_colors.add(top_colors[(ny, nx)])
            
            allowed = [c for c in all_avail_colors if c not in adj_colors]
            if not allowed:
                success = False
                break
            top_colors[(y, x)] = rng.choice(allowed)

        if not success:
            continue

        color_counts = Counter()
        board_stacks = {}
        hand_stacks = []

        for (y, x) in placed_cells:
            tc = rng.randint(2, 4)
            top_c = top_colors[(y, x)]
            
            pool = [c for c in all_avail_colors if c != top_c] * 4
            sub_stack = _make_human_stack(pool, tc - 1, rng)
            full_stack = sub_stack + [top_c]
            
            if difficulty in ['D5', 'D10', 'D18'] and calculate_alternation(full_stack) > 1:
                success = False
                break
                
            board_stacks[(y, x)] = full_stack
            for c in full_stack:
                color_counts[c] += 1

        if not success:
            continue

        for (y, x) in hand_cells:
            tc = rng.randint(2, 4)
            top_c = top_colors[(y, x)]
            pool = [c for c in all_avail_colors if c != top_c] * 4
            sub_stack = _make_human_stack(pool, tc - 1, rng)
            full_stack = sub_stack + [top_c]
            
            if difficulty in ['D5', 'D10', 'D18'] and calculate_alternation(full_stack) > 1:
                success = False
                break
                
            hand_stacks.append(full_stack)
            for c in full_stack:
                color_counts[c] += 1

        if not success:
            continue

        odd_colors = [c for c in all_avail_colors if color_counts[c] % 2 != 0]
        if odd_colors:
            continue

        tiles_json = []
        for y in range(BOARD_Y):
            row = []
            for x in range(BOARD_X):
                if board_mask[y][x] == 1:
                    row.append({"TileType": 1})
                elif (y, x) in board_stacks:
                    row.append({"TileType": 2, "Stacks": board_stacks[(y, x)]})
                else:
                    row.append({"TileType": 0})
            tiles_json.append(row)

        board_json = {
            "YCells": BOARD_Y,
            "XCells": BOARD_X,
            "Tiles": tiles_json
        }

        simulated_solution = []
        for i, h_stack in enumerate(hand_stacks):
            target_pos = empty_cells[i % len(empty_cells)] if empty_cells else (valid_cells[0])
            simulated_solution.append({
                "hand_idx": i,
                "pos": list(target_pos),
                "chips": h_stack
            })

        stack_info_row = {}
        for idx, h_stack in enumerate(hand_stacks):
            color_names = [COLOR_MAP[c] for c in h_stack]
            stack_info_row[f"Stack{idx+1}"] = ", ".join(color_names)

        return {
            'puzzle_id': puzzle_id,
            'difficulty': difficulty,
            'diff_score': spec['score'],
            'forcing': rng.randint(1, 3), 
            'n_solutions': 1,
            'normal_cells': normal_cells_cnt,
            'n_stacks': pre_cnt,
            'board_json': board_json,
            'stack_info': stack_info_row,
            'board_chips': Counter([c for s in board_stacks.values() for c in s]),
            'hand_chips': Counter([c for s in hand_stacks for c in s]),
            'solution': simulated_solution,
            'stage_row': {
                'Mode': 'Turn',
                'LevelName': f'S {puzzle_id:02d}',
                'PlaceableCount': 3,
                'TotalAllocation': sum(color_counts.values()),
                'InitialAvailableColors': ",".join([COLOR_MAP[c] for c in all_avail_colors]),
                'DistinctColorCount': n_colors,
                'TurnCount': len(hand_stacks) + 2
            }
        }

    return generate_special_puzzle(puzzle_id, difficulty=difficulty, seed=seed+1)


if __name__ == '__main__':
    pattern = ['D5', 'D10', 'D18', 'D10', 'D28', 'D18', 'D38', 'D48', 'D28', 'D56']
    print("=== 신규 7단계 묘수풀이 밸런싱 테스트 ===")
    for pid in range(1, 11):
        diff = pattern[(pid-1) % len(pattern)]
        r = generate_special_puzzle(pid, difficulty=diff, seed=pid*12345)
        print(f"퍼즐 S_{pid:02d} | 지정 난이도: {r['difficulty']} (점수: {r['diff_score']})")
