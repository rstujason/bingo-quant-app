from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 (穩定 V8.9 核心) ---

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
    
    co_occ = Counter()
    for d in all_draws[:100]: 
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1

    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20
    status = {'odd': o_20 <= 160, 'even': e_20 <= 160, 'small': s_20 <= 160, 'big': b_20 <= 160}

    short_heat = Counter([n for d in all_draws[:15] for n in d])
    long_freq = Counter([n for d in all_draws[:50] for n in d])
    
    all_analysis = []
    for i in range(1, 81):
        streak = 0
        for d in all_draws:
            if i in d: streak += 1
            else: break
        l_penalty = -15.0 if streak >= 3 else 0.0
        cur_wp = 1.2 if (i%2!=0 and status['odd']) or (i%2==0 and status['even']) else 1.0
        cur_ws = 1.2 if (i<=40 and status['small']) or (i>40 and status['big']) else 1.0
        final_score = (long_freq[i] + (5.0 if streak==1 else 2.0 if streak==2 else 0) + l_penalty) * cur_wp * cur_ws - (short_heat[i]*2.0)
        all_analysis.append({'no': i, 'score': round(final_score, 1)})

    def get_synergy(n1, n2): return co_occ.get(tuple(sorted((n1, n2))), 0)

    def generate_squads(pool, size, count):
        squads = []
        sorted_seeds = sorted(pool, key=lambda x: x['score'], reverse=True)[:count]
        for i, seed in enumerate(sorted_seeds):
            partners = sorted([p for p in pool if p['no'] != seed['no']], key=lambda x: (get_synergy(seed['no'], x['no']), x['score']), reverse=True)[:size-1]
            squads.append({"id": i+1, "picks": [n['no'] for n in sorted([seed] + partners, key=lambda x:x['no'])]})
        return squads

    res_3star = generate_squads(all_analysis, 3, 10)
    res_6star = generate_squads(all_analysis, 6, 10)

    today_draws = [ [int(x) for x in item.get('BigShowOrder','').split(',') if x.strip().isdigit()] for item in data_today if item.get('BigShowOrder','') ]
    today_balls = [n for d in today_draws if len(d)==20 for n in d]
    p_day = f"{len([n for n in today_balls if n%2!=0])}:{len(today_balls)-len([n for n in today_balls if n%2!=0])}"
    s_day = f"{len([n for n in today_balls if n<=40])}:{len(today_balls)-len([n for n in today_balls if n<=40])}"

    return (res_3star, res_6star, p_day, s_day, f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, target_date)

# --- 2. 網頁前端 (新增 Load All 功能) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    (res_3star, res_6star, p_day, s_day, p_20, s_20, status, latest_win, latest_no, active_date) = get_data_and_analyze(date)
    
    html_content = """
    <html>
    <head>
        <title>量化矩陣 V9.0 一鍵裝載版</title>
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
            .stat-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); padding: 6px; border-radius: 12px; text-align: center; position: relative; }
            .miss-badge { position: absolute; top: -5px; right: -5px; background: #ef4444; color: white; font-size: 8px; font-weight: 900; padding: 1px 4px; border-radius: 4px; }
            .profit-input { background: #1e293b; border: 1px solid #334155; color: #f1f5f9; text-align: center; border-radius: 8px; font-weight: bold; width: 100%; height: 32px; }

            .dist-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 4px; background: #fefce8; padding: 12px; border-radius: 16px; border: 2px solid #fde047; }
            .dist-ball { background: #ffffff; color: #64748b; font-weight: bold; font-size: 10px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 8px; border: 1px solid #e2e8f0; transition: all 0.3s; }
            .active-3s { background: #f59e0b !important; color: white !important; box-shadow: 0 0 10px #f59e0b; border-color: #f59e0b; }
            .active-6s { background: #6366f1 !important; color: white !important; box-shadow: 0 0 10px #6366f1; border-color: #6366f1; }
            
            .control-btn { color: white; padding: 2px 10px; border-radius: 6px; font-size: 8px; font-weight: 900; text-transform: uppercase; transition: all 0.2s; }
            .btn-clear { background: #991b1b; }
            .btn-load { background: #065f46; }
            .control-btn:hover { opacity: 0.8; transform: scale(1.05); }
        </style>
    </head>
    <body class="bg-slate-50 font-sans text-slate-900 pb-20 text-[12px]">
        <div class="max-w-6xl mx-auto p-4 md:p-8">
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-indigo-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase italic">Parity Monitor</span>{% if status.odd or status.even %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg font-black italic">奇 {{ p_day }} 偶</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline">近 20 期觸發</p><p class="text-xl font-black text-amber-300">{{ p_20 }}</p></div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase italic">Size Monitor</span>{% if status.small or status.big %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg font-black tracking-tighter">小 {{ s_day }} 大</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline">近 20 期觸發</p><p class="text-xl font-black text-amber-300">{{ s_20 }}</p></div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-10">
                <div class="lg:col-span-3 bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <div class="flex justify-between items-center mb-6 border-b pb-4 text-slate-400 italic">
                        <h3 class="text-xs font-black uppercase">📢 Latest Draw: <span class="text-indigo-600">{{ latest_no }}</span></h3>
                        <button onclick="location.reload()" class="bg-indigo-500 text-white px-4 py-1.5 rounded-xl text-[10px] font-black shadow-lg">Refresh</button>
                    </div>
                    <div class="space-y-6">
                        <div><p class="text-[9px] font-black text-amber-500 mb-2 uppercase">3-Star Tracking</p>
                            <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-3s" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                        </div>
                        <div><p class="text-[9px] font-black text-indigo-500 mb-2 uppercase">6-Star Tracking</p>
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
                                <div class="stat-card" id="alert-3s-all"><p class="text-[6px] text-slate-400">全中</p><p class="text-lg font-black text-amber-400" id="count-3s-3">0</p><div class="miss-badge" id="miss-3s-disp">0</div></div>
                            </div>
                        </div>
                        <div class="bg-slate-800/50 p-3 rounded-2xl border border-slate-700">
                            <p class="text-[7px] font-black text-indigo-400 mb-2 uppercase">6-Star Stats</p>
                            <div class="grid grid-cols-2 gap-2">
                                <div class="stat-card"><p class="text-[6px] text-slate-400">中 3</p><p class="text-sm font-black" id="count-6s-3">0</p></div>
                                <div class="stat-card"><p class="text-[6px] text-slate-400">中 4</p><p class="text-sm font-black" id="count-6s-4">0</p></div>
                                <div class="stat-card" id="alert-6s-5"><p class="text-[6px] text-slate-400">中 5</p><p class="text-sm font-black text-amber-300" id="count-6s-5">0</p></div>
                                <div class="stat-card" id="alert-6s-6"><p class="text-[6px] text-slate-400">全中</p><p class="text-sm font-black text-amber-400" id="count-6s-6">0</p><div class="miss-badge" id="miss-6s-disp">0</div></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-slate-900 p-8 rounded-[3rem] shadow-2xl border-4 border-slate-800 text-white mb-10">
                <div class="flex justify-between items-center mb-8 border-b border-slate-700 pb-4">
                    <h3 class="text-[11px] font-black uppercase tracking-[0.5em] text-emerald-400 italic">Profit Analysis Terminal</h3>
                    <div class="flex gap-4">
                        <div class="text-right"><p class="text-[8px] text-slate-400 uppercase">Investment</p><p class="text-lg font-mono font-black" id="display-total-cost">$ 0</p></div>
                        <div class="text-right border-l border-slate-700 pl-4"><p class="text-[8px] text-slate-400 uppercase">Net Profit</p><p class="text-lg font-mono font-black text-emerald-400" id="display-net-profit">$ 0</p></div>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                    <div class="bg-slate-800/50 p-4 rounded-2xl">
                        <p class="text-[9px] font-black text-slate-400 uppercase italic mb-2">Investment</p>
                        <input type="number" id="in-sets" class="profit-input" oninput="calculateProfit()" placeholder="購買組數">
                    </div>
                    <div class="bg-slate-800/50 p-4 rounded-2xl">
                        <p class="text-[9px] font-black text-amber-500 uppercase italic mb-2">3-Star Prize</p>
                        <div class="grid grid-cols-2 gap-2">
                            <input type="number" id="in-3h2" class="profit-input" oninput="calculateProfit()" placeholder="三中二">
                            <input type="number" id="in-3h3" class="profit-input" oninput="calculateProfit()" placeholder="三中三">
                        </div>
                    </div>
                    <div class="bg-slate-800/50 p-4 rounded-2xl">
                        <p class="text-[9px] font-black text-indigo-400 uppercase italic mb-2">6-Star Prize</p>
                        <div class="grid grid-cols-2 gap-2">
                            <input type="number" id="in-6h3" class="profit-input" oninput="calculateProfit()" placeholder="中3">
                            <input type="number" id="in-6h4" class="profit-input" oninput="calculateProfit()" placeholder="中4">
                            <input type="number" id="in-6h5" class="profit-input" oninput="calculateProfit()" placeholder="中5">
                            <input type="number" id="in-6h6" class="profit-input" oninput="calculateProfit()" placeholder="全中">
                        </div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10">
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100">
                    <h3 class="text-[10px] font-black text-amber-600 uppercase tracking-widest mb-4 italic">📡 3-Star Matrix Distribution</h3>
                    <div class="dist-grid" id="grid-3s">{% for i in range(1, 81) %}<div class="dist-ball" id="dist3s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div>
                </div>
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100">
                    <h3 class="text-[10px] font-black text-indigo-600 uppercase tracking-widest mb-4 italic">📡 6-Star Matrix Distribution</h3>
                    <div class="dist-grid" id="grid-6s">{% for i in range(1, 81) %}<div class="dist-ball" id="dist6s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div>
                </div>
            </div>

            <div class="space-y-8 mb-20">
                <div class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl border-4 border-slate-800">
                    <div class="flex justify-between items-center mb-6 px-2">
                        <h3 class="text-[10px] font-black uppercase tracking-[0.5em] text-amber-400 italic">3-Star Matrix (Top 10)</h3>
                        <div class="flex gap-2">
                            <button onclick="loadAllStrategies('3s')" class="control-btn btn-load">Load All 3S</button>
                            <button onclick="clearMatrix('3s')" class="control-btn btn-clear">Clear All 3S</button>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
                        {% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-slate-500">SET {{ i }}</p><div class="flex gap-1">{% for j in range(1, 4) %}<input type="text" id="3s-g{{i}}n{{j}}" class="w-full h-8 text-center text-sm font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}
                    </div>
                </div>
                <div class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl border-4 border-slate-800">
                    <div class="flex justify-between items-center mb-6 px-2">
                        <h3 class="text-[10px] font-black uppercase tracking-[0.5em] text-indigo-400 italic">6-Star Matrix (Top 10)</h3>
                        <div class="flex gap-2">
                            <button onclick="loadAllStrategies('6s')" class="control-btn btn-load">Load All 6S</button>
                            <button onclick="clearMatrix('6s')" class="control-btn btn-clear">Clear All 6S</button>
                        </div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
                        {% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-indigo-300">SQUAD {{ i }}</p><div class="grid grid-cols-3 gap-1">{% for j in range(1, 7) %}<input type="text" id="6s-g{{i}}n{{j}}" class="w-full h-8 text-center text-[10px] font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-20">
                {% for sq in res_3star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black uppercase">G{{ sq.id }} (3S)<div class="flex justify-center gap-1 my-2">{% for n in sq.picks %}<span class="bg-slate-900 text-white px-1.5 rounded">{{ "%02d" | format(n) }}</span>{% endfor %}</div><button onclick='quickFill("3s", {{ sq.id }}, {{ sq.picks | tojson }})' class="w-full bg-amber-50 text-amber-600 py-1 rounded">Load</button></div>{% endfor %}
                {% for sq in res_6star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black text-indigo-400 uppercase">S{{ sq.id }} (6S)<div class="grid grid-cols-3 gap-1 my-2">{% for n in sq.picks %}<span class="bg-slate-900 text-white rounded">{{ "%02d" | format(n) }}</span>{% endfor %}</div><button onclick='quickFill("6s", {{ sq.id }}, {{ sq.picks | tojson }})' class="w-full bg-indigo-50 text-indigo-600 py-1 rounded">Load</button></div>{% endfor %}
            </div>
        </div>

        <script>
            const winNums = {{ latest_win | tojson }};
            const currentNo = "{{ latest_no }}";
            const server3S = {{ res_3star | tojson }};
            const server6S = {{ res_6star | tojson }};

            // --- 🚀 V9.0 全自動裝載邏輯 ---
            function loadAllStrategies(type) {
                const data = type === '3s' ? server3S : server6S;
                const size = type === '3s' ? 3 : 6;
                data.forEach(sq => {
                    sq.picks.forEach((n, idx) => {
                        const inputId = `${type}-g${sq.id}n${idx+1}`;
                        const el = document.getElementById(inputId);
                        if(el) el.value = n.toString().padStart(2, '0');
                    });
                });
                saveAndCompare();
            }

            function clearMatrix(type) {
                const size = (type === '3s') ? 3 : 6;
                for(let i=1; i<=10; i++) {
                    for(let j=1; j<=size; j++) document.getElementById(`${type}-g${i}n${j}`).value = "";
                }
                saveAndCompare();
            }

            function calculateProfit() {
                const sets = parseInt(document.getElementById('in-sets').value) || 0;
                const cost = sets * 25;
                const prizes = {
                    s3h2: (parseInt(document.getElementById('in-3h2').value) || 0) * 50,
                    s3h3: (parseInt(document.getElementById('in-3h3').value) || 0) * 1000,
                    s6h3: (parseInt(document.getElementById('in-6h3').value) || 0) * 25,
                    s6h4: (parseInt(document.getElementById('in-6h4').value) || 0) * 200,
                    s6h5: (parseInt(document.getElementById('in-6h5').value) || 0) * 1200,
                    s6h6: (parseInt(document.getElementById('in-6h6').value) || 0) * 50000
                };
                const totalPrize = Object.values(prizes).reduce((a, b) => a + b, 0);
                const netProfit = totalPrize - cost;
                document.getElementById('display-total-cost').innerText = "$ " + cost;
                const netDisp = document.getElementById('display-net-profit');
                netDisp.innerText = "$ " + netProfit;
                netDisp.className = netProfit >= 0 ? "text-lg font-mono font-black text-emerald-400" : "text-lg font-mono font-black text-rose-500";
                const profitData = { sets, s3h2: document.getElementById('in-3h2').value, s3h3: document.getElementById('in-3h3').value, s6h3: document.getElementById('in-6h3').value, s6h4: document.getElementById('in-6h4').value, s6h5: document.getElementById('in-6h5').value, s6h6: document.getElementById('in-6h6').value };
                localStorage.setItem('bingo_profit_v90', JSON.stringify(profitData));
            }

            function saveAndCompare() {
                const data = { s3: {}, s6: {} };
                for(let i=1; i<=10; i++) {
                    data.s3[i] = [1,2,3].map(j => document.getElementById(`3s-g${i}n${j}`).value);
                    data.s6[i] = [1,2,3,4,5,6].map(j => document.getElementById(`6s-g${i}n${j}`).value);
                }
                localStorage.setItem('bingo_v90_matrix', JSON.stringify(data));
                executeComparison();
            }

            function loadMatrix() {
                const saved = localStorage.getItem('bingo_v90_matrix');
                if(saved) {
                    const d = JSON.parse(saved);
                    for(let i=1; i<=10; i++) {
                        if(d.s3[i]) d.s3[i].forEach((v, j) => document.getElementById(`3s-g${i}n${j+1}`).value = v);
                        if(d.s6[i]) d.s6[i].forEach((v, j) => document.getElementById(`6s-g${i}n${j+1}`).value = v);
                    }
                }
                const savedProfit = localStorage.getItem('bingo_profit_v90');
                if(savedProfit) {
                    const d = JSON.parse(savedProfit);
                    document.getElementById('in-sets').value = d.sets || "";
                    ['3h2', '3h3', '6h3', '6h4', '6h5', '6h6'].forEach(k => { if(document.getElementById('in-'+k)) document.getElementById('in-'+k).value = d['s'+k] || ""; });
                    calculateProfit();
                }
                executeComparison();
                handleMissCounter();
            }

            function handleMissCounter() {
                const lastNo = localStorage.getItem('miss_last_no_v90');
                if (lastNo && lastNo !== currentNo) {
                    let miss3 = parseInt(localStorage.getItem('miss_3s_v90') || '0');
                    let miss6 = parseInt(localStorage.getItem('miss_6s_v90') || '0');
                    const hit3s = parseInt(document.getElementById('count-3s-3').innerText);
                    const hit6s = parseInt(document.getElementById('count-6s-6').innerText);
                    miss3 = hit3s === 0 ? miss3 + 1 : 0; miss6 = hit6s === 0 ? miss6 + 1 : 0;
                    localStorage.setItem('miss_3s_v90', miss3); localStorage.setItem('miss_6s_v90', miss6);
                }
                localStorage.setItem('miss_last_no_v90', currentNo);
                document.getElementById('miss-3s-disp').innerText = localStorage.getItem('miss_3s_v90') || 0;
                document.getElementById('miss-6s-disp').innerText = localStorage.getItem('miss_6s_v90') || 0;
            }

            function quickFill(type, id, numbers) {
                numbers.forEach((n, j) => document.getElementById(`${type}-g${id}n${j+1}`).value = n.toString().padStart(2, '0'));
                saveAndCompare();
            }

            function executeComparison() {
                document.querySelectorAll('.latest-ball').forEach(el => { for(let i=1; i<=10; i++) el.classList.remove(`hit-g${i}`); });
                document.querySelectorAll('.dist-ball').forEach(el => el.classList.remove('active-3s', 'active-6s'));
                let stats = { s3_2: 0, s3_3: 0, s6_3: 0, s6_4: 0, s6_5: 0, s6_6: 0 };
                let used3s = new Set(); let used6s = new Set();
                for(let i=1; i<=10; i++) {
                    const sq3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h3 = 0; sq3.forEach(n => { if(winNums.includes(n)) { h3++; document.querySelector(`.ball-3s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } used3s.add(n); });
                    if(h3 === 2) stats.s3_2++; else if(h3 === 3 && sq3.length === 3) stats.s3_3++;
                    const sq6 = [1,2,3,4,5,6].map(j => Number(document.getElementById(`6s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h6 = 0; sq6.forEach(n => { if(winNums.includes(n)) { h6++; document.querySelector(`.ball-6s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } used6s.add(n); });
                    if(h6 === 3) stats.s6_3++; else if(h6 === 4) stats.s6_4++; else if(h6 === 5) stats.s6_5++; else if(h6 === 6 && sq6.length === 6) stats.s6_6++;
                }
                used3s.forEach(n => { if(n >= 1 && n <= 80) document.getElementById('dist3s-'+n)?.classList.add('active-3s'); });
                used6s.forEach(n => { if(n >= 1 && n <= 80) document.getElementById('dist6s-'+n)?.classList.add('active-6s'); });
                document.getElementById('count-3s-2').innerText = stats.s3_2; document.getElementById('count-3s-3').innerText = stats.s3_3;
                document.getElementById('count-6s-3').innerText = stats.s6_3; document.getElementById('count-6s-4').innerText = stats.s6_4;
                document.getElementById('count-6s-5').innerText = stats.s6_5; document.getElementById('count-6s-6').innerText = stats.s6_6;
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








