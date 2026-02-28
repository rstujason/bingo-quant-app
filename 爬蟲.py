from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 (V7.7 10組矩陣版) ---

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
    
    # 100 期共現矩陣 (核心拖牌引力)
    co_occ = Counter()
    for d in all_draws[:100]:
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1

    # 環境壓力監控
    all_balls = [n for d in all_draws for n in d]
    o_day = len([n for n in all_balls if n % 2 != 0]); e_day = len(all_balls) - o_day
    s_day = len([n for n in all_balls if n <= 40]); b_day = len(all_balls) - s_day
    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20

    THRESHOLD = 160 
    status = {'odd': o_20 <= THRESHOLD, 'even': e_20 <= THRESHOLD, 'small': s_20 <= THRESHOLD, 'big': b_20 <= THRESHOLD}
    wp_odd = 1.2 if status['odd'] else 1.0; wp_even = 1.2 if status['even'] else 1.0
    ws_small = 1.2 if status['small'] else 1.0; ws_big = 1.2 if status['big'] else 1.0

    short_heat = Counter([n for d in all_draws[:15] for n in d]) # 07.扣
    long_freq = Counter([n for d in all_draws[:50] for n in d])  # 01.基
    
    all_analysis = []
    for i in range(1, 81):
        f_score = long_freq[i] * 1.0 
        streak = 0
        for d in all_draws:
            if i in d: streak += 1
            else: break
        r_score = 5.0 if streak == 1 else 2.0 if streak == 2 else 0.0 # 02.莊
        l_penalty = -15.0 if streak >= 3 else 0.0 # 03.連
        cur_wp = wp_odd if i % 2 != 0 else wp_even
        cur_ws = ws_small if i <= 40 else ws_big
        h_penalty = -(short_heat[i] * 2.0) # 07.扣
        
        final_score = (f_score + r_score + l_penalty) * cur_wp * cur_ws + h_penalty
        omission = next((idx for idx, d in enumerate(all_draws) if i in d), 99)
        all_analysis.append({'no': i, 'score': round(final_score, 1), 'omission': omission, 'section': (i-1)//20,
                             'details': {'基': f_score, '莊': r_score, '連': l_penalty, '權': f"x{cur_wp*cur_ws:.2f}", '扣': h_penalty}})

    top_hot_list = sorted(all_analysis, key=lambda x: x['score'], reverse=True)[:10]
    top_cold_list = sorted(all_analysis, key=lambda x: x['omission'], reverse=True)[:10]

    def get_synergy(n1, n2): return co_occ.get(tuple(sorted((n1, n2))), 0)
    used = set()
    results = []
    
    # 產生 10 組三星小隊
    sorted_seeds = sorted(all_analysis, key=lambda x: x['score'], reverse=True)
    for i in range(10):
        seed = next(p for p in sorted_seeds if p['no'] not in used)
        partners = sorted([p for p in all_analysis if p['no'] not in used and p['no'] != seed['no']], 
                          key=lambda x: (get_synergy(seed['no'], x['no']), x['score']), reverse=True)[:2]
        squad = [seed.copy()] + [p.copy() for p in partners]
        for p in squad: p['star'] = True; used.add(p['no'])
        results.append({"id": i+1, "name": f"第{i+1}組", "picks": sorted(squad, key=lambda x:x['no'])})

    return (results, f"{o_day}:{e_day}", f"{s_day}:{b_day}", f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, target_date, top_hot_list, top_cold_list)

# --- 2. 網頁前端 (矩陣對獎區與彩色識別) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    (results, p_day, s_day, p_20, s_20, status, latest_win, latest_no, active_date, top_hot, top_cold) = get_data_and_analyze(date)
    
    html_content = """
    <html>
    <head>
        <title>量化矩陣 V7.7</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            /* 10組專屬命中顏色  */
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

            .latest-ball { background: #f1f5f9; color: #475569; font-weight: bold; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 12px; border: 1px solid #e2e8f0; transition: all 0.3s; }
            .star-box { border: 2px solid #fbbf24 !important; background-color: #fffbeb !important; }
            .formula-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
        </style>
    </head>
    <body class="bg-slate-50 font-sans text-slate-900 pb-20">
        <div class="max-w-5xl mx-auto p-4 md:p-8">
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-indigo-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase opacity-80 italic">Parity Monitor</span>{% if status.odd or status.even %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center">
                        <div><p class="text-[8px] opacity-60 uppercase mb-1">今日累計</p><p class="text-lg font-black tracking-tighter">奇 {{ p_day }} 偶</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold uppercase mb-1 underline">最近 20 期觸發</p><p class="text-xl font-black text-amber-300 tracking-tighter">{{ p_20 }}</p></div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4"><span class="text-[10px] font-black uppercase opacity-80 italic">Size Monitor</span>{% if status.small or status.big %}<div class="bg-green-500 text-[8px] font-black px-2 py-1 rounded-full animate-pulse">✅ 補償激活</div>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center">
                        <div><p class="text-[8px] opacity-60 uppercase mb-1">今日累計</p><p class="text-lg font-black tracking-tighter">小 {{ s_day }} 大</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold uppercase mb-1 underline">最近 20 期觸發</p><p class="text-xl font-black text-amber-300 tracking-tighter">{{ s_20 }}</p></div>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 mb-6">
                <div class="flex justify-between items-center mb-6 px-2">
                    <h3 class="text-[10px] font-black text-slate-400 uppercase tracking-widest italic">📢 Latest Draw: <span class="text-indigo-600 font-mono">{{ latest_no }}</span></h3>
                    <button onclick="location.reload()" class="bg-indigo-500 text-white px-5 py-2 rounded-xl text-[10px] font-black shadow-lg">Refresh</button>
                </div>
                <div class="flex flex-wrap gap-2.5 justify-center">
                    {% for n in latest_win %}<div class="latest-ball" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}
                </div>
            </div>

            <div id="matrixBox" class="bg-slate-900 p-6 md:p-10 rounded-[3rem] shadow-2xl text-white mb-10 border-4 border-slate-800">
                <h3 class="text-center text-[10px] font-black uppercase tracking-[0.5em] mb-8 text-indigo-400 italic">Quantitative 3-Star Matrix</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
                    {% for i in range(1, 11) %}
                    <div class="bg-slate-800/50 p-4 rounded-2xl border border-slate-700">
                        <p class="text-[8px] font-black mb-2 opacity-50 uppercase">Set {{ i }}</p>
                        <div class="flex gap-2 justify-center">
                            {% for j in range(1, 4) %}
                            <input type="text" id="g{{i}}n{{j}}" maxlength="2" 
                                   class="w-10 h-10 text-center text-lg font-black bg-slate-900 rounded-lg border border-slate-600 focus:border-indigo-400 outline-none transition-all" 
                                   placeholder="--" oninput="saveMatrix()">
                            {% endfor %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <button onclick="executeComparison()" class="w-full mt-10 bg-indigo-500 hover:bg-indigo-600 text-white font-black py-5 rounded-2xl shadow-xl uppercase tracking-widest text-sm transition-all italic">Execute Matrix Synergy Analysis</button>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-20">
                {% for squad in results %}
                <div class="bg-white p-4 rounded-2xl shadow-sm border-2 border-slate-100 text-center">
                    <p class="text-[9px] font-black text-slate-400 uppercase mb-3">{{ squad.name }}</p>
                    <div class="flex justify-center gap-1 mb-3">
                        {% for p in squad.picks %}
                        <span class="bg-slate-900 text-white text-[10px] font-mono w-7 py-1 rounded">{{ "%02d" | format(p.no) }}</span>
                        {% endfor %}
                    </div>
                    <button onclick='quickFillMatrix({{ squad.id }}, {{ squad.picks | map(attribute="no") | list | tojson }})' 
                            class="w-full bg-slate-100 hover:bg-indigo-100 text-indigo-600 py-1.5 rounded-lg text-[8px] font-black uppercase transition-colors">🚀 Load</button>
                </div>
                {% endfor %}
            </div>

            <div class="mt-20 border-t-2 border-slate-200 pt-10">
                <div class="flex items-center space-x-3 mb-10"><div class="w-3 h-8 bg-indigo-600 rounded-full"></div><h2 class="text-2xl font-black text-slate-800 tracking-tighter italic uppercase">Technical Whitepaper V7.7</h2></div>
                <div class="formula-card p-12 rounded-[3.5rem] shadow-2xl text-white mb-12 text-center border border-white/10">
                    <p class="text-[10px] font-bold text-indigo-300 uppercase tracking-[0.4em] mb-6 underline underline-offset-8 italic">Squad Synergy Multi-Factor Model</p>
                    <div class="text-xl md:text-3xl font-serif italic mb-6">$$Score = \\left( \\text{基} + \\text{莊} + \\text{連} \\right) \\times W_p \\times W_s + \\text{扣}$$</div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 text-[11px] text-slate-500 leading-relaxed italic">
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-4">
                        <p>● <b>01. 基 (Base Momentum)</b>: 50期出球頻率慣性分。</p>
                        <p>● <b>02. 莊 (Streak Bonus)</b>: 連莊動能 (連1期+5, 連2期+2)。</p>
                        <p>● <b>03. 連 (Exhaustion)</b>: 產出$$ \\ge 3 $$期判定竭盡，修正 **-15.0 分**。</p>
                        <p>● <b>04. 拖 (Synergy Matrix)</b>: 100期共現矩陣，組內引力加成 **0.3**。</p>
                    </div>
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-4">
                        <p>● <b>05. $$W_p$$ (Parity)</b>: 20期奇偶比 $$ n \\le 160 $$ 觸發 **1.2倍**。</p>
                        <p>● <b>06. $$W_s$$ (Size)</b>: 20期大小比規則同上，雙重觸發達 **1.44倍**。</p>
                        <p>● <b>07. 扣 (Heat Filter)</b>: 15期過熱過濾，每出現一次扣 **2.0 分**。</p>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const winNums = {{ latest_win | tojson }};
            
            function saveMatrix() {
                const data = {};
                for(let i=1; i<=10; i++) {
                    data[i] = [document.getElementById(`g${i}n1`).value, document.getElementById(`g${i}n2`).value, document.getElementById(`g${i}n3`).value];
                }
                localStorage.setItem('bingo_matrix_v77', JSON.stringify(data));
            }

            function loadMatrix() {
                const saved = localStorage.getItem('bingo_matrix_v77');
                if(saved) {
                    const data = JSON.parse(saved);
                    for(let i=1; i<=10; i++) {
                        if(data[i]) {
                            document.getElementById(`g${i}n1`).value = data[i][0];
                            document.getElementById(`g${i}n2`).value = data[i][1];
                            document.getElementById(`g${i}n3`).value = data[i][2];
                        }
                    }
                }
                executeComparison();
            }

            function quickFillMatrix(id, numbers) {
                document.getElementById(`g${id}n1`).value = numbers[0].toString().padStart(2, '0');
                document.getElementById(`g${id}n2`).value = numbers[1].toString().padStart(2, '0');
                document.getElementById(`g${id}n3`).value = numbers[2].toString().padStart(2, '0');
                saveMatrix(); executeComparison();
            }

            function executeComparison() {
                // 重置所有球顏色
                document.querySelectorAll('.latest-ball').forEach(el => {
                    for(let i=1; i<=10; i++) el.classList.remove(`hit-g${i}`);
                });

                for(let i=1; i<=10; i++) {
                    const squad = [
                        Number(document.getElementById(`g${i}n1`).value),
                        Number(document.getElementById(`g${i}n2`).value),
                        Number(document.getElementById(`g${i}n3`).value)
                    ];
                    squad.forEach(num => {
                        if(winNums.includes(num)) {
                            document.querySelector(`.latest-ball[data-val="${num}"]`)?.classList.add(`hit-g${i}`);
                        }
                    });
                }
            }

            window.onload = loadMatrix;
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






