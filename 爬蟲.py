from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 (V8.6：領頭羊重疊與 100 期精準版) ---

def get_data_and_analyze(target_date=None):
    now = datetime.datetime.now()
    if not target_date: target_date = now.strftime("%Y-%m-%d")
    yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://winwin.tw/Bingo'}

    def fetch_api(date_str):
        url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            return resp.json() if resp.status_code == 200 else []
        except: return []

    # 跨日聚合數據
    data_today = fetch_api(target_date)
    data_yesterday = fetch_api(yesterday)
    full_raw_data = data_today + data_yesterday 

    if not full_raw_data:
        return [], [], "0:0", "0:0", "0:0", "0:0", {}, [], "N/A", target_date

    all_draws = []
    for item in full_raw_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: all_draws.append(nums)
    
    latest_no = full_raw_data[0].get('No', 'N/A')
    latest_win_nums = all_draws[0] if all_draws else []
    
    # --- 100 期共現矩陣 (精準引力) ---
    co_occ = Counter()
    for d in all_draws[:100]: 
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1

    # 環境統計 (今日全天)
    today_balls = [n for d in [nums for nums in ([ [int(x) for x in item.get('BigShowOrder','').split(',') if x.strip().isdigit()] for item in data_today if item.get('BigShowOrder','')]) if len(nums)==20] for n in d]
    o_day = len([n for n in today_balls if n % 2 != 0]); e_day = len(today_balls) - o_day
    s_day = len([n for n in today_balls if n <= 40]); b_day = len(today_balls) - s_day
    
    # 最近 20 期補償判定
    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20
    status = {'odd': o_20 <= 160, 'even': e_20 <= 160, 'small': s_20 <= 160, 'big': b_20 <= 160}

    wp_odd = 1.2 if status['odd'] else 1.0; wp_even = 1.2 if status['even'] else 1.0
    ws_small = 1.2 if status['small'] else 1.0; ws_big = 1.2 if status['big'] else 1.0

    short_heat = Counter([n for d in all_draws[:15] for n in d])
    long_freq = Counter([n for d in all_draws[:50] for n in d])
    
    all_analysis = []
    for i in range(1, 81):
        f_score = long_freq[i] * 1.0 
        streak = 0
        for d in all_draws:
            if i in d: streak += 1
            else: break
        r_score = 5.0 if streak == 1 else 2.0 if streak == 2 else 0.0
        l_penalty = -15.0 if streak >= 3 else 0.0
        cur_wp = (wp_odd if i % 2 != 0 else wp_even)
        cur_ws = (ws_small if i <= 40 else ws_big)
        h_penalty = -(short_heat[i] * 2.0)
        final_score = (f_score + r_score + l_penalty) * cur_wp * cur_ws + h_penalty
        omission = next((idx for idx, d in enumerate(all_draws) if i in d), 99)
        all_analysis.append({'no': i, 'score': round(final_score, 1), 'omission': omission})

    def get_synergy(n1, n2): return co_occ.get(tuple(sorted((n1, n2))), 0)

    # 策略生成邏輯 (V8.6：領頭羊重疊)
    def generate_squads(pool, size, count, offset=0):
        used = set(); squads = []
        # 依照指定 offset 選取種子
        sorted_seeds = sorted(pool, key=lambda x: x['score'], reverse=True)[offset:offset+count]
        for i, seed in enumerate(sorted_seeds):
            # 選取種子後，尋找其最強的 size-1 個夥伴
            partners = sorted([p for p in pool if p['no'] != seed['no']], 
                              key=lambda x: (get_synergy(seed['no'], x['no']), x['score']), reverse=True)[:size-1]
            squad = [seed.copy()] + [p.copy() for p in partners]
            squads.append({"id": i+1, "picks": sorted(squad, key=lambda x:x['no'])})
        return squads

    # 三星與六星都從 1~10 名開始取種子
    res_3star = generate_squads(all_analysis, 3, 10, offset=0)
    res_6star = generate_squads(all_analysis, 6, 10, offset=0)

    return (res_3star, res_6star, f"{o_day}:{e_day}", f"{s_day}:{b_day}", f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, target_date)

# --- 2. 網頁前端 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    (res_3star, res_6star, p_day, s_day, p_20, s_20, status, latest_win, latest_no, active_date) = get_data_and_analyze(date)
    
    html_content = """
    <html>
    <head>
        <title>量化矩陣 V8.6 核心收斂版</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .hit-g1 { background-color: #ef4444 !important; box-shadow: 0 0 15px #ef4444; color: white !important; }
            .hit-g2 { background-color: #f97316 !important; box-shadow: 0 0 15px #f97316; color: white !important; }
            .hit-g3 { background-color: #f59e0b !important; box-shadow: 0 0 15px #f59e0b; color: white !important; }
            .hit-g4 { background-color: #84cc16 !important; box-shadow: 0 0 15px #84cc16; color: white !important; }
            .hit-g5 { background-color: #10b981 !important; box-shadow: 0 0 15px #10b981; color: white !important; }
            .hit-g6 { background-color: #06b6d4 !important; box-shadow: 0 0 15px #06b6d4; color: white !important; }
            .hit-g7 { background-color: #3b82f6 !important; box-shadow: 0 0 15px #3b82f6; color: white !important; }
            .hit-g8 { background-color: #6366f1 !important; box-shadow: 0 0 15px #6366f1; color: white !important; }
            .hit-g9 { background-color: #8b5cf6 !important; box-shadow: 0 0 15px #8b5cf6; color: white !important; }
            .hit-g10 { background-color: #d946ef !important; box-shadow: 0 0 15px #d946ef; color: white !important; }

            .latest-ball { background: #f1f5f9; color: #475569; font-weight: bold; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 13px; border: 1px solid #e2e8f0; transition: all 0.3s; }
            .alert-gold { animation: gold-blink 1s infinite alternate; border: 2px solid #fbbf24 !important; }
            @keyframes gold-blink { from { box-shadow: 0 0 5px #fbbf24; background: #1e293b; } to { box-shadow: 0 0 25px #f59e0b; background: #fbbf24; color: #78350f; } }
            .stat-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); padding: 6px; border-radius: 12px; text-align: center; position: relative; }
            .miss-badge { position: absolute; top: -5px; right: -5px; background: #ef4444; color: white; font-size: 8px; font-weight: 900; padding: 1px 4px; border-radius: 4px; }
            .formula-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
        </style>
    </head>
    <body class="bg-slate-50 font-sans text-slate-900 pb-20 text-[12px]">
        <div class="max-w-6xl mx-auto p-4 md:p-8">
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-indigo-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase italic">Parity Monitor</span>{% if status.odd or status.even %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg font-black tracking-tighter">奇 {{ p_day }} 偶</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline">最近 20 期觸發</p><p class="text-xl font-black text-amber-300">{{ p_20 }}</p></div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase italic">Size Monitor</span>{% if status.small or status.big %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg font-black tracking-tighter">小 {{ s_day }} 大</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline">最近 20 期觸發</p><p class="text-xl font-black text-amber-300">{{ s_20 }}</p></div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-10">
                <div class="lg:col-span-3 bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <div class="flex justify-between items-center mb-6 border-b pb-4">
                        <h3 class="text-xs font-black text-slate-400 uppercase italic">📢 Latest Draw: <span class="text-indigo-600">{{ latest_no }}</span></h3>
                        <button onclick="location.reload()" class="bg-indigo-500 text-white px-4 py-1.5 rounded-xl text-[10px] font-black shadow-lg">Refresh</button>
                    </div>
                    <div class="space-y-6">
                        <div><p class="text-[9px] font-black text-amber-500 mb-2 uppercase">3-Star Matrix Tracking</p>
                            <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-3s" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                        </div>
                        <div><p class="text-[9px] font-black text-indigo-500 mb-2 uppercase">6-Star Matrix Tracking</p>
                            <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-6s" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                        </div>
                    </div>
                </div>

                <div class="bg-slate-900 p-5 rounded-3xl shadow-xl border-4 border-slate-800 text-white">
                    <h4 class="text-center text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-4">Battle Report</h4>
                    <div class="space-y-4">
                        <div class="bg-slate-800/50 p-3 rounded-2xl border border-slate-700">
                            <p class="text-[7px] font-black text-amber-500 mb-2 uppercase">3-Star Stats</p>
                            <div class="grid grid-cols-2 gap-2">
                                <div class="stat-card"><p class="text-[6px] text-slate-400">中 2</p><p class="text-lg font-black" id="count-3s-2">0</p></div>
                                <div class="stat-card" id="alert-3s-all">
                                    <p class="text-[6px] text-slate-400">全中</p><p class="text-lg font-black" id="count-3s-3">0</p>
                                    <div class="miss-badge" id="miss-3s-disp">0</div>
                                </div>
                            </div>
                        </div>
                        <div class="bg-slate-800/50 p-3 rounded-2xl border border-slate-700">
                            <p class="text-[7px] font-black text-indigo-400 mb-2 uppercase">6-Star Stats</p>
                            <div class="grid grid-cols-2 gap-2">
                                <div class="stat-card"><p class="text-[6px] text-slate-400">中 3</p><p class="text-sm font-black" id="count-6s-3">0</p></div>
                                <div class="stat-card"><p class="text-[6px] text-slate-400">中 4</p><p class="text-sm font-black" id="count-6s-4">0</p></div>
                                <div class="stat-card" id="alert-6s-5"><p class="text-[6px] text-slate-400">中 5</p><p class="text-sm font-black" id="count-6s-5">0</p></div>
                                <div class="stat-card" id="alert-6s-6">
                                    <p class="text-[6px] text-slate-400">全中</p><p class="text-sm font-black" id="count-6s-6">0</p>
                                    <div class="miss-badge" id="miss-6s-disp">0</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="space-y-8 mb-20">
                <div class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl border-4 border-slate-800">
                    <h3 class="text-center text-[10px] font-black uppercase tracking-[0.5em] mb-6 text-amber-400 italic">3-Star Matrix (Top 1-10 Seeds)</h3>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
                        {% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-slate-500">SET {{ i }}</p><div class="flex gap-1">{% for j in range(1, 4) %}<input type="text" id="3s-g{{i}}n{{j}}" class="w-full h-8 text-center text-sm font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}
                    </div>
                </div>
                <div class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl border-4 border-slate-800">
                    <h3 class="text-center text-[10px] font-black uppercase tracking-[0.5em] mb-6 text-indigo-400 italic">6-Star Matrix (Top 1-10 Seeds)</h3>
                    <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
                        {% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-indigo-300">SQUAD {{ i }}</p><div class="grid grid-cols-3 gap-1">{% for j in range(1, 7) %}<input type="text" id="6s-g{{i}}n{{j}}" class="w-full h-8 text-center text-[10px] font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-20">
                {% for squad in res_3star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black uppercase">G{{ squad.id }} (3S)<div class="flex justify-center gap-1 my-2">{% for p in squad.picks %}<span class="bg-slate-900 text-white px-1.5 rounded">{{ "%02d" | format(p.no) }}</span>{% endfor %}</div><button onclick='quickFill("3s", {{ squad.id }}, {{ squad.picks | map(attribute="no") | list | tojson }})' class="w-full bg-amber-50 text-amber-600 py-1 rounded">Load</button></div>{% endfor %}
                {% for squad in res_6star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black text-indigo-400 uppercase">S{{ squad.id }} (6S)<div class="grid grid-cols-3 gap-1 my-2">{% for p in squad.picks %}<span class="bg-slate-900 text-white rounded">{{ "%02d" | format(p.no) }}</span>{% endfor %}</div><button onclick='quickFill("6s", {{ squad.id }}, {{ squad.picks | map(attribute="no") | list | tojson }})' class="w-full bg-indigo-50 text-indigo-600 py-1 rounded">Load</button></div>{% endfor %}
            </div>

            <div class="mt-20 border-t-2 border-slate-200 pt-10 text-[11px] text-slate-500 leading-relaxed italic">
                <h2 class="text-2xl font-black text-slate-800 tracking-tighter uppercase mb-10">Technical Whitepaper V8.6</h2>
                <div class="formula-card p-12 rounded-[3.5rem] shadow-2xl text-white mb-12 text-center border border-white/10 relative">
                    <p class="text-[10px] font-bold text-indigo-300 uppercase tracking-[0.4em] mb-4">100-Period Cross-Day Convergent Model</p>
                    <div class="text-xl md:text-3xl font-serif italic mb-6">$$Score = \\left( \\text{基} + \\text{莊} + \\text{連} \\right) \\times W_p \\times W_s + \\text{扣}$$</div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-4">
                        <p>● <b>01. 基 (Base)</b>: 50期頻率分。● <b>02. 莊 (Streak)</b>: 連莊分。● <b>03. 連 (Exhaustion)</b>: $$ \\ge 3 $$期修正 **-15.0 分**。</p>
                        <p>● <b>04. 拖 (Synergy)</b>: **100期跨日共現矩陣**，三星/六星共用 Top 10 種子號。</p>
                    </div>
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-4">
                        <p>● <b>05/06. $$W_{p,s}$$</b>: 補償 (1.2倍)。● <b>07. 扣 (Heat)</b>: 15期過熱過濾 (-2.0)。</p>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const winNums = {{ latest_win | tojson }};
            const currentNo = "{{ latest_no }}";

            function saveAndCompare() {
                const data = { s3: {}, s6: {} };
                for(let i=1; i<=10; i++) {
                    data.s3[i] = [1,2,3].map(j => document.getElementById(`3s-g${i}n${j}`).value);
                    data.s6[i] = [1,2,3,4,5,6].map(j => document.getElementById(`6s-g${i}n${j}`).value);
                }
                localStorage.setItem('bingo_v86_matrix', JSON.stringify(data));
                executeComparison();
            }

            function loadMatrix() {
                const saved = localStorage.getItem('bingo_v86_matrix');
                if(saved) {
                    const d = JSON.parse(saved);
                    for(let i=1; i<=10; i++) {
                        if(d.s3[i]) d.s3[i].forEach((v, j) => document.getElementById(`3s-g${i}n${j+1}`).value = v);
                        if(d.s6[i]) d.s6[i].forEach((v, j) => document.getElementById(`6s-g${i}n${j+1}`).value = v);
                    }
                }
                executeComparison();
                handleMissCounter();
            }

            function handleMissCounter() {
                const lastNo = localStorage.getItem('miss_last_no_v86');
                if (lastNo && lastNo !== currentNo) {
                    let miss3 = parseInt(localStorage.getItem('miss_3s_v86') || '0');
                    let miss6 = parseInt(localStorage.getItem('miss_6s_v86') || '0');
                    const hit3s = parseInt(document.getElementById('count-3s-3').innerText);
                    const hit6s = parseInt(document.getElementById('count-6s-6').innerText);
                    if (hit3s === 0) miss3++; else miss3 = 0;
                    if (hit6s === 0) miss6++; else miss6 = 0;
                    localStorage.setItem('miss_3s_v86', miss3);
                    localStorage.setItem('miss_6s_v86', miss6);
                }
                localStorage.setItem('miss_last_no_v86', currentNo);
                document.getElementById('miss-3s-disp').innerText = localStorage.getItem('miss_3s_v86') || 0;
                document.getElementById('miss-6s-disp').innerText = localStorage.getItem('miss_6s_v86') || 0;
            }

            function quickFill(type, id, numbers) {
                numbers.forEach((n, j) => document.getElementById(`${type}-g${id}n${j+1}`).value = n.toString().padStart(2, '0'));
                saveAndCompare();
            }

            function executeComparison() {
                document.querySelectorAll('.latest-ball').forEach(el => { for(let i=1; i<=10; i++) el.classList.remove(`hit-g${i}`); });
                let stats = { s3_2: 0, s3_3: 0, s6_3: 0, s6_4: 0, s6_5: 0, s6_6: 0 };
                for(let i=1; i<=10; i++) {
                    const sq3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h3 = 0; sq3.forEach(n => { if(winNums.includes(n)) { h3++; document.querySelector(`.ball-3s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } });
                    if(h3 === 2) stats.s3_2++; else if(h3 === 3 && sq3.length === 3) stats.s3_3++;
                    
                    const sq6 = [1,2,3,4,5,6].map(j => Number(document.getElementById(`6s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h6 = 0; sq6.forEach(n => { if(winNums.includes(n)) { h6++; document.querySelector(`.ball-6s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } });
                    if(h6 === 3) stats.s6_3++; else if(h6 === 4) stats.s6_4++; else if(h6 === 5) stats.s6_5++; else if(h6 === 6 && sq6.length === 6) stats.s6_6++;
                }
                document.getElementById('count-3s-2').innerText = stats.s3_2;
                document.getElementById('count-3s-3').innerText = stats.s3_3;
                document.getElementById('count-6s-3').innerText = stats.s6_3;
                document.getElementById('count-6s-4').innerText = stats.s6_4;
                document.getElementById('count-6s-5').innerText = stats.s6_5;
                document.getElementById('count-6s-6').innerText = stats.s6_6;
                if(stats.s3_3 > 0) document.getElementById('alert-3s-all').classList.add('alert-gold'); else document.getElementById('alert-3s-all').classList.remove('alert-gold');
                if(stats.s6_5 > 0) document.getElementById('alert-6s-5').classList.add('alert-gold'); else document.getElementById('alert-6s-5').classList.remove('alert-gold');
                if(stats.s6_6 > 0) document.getElementById('alert-6s-6').classList.add('alert-gold'); else document.getElementById('alert-6s-6').classList.remove('alert-gold');
            }
            window.onload = loadMatrix;
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(res_3star=res_3star, res_6star=res_6star, p_day=p_day, s_day=s_day, p_20=p_20, s_20=s_20, status=status, latest_win=latest_win, latest_no=latest_no, active_date=active_date)

    
if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)







