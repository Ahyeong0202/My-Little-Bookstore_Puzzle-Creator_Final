"""
update_tblstage.py
──────────────────
generate_special.py로 생성한 퍼즐들을 tblStage.xlsx에 추가.

사용법:
  python3 update_tblstage.py <tblStage.xlsx 경로> <시작번호> <끝번호> [출력경로]

예:
  python3 update_tblstage.py data/tblStage.xlsx 35 40
  → data/tblStage_updated.xlsx 생성

추가 내용:
  - Stage 탭: Mode=Turn 행 추가 (Id=1035~)
  - StackInfo 탭: Stack1~N 행 추가 (Id=35~)
"""

import sys, json
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Font
import re

# generate_special 임포트 (같은 디렉토리)
sys.path.insert(0, str(Path(__file__).parent))
from generate_special import generate_special_puzzle, analyze_special


# ── 보상 공식 생성 (기존 패턴 유지)
def _xp_formula(row_num):
    return f'=CEILING(65+((A{row_num}-1000)^ 1.3), 5)'
def _gold_formula(row_num):
    return f'=CEILING(800+((A{row_num}-1002)^ 3), 5)'
def _token_formula(row_num):
    return f'=CEILING(10+((A{row_num}-1000)^ 1.5), 5)'
def _gem_formula(row_num):
    return f'=CEILING(5+((A{row_num}-1000)^ 1.45), 5)'


def update_tblstage(
    xlsx_path: str,
    start: int,
    end: int,
    output_path: str = None,
    seed_base: int = 12345,
):
    """
    tblStage.xlsx에 특수 퍼즐 행 추가.

    Parameters
    ----------
    xlsx_path   : 원본 tblStage.xlsx 경로
    start, end  : 추가할 S 번호 범위 (start~end 포함)
    output_path : 저장 경로 (None이면 _updated 접미사)
    """
    src = Path(xlsx_path)
    if output_path is None:
        output_path = str(src.parent / (src.stem + '_updated.xlsx'))

    wb = load_workbook(str(src))
    ws_stage  = wb['Stage']
    ws_stack  = wb['StackInfo']

    # ── Stage 탭 헤더 파악
    stage_headers = [c.value for c in next(ws_stage.iter_rows(min_row=1, max_row=1))]
    # 마지막 데이터 행 번호 (1-indexed, 헤더 포함)
    stage_last_row = ws_stage.max_row

    # StackInfo 헤더
    stack_headers = [c.value for c in next(ws_stack.iter_rows(min_row=1, max_row=1))]
    stack_last_row = ws_stack.max_row

    # ── 기존 Id 확인 (중복 방지)
    existing_stage_ids = set()
    for row in ws_stage.iter_rows(min_row=2, values_only=True):
        if row[0]: existing_stage_ids.add(row[0])

    existing_stack_ids = set()
    for row in ws_stack.iter_rows(min_row=2, values_only=True):
        if row[0]: existing_stack_ids.add(row[0])

    print(f'기존 Stage 행: {len(existing_stage_ids)}개 (Turn: {sum(1 for i in existing_stage_ids if isinstance(i,int) and i>=1000)}개)')
    print(f'기존 StackInfo 행: {len(existing_stack_ids)}개')
    print()

    added_stage = 0
    added_stack = 0
    generated = []

    for pid in range(start, end + 1):
        stage_id  = 1000 + pid
        stack_id  = pid

        # 중복 체크
        if stage_id in existing_stage_ids:
            print(f'  S_{pid:02d}: Stage Id={stage_id} 이미 존재 — 스킵')
            continue
        if stack_id in existing_stack_ids:
            print(f'  S_{pid:02d}: StackInfo Id={stack_id} 이미 존재 — 스킵')
            continue

        # 난이도 파라미터 (TurnCount=3 고정 — Stack1~Stack3만 사용)
        if   pid <= 10: n_colors, turn_count, normal_cells = 2, 3, 2
        elif pid <= 20: n_colors, turn_count, normal_cells = 2, 3, 1
        else:            n_colors, turn_count, normal_cells = 3, 3, 1

        try:
            r = generate_special_puzzle(
                puzzle_id=pid,
                n_colors=n_colors,
                turn_count=turn_count,
                normal_cells=normal_cells,
                seed=pid * seed_base,
            )
        except RuntimeError as e:
            print(f'  S_{pid:02d}: 생성 실패 — {e}')
            continue

        diff = analyze_special(r)

        # ── Stage 탭에 행 추가
        stage_row_num = stage_last_row + added_stage + 1
        sr = r['stage_row']

        # stage_headers 순서에 맞게 값 세팅
        row_vals = []
        for h in stage_headers:
            if h == 'Id':                      row_vals.append(stage_id)
            elif h == 'Mode':                  row_vals.append('Turn')
            elif h == 'LevelName':             row_vals.append(f'S {pid:02d}')
            elif h == 'PlaceableCount':        row_vals.append(3)
            elif h == 'IsPreview':             row_vals.append(False)
            elif h == 'TotalAllocation':       row_vals.append(3)  # 특수 퍼즐 고정
            elif h == 'InitialAvailableColors':row_vals.append(None)
            elif h == 'DistinctColorCount':    row_vals.append(None)
            elif h == 'ColorDuplicationRate':  row_vals.append(None)
            elif h == 'ProgressAddNewColor':   row_vals.append(None)
            elif h == 'NewColorsMilestones':   row_vals.append(None)
            elif h == 'Extra':                 row_vals.append(pid)
            elif h == 'TurnCount':             row_vals.append(3)  # Stack3까지만 사용
            elif h == 'IceCount':              row_vals.append(0)
            elif h == 'GrassCount':            row_vals.append(0)
            elif h == 'WoodCount':             row_vals.append(0)
            elif h == 'CameraPictureCount':    row_vals.append(0)
            elif h == 'GenreXPReward':         row_vals.append(10)
            elif h == 'XpReward':              row_vals.append(_xp_formula(stage_row_num))
            elif h == 'GoldReward':            row_vals.append(_gold_formula(stage_row_num))
            elif h == 'TokenReward':           row_vals.append(_token_formula(stage_row_num))
            elif h == 'GemReward':             row_vals.append(_gem_formula(stage_row_num))
            else:                              row_vals.append(None)

        ws_stage.append(row_vals)
        added_stage += 1

        # ── StackInfo 탭에 행 추가
        si = r['stack_info']
        stack_vals = []
        for h in stack_headers:
            if h == 'Id':
                stack_vals.append(stack_id)
            elif h and h.startswith('Stack'):
                stack_vals.append(si.get(h))
            else:
                stack_vals.append(None)
        ws_stack.append(stack_vals)
        added_stack += 1

        total = r['board_chips'] + r['hand_chips']
        ok = all(v % 10 == 0 for v in total.values())
        print(f'  S_{pid:02d} [{diff["score"]:4.0f}점] '
              f'보드={dict(r["board_chips"])} 손패={dict(r["hand_chips"])} '
              f'{"✓" if ok else "✗"} Normal={normal_cells}')

        generated.append({
            'pid': pid,
            'board_json': r['board_json'],
            'stack_info': r['stack_info'],
            'stage_row':  r['stage_row'],
            'diff':       diff,
        })

    # ── 저장
    wb.save(output_path)
    print()
    print(f'저장 완료: {output_path}')
    print(f'  Stage 추가: {added_stage}행')
    print(f'  StackInfo 추가: {added_stack}행')
    return generated


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('사용법: python3 update_tblstage.py <tblStage.xlsx> <시작번호> <끝번호> [출력경로]')
        sys.exit(1)

    xlsx  = sys.argv[1]
    start = int(sys.argv[2])
    end   = int(sys.argv[3])
    out   = sys.argv[4] if len(sys.argv) > 4 else None

    result = update_tblstage(xlsx, start, end, out)
    print(f'\n생성된 퍼즐: {len(result)}개')
