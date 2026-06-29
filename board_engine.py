"""
hybrid02_board.py
──────────────────
PuzzleActionController.cs의 ProcessSingleStepTransferSequentiallyHybrid02 규칙을
그대로 재현한 Python 시뮬레이터.

원본 C# 로직 요약 (HYBRID_02):
  - 어떤 칸(startHex)에 칩을 놓으면, "같은 색 top을 가진 이웃 칸들"을 찾는다.
  - 이웃이 0개 → 종료.
  - 이웃이 1개 → top 칩 수가 적은 쪽이 많은 쪽으로 흡수(스택 전체 이동).
                 동률이면 "같은 색 이웃 개수"가 적은(또는 같은) 쪽이 흡수당함.
                 (startNeighbors <= neighborNeighbors 이면 start가 neighbor로 흡수)
  - 이웃이 2개 이상 → 조건 없이 무조건 모든 이웃이 startHex로 흡수됨.
  - 흡수 후 칩이 남은 칸들은 재귀적으로 다시 같은 과정을 반복(큐에 다시 들어감).

주의: 원본 C#에는 이웃 1개 분기 끝에서 neighbor를 한 번 더 무조건 큐에 넣는
버그성 중복 호출이 있으나(라인 325), 이는 "같은 칸을 다시 검사"하는 것과
동일한 효과(이미 비었으면 즉시 종료)라 결과(클리어 여부)에는 영향이 없으므로
시뮬레이터에서는 재현하지 않는다 — 단, 무한 재귀 방지를 위해 호출 횟수 제한을 둔다.
"""

import copy

NEIGHBORS_EVEN_COL = [(-1, 0), (+1, 0), (0, -1), (0, +1), (-1, -1), (-1, +1)]
NEIGHBORS_ODD_COL  = [(-1, 0), (+1, 0), (0, -1), (0, +1), (+1, -1), (+1, +1)]
MATCH_TARGET = 10  # 같은 색이 top부터 연속 10개 쌓이면 소멸


def get_neighbors(y, x, Y, X):
    # 이 게임의 헥스 좌표계는 "열(x) 기준" 시프트를 사용한다.
    # x가 짝수인 열은 위쪽 대각선(EVEN_COL), 홀수인 열은 아래쪽 대각선(ODD_COL)을 이웃으로 갖는다.
    # (zip 샘플 S01, S02의 실제 해로 교차 검증됨)
    offs = NEIGHBORS_EVEN_COL if x % 2 == 0 else NEIGHBORS_ODD_COL
    return [(y + dy, x + dx) for dy, dx in offs if 0 <= y + dy < Y and 0 <= x + dx < X]


class Board:
    """
    grid[y][x] = None (Blank, 칩을 놓을 수 없음)
               | {'chips': [...]}  (Normal/Stack 칸. chips[-1] = top)
    """

    def __init__(self, grid):
        self.Y = len(grid)
        self.X = len(grid[0])
        self.g = copy.deepcopy(grid)

    def top(self, y, x):
        c = self.g[y][x]
        if c is None or not c['chips']:
            return None
        return c['chips'][-1]

    def depth(self, y, x):
        c = self.g[y][x]
        return 0 if c is None else len(c['chips'])

    def is_empty(self, y, x):
        c = self.g[y][x]
        return c is not None and len(c['chips']) == 0

    def find_same_color_neighbors(self, y, x):
        """startHex와 top 색이 같은 이웃 칸들의 좌표 목록 (FindSameColorNeighbors 재현)."""
        t = self.top(y, x)
        if t is None:
            return []
        return [(ny, nx) for ny, nx in get_neighbors(y, x, self.Y, self.X) if self.top(ny, nx) == t]

    def transfer(self, src, dst):
        """
        source 칸의 top부터 연속된 같은 색(top_streak)만큼만 target 칸 위로 옮긴다.
        (TransferTiles 재현 — 전체 스택이 아니라 '맨 위 같은 색 묶음'만 이동한다.
        예: [Orange,Orange,Orange,Red,Red,Red,Red] → top Red 4개만 이동, Orange 3개는 남음)
        """
        sy, sx = src
        dy, dx = dst
        streak = self.top_streak(sy, sx)
        if streak == 0:
            return
        src_chips = self.g[sy][sx]['chips']
        moving = src_chips[-streak:]
        del src_chips[-streak:]
        self.g[dy][dx]['chips'].extend(moving)
        self._pop_streak_if_full((dy, dx))

    def top_streak(self, y, x):
        """해당 칸의 top부터 연속으로 같은 색인 칩의 개수 (NumberOfTopColorLayers 재현)."""
        c = self.g[y][x]
        if c is None or not c['chips']:
            return 0
        chips = c['chips']
        top = chips[-1]
        cnt = 0
        for ch in reversed(chips):
            if ch == top:
                cnt += 1
            else:
                break
        return cnt

    def _pop_streak_if_full(self, pos):
        """
        칸의 top 연속 색 개수가 MATCH_TARGET(10) 이상이면, 그 연속분(10개)을 제거한다.
        (CheckIsHexFull -> HexFullAnimation 재현)
        """
        y, x = pos
        while self.top_streak(y, x) >= MATCH_TARGET:
            chips = self.g[y][x]['chips']
            del chips[-MATCH_TARGET:]

    def place(self, y, x, stack):
        """빈 칸에만 스택을 놓을 수 있다. 칩이 있는 칸에는 놓을 수 없다."""
        assert self.is_empty(y, x), f"({y},{x})는 빈 칸이 아니라 놓을 수 없음"
        self.g[y][x]['chips'].extend(stack)
        self._pop_streak_if_full((y, x))
        self._resolve_from((y, x))

    def _resolve_from(self, start, max_steps=2000):
        """start 칸을 기준으로 HYBRID_02 흡수 로직을 큐 방식으로 처리."""
        queue = [start]
        steps = 0
        while queue and steps < max_steps:
            steps += 1
            cy, cx = queue.pop(0)
            if self.depth(cy, cx) == 0:
                continue

            neighbors = self.find_same_color_neighbors(cy, cx)

            if len(neighbors) == 0:
                continue

            elif len(neighbors) == 1:
                ny, nx = neighbors[0]
                start_layers = self.top_streak(cy, cx)
                nb_layers = self.top_streak(ny, nx)

                if start_layers < nb_layers:
                    # start가 neighbor로 흡수됨 (start의 top뭉치만 이동)
                    self.transfer((cy, cx), (ny, nx))
                    if self.depth(cy, cx) > 0:
                        queue.append((cy, cx))
                    if self.depth(ny, nx) > 0:
                        queue.append((ny, nx))
                elif nb_layers < start_layers:
                    # neighbor가 start로 흡수됨 (neighbor의 top뭉치만 이동)
                    self.transfer((ny, nx), (cy, cx))
                    if self.depth(cy, cx) > 0:
                        queue.append((cy, cx))
                    if self.depth(ny, nx) > 0:
                        queue.append((ny, nx))
                else:
                    # 동률 → 같은 색 이웃 개수로 판단
                    start_nb_count = len(self.find_same_color_neighbors(cy, cx))
                    nb_nb_count = len(self.find_same_color_neighbors(ny, nx))
                    if start_nb_count <= nb_nb_count:
                        self.transfer((cy, cx), (ny, nx))
                    else:
                        self.transfer((ny, nx), (cy, cx))
                    if self.depth(cy, cx) > 0:
                        queue.append((cy, cx))
                    if self.depth(ny, nx) > 0:
                        queue.append((ny, nx))

            else:
                # 이웃이 2개 이상 → 무조건 모두 start로 흡수
                affected = []
                for (ny, nx) in neighbors:
                    self.transfer((ny, nx), (cy, cx))
                    if self.depth(ny, nx) > 0:
                        affected.append((ny, nx))
                for hex_ in affected:
                    queue.append(hex_)
                if self.depth(cy, cx) > 0:
                    queue.append((cy, cx))

    def free_cells(self):
        """완전히 빈(놓을 칸 비어있는) 칸들 — 참고용."""
        return [(y, x) for y in range(self.Y) for x in range(self.X) if self.is_empty(y, x)]

    def placeable_cells(self):
        """칩을 놓을 수 있는 칸 = 완전히 빈 칸만."""
        return self.free_cells()

    def all_clear(self):
        return all(
            self.g[y][x] is None or not self.g[y][x]['chips']
            for y in range(self.Y) for x in range(self.X)
        )


def make_cell(chips=None):
    return {'chips': list(chips) if chips else []}


def count_solutions(grid, Y, X, hand_stacks, max_count=20, max_states=150000):
    """
    HYBRID_02 규칙으로 모든 손패를 순서/위치 조합으로 배치해봤을 때
    보드를 완전히 비울 수 있는 해의 개수를 센다 (DFS).
    어느 칸(Blank 제외)에든 손패를 놓을 수 있다 — 이미 칩이 있는 칸도 포함.
    """
    init = Board(grid)
    n = len(hand_stacks)
    dfs = [(init, frozenset(), [])]
    solutions = []
    visited = 0
    while dfs and len(solutions) < max_count:
        board, used, path = dfs.pop()
        visited += 1
        if visited > max_states:
            break
        placeable = board.placeable_cells()
        remaining = [i for i in range(n) if i not in used]
        if not remaining:
            if board.all_clear():
                solutions.append(path)
            continue
        for hi in remaining:
            for (py, px) in placeable:
                nb = Board(board.g)
                nb.place(py, px, hand_stacks[hi])
                dfs.append((nb, used | {hi}, path + [{'hand_idx': hi, 'pos': (py, px), 'chips': hand_stacks[hi]}]))
    return solutions
