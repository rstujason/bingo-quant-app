from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 (V7.4 三星小隊與全參數) ---

def get_data_and_analyze(target_date=None):
    now = datetime.datetime.now()
    if not target_date: target_date = now.strftime("%Y-%m-%d")
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://winwin.tw/Bingo'}

    def fetch_api(date_str):
        url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            return resp.json() if resp.status_code == 200 else None
        except: return None

    api_data = fetch_api(target_date)
    if not api_data and target_date == now.strftime("%Y-%m-%d"):
        target_date = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        api_data = fetch_api(target_date)

    if not api_data:
        return [], "0:0", "0:0", "0:0", "0:0", {}, [], "N/A", target_date, [], []

    all_draws = []
    for item in api_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: all_draws.append(nums)
    
    latest_no = api_data[0].get('No', 'N/A')
    latest_win_nums = all_draws[0] if all_draws else []
    
    co_occ = Counter()
    for d in all_draws[:100]:
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1

    all_balls = [n for d in all_draws for n in d]
    o_day = len([n for n in all_balls if n % 2 != 0]); e_day = len(all_balls) - o_day
    s_day = len([n for n in all_balls if n <= 40]); b_day = len(all_balls) - s_day
    
    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20

    THRESHOLD = 160 #
    status = {'odd': o_20 <= THRESHOLD, 'even': e_20 <= THRESHOLD, 'small': s_20 <= THRESHOLD, 'big': b_20 <= THRESHOLD}

    wp_odd = 1.2 if status['odd'] else 1.0; wp_even = 1.2 if status['even'] else 1.0
    ws_small = 1.2 if status['small'] else 1.0; ws_big = 1.2 if status['big'] else 1.0

    short_heat = Counter([n for d in all_draws[:15] for n in d]) # 扣
    long_freq = Counter([n for d in all_draws[:50] for n in d])  # 基
    
    all_analysis = []
    for i in range(1, 81):
        f_score = long_freq[i] * 1.0 # 基
        streak = 0
        for d in all_draws:
            if i in d: streak += 1
            else: break
        r_score = 5.0 if streak == 1 else 2.0 if streak == 2 else 0.0 # 莊
        l_penalty = -15.0 if streak >= 3 else 0.0 # 連
        
        cur_wp = wp_odd if i % 2 != 0 else wp_even
        cur_ws = ws_small if i <= 40 else ws_big
        h_penalty = -(short_heat[i] * 2.0) # 扣
        
        final_score = (f_score + r_score + l_penalty) * cur_wp * cur_ws + h_penalty
        
        omission = next((idx for idx, d in enumerate(all_draws) if i in d), 99)
        all_analysis.append({'no': i, 'score': round(final_score, 1), 'omission': omission, 'section': (i-1)//20,
                             'details': {'基': f_score, '莊': r_score, '連': l_penalty, '權': f"x{cur_wp*cur_ws:.2f}", '扣': h_penalty}})

    top_hot = sorted(all_analysis, key=lambda x: x['score'], reverse=True)[:10]
    top_cold = sorted(all_analysis, key=lambda x: x['omission'], reverse=True)[:10]

    def get_synergy(n1, n2): return co_occ.get(tuple(sorted((n1, n2))), 0)
    used = set()
    sorted_score = sorted(all_analysis, key=lambda x: x['score'], reverse=True)
    sorted_omission = sorted(all_analysis, key=lambda x: x['omission'], reverse=True)

    g1 = []
    seed_h = next(p for p in sorted_score if p['no'] not in used)
    item_sh = seed_h.copy(); item_sh['tag'] = "熱門種子"; item_sh['star'] = True; g1.append(item_sh); used.add(seed_h['no'])
    partner_h = sorted([p for p in all_analysis if p['no'] not in used], key=lambda x: get_synergy(seed_h['no'], x['no']), reverse=True)[0]
    item_ph = partner_h.copy(); item_ph['tag'] = "最強協同"; item_ph['star'] = True; g1.append(item_ph); used.add(partner_h['no'])
    seed_c = next(p for p in sorted_omission if p['no'] not in used)
    item_sc = seed_c.copy(); item_sc['tag'] = "冷門種子"; item_sc['star'] = True; g1.append(item_sc); used.add(seed_c['no'])

    g2 = []
    seed_h2 = next(p for p in sorted_score if p['no'] not in used)
    item_sh2 = seed_h2.copy(); item_sh2['tag'] = "熱門種子"; item_sh2['star'] = True; g2.append(item_sh2); used.add(seed_h2['no'])
    cold_partners = sorted([p for p in all_analysis if p['no'] not in used], key=lambda x: (get_synergy(seed_h2['no'], x['no']), x['omission']), reverse=True)[:2]
    for p in cold_partners:
        item_cp = p.copy(); item_cp['tag'] = "默契冷門"; item_cp['star'] = True; g2.append(item_cp); used.add(p['no'])

    g3 = [dict(p, tag="熱門", star=False) for p in sorted(all_analysis, key=lambda x: x['score'], reverse=True)[:6]]

    results = [
        {"id":"G1", "name":"第一組 (均衡三星核心)", "picks":sorted(g1, key=lambda x:x['no']), "clr":"border-amber-400", "desc":"1熱+1友+1冷"},
        {"id":"G2", "name":"第二組 (熱點三星冷友)", "picks":sorted(g2, key=lambda x:x['no']), "clr":"border-emerald-400", "desc":"1熱+2冷友"},
        {"id":"G3", "name":"第三組 (6星共振核心)", "picks":sorted(g3, key=lambda x:x['no']), "size":6, "clr":"border-slate-800", "desc":"純高分推薦"}
    ]
    return (results, f"{o_day}:{e_day}", f"{s_day}:{b_day}", f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, target_date, top_hot, top_cold)

# --- 2. 網頁前端 (深色標籤與白皮書補完) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    (results, p_day, s_day, p_20, s_20, status, latest_win, latest_no, active_date, top_hot, top_cold) = get_data_and_analyze(date)
    
    html_content = """
    <html>
    <head>
        <title>量化終端 V7.4</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            .hit-highlight { color: white !important; background-color: #ef4444 !important; font-weight: bold; border-radius: 50%; box-shadow: 0 0 15px rgba(239, 68, 68, 0.7); transform: scale(1.1); }
            .prev-hit { background-color: #6366f1 !important; color: white !important; border-radius: 4px; padding: 0 4px; }
            .latest-ball { background: #f1f5f9; color: #475569; font-weight: bold; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 11px; border: 1px solid #e2e8f0; }
            .star-box { border: 3px solid #fbbf24 !important; box-shadow: inset 0 0 10px rgba(251, 191, 36, 0.4); background-color: #fffbeb !important; }
            
            /* --- 🎨 深色標籤顏色重製 (對齊 User 要求) --- */
            .tag-hot { background: #991b1b; color: #ffffff; border: 1px solid #7f1d1d; } /* 深紅 */
            .tag-cold { background: #1e3a8a; color: #ffffff; border: 1px solid #172554; } /* 深藍 */
            .tag-synergy { background: #92400e; color: #ffffff; border: 1px solid #78350f; } /* 深金/最強協同 */
            
            .formula-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
            .status-monitor { display: flex; align-items: center; gap: 6px; font-size: 9px; font-weight: 900; padding: 2px 8px; border-radius: 99px; }
            .status-active { background: #22c55e; color: white; animation: pulse 2s infinite; }
            .status-idle { background: rgba(255,255,255,0.15); color: rgba(255,255,255,0.7); }
            @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        </style>
    </head>
    <body class="bg-slate-50 font-sans text-slate-900 pb-20">
        <div class="max-w-4xl mx-auto p-4 md:p-8">
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-indigo-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <div class="flex justify-between items-center mb-4">
                        <span class="text-[10px] font-black uppercase tracking-widest italic opacity-80">Parity Monitor</span>
                        {% if status.odd or status.even %}<div class="status-monitor status-active">✅ 補償激活</div>
                        {% else %}<div class="status-monitor status-idle">⚪ 監控中</div>{% endif %}
                    </div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center">
                        <div><p class="text-[8px] opacity-60 mb-1 uppercase">Today stats</p><p class="text-lg font-black italic tracking-tighter">奇 {{ p_day }} 偶</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold mb-1 uppercase underline underline-offset-4">Recent 20 Draws</p><p class="text-xl font-black text-amber-300 tracking-tighter">{{ p_20 }}</p></div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4">
                        <span class="text-[10px] font-black uppercase tracking-widest italic opacity-80">Size Monitor</span>
                        {% if status.small or status.big %}<div class="status-monitor status-active">✅ 補償激活</div>
                        {% else %}<div class="status-monitor status-idle">⚪ 監控中</div>{% endif %}
                    </div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center">
                        <div><p class="text-[8px] opacity-60 mb-1 uppercase">Today stats</p><p class="text-lg font-black italic tracking-tighter">小 {{ s_day }} 大</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold mb-1 uppercase underline underline-offset-4">Recent 20 Draws</p><p class="text-xl font-black text-amber-300 tracking-tighter">{{ s_20 }}</p></div>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 mb-6">
                <div class="flex justify-between items-center mb-6 px-2">
                    <h3 class="text-[10px] font-black text-slate-400 uppercase tracking-widest italic">📢 Latest Draw: <span class="text-indigo-600 font-mono">{{ latest_no }}</span></h3>
                    <button onclick="location.reload()" class="bg-indigo-500 hover:bg-indigo-600 text-white px-5 py-2 rounded-xl text-[10px] font-black shadow-lg active:scale-95">Refresh</button>
                </div>
                <div class="flex flex-wrap gap-2.5 justify-center">
                    {% for n in latest_win %}<div class="latest-ball" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}
                </div>
            </div>

            <div id="prevSection" class="hidden bg-slate-100 p-4 rounded-2xl mb-6 border-l-8 border-slate-400">
                <div class="flex justify-between items-center mb-2">
                    <h4 class="text-[10px] font-black text-slate-500 uppercase italic">🕰️ Previous Prediction Review (<span id="prevNoDisplay">--</span>)</h4>
                    <button onclick="clearHistory()" class="text-[8px] text-slate-400 hover:underline">Clear History</button>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-white p-2 rounded-xl text-[10px] font-bold text-slate-600 italic">G1 Core: <span id="prevG1List" class="font-mono">--</span></div>
                    <div class="bg-white p-2 rounded-xl text-[10px] font-bold text-slate-600 italic">G2 Core: <span id="prevG2List" class="font-mono">--</span></div>
                </div>
            </div>

            <div id="compBox" class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl text-white mb-10 text-center border-4 border-slate-800">
                <div class="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
                    {% for i in range(1, 7) %}<input type="text" id="myNum{{i}}" maxlength="2" class="h-14 text-center text-2xl font-black text-white bg-slate-800 rounded-2xl border-2 border-slate-700 outline-none focus:border-indigo-400" placeholder="--" oninput="saveInputs()">{% endfor %}
                </div>
                <button onclick="startComparison()" class="w-full bg-indigo-500 text-white font-black py-4 rounded-xl text-sm uppercase tracking-widest shadow-xl italic">Execute Quantitative Analysis</button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
                {% for group in results %}
                <div class="bg-white p-5 rounded-3xl shadow-sm border-4 {{ group.clr }} flex flex-col">
                    <div class="flex justify-between items-start mb-2">
                        <div><h2 class="text-[10px] font-black text-slate-800 uppercase italic">{{ group.name }}</h2><p class="text-[8px] text-slate-400 font-bold">{{ group.desc }}</p></div>
                        <button onclick="toggleDetail('{{ group.id }}')" class="text-[8px] bg-slate-100 px-2 py-1 rounded font-bold uppercase tracking-widest">Detail</button>
                    </div>
                    <div class="grid {{ 'grid-cols-3' if group.id == 'G3' else 'grid-cols-1' }} gap-3 mb-4">
                        {% for p in group.picks %}
                        <div class="bg-slate-50 pt-6 pb-4 rounded-2xl text-center relative overflow-hidden num-card {% if p.star %}star-box{% endif %}" data-val="{{ p.no }}">
                            <span class="absolute top-0 left-0 w-full text-[7px] font-black py-0.5 {% if '熱門' in p.tag %}tag-hot{% elif '冷門' in p.tag %}tag-cold{% else %}tag-synergy{% endif %}">{{ p.tag }}</span>
                            <p class="text-3xl font-black text-slate-800 font-mono">{{ "%02d" | format(p.no) }}</p>
                        </div>
                        {% endfor %}
                    </div>
                    <button onclick='quickFill({{ group.picks | map(attribute="no") | list | tojson }})' class="mt-auto w-full bg-slate-900 text-white py-3 rounded-xl text-[10px] font-black tracking-widest transition-all">🚀 Load Squad into Comp</button>
                </div>
                {% endfor %}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-20">
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100">
                    <h3 class="text-xs font-black text-rose-800 uppercase tracking-widest mb-6 italic border-l-4 border-rose-800 pl-2">🔥 Hot List Top 10 (Quant Score)</h3>
                    <div class="space-y-3">
                        {% for p in top_hot %}
                        <div class="flex items-center gap-3">
                            <span class="text-[10px] font-black text-slate-400 w-4">#{{ loop.index }}</span>
                            <span class="bg-slate-900 text-white text-[11px] font-mono px-2 py-1 rounded-lg w-8 text-center">{{ "%02d" | format(p.no) }}</span>
                            <div class="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                <div class="h-full bg-rose-700" style="width: {{ (p.score / top_hot[0].score) * 100 }}%"></div>
                            </div>
                            <span class="text-[9px] font-bold text-slate-500 w-8">{{ p.score }}</span>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100">
                    <h3 class="text-xs font-black text-blue-800 uppercase tracking-widest mb-6 italic border-l-4 border-blue-800 pl-2">❄️ Cold List Top 10 (Omission)</h3>
                    <div class="space-y-3">
                        {% for p in top_cold %}
                        <div class="flex items-center gap-3">
                            <span class="text-[10px] font-black text-slate-400 w-4">#{{ loop.index }}</span>
                            <span class="bg-slate-900 text-white text-[11px] font-mono px-2 py-1 rounded-lg w-8 text-center">{{ "%02d" | format(p.no) }}</span>
                            <div class="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                <div class="h-full bg-blue-900" style="width: {{ (p.omission / top_cold[0].omission) * 100 }}%"></div>
                            </div>
                            <span class="text-[9px] font-bold text-slate-500 w-8">{{ p.omission }}</span>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <div class="mt-20 border-t-2 border-slate-200 pt-10">
                <div class="flex items-center space-x-3 mb-10"><div class="w-3 h-8 bg-indigo-600 rounded-full"></div><h2 class="text-2xl font-black text-slate-800 tracking-tighter italic uppercase">Technical Whitepaper V7.4</h2></div>
                <div class="formula-card p-12 rounded-[3.5rem] shadow-2xl text-white mb-12 text-center border border-white/10 relative overflow-hidden">
                    <p class="text-[10px] font-bold text-indigo-300 uppercase tracking-[0.4em] mb-6 underline underline-offset-8 italic">Squad Synergistic Scoring Model</p>
                    <div class="text-xl md:text-3xl font-serif italic mb-6">
                        $$Score = \\left( \\text{基} + \\text{莊} + \\text{連} \\right) \\times W_p \\times W_s + \\text{扣}$$
                    </div>
                    <div class="bg-white/5 p-4 rounded-2xl inline-block text-[11px] font-mono italic">拖 (Internal Synergy) = 100-period Co-occurrence Weighting (0.3)</div>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 text-sm">
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-6 hover:shadow-lg transition-all">
                        <div class="border-b pb-4"><h3 class="font-black text-indigo-700 mb-2 italic uppercase">01. 基 (Base Momentum)</h3><p class="text-[11px] text-slate-500 leading-relaxed">過去 50 期長期出現頻率，代表號碼的核心慣性動能與基礎得分值。</p></div>
                        <div class="border-b pb-4"><h3 class="font-black text-emerald-700 mb-2 italic uppercase">02. 莊 (Streak Bonus)</h3><p class="text-[11px] text-slate-500 leading-relaxed">連 1 期 **+5.0**，連 2 期 **+2.0**。捕捉號碼剛開出時的短期爆發熱度。</p></div>
                        <div class="border-b pb-4"><h3 class="font-black text-rose-700 mb-2 italic uppercase">03. 連 (Exhaustion Penalty)</h3><p class="text-[11px] text-slate-500 leading-relaxed">機率避讓核心。若號碼連續產出 $$ \\ge 3 $$ 期，判定為能量枯竭，強制扣除 **15.0 分**。</p></div>
                        <div><h3 class="font-black text-amber-700 mb-2 italic uppercase">04. 拖 (Internal Synergy)</h3><p class="text-[11px] text-slate-500 leading-relaxed">建立 100 期共現矩陣。系統選定種子號後，計算其與組員之引力引數 **0.3** 進行協同加分。</p></div>
                    </div>
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-6 hover:shadow-lg transition-all">
                        <div class="border-b pb-4"><h3 class="font-black text-blue-700 mb-2 italic uppercase">05. $$W_p$$ (Parity Reversion)</h3><p class="text-[11px] text-slate-500 leading-relaxed mb-4">偵測 20 期 (400球) 奇偶比。低於 **160 (40%)** 時觸發動態補償權重。</p>
                            <div class="bg-slate-50 p-4 rounded-xl text-[10px] font-mono">$$W_p = \\begin{cases} 1.2 & n \\le 160 \\\\ 1.0 & n > 160 \\end{cases}$$</div>
                        </div>
                        <div class="border-b pb-4"><h3 class="font-black text-cyan-700 mb-2 italic uppercase">06. $$W_s$$ (Size Reversion)</h3><p class="text-[11px] text-slate-500 leading-relaxed mb-4">偵測 20 期大小比。規則同奇偶補償。若雙重疊加觸發，權重可達 **1.44 倍**。</p>
                            <div class="bg-rose-50 p-2 rounded-xl text-center text-[10px] font-black text-rose-600 italic uppercase">Max Logic: $W_p \\times W_s = 1.44$</div>
                        </div>
                        <div><h3 class="font-black text-slate-600 mb-2 italic uppercase">07. 扣 (Heat Filtering)</h3><p class="text-[11px] text-slate-500 leading-relaxed">過熱保護。統計近 15 期極短期產量，每出現一期扣 **2.0 分**，防止在高位區間盲目追盤。</p></div>
                    </div>
                </div>
                <div class="mt-16 text-center text-[10px] font-black text-slate-400 uppercase tracking-[1em] opacity-40 italic">Binary Reversion • Synergy Matrix • Quant V7.4</div>
            </div>
        </div>

        <script>
            const currentNo = "{{ latest_no }}";
            const currentWinNums = Array.from(document.querySelectorAll('.latest-ball')).map(el => parseInt(el.dataset.val));
            const g1Picks = {{ results[0].picks | map(attribute='no') | list | tojson }};
            const g2Picks = {{ results[1].picks | map(attribute='no') | list | tojson }};

            function saveInputs() { const nums = []; for (let i = 1; i <= 6; i++) nums.push(document.getElementById('myNum' + i).value); localStorage.setItem('bingo_saved_nums', JSON.stringify(nums)); }
            function loadAndSync() {
                const savedInputs = localStorage.getItem('bingo_saved_nums');
                if (savedInputs) { const nums = JSON.parse(savedInputs); nums.forEach((val, i) => document.getElementById('myNum' + (i + 1)).value = val); }
                const lastSavedNo = localStorage.getItem('saved_latest_no');
                if (lastSavedNo && lastSavedNo !== currentNo) {
                    localStorage.setItem('prev_no', lastSavedNo);
                    localStorage.setItem('prev_g1', localStorage.getItem('curr_g1'));
                    localStorage.setItem('prev_g2', localStorage.getItem('curr_g2'));
                }
                localStorage.setItem('saved_latest_no', currentNo);
                localStorage.setItem('curr_g1', JSON.stringify(g1Picks));
                localStorage.setItem('curr_g2', JSON.stringify(g2Picks));
                renderHistory(); startComparison();
            }
            function renderHistory() {
                const prevNo = localStorage.getItem('prev_no');
                const prevG1 = JSON.parse(localStorage.getItem('prev_g1'));
                const prevG2 = JSON.parse(localStorage.getItem('prev_g2'));
                if (prevNo && prevG1 && prevG2) {
                    document.getElementById('prevSection').classList.remove('hidden');
                    document.getElementById('prevNoDisplay').innerText = prevNo;
                    document.getElementById('prevG1List').innerHTML = prevG1.map(n => currentWinNums.includes(n) ? `<span class="prev-hit">${n.toString().padStart(2,'0')}</span>` : n.toString().padStart(2,'0')).join(', ');
                    document.getElementById('prevG2List').innerHTML = prevG2.map(n => currentWinNums.includes(n) ? `<span class="prev-hit">${n.toString().padStart(2,'0')}</span>` : n.toString().padStart(2,'0')).join(', ');
                }
            }
            function clearHistory() { localStorage.clear(); location.reload(); }
            window.onload = loadAndSync;
            function toggleDetail(id) { const el = document.getElementById('detail-' + id); el.style.display = (el.style.display === "block") ? "none" : "block"; }
            function quickFill(numbers) {
                for (let i = 1; i <= 6; i++) document.getElementById('myNum' + i).value = "";
                numbers.forEach((num, index) => { if (index < 6) document.getElementById('myNum' + (index + 1)).value = num.toString().padStart(2, '0'); });
                saveInputs(); startComparison(); document.getElementById('compBox').scrollIntoView({ behavior: 'smooth' });
            }
            function startComparison() {
                const winNums = currentWinNums;
                const myInputs = []; for(let i=1; i<=6; i++) { let val = document.getElementById('myNum' + i).value; if(val !== "") myInputs.push(Number(val)); }
                document.querySelectorAll('.latest-ball').forEach(ball => ball.classList.remove('hit-highlight'));
                document.querySelectorAll('.num-card').forEach(card => card.classList.remove('hit-highlight'));
                myInputs.forEach(myNum => { if (winNums.includes(myNum)) { 
                    document.querySelector(`.latest-ball[data-val="${myNum}"]`)?.classList.add('hit-highlight'); 
                    document.querySelectorAll(`.num-card[data-val="${myNum}"]`).forEach(c => c.classList.add('hit-highlight')); 
                } });
            }
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(results=results, p_day=p_day, s_day=s_day, p_20=p_20, s_20=s_20, status=status, latest_win=latest_win, latest_no=latest_no, active_date=active_date, top_hot=top_hot, top_cold=top_cold)

if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)




