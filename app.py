import streamlit as st
import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import math

st.set_page_config(page_title="Puzzle Creator Dashboard", layout="wide", page_icon="🧩")

# ── 경로
BASE = Path(__file__).parent
LEVELS_DIR = BASE / "data" / "levels"
INTEGRATED_CSV = BASE / "data" / "integrated_difficulty.csv"
TBLSTAGE_PATH = BASE / "data" / "tblStage_500.xlsx"

# ── 색상
COLOR_MAP = {0:'Blue',1:'Yellow',2:'Red',3:'Green',4:'Orange',5:'Purple',6:'White',7:'Black'}
HEX_COLORS = {
    'Normal':'#D0D0D0','Blank':'#1a1a2e','Stack':'#4A90D9',
    'Lock':'#2C2C2C','Plank':'#8B5E3C','Ice':'#A8D8EA',
    'StackLock':'#6A4C93','Grass':'#52C41A','Ads':'#FA8C16',
    'CameraPicture':'#EB2F96',
}
CHIP_COLORS = {
    0:'#1890FF',1:'#FADB14',2:'#F5222D',3:'#52C41A',
    4:'#FA8C16',5:'#722ED1',6:'#FAFAFA',7:'#141414'
}
TILETYPE_NAME = {
    0:'Normal',1:'Blank',2:'Stack',3:'Lock',4:'Plank',
    5:'Ice',6:'StackLock',7:'Grass',8:'Ads',9:'CameraPicture'
}
NEIGH_EVEN = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1)]
NEIGH_ODD  = [(-1,0),(1,0),(0,-1),(0,1),(1,-1),(1,1)]

# ── 헥사 그리드 → Plotly 좌표 변환 (Horizontal pointy-top)
def hex_to_pixel(row, col, size=40):
    x = size * math.sqrt(3) * (col + 0.5 * (row % 2))
    y = size * 1.5 * row
    return x, -y  # y 반전

def make_hex_path(cx, cy, size=38):
    pts = []
    for i in range(6):
        angle = math.pi/180 * (60*i - 30)
        pts.append((cx + size*math.cos(angle), cy + size*math.sin(angle)))
    pts.append(pts[0])
    return [p[0] for p in pts], [p[1] for p in pts]

# ── 캐시 로더
@st.cache_data
def load_integrated():
    if INTEGRATED_CSV.exists():
        return pd.read_csv(INTEGRATED_CSV)
    return pd.DataFrame()

@st.cache_data
def load_tblstage():
    if TBLSTAGE_PATH.exists():
        df = pd.read_excel(TBLSTAGE_PATH, sheet_name='Stage', header=0)
        return df[df['LevelName'].str.startswith('N ', na=False)].reset_index(drop=True)
    return pd.DataFrame()

@st.cache_data
def load_level(lv: int):
    path = LEVELS_DIR / f"N_{lv:03d}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None

# ── 사이드바
st.sidebar.title("🧩 Puzzle Creator")
tab = st.sidebar.radio("페이지", ["🗺️ 판 모양 뷰어", "📊 난이도 계산기", "📈 난이도 곡선", "🔗 통합 분석"])

# ════════════════════════════════════════
# 탭 1: 판 모양 뷰어
# ════════════════════════════════════════
if tab == "🗺️ 판 모양 뷰어":
    st.title("🗺️ 판 모양 뷰어")

    col1, col2 = st.columns([1, 3])
    with col1:
        lv = st.number_input("레벨 선택", min_value=1, max_value=500, value=1, step=1)
        st.markdown("---")
        show_coord = st.checkbox("좌표 표시", value=False)
        show_chips = st.checkbox("칩 색상 표시", value=True)
        hex_size   = st.slider("헥사 크기", 20, 60, 38)

    data = load_level(int(lv))
    if data is None:
        st.error(f"N_{lv:03d}.json 파일을 찾을 수 없습니다.")
    else:
        Y = data['YCells']; X = data['XCells']
        tiles = data['Tiles']

        # 타일 통계
        type_count = {}
        for y in range(Y):
            for x in range(X):
                tt = tiles[y][x].get('TileType', 0)
                name = TILETYPE_NAME.get(tt, str(tt))
                type_count[name] = type_count.get(name, 0) + 1

        with col1:
            st.markdown(f"**보드**: {X}×{Y}")
            st.markdown("**타일 구성**")
            for name, cnt in sorted(type_count.items(), key=lambda x: -x[1]):
                if name != 'Blank':
                    st.markdown(f"- {name}: {cnt}개")

            # H1 지표
            from level_analyzer_v2 import analyze_level
            h1 = analyze_level(data)
            with st.expander("H1 지표"):
                for k in ['H1_1','H1_2','H1_3','H1_5','H1_6','H1_7','H1_9','H1_12','H1_14']:
                    st.markdown(f"**{k}**: {h1[k]}")

        with col2:
            fig = go.Figure()
            for y in range(Y):
                for x in range(X):
                    tile = tiles[y][x]
                    tt   = tile.get('TileType', 0)
                    name = TILETYPE_NAME.get(tt, 'Normal')
                    if name == 'Blank':
                        continue
                    cx, cy = hex_to_pixel(y, x, hex_size)
                    hx, hy = make_hex_path(cx, cy, hex_size*0.92)
                    color  = HEX_COLORS.get(name, '#CCCCCC')

                    fig.add_trace(go.Scatter(
                        x=hx, y=hy, fill='toself',
                        fillcolor=color, line=dict(color='white', width=1.5),
                        mode='lines', hoverinfo='skip', showlegend=False
                    ))

                    # 레이블
                    label = name[:2]
                    if name in ('Stack','StackLock','Ice') and 'Stacks' in tile:
                        stacks = tile['Stacks']
                        if show_chips and stacks:
                            label = '+'.join(COLOR_MAP.get(c,'?')[0] for c in stacks[:4])
                        else:
                            label = f"S{len(stacks)}"
                    elif name in ('Lock','Plank') and 'Level' in tile:
                        label = f"L{tile['Level']}"
                    elif name == 'StackLock' and 'UnlockLevel' in tile:
                        label = f"SL{tile['UnlockLevel']}"

                    if show_coord:
                        label = f"({y},{x})\n{label}"

                    fig.add_annotation(
                        x=cx, y=cy, text=label,
                        showarrow=False,
                        font=dict(size=9, color='white' if tt not in (0,) else '#333'),
                        align='center'
                    )

            fig.update_layout(
                height=600, margin=dict(l=10,r=10,t=10,b=10),
                xaxis=dict(visible=False, scaleanchor='y'),
                yaxis=dict(visible=False),
                plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════
# 탭 2: 난이도 계산기
# ════════════════════════════════════════
elif tab == "📊 난이도 계산기":
    st.title("📊 난이도 계산기")
    st.caption("Stage 탭 파라미터 기반 난이도 점수 계산 (#Level_Calculator 재현)")

    tbl = load_tblstage()
    intg = load_integrated()

    if tbl.empty:
        st.error("tblStage_500.xlsx를 data/ 폴더에 넣어주세요.")
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("⚙️ 가중치 설정")
            w_alloc = st.slider("TotalAllocation",    0, 30, 20)
            w_init  = st.slider("초기 색상 수",       0, 20, 12)
            w_dist  = st.slider("스택당 색상 수",     0, 20, 10)
            w_dup   = st.slider("중복 확률 (역수)",   0, 20,  8)
            w_prog  = st.slider("첫 임계값 (역수)",   0, 20, 10)
            w_new   = st.slider("추가 색상 수",       0, 20,  8)
            w_gim   = st.slider("기믹 비율",          0, 20, 14)
            total_w = w_alloc+w_init+w_dist+w_dup+w_prog+w_new+w_gim
            st.metric("총 가중치", f"{total_w} pt")

        def parse_avg(val):
            try:
                parts = [float(x) for x in str(val).split(',')]
                return np.mean(parts)
            except: return 0.0

        def parse_first(val):
            try: return float(str(val).split(',')[0])
            except: return 0.0

        def parse_count(val):
            if pd.isna(val): return 0
            return len([c for c in str(val).split(',') if c.strip()])

        def norm(v, lo, hi, inv=False):
            if hi==lo: return 0.0
            n = max(0.0, min(1.0, (v-lo)/(hi-lo)))
            return 1-n if inv else n

        RANGES = dict(alloc=(10,300),init=(1,5),dist=(1,4),dup=(0.1,0.8),prog=(2,30),new=(0,5))

        scores = []
        for _, row in tbl.iterrows():
            alloc = float(row['TotalAllocation']) if not pd.isna(row['TotalAllocation']) else 0
            init  = parse_count(row['InitialAvailableColors'])
            dist  = parse_avg(row['DistinctColorCount'])
            dup   = parse_avg(row['ColorDuplicationRate'])
            prog  = parse_first(row['ProgressAddNewColor'])
            new_c = parse_count(row['NewColorsMilestones'])
            gim   = sum([float(row.get(c,0) or 0) for c in ['GrassCount','WoodCount','IceCount','TurnCount','CameraPictureCount']])
            gim_r = gim/max(alloc,1)

            s = (norm(alloc,*RANGES['alloc'])*w_alloc +
                 norm(init, *RANGES['init'])*w_init +
                 norm(dist, *RANGES['dist'])*w_dist +
                 norm(dup,  *RANGES['dup'],inv=True)*w_dup +
                 norm(prog, *RANGES['prog'],inv=True)*w_prog +
                 norm(new_c,*RANGES['new'])*w_new +
                 norm(gim_r,0,0.5)*w_gim)
            scores.append(round(s/total_w*100 if total_w>0 else 0, 1))

        tbl['계산_난이도'] = scores

        with col2:
            st.subheader("📋 레벨별 난이도")
            lv_range = st.slider("레벨 범위", 1, 500, (1, 100))
            sub = tbl.iloc[lv_range[0]-1:lv_range[1]].copy()
            sub.index = range(lv_range[0], lv_range[1]+1)

            grade_map = lambda d: '매우쉬움' if d<25 else '쉬움' if d<45 else '보통' if d<60 else '어려움' if d<75 else '매우어려움'
            color_map = {'매우쉬움':'#1890FF','쉬움':'#52C41A','보통':'#FADB14','어려움':'#FA8C16','매우어려움':'#F5222D'}

            fig = go.Figure()
            x_vals = list(range(lv_range[0], lv_range[1]+1))
            y_vals = sub['계산_난이도'].tolist()
            colors = [color_map[grade_map(d)] for d in y_vals]

            fig.add_trace(go.Bar(x=x_vals, y=y_vals, marker_color=colors, name='계산 난이도'))
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=pd.Series(y_vals).rolling(5,center=True,min_periods=1).mean().tolist(),
                mode='lines', line=dict(color='white',width=2), name='이동평균'
            ))
            fig.update_layout(height=400, margin=dict(l=10,r=10,t=10,b=10),
                              plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                              font_color='white', xaxis_title='레벨', yaxis_title='난이도',
                              yaxis=dict(range=[0,105]))
            st.plotly_chart(fig, use_container_width=True)

            show_cols = ['LevelName','TotalAllocation','계산_난이도']
            st.dataframe(sub[show_cols].rename(columns={'계산_난이도':'난이도점수'}), height=300)

# ════════════════════════════════════════
# 탭 3: 난이도 곡선
# ════════════════════════════════════════
elif tab == "📈 난이도 곡선":
    st.title("📈 난이도 곡선")

    intg = load_integrated()
    if intg.empty:
        st.error("integrated_difficulty.csv를 data/ 폴더에 넣어주세요.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("평균 통합 난이도", f"{intg['integrated'].mean():.1f}")
        col2.metric("최고점 (레벨)", f"{intg['integrated'].max():.1f} (Lv{intg['integrated'].idxmax()+1})")
        col3.metric("최저점 (레벨)", f"{intg['integrated'].min():.1f} (Lv{intg['integrated'].idxmin()+1})")

        lv_range = st.slider("레벨 범위", 1, 500, (1, 500), key='curve_range')
        sub = intg.iloc[lv_range[0]-1:lv_range[1]]
        x   = list(range(lv_range[0], lv_range[1]+1))

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=sub['board_score'].tolist(),
                                 mode='lines', name='판 모양 난이도',
                                 line=dict(color='#FA8C16', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=x, y=sub['gameplay_score'].tolist(),
                                 mode='lines', name='게임 진행 난이도',
                                 line=dict(color='#1890FF', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=x, y=sub['integrated'].tolist(),
                                 mode='lines', name='통합 원시값',
                                 line=dict(color='#AAAAAA', width=1)))
        fig.add_trace(go.Scatter(x=x, y=sub['integrated_sm'].tolist(),
                                 mode='lines', name='통합 이동평균',
                                 line=dict(color='#52C41A', width=3)))

        fig.update_layout(height=450, margin=dict(l=10,r=10,t=20,b=10),
                          plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                          font_color='white', xaxis_title='레벨', yaxis_title='난이도',
                          yaxis=dict(range=[0,105]), legend=dict(orientation='h',y=1.1))
        st.plotly_chart(fig, use_container_width=True)

        # 구간 평균
        st.subheader("구간별 평균")
        zone_size = st.select_slider("구간 크기", [10,25,50,100], value=50)
        zones = []
        for i in range(0, 500, zone_size):
            lo2, hi2 = i, min(i+zone_size, 500)
            sub2 = intg.iloc[lo2:hi2]
            zones.append({
                '구간': f"Lv{lo2+1}-{hi2}",
                '판 모양': round(sub2['board_score'].mean(),1),
                '게임 진행': round(sub2['gameplay_score'].mean(),1),
                '통합 평균': round(sub2['integrated'].mean(),1),
                '최고': round(sub2['integrated'].max(),1),
                '최저': round(sub2['integrated'].min(),1),
            })
        zone_df = pd.DataFrame(zones)

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=zone_df['구간'], y=zone_df['판 모양'],
                              name='판 모양', marker_color='#FA8C16'))
        fig2.add_trace(go.Bar(x=zone_df['구간'], y=zone_df['게임 진행'],
                              name='게임 진행', marker_color='#1890FF'))
        fig2.add_trace(go.Scatter(x=zone_df['구간'], y=zone_df['통합 평균'],
                                  mode='lines+markers', name='통합 평균',
                                  line=dict(color='#52C41A', width=2)))
        fig2.update_layout(height=350, barmode='group',
                           plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                           font_color='white', yaxis=dict(range=[0,100]),
                           margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(zone_df, use_container_width=True)

# ════════════════════════════════════════
# 탭 4: 통합 분석
# ════════════════════════════════════════
elif tab == "🔗 통합 분석":
    st.title("🔗 통합 분석")

    intg = load_integrated()
    if intg.empty:
        st.error("integrated_difficulty.csv가 없습니다.")
    else:
        w_board    = st.slider("판 모양 가중치 (%)", 0, 100, 50)
        w_gameplay = 100 - w_board
        st.caption(f"판 모양 {w_board}% : 게임 진행 {w_gameplay}%")

        custom = (intg['board_score']*w_board + intg['gameplay_score']*w_gameplay) / 100
        custom_sm = custom.rolling(5, center=True, min_periods=1).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(1,501)), y=custom.tolist(),
                                 mode='lines', name='통합 원시',
                                 line=dict(color='#AAAAAA',width=1)))
        fig.add_trace(go.Scatter(x=list(range(1,501)), y=custom_sm.tolist(),
                                 mode='lines', name='통합 이동평균',
                                 line=dict(color='#52C41A',width=3)))

        # 기존 50:50 비교
        fig.add_trace(go.Scatter(x=list(range(1,501)), y=intg['integrated_sm'].tolist(),
                                 mode='lines', name='기존 50:50',
                                 line=dict(color='#1890FF',width=1,dash='dash')))

        fig.update_layout(height=450, plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                          font_color='white', xaxis_title='레벨', yaxis_title='난이도',
                          yaxis=dict(range=[0,105]),
                          legend=dict(orientation='h',y=1.1),
                          margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("평균", f"{custom.mean():.1f}")
        col2.metric("최고", f"{custom.max():.1f} (Lv{custom.idxmax()+1})")
        col3.metric("최저", f"{custom.min():.1f} (Lv{custom.idxmin()+1})")

        # 등급 분포
        grades = pd.cut(custom, bins=[0,25,45,60,75,100],
                        labels=['매우쉬움','쉬움','보통','어려움','매우어려움'])
        grade_cnt = grades.value_counts().sort_index()
        fig3 = px.bar(x=grade_cnt.index, y=grade_cnt.values,
                      color=grade_cnt.index,
                      color_discrete_map={'매우쉬움':'#1890FF','쉬움':'#52C41A',
                                          '보통':'#FADB14','어려움':'#FA8C16','매우어려움':'#F5222D'})
        fig3.update_layout(height=300, showlegend=False,
                           plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                           font_color='white', xaxis_title='등급', yaxis_title='개수',
                           margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig3, use_container_width=True)
