from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools

app = FastAPI()

# --- 1. 核心量化分析邏輯 (V6.7) ---

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
        api_data = fetch_api((now - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))

    if not api_data:
        return [], "0:0", "0:0", "0:0", "0:0", {}, [], "N/A", target_date

    all_draws = []
    for item in api_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: all_draws.append(nums)
    
    latest_no = api_data[0].get('No', 'N/A')
    latest_win_nums = all_draws[0] if all_draws else []
    
    # 環境統計
    all_balls = [n for d in all_draws for n in d]
    o_day = len([n for n in all_balls if n % 2 != 0]); e_day = len(all_balls) - o_day
    s_day = len([n for n in all_balls if n <= 40]); b_day = len(all_balls) - s_day
    
    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20

    # 閥值判定
    THRESHOLD = 160 
    status = {
        'odd': o_20 <= THRESHOLD, 'even': e_20 <= THRESHOLD,
        'small': s_20 <= THRESHOLD, 'big': b_20 <= THRESHOLD
    }

    # 權重分配
    wp_odd = 1.2 if status['odd'] else 1.0
    wp_even = 1.2 if status['even'] else 1.0
    ws_small = 1.2 if status['small'] else 1.0
    ws_big = 1.2 if status['big'] else 1.0

    co_occ = Counter()
    for d in all_draws[:100]:
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1

    short_heat = Counter([n for d in all_draws[:15] for n in d])
    long_freq = Counter([n for d in all_draws[:50] for n in d])
    
    all_analysis = []
    for i in range(1, 81):
        f_score = long_freq[i] * 1.0 # 基
        streak = 0
        for d in all_draws:
            if i in d: streak += 1
            else: break
        r_score = 5.0 if streak == 1 else 2.0 if streak == 2 else 0.0 # 莊
        l_penalty = -15.0 if streak >= 3 else 0.0 # 連
        d_score = sum(co_occ.get(tuple(sorted((i, ln))), 0) for ln in latest_win_nums) * 0.3 # 拖
        
        cur_wp = wp_odd if i % 2 != 0 else wp_even
        cur_ws = ws_small if i <= 40 else ws_big
        h_penalty = -(short_heat[i] * 2.0) # 扣
        
        final_score = (f_score + r_score + l_penalty + d_score) * cur_wp * cur_ws + h_penalty
        
        omission = next((idx for idx, d in enumerate(all_draws) if i in d), 99)
        all_analysis.append({
            'no': i, 'score': round(final_score, 1), 'omission': omission, 'section': (i-1)//20,
            'details': {'基': f_score, '莊': r_score, '連': l_penalty, '拖': round(d_score, 1), '權': f"x{cur_wp*cur_ws:.2f}", '扣': h_penalty}
        })

    def select_group(pool, h_c, c_c, used_set):
        sorted_score = sorted(pool, key=lambda x: x['score'], reverse=True)
        sorted_omission = sorted(pool, key=lambda x: x['omission'], reverse=True)
        res = []
        sec_counts = Counter()
        for p in sorted_score:
            if p['no'] not in used_set and len([x for x in res if x['tag']=='熱門']) < h_c:
                if sec_counts[p['section']] < 2:
                    p_c = p.copy(); p_c['tag']='熱門'; res.append(p_c); used_set.add(p['no']); sec_counts[p['section']]+=1
        for p in sorted_omission:
            if p['no'] not in used_set and len([x for x in res if x['tag']=='冷門']) < c_c:
                if sec_counts[p['section']] < 2:
                    p_c = p.copy(); p_c['tag']='冷門'; res.append(p_c); used_set.add(p['no']); sec_counts[p['section']]+=1
        return res

    used = set()
    g1 = select_group(all_analysis, 2, 2, used)
    g2 = select_group(all_analysis, 1, 3, used)
    g3 = [dict(p, tag="熱門") for p in sorted(all_analysis, key=lambda x: x['score'], reverse=True)[:6]]

    results = [
        {"id":"G1", "name":"第一組 (2熱2冷)", "picks":sorted(g1, key=lambda x:x['no']), "clr":"border-amber-400"},
        {"id":"G2", "name":"第二組 (1熱3冷)", "picks":sorted(g2, key=lambda x:x['no']), "clr":"border-emerald-400"},
        {"id":"G3", "name":"第三組 (6星共振)", "picks":sorted(g3, key=lambda x:x['no']), "size":6, "clr":"border-slate-800"}
    ]
    return (results, f"奇 {o_day} : 偶 {e_day}", f"小 {s_day} : 大 {b_day}", 
            f"奇 {o_20} : 偶 {e_20}", f"小 {s_20} : 大 {b_20}", 
            status, latest_win_nums, latest_no, target_date)

# --- 2. 網頁前端 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    (results, p_day, s_day, p_20, s_20, 
     status, latest_win, latest_no, active_date) = get_data_and_analyze(date)
    
    html_content = """
    <html>
    <head>
        <title>量化終端 V6.7</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            .hit-highlight { color: white !important; background-color: #ef4444 !important; font-weight: bold; border-radius: 50%; box-shadow: 0 0 15px rgba(239, 68, 68, 0.7); transform: scale(1.1); }
            .latest-ball { background: #f1f5f9; color: #475569; font-weight: bold; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 11px; border: 1px solid #e2e8f0; }
            .formula-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
            .tag-hot { background: #fee2e2; color: #ef4444; border: 1px solid #fecaca; }
            .tag-cold { background: #e0f2fe; color: #0ea5e9; border: 1px solid #bae6fd; }
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
                        <span class="text-[10px] font-black uppercase opacity-80 tracking-widest italic">Parity Monitor</span>
                        {% if status.odd or status.even %}
                            <div class="status-monitor status-active">✅ 補償激活 (x1.2)</div>
                        {% else %}
                            <div class="status-monitor status-idle">⚪ 監控中 (未達閥值)</div>
                        {% endif %}
                    </div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60 uppercase mb-1">今日全天累計</p><p class="text-lg font-black tracking-tighter">{{ p_day }}</p></div>
                        <div class="border-l border-white/10">
                            <p class="text-[8px] text-amber-300 font-bold uppercase mb-1 underline">最近 20 期觸發區</p>
                            <p class="text-xl font-black text-amber-300 tracking-tighter">{{ p_20 }}</p>
                        </div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4">
                        <span class="text-[10px] font-black uppercase opacity-80 tracking-widest italic">Size Monitor</span>
                        {% if status.small or status.big %}
                            <div class="status-monitor status-active">✅ 補償激活 (x1.2)</div>
                        {% else %}
                            <div class="status-monitor status-idle">⚪ 監控中 (未達閥值)</div>
                        {% endif %}
                    </div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60 uppercase mb-1">今日全天累計</p><p class="text-lg font-black tracking-tighter">{{ s_day }}</p></div>
                        <div class="border-l border-white/10">
                            <p class="text-[8px] text-amber-300 font-bold uppercase mb-1 underline">最近 20 期觸發區</p>
                            <p class="text-xl font-black text-amber-300 tracking-tighter">{{ s_20 }}</p>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 mb-6 flex justify-between items-center">
                <h1 class="text-xl font-black text-slate-800 italic tracking-tighter uppercase italic">Quant Terminal V6.7</h1>
                <button onclick="location.reload()" class="bg-indigo-500 text-white px-5 py-2 rounded-xl text-[10px] font-black shadow-lg">Refresh</button>
            </div>
            
            <div class="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 mb-6 text-center">
                <h3 class="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4 italic">📢 Latest Draw: {{ latest_no }}</h3>
                <div class="flex flex-wrap gap-2.5 justify-center">
                    {% for n in latest_win %}<div class="latest-ball" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}
                </div>
            </div>

            <div id="compBox" class="bg-slate-900 p-8 rounded-[2.5rem] shadow-2xl text-white mb-10 text-center border-4 border-slate-800">
                <div class="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
                    {% for i in range(1, 7) %}<input type="text" id="myNum{{i}}" maxlength="2" class="h-14 text-center text-2xl font-black text-white bg-slate-800 rounded-2xl border-2 border-slate-700 outline-none focus:border-indigo-400" placeholder="--">{% endfor %}
                </div>
                <button onclick="startComparison()" class="w-full bg-indigo-500 text-white font-black py-4 rounded-xl text-sm uppercase tracking-widest">執行對獎</button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-20">
                {% for group in results %}
                <div class="bg-white p-5 rounded-3xl shadow-sm border-4 {{ group.clr }} flex flex-col">
                    <div class="flex justify-between items-start mb-4"><h2 class="text-[10px] font-black text-slate-800 uppercase italic">{{ group.name }}</h2><button onclick="toggleDetail('{{ group.id }}')" class="text-[8px] bg-slate-100 px-2 py-1 rounded font-bold uppercase">Detail</button></div>
                    <div class="grid {{ 'grid-cols-3' if group.id == 'G3' else 'grid-cols-2' }} gap-2.5 mb-4">
                        {% for p in group.picks %}<div class="bg-slate-50 pt-6 pb-4 rounded-2xl text-center relative overflow-hidden num-card" data-val="{{ p.no }}"><span class="absolute top-0 left-0 w-full text-[7px] font-black py-0.5 {{ 'tag-hot' if p.tag == '熱門' else 'tag-cold' }}">{{ p.tag }}</span><p class="text-2xl font-black text-slate-800 font-mono">{{ "%02d" | format(p.no) }}</p></div>{% endfor %}
                    </div>
                    <div id="detail-{{ group.id }}" class="strategy-detail bg-slate-50 p-3 rounded-xl mb-4 text-[8px] font-bold text-slate-500 space-y-1">
                        {% for p in group.picks %}<div class="flex justify-between border-b border-slate-100 pb-1"><span>No.{{ "%02d" | format(p.no) }}</span><span>基:{{p.details['基']}}|權:{{p.details['權']}}|拖:{{p.details['拖']}}|扣:{{p.details['扣']}}</span></div>{% endfor %}
                    </div>
                    <button onclick='quickFill({{ group.picks | map(attribute="no") | list | tojson }})' class="mt-auto w-full bg-slate-900 text-white py-3 rounded-xl text-[10px] font-black tracking-widest transition-all">🚀 快速對獎</button>
                </div>
                {% endfor %}
            </div>

            <div class="mt-20 border-t-2 border-slate-200 pt-10">
                <div class="flex items-center space-x-3 mb-10"><div class="w-3 h-8 bg-indigo-600 rounded-full"></div><h2 class="text-2xl font-black text-slate-800 tracking-tighter italic uppercase">Technical Whitepaper V6.7</h2></div>

                <div class="formula-card p-12 rounded-[3.5rem] shadow-2xl text-white mb-12 text-center border border-white/10">
                    <p class="text-[10px] font-bold text-indigo-300 uppercase tracking-[0.4em] mb-6 underline underline-offset-8">Master Scoring Model</p>
                    <div class="text-xl md:text-3xl font-serif italic mb-6">
                        $$Score = \\left( \\text{基} + \\text{莊} + \\text{連} + \\text{拖} \\right) \\times W_p \\times W_s + \\text{扣}$$
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 text-sm">
                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-6">
                        <div>
                            <h3 class="font-black text-indigo-500 mb-2 italic">01. 基 (Base Frequency)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed">過去 50 期長期出現頻率，決定號碼的核心慣性動能。</p>
                        </div>
                        <div>
                            <h3 class="font-black text-emerald-500 mb-2 italic">02. 莊 (Streak Bonus)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed">連 1 期 **+5.0**，連 2 期 **+2.0**，捕捉短期出球爆發力。</p>
                        </div>
                        <div>
                            <h3 class="font-black text-rose-500 mb-2 italic">03. 連 (Exhaustion Penalty)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed">「連莊不破三」原則。連續產出 $$ \\ge 3 $$ 期則判定能量耗盡，強制扣除 **15.0 分**。</p>
                        </div>
                        <div>
                            <h3 class="font-black text-amber-500 mb-2 italic">04. 拖 (Synergy Drag)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed">分析 100 期兩兩共現機率，計算與最新獎號的引力總和 $\\sum f_{i, latest}$ 並乘 **0.3**。</p>
                        </div>
                    </div>

                    <div class="bg-white p-8 rounded-[2.5rem] shadow-sm border border-slate-100 space-y-6">
                        <div>
                            <h3 class="font-black text-blue-500 mb-2 italic uppercase">05. $$W_p$$ (Parity Weight)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed mb-3">
                                偵測近 20 期 (400球) 奇偶比。低於 **160 (40%)** 時觸發補償權重。
                            </p>
                            <div class="bg-slate-50 p-3 rounded-xl text-[10px] font-mono">
                                $$W = \\begin{cases} 1.2 & n \\le 160 \\\\ 1.0 & n > 160 \\end{cases}$$
                            </div>
                        </div>
                        <div>
                            <h3 class="font-black text-cyan-500 mb-2 italic uppercase">06. $$W_s$$ (Size Weight)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed mb-3">
                                偵測近 20 期大小比。規則同奇偶補償，若雙重疊加觸發，權重可達 **1.44 倍**。
                            </p>
                        </div>
                        <div>
                            <h3 class="font-black text-slate-400 mb-2 italic uppercase">07. 扣 (Heat Filter)</h3>
                            <p class="text-[11px] text-slate-500 leading-relaxed">
                                偵測近 15 期過熱度，每開出一期扣 **2.0 分**，防止盲目追高導致勝率下降。
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            function toggleDetail(id) { const el = document.getElementById('detail-' + id); el.style.display = (el.style.display === "block") ? "none" : "block"; }
            function quickFill(numbers) {
                for (let i = 1; i <= 6; i++) document.getElementById('myNum' + i).value = "";
                numbers.forEach((num, index) => { if (index < 6) document.getElementById('myNum' + (index + 1)).value = num.toString().padStart(2, '0'); });
                startComparison(); document.getElementById('compBox').scrollIntoView({ behavior: 'smooth' });
            }
            function startComparison() {
                const winNums = Array.from(document.querySelectorAll('.latest-ball')).map(el => parseInt(el.dataset.val));
                const myInputs = []; for(let i=1; i<=6; i++) { let val = document.getElementById('myNum' + i).value; if(val !== "") myInputs.push(Number(val)); }
                if (myInputs.length < 3) return alert('請輸入至少 3 個號碼');
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
    return template.render(results=results, p_day=p_day, s_day=s_day, p_20=p_20, s_20=s_20, status=status, latest_win=latest_win, latest_no=latest_no, active_date=active_date)

if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)



