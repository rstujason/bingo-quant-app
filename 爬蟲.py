from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 ---

def get_data_and_analyze(target_date=None, mode_exclusive=True):
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
        return [], [], [], "0:0", "0:0", "0:0", "0:0", {}, [], "N/A", "--:--", target_date, []

    all_draws = []
    recent_history = [] 
    for item in full_raw_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: 
                all_draws.append(nums)
                if len(recent_history) < 20:
                    raw_date = item.get('OpenDate', '')
                    d_time = raw_date[11:16] if 'T' in raw_date else '--:--'
                    recent_history.append({"no": item.get('No'), "time": d_time, "nums": nums})
    
    latest_no = full_raw_data[0].get('No', 'N/A')
    raw_latest_date = full_raw_data[0].get('OpenDate', '')
    latest_time = raw_latest_date[11:16] if 'T' in raw_latest_date else '--:--'
    latest_win_nums = all_draws[0] if all_draws else []
    
    co_occ = Counter()
    for d in all_draws[:200]: 
        for pair in itertools.combinations(sorted(d), 2): co_occ[pair] += 1
    
    recent_20 = all_draws[:20]
    o_20 = len([n for d in recent_20 for n in d if n % 2 != 0]); e_20 = 400 - o_20
    s_20 = len([n for d in recent_20 for n in d if n <= 40]); b_20 = 400 - s_20
    status = {'odd': o_20 <= 160, 'even': e_20 <= 160, 'small': s_20 <= 160, 'big': b_20 <= 160}

    long_freq = Counter([n for d in all_draws[:50] for n in d])
    short_heat = Counter([n for d in all_draws[:15] for n in d])
    
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

    def generate_squads_smart(pool, size, count, exclusive, cat_used):
        squads = []
        sorted_seeds = sorted(pool, key=lambda x: x['score'], reverse=True)[:count]
        for i, seed in enumerate(sorted_seeds):
            seed_no = seed['no']
            avoid = cat_used if exclusive else {seed_no}
            all_partners = sorted([p for p in pool if p['no'] not in avoid and p['no'] != seed_no], 
                                  key=lambda x: (get_synergy(seed_no, x['no']), x['score']), reverse=True)
            p_idx = size - 1
            cur_squad = sorted([seed_no] + [p['no'] for p in all_partners[:p_idx]])
            if exclusive:
                for n in cur_squad: cat_used.add(n)
            squads.append({"id": i+1, "picks": cur_squad})
        return squads

    ranked = sorted(all_analysis, key=lambda x: x['score'], reverse=True)
    s1 = ranked[0]['no']; s2 = ranked[1]['no']
    p1 = sorted([p for p in all_analysis if p['no'] not in [s1, s2]], key=lambda x: get_synergy(s1, x['no']), reverse=True)[:2]
    p1_nos = [p['no'] for p in p1]
    p2 = sorted([p for p in all_analysis if p['no'] not in [s1, s2] + p1_nos], key=lambda x: get_synergy(s2, x['no']), reverse=True)[:2]
    vip_6s = sorted([s1, s2] + p1_nos + [p['no'] for p in p2])

    u3 = set(); u4 = set()
    res_3star = generate_squads_smart(all_analysis, 3, 10, mode_exclusive, u3)
    res_4star = generate_squads_smart(all_analysis, 4, 10, mode_exclusive, u4)

    today_draws = [[int(x) for x in item.get('BigShowOrder','').split(',') if x.strip().isdigit()] for item in data_today if item.get('BigShowOrder','')]
    today_balls = [n for d in today_draws if len(d)==20 for n in d]
    p_day = f"{len([n for n in today_balls if n%2!=0])}:{len(today_balls)-len([n for n in today_balls if n%2!=0])}"
    s_day = f"{len([n for n in today_balls if n<=40])}:{len(today_balls)-len([n for n in today_balls if n<=40])}"

    return (res_3star, res_4star, vip_6s, p_day, s_day, f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, latest_time, target_date, recent_history)

# --- 2. 網頁前端 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None, exclusive: bool = True):
    (res_3star, res_4star, vip_6s, p_day, s_day, p_20, s_20, status, latest_win, latest_no, latest_time, active_date, recent_history) = get_data_and_analyze(date, exclusive)
    
    html_content = """
    <html class="dark">
    <head>
        <title>賓果量化 VIP</title>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>tailwind.config = { darkMode: 'class' }</script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
            body { font-family: 'Noto Sans TC', sans-serif; transition: background-color 0.3s; }
            .latest-ball { background: #f1f5f9; color: #475569; font-weight: 900; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 11px; border: 1px solid #e2e8f0; }
            .dark .latest-ball { background: #1e293b; color: #94a3b8; border-color: #334155; }
            .ball-hit { background-color: #fbbf24 !important; color: #000 !important; font-weight: 900; box-shadow: 0 0 12px rgba(251, 191, 36, 0.5); border: none !important; }

            .badge-graphical { padding: 3px 8px; border-radius: 6px; font-size: 9px; font-weight: 900; display: inline-flex; align-items: center; justify-content: center; margin: 2px; }
            .badge-3s { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; }
            .badge-4s { background: linear-gradient(135deg, #6366f1 0%, #4338ca 100%); color: white; }
            .badge-6s { background: linear-gradient(135deg, #be123c 0%, #9f1239 100%); color: white; }
            .badge-jackpot { background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); color: black !important; border: 1px solid #fff; animation: pulse-gold 1.5s infinite; }
            
            /* 全中標示 */
            .matrix-jackpot { border: 2px solid #fbbf24 !important; box-shadow: 0 0 20px rgba(251, 191, 36, 0.6); animation: jackpot-blink 1s infinite alternate; background: rgba(251, 191, 36, 0.1) !important; }

            @keyframes pulse-gold { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
            @keyframes jackpot-blink { from { border-color: #fbbf24; } to { border-color: #fff; transform: scale(1.02); } }

            .streak-start-3s { border: 3px solid #a855f7 !important; position: relative; background: rgba(168, 85, 247, 0.05) !important; }
            .streak-start-3s::after { content: '未命中起點'; position: absolute; top: -10px; right: 10px; background: #a855f7; color: white; font-size: 8px; padding: 1px 6px; border-radius: 4px; font-weight: 900; }

            .dist-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 3px; background: #fefce8; padding: 10px; border-radius: 16px; }
            .dark .dist-grid { background: #0f172a; border: 1px solid #1e293b; }
            .dist-ball { background: #ffffff; color: #64748b; font-weight: 900; font-size: 9px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 6px; border: 1px solid #e2e8f0; }
            .dark .dist-ball { background: #1e293b; color: #475569; border-color: #0f172a; }
            
            /* 分佈圖亮燈顏色 */
            .active-3s { background: #f59e0b !important; color: white !important; border: none !important; }
            .active-4s { background: #6366f1 !important; color: white !important; border: none !important; }
            .active-6s { background: #be123c !important; color: white !important; border: none !important; }

            .bt-miss-normal { background: #1e293b; color: #94a3b8; border: 1px solid #334155; }
            .bt-miss-alert { background: #be123c; color: white; animation: pulse-red 1s infinite alternate; }
            @keyframes pulse-red { from { opacity: 0.8; } to { opacity: 1; } }

            .alert-jackpot-glow { animation: jackpot-blink 1s infinite alternate; border: 2px solid #fbbf24 !important; }

            .profit-input { background: #f8fafc; border: 1px solid #e2e8f0; color: #1e293b; text-align: center; border-radius: 8px; font-weight: 900; width: 100%; height: 32px; font-size: 14px; }
            .dark .profit-input { background: #0f172a; border-color: #334155; color: #f1f5f9; }
        </style>
    </head>
    <body class="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-200 pb-20 text-[12px]">
        <div class="max-w-6xl mx-auto p-4 md:p-8">
            
            <div class="flex justify-between items-center mb-6">
                <h1 class="text-xl font-black italic uppercase dark:text-white tracking-tighter">賓果量化 <span class="text-rose-600 font-black">VIP</span></h1>
                <button onclick="toggleDarkMode()" id="theme-btn" class="bg-slate-800 text-amber-400 px-4 py-2 rounded-xl font-black text-[10px] shadow-lg">🌙 切換模式</button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 text-white text-center italic font-black">
                <div class="bg-indigo-700 p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <p class="text-[10px] uppercase mb-4 tracking-widest underline underline-offset-4">奇偶動能分析</p>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4"><div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg">{{ p_day }}</p></div><div class="border-l border-white/10"><p class="text-[8px] text-amber-300 underline underline-offset-2">最近 20 期</p><p class="text-xl font-black text-amber-300">{{ p_20 }}</p></div></div>
                </div>
                <div class="bg-emerald-700 p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <p class="text-[10px] uppercase mb-4 tracking-widest underline underline-offset-4">大小動能分析</p>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4"><div><p class="text-[8px] opacity-60">今日累計</p><p class="text-lg">{{ s_day }}</p></div><div class="border-l border-white/10"><p class="text-[8px] text-amber-300 underline underline-offset-2">最近 20 期</p><p class="text-xl font-black text-amber-300">{{ s_20 }}</p></div></div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6 text-center font-black">
                <div class="lg:col-span-3 bg-white dark:bg-slate-900 p-6 rounded-3xl shadow-sm border border-slate-100 dark:border-slate-800 italic">
                    <div class="flex justify-between items-center mb-6 border-b pb-4 text-slate-400 font-black">
                        <h3 class="text-xs uppercase tracking-widest">📢 最新期號: <span class="text-indigo-600 dark:text-indigo-400 font-mono">{{ latest_no }} ({{ latest_time }})</span></h3>
                        <button onclick="location.reload()" class="bg-indigo-500 text-white px-5 py-2 rounded-xl text-[10px] shadow-lg">刷新數據</button>
                    </div>
                    <div class="space-y-6 text-center">
                        <div class="bg-rose-50 dark:bg-rose-950/20 p-5 rounded-[2.5rem] border-2 border-rose-100 dark:border-rose-900/30">
                            <p class="text-[10px] font-black text-rose-500 mb-4 uppercase tracking-[0.4em] underline underline-offset-8 italic">🔥 VIP 雙核心狙擊組合</p>
                            <div class="flex justify-center items-center gap-2">
                                {% for n in vip_6s %}<div class="latest-ball" style="background:#be123c; color:white; border:none; width:36px; height:36px;">{{ "%02d" | format(n) }}</div>{% endfor %}
                                <button onclick='quickFill("6s", 1, {{ vip_6s | tojson }})' class="ml-2 bg-rose-600 text-white px-4 py-2 rounded-xl text-[10px] font-black shadow-lg">裝載</button>
                            </div>
                        </div>
                        <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-all" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                    </div>
                </div>
                <div class="bg-slate-900 p-5 rounded-3xl shadow-xl border-4 border-slate-800 text-white font-black italic">
                    <h4 class="text-center text-[9px] font-black text-indigo-400 uppercase mb-4">即時中獎監控</h4>
                    <div class="space-y-3">
                        <div id="card-3s" class="bg-slate-800/50 p-2 rounded-2xl border border-slate-700 transition-all"><p class="text-[7px] text-amber-500 mb-1.5 uppercase">3-Star (未命中: <span id="bt-count-3s-live">0</span>)</p><div class="grid grid-cols-2 gap-2 text-center"><div class="stat-card"><p class="text-[5px] text-slate-400">中2</p><p class="text-lg" id="count-3s-2">0</p></div><div class="stat-card"><p class="text-[5px] text-slate-400">全中</p><p class="text-lg text-amber-400" id="count-3s-3">0</p></div></div></div>
                        <div id="card-4s" class="bg-slate-800/50 p-2 rounded-2xl border border-slate-700 transition-all"><p class="text-[7px] text-indigo-400 mb-1.5 uppercase">4-Star (未命中: <span id="bt-count-4s-live">0</span>)</p><div class="grid grid-cols-3 gap-1 text-center"><div class="stat-card"><p class="text-[5px] text-slate-400">中2</p><p class="text-md" id="count-4s-2">0</p></div><div class="stat-card"><p class="text-[5px] text-slate-400">中3</p><p class="text-md" id="count-4s-3">0</p></div><div class="stat-card"><p class="text-[5px] text-slate-400">全中</p><p class="text-md text-indigo-400" id="count-4s-4">0</p></div></div></div>
                        <div id="card-6s" class="bg-slate-800/50 p-2 rounded-2xl border border-slate-700 transition-all"><p class="text-[7px] text-rose-500 mb-1.5 uppercase">VIP 6-Star (未命中: <span id="bt-count-6s-live">0</span>)</p><div class="grid grid-cols-4 gap-0.5 text-center font-black"><div class="stat-card"><p class="text-[4px] text-slate-400">中3</p><p class="text-[10px]" id="count-6s-3">0</p></div><div class="stat-card"><p class="text-[4px] text-slate-400">中4</p><p class="text-[10px]" id="count-6s-4">0</p></div><div class="stat-card"><p class="text-[4px] text-slate-400">中5</p><p class="text-[10px]" id="count-6s-5">0</p></div><div class="stat-card"><p class="text-[4px] text-slate-400">全中</p><p class="text-[10px] text-rose-400" id="count-6s-6">0</p></div></div></div>
                    </div>
                </div>
            </div>

            <div class="bg-white dark:bg-slate-900 p-6 rounded-[3rem] shadow-xl border border-slate-200 dark:border-slate-800 mb-6 italic">
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div class="space-y-2 text-center font-black border-r dark:border-slate-800 pr-4">
                        <label class="text-[8px] text-slate-400 uppercase">倍數 / 組數</label>
                        <div class="flex gap-2"><input type="number" id="in-multiplier" class="profit-input" value="1" oninput="calculateProfit()"><input type="number" id="in-sets" class="profit-input" value="10" oninput="calculateProfit()"></div>
                        <button onclick="postToDailyJournal()" class="w-full mt-2 bg-emerald-600 text-white py-2 rounded-xl text-[10px] font-black uppercase">存入日誌</button>
                    </div>
                    <div class="space-y-2 px-2 text-center border-r dark:border-slate-800 font-black">
                        <p class="text-[9px] text-amber-500 uppercase border-b">三星命中</p>
                        <div class="grid grid-cols-2 gap-2 mt-2"><input type="number" id="in-3h2" class="profit-input" placeholder="中2" oninput="calculateProfit()"><input type="number" id="in-3h3" class="profit-input" placeholder="全中" oninput="calculateProfit()"></div>
                    </div>
                    <div class="space-y-2 px-2 text-center border-r dark:border-slate-800 font-black">
                        <p class="text-[9px] text-indigo-500 uppercase border-b">四星命中</p>
                        <div class="grid grid-cols-3 gap-1 mt-2"><input type="number" id="in-4h2" class="profit-input" placeholder="2" oninput="calculateProfit()"><input type="number" id="in-4h3" class="profit-input" placeholder="3" oninput="calculateProfit()"><input type="number" id="in-4h4" class="profit-input" placeholder="全" oninput="calculateProfit()"></div>
                    </div>
                    <div class="space-y-2 px-2 text-center font-black">
                        <p class="text-[9px] text-rose-500 uppercase border-b">六星命中</p>
                        <div class="grid grid-cols-2 gap-1 mt-2"><input type="number" id="in-6h3" class="profit-input" placeholder="3" oninput="calculateProfit()"><input type="number" id="in-6h4" class="profit-input" placeholder="4" oninput="calculateProfit()"><input type="number" id="in-6h5" class="profit-input" placeholder="5" oninput="calculateProfit()"><input type="number" id="in-6h6" class="profit-input" placeholder="全" oninput="calculateProfit()"></div>
                    </div>
                </div>
                <div class="grid grid-cols-3 gap-4 mt-6 text-center bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border dark:border-slate-800 font-black">
                    <div><p class="text-[8px] text-slate-400 uppercase">成本</p><p class="text-lg text-rose-500" id="display-total-cost">-$ 0</p></div>
                    <div><p class="text-[8px] text-slate-400 uppercase">獎金</p><p class="text-lg text-indigo-400" id="display-total-prize">+$ 0</p></div>
                    <div class="border-l dark:border-slate-800"><p class="text-[8px] text-indigo-600 uppercase">預估淨利</p><p class="text-lg text-emerald-400" id="display-net-profit">$ 0</p></div>
                </div>
            </div>

            <div class="bg-emerald-900 p-8 rounded-[3rem] shadow-2xl text-white mb-6 border-4 border-emerald-800 italic">
                <div class="flex justify-between items-center mb-6">
                    <h3 class="text-[11px] font-black uppercase tracking-[0.3em]">今日實戰累計日誌</h3>
                    <button onclick="resetDailyJournal()" class="text-[8px] bg-red-900 px-4 py-1 rounded-full uppercase">清空日誌</button>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6 text-center font-black">
                    <div class="bg-black/20 p-5 rounded-3xl"><p class="text-[9px] text-emerald-300 mb-1">今日成本</p><p class="text-2xl font-mono" id="day-total-cost">$ 0</p></div>
                    <div class="bg-black/20 p-5 rounded-3xl"><p class="text-[9px] text-emerald-300 mb-1">今日獎金</p><p class="text-2xl font-mono" id="day-total-prize">$ 0</p></div>
                    <div class="bg-emerald-500 text-emerald-950 p-5 rounded-3xl shadow-lg border-2 border-emerald-400 font-black"><p class="text-[9px] mb-1">今日累積純利</p><p class="text-3xl font-mono" id="day-net-profit">$ 0</p></div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 text-center italic font-black uppercase">
                <div class="bg-white dark:bg-slate-900 p-4 rounded-3xl border dark:border-slate-800"><h3 class="text-[8px] text-amber-600 mb-3 underline">📡 三星分佈</h3><div class="dist-grid" id="dist-grid-3s">{% for i in range(1, 81) %}<div class="dist-ball" id="dist3s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div></div>
                <div class="bg-white dark:bg-slate-900 p-4 rounded-3xl border dark:border-slate-800"><h3 class="text-[8px] text-indigo-600 mb-3 underline">📡 四星分佈</h3><div class="dist-grid" id="dist-grid-4s">{% for i in range(1, 81) %}<div class="dist-ball" id="dist4s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div></div>
                <div class="bg-white dark:bg-slate-900 p-4 rounded-3xl border dark:border-slate-800"><h3 class="text-[8px] text-rose-600 mb-3 underline">📡 六星狙擊</h3><div class="dist-grid" id="dist-grid-6s">{% for i in range(1, 81) %}<div class="dist-ball" id="dist6s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div></div>
            </div>

            <div class="space-y-6 mb-10">
                <div class="bg-slate-900 p-6 rounded-[3rem] shadow-2xl border-4 border-slate-800 text-white font-black">
                    <div class="flex justify-between items-center mb-4 px-2 text-amber-400"><h3 class="text-[10px]">三星矩陣庫</h3><div class="flex gap-2"><button onclick="loadAll('3s')" class="bg-green-700 px-3 py-1 rounded text-[8px]">裝載</button><button onclick="clearMatrix('3s')" class="bg-red-900 px-3 py-1 rounded text-[8px]">清除</button></div></div>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">{% for i in range(1, 11) %}<div id="set-3s-{{i}}" class="bg-slate-800/50 p-2 rounded-xl text-center border border-transparent"><p class="text-[7px] text-slate-500 uppercase">SET {{ i }}</p><div class="flex gap-1">{% for j in range(1, 4) %}<input type="text" id="3s-g{{i}}n{{j}}" class="w-full h-8 text-center text-sm font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}</div>
                </div>
                <div class="bg-slate-900 p-6 rounded-[3rem] shadow-2xl border-4 border-slate-800 text-white font-black">
                    <div class="flex justify-between items-center mb-4 px-2 text-indigo-400"><h3 class="text-[10px]">四星矩陣庫</h3><div class="flex gap-2"><button onclick="loadAll('4s')" class="bg-indigo-700 px-3 py-1 rounded text-[8px]">裝載</button><button onclick="clearMatrix('4s')" class="bg-red-900 px-3 py-1 rounded text-[8px]">清除</button></div></div>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">{% for i in range(1, 11) %}<div id="set-4s-{{i}}" class="bg-slate-800/50 p-2 rounded-xl text-center border border-transparent"><p class="text-[7px] text-indigo-300 uppercase">S{{ i }}</p><div class="flex gap-1">{% for j in range(1, 5) %}<input type="text" id="4s-g{{i}}n{{j}}" class="w-full h-8 text-center text-xs font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}</div>
                </div>
                <div class="bg-slate-900 p-6 rounded-[3rem] shadow-2xl border-4 border-slate-800 text-white font-black text-center">
                    <h3 class="text-[10px] text-rose-400 uppercase mb-4 underline underline-offset-8">🔥 VIP 六星狙擊中心</h3>
                    <div class="flex justify-center"><div id="set-6s-1" class="bg-slate-800/50 p-6 rounded-[2.5rem] border-2 border-rose-900/50 w-full max-w-xl"><div class="grid grid-cols-6 gap-2">{% for j in range(1, 7) %}<input type="text" id="6s-g1n{{j}}" class="w-full h-12 text-center text-xl font-black bg-slate-950 rounded-xl border-2 border-slate-700 text-rose-500 outline-none" oninput="saveAndCompare()">{% endfor %}</div></div></div>
                </div>
            </div>

            <div class="bg-white dark:bg-slate-900 p-6 rounded-[3.5rem] shadow-xl border border-slate-200 dark:border-slate-800 mb-10 italic">
                <div class="flex flex-col md:flex-row justify-between items-center mb-6 border-b dark:border-slate-800 pb-4 gap-4">
                    <h3 class="text-sm text-slate-800 dark:text-slate-200 underline underline-offset-8 font-black">🕰️ 歷史 20 期實戰分析</h3>
                    <div class="flex flex-wrap justify-center gap-2 font-black">
                        <div id="bt-box-3s" class="bt-miss-normal px-4 py-1.5 rounded-xl text-[9px]">三星未命中: <span id="bt-count-3s">0</span></div>
                        <div id="bt-box-4s" class="bt-miss-normal px-4 py-1.5 rounded-xl text-[9px]">四星未命中: <span id="bt-count-4s">0</span></div>
                        <div id="bt-box-6s" class="bt-miss-normal px-4 py-1.5 rounded-xl text-[9px]">六星未命中: <span id="bt-count-6s">0</span></div>
                    </div>
                </div>
                <div id="backtest-body" class="space-y-4 font-mono font-black uppercase italic"></div>
            </div>
        </div>

        <script>
            const server3S = {{ res_3star | tojson }}; const server4S = {{ res_4star | tojson }};
            const server6S_VIP = {{ vip_6s | tojson }};
            const recentHistory = {{ recent_history | tojson }}; const winNums = {{ latest_win | tojson }};

            function toggleDarkMode() { const isDark = document.documentElement.classList.toggle('dark'); localStorage.setItem('bingo_v120_dark', isDark); updateThemeUI(isDark); }
            function updateThemeUI(isDark) { document.getElementById('theme-btn').innerText = isDark ? '☀️ 亮色切換' : '🌙 深色切換'; }
            function clearMatrix(t) { const sz = (t === '3s') ? 3 : (t === '4s' ? 4 : 6); const limit = (t === '6s') ? 1 : 10; for(let i=1; i<=limit; i++) { for(let j=1; j<=sz; j++) { const el = document.getElementById(`${t}-g${i}n${j}`); if(el) el.value = ""; } } saveAndCompare(); }
            function loadAll(t) { if(t === '6s') { quickFill('6s', 1, server6S_VIP); return; } (t === '3s' ? server3S : server4S).forEach(sq => { sq.picks.forEach((n, idx) => { const el = document.getElementById(`${t}-g${sq.id}n${idx+1}`); if(el) el.value = n.toString().padStart(2, '0'); }); }); saveAndCompare(); }
            function quickFill(t, id, ns) { ns.forEach((n, j) => { const el = document.getElementById(`${t}-g${id}n${j+1}`); if(el) el.value = n.toString().padStart(2, '0'); }); saveAndCompare(); }

            function calculateProfit() {
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const sets = parseInt(document.getElementById('in-sets').value) || 10;
                const cost = sets * multi * 25;
                const prize = (
                    (parseInt(document.getElementById('in-3h2').value)||0)*50 + 
                    (parseInt(document.getElementById('in-3h3').value)||0)*1000 + 
                    (parseInt(document.getElementById('in-4h2').value)||0)*25 + 
                    (parseInt(document.getElementById('in-4h3').value)||0)*150 + 
                    (parseInt(document.getElementById('in-4h4').value)||0)*2000 + 
                    (parseInt(document.getElementById('in-6h3').value)||0)*25 + 
                    (parseInt(document.getElementById('in-6h4').value)||0)*200 + 
                    (parseInt(document.getElementById('in-6h5').value)||0)*1200 + 
                    (parseInt(document.getElementById('in-6h6').value)||0)*50000
                ) * multi;
                const net = prize - cost;
                document.getElementById('display-total-cost').innerText = "-$ " + cost.toLocaleString();
                document.getElementById('display-total-prize').innerText = "+$ " + prize.toLocaleString();
                const nd = document.getElementById('display-net-profit');
                nd.innerText = (net >= 0 ? "+$ " : "-$ ") + Math.abs(net).toLocaleString();
                nd.className = net >= 0 ? "text-lg font-black text-emerald-400" : "text-lg font-black text-rose-500";
                runBacktest(); 
            }

            function postToDailyJournal() {
                let log = JSON.parse(localStorage.getItem('bingo_journal_v120') || '{"cost":0, "prize":0}');
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const sets = parseInt(document.getElementById('in-sets').value) || 10;
                const cost = sets * multi * 25;
                const prize = (
                    (parseInt(document.getElementById('in-3h2').value)||0)*50 + (parseInt(document.getElementById('in-3h3').value)||0)*1000 + (parseInt(document.getElementById('in-4h2').value)||0)*25 + (parseInt(document.getElementById('in-4h3').value)||0)*150 + (parseInt(document.getElementById('in-4h4').value)||0)*2000 + (parseInt(document.getElementById('in-6h3').value)||0)*25 + (parseInt(document.getElementById('in-6h4').value)||0)*200 + (parseInt(document.getElementById('in-6h5').value)||0)*1200 + (parseInt(document.getElementById('in-6h6').value)||0)*50000
                ) * multi;
                log.cost += cost; log.prize += prize;
                localStorage.setItem('bingo_journal_v120', JSON.stringify(log)); updateJournalDisplay(); alert("數據已存入今日實戰日誌！");
            }

            function updateJournalDisplay() {
                const log = JSON.parse(localStorage.getItem('bingo_journal_v120') || '{"cost":0, "prize":0}');
                const net = log.prize - log.cost;
                document.getElementById('day-total-cost').innerText = "$ " + log.cost.toLocaleString();
                document.getElementById('day-total-prize').innerText = "$ " + log.prize.toLocaleString();
                const nd = document.getElementById('day-net-profit'); 
                nd.innerText = (net>=0?"+$ ": "-$ ")+Math.abs(net).toLocaleString();
                nd.className = net>=0?"text-3xl font-mono font-black text-emerald-950 dark:text-emerald-400":"text-3xl font-mono font-black text-rose-500";
            }

            function resetDailyJournal() { if(confirm("確定重置數據？")) { localStorage.setItem('bingo_journal_v120', '{"cost":0, "prize":0}'); updateJournalDisplay(); } }

            function runBacktest() {
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const m3S = []; const m4S = []; const m6S = [];
                for(let i=1; i<=10; i++) {
                    const s3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n>0);
                    const s4 = [1,2,3,4].map(j => Number(document.getElementById(`4s-g${i}n${j}`).value)).filter(n => n>0);
                    if(s3.length === 3) m3S.push(s3); if(s4.length === 4) m4S.push(s4);
                }
                const s6_v = [1,2,3,4,5,6].map(j => Number(document.getElementById(`6s-g1n${j}`).value)).filter(n => n>0);
                if(s6_v.length === 6) m6S.push(s6_v);

                let html = ""; let m3 = 0, m4 = 0, m6 = 0; let f3 = false, f4 = false, f6 = false;
                let startNo3s = null; 

                for (let i = 0; i < recentHistory.length; i++) {
                    let hasJack3 = false;
                    m3S.forEach(sq => { if(sq.filter(n => recentHistory[i].nums.includes(n)).length === 3) hasJack3 = true; });
                    if(hasJack3) { if(i > 0) startNo3s = recentHistory[i-1].no; f3 = true; break; }
                }
                if(!f3 && recentHistory.length > 0) startNo3s = recentHistory[recentHistory.length - 1].no;

                f3 = false; 
                recentHistory.forEach((draw, idx) => {
                    let pPrize = 0; let details = []; let hBig3=false, hBig4=false, hBig6=false;
                    m3S.forEach(sq => { const h = sq.filter(n => draw.nums.includes(n)).length; if(h===2) {pPrize+=50; details.push('<span class="badge-graphical badge-3s">3中2</span>');} else if(h===3) {pPrize+=1000; details.push('<span class="badge-graphical badge-jackpot">🏆 3中3</span>'); hBig3=true;} });
                    m4S.forEach(sq => { const h = sq.filter(n => draw.nums.includes(n)).length; if(h===2) {pPrize+=25; details.push('<span class="badge-graphical badge-4s">4中2</span>');} else if(h===3) {pPrize+=150; details.push('<span class="badge-graphical badge-4s">4中3</span>');} else if(h===4) {pPrize+=2000; details.push('<span class="badge-graphical badge-jackpot">🏆 4中4</span>'); hBig4=true;} });
                    m6S.forEach(sq => { const h = sq.filter(n => draw.nums.includes(n)).length; if(h===3) {pPrize+=25; details.push('<span class="badge-graphical badge-6s">6中3</span>');} else if(h===4) {pPrize+=200; details.push('<span class="badge-graphical badge-6s">6中4</span>');} else if(h>=5) {pPrize+=1200; details.push('<span class="badge-graphical badge-jackpot">🏆 6星捷</span>'); hBig6=true;} });
                    if(!f3) { if(!hBig3) m3++; else f3 = true; }
                    if(!f4) { if(!hBig4) m4++; else f4 = true; }
                    if(!f6) { if(!hBig6) m6++; else f6 = true; }
                    const finalP = pPrize * multi;
                    const isStart3s = (draw.no === startNo3s);
                    let cardHtml = `<div class="p-4 rounded-[2rem] border transition-all ${isStart3s ? 'streak-start-3s' : 'bg-slate-50 dark:bg-slate-800/40 border-slate-100 dark:border-slate-800'}"><div class="flex justify-between items-center mb-3"><span class="text-[12px] font-black text-indigo-600 dark:text-indigo-400"># ${draw.no}</span><span class="text-[9px] opacity-40 font-mono italic underline underline-offset-4">${draw.time}</span></div><div class="flex flex-wrap gap-1.5 mb-3">`;
                    draw.nums.forEach(n => { const hit = m3S.some(s => s.includes(n)) || m4S.some(s => s.includes(n)) || m6S.some(s => s.includes(n)); cardHtml += `<span class="w-6 h-6 flex items-center justify-center text-[10px] rounded-full ${hit ? 'ball-hit' : 'bg-white dark:bg-slate-900 text-slate-300 dark:text-slate-600 border border-slate-100 dark:border-slate-800'}">${n.toString().padStart(2,'0')}</span>`; });
                    cardHtml += `</div><div class="flex justify-between items-center border-t dark:border-slate-700/50 pt-3"><div class="flex flex-wrap gap-1">${details.join('')}</div><div class="text-right"><span class="text-[12px] font-black ${finalP>0?'text-emerald-500':'text-slate-400 opacity-20'}">$ ${finalP.toLocaleString()}</span></div></div></div>`;
                    html += cardHtml;
                });
                document.getElementById('backtest-body').innerHTML = html;
                document.getElementById('bt-count-3s-live').innerText = m3; document.getElementById('bt-count-3s').innerText = m3;
                document.getElementById('bt-count-4s-live').innerText = m4; document.getElementById('bt-count-4s').innerText = m4;
                document.getElementById('bt-count-6s-live').innerText = m6; document.getElementById('bt-count-6s').innerText = m6;
                const alertClass = (count) => count >= 12 ? "bt-miss-alert px-4 py-1.5 rounded-xl text-[9px] font-black" : "bt-miss-normal px-4 py-1.5 rounded-xl text-[9px] font-black";
                document.getElementById('bt-box-3s').className = alertClass(m3); document.getElementById('bt-box-4s').className = alertClass(m4); document.getElementById('bt-box-6s').className = alertClass(m6);
            }

            function saveAndCompare() {
                const d = { s3: {}, s4: {}, s6: {} };
                for(let i=1; i<=10; i++) { d.s3[i] = [1,2,3].map(j => document.getElementById(`3s-g${i}n${j}`).value); d.s4[i] = [1,2,3,4].map(j => document.getElementById(`4s-g${i}n${j}`).value); }
                d.s6[1] = [1,2,3,4,5,6].map(j => document.getElementById(`6s-g1n${j}`).value);
                localStorage.setItem('bingo_v120_matrix', JSON.stringify(d)); executeComparison();
            }

            // 💡 修復：分佈圖亮燈與全中框標示邏輯
            function executeComparison() {
                // 1. 清除舊狀態
                document.querySelectorAll('.ball-all').forEach(el => { for(let i=1; i<=10; i++) el.classList.remove(`hit-g${i}`); });
                document.querySelectorAll('.dist-ball').forEach(el => el.classList.remove('active-3s', 'active-4s', 'active-6s'));
                for(let i=1; i<=10; i++) {
                    document.getElementById(`set-3s-${i}`)?.classList.remove('matrix-jackpot');
                    document.getElementById(`set-4s-${i}`)?.classList.remove('matrix-jackpot');
                }
                document.getElementById(`set-6s-1`)?.classList.remove('matrix-jackpot');

                let st = { s3_2: 0, s3_3: 0, s4_2: 0, s4_3: 0, s4_4: 0, s6_3:0, s6_4:0, s6_5:0, s6_6:0 }; 
                
                // 2. 處理 3 星與 4 星
                for(let i=1; i<=10; i++) {
                    // 三星分佈與中獎
                    const sq3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h3 = 0; 
                    sq3.forEach(n => { 
                        document.getElementById(`dist3s-${n}`)?.classList.add('active-3s');
                        if(winNums.includes(n)) { h3++; document.querySelector(`.ball-all[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } 
                    });
                    if(h3 === 2) st.s3_2++; else if(h3 === 3 && sq3.length === 3) { st.s3_3++; document.getElementById(`set-3s-${i}`).classList.add('matrix-jackpot'); }

                    // 四星分佈與中獎
                    const sq4 = [1,2,3,4].map(j => Number(document.getElementById(`4s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h4 = 0; 
                    sq4.forEach(n => { 
                        document.getElementById(`dist4s-${n}`)?.classList.add('active-4s');
                        if(winNums.includes(n)) h4++; 
                    });
                    if(h4 === 2) st.s4_2++; else if(h4 === 3) st.s4_3++; else if(h4 === 4 && sq4.length === 4) { st.s4_4++; document.getElementById(`set-4s-${i}`).classList.add('matrix-jackpot'); }
                }

                // 3. 處理 6 星
                const sq6 = [1,2,3,4,5,6].map(j => Number(document.getElementById(`6s-g1n${j}`).value)).filter(n => n > 0);
                let h6 = 0; 
                sq6.forEach(n => { 
                    document.getElementById(`dist6s-${n}`)?.classList.add('active-6s');
                    if(winNums.includes(n)) h6++; 
                });
                if(h6===3) st.s6_3++; else if(h6===4) st.s6_4++; else if(h6===5) st.s6_5++; else if(h6===6) { st.s6_6++; document.getElementById(`set-6s-1`).classList.add('matrix-jackpot'); }

                // 4. 更新看板數字
                document.getElementById('count-3s-2').innerText = st.s3_2; document.getElementById('count-3s-3').innerText = st.s3_3;
                document.getElementById('count-4s-2').innerText = st.s4_2; document.getElementById('count-4s-3').innerText = st.s4_3; document.getElementById('count-4s-4').innerText = st.s4_4;
                document.getElementById('count-6s-3').innerText = st.s6_3; document.getElementById('count-6s-4').innerText = st.s6_4;
                document.getElementById('count-6s-5').innerText = st.s6_5; document.getElementById('count-6s-6').innerText = st.s6_6;
                
                const c3 = document.getElementById('card-3s'); if(st.s3_3 > 0) c3.classList.add('alert-jackpot-glow'); else c3.classList.remove('alert-jackpot-glow');
                const c4 = document.getElementById('card-4s'); if(st.s4_4 > 0) c4.classList.add('alert-jackpot-glow'); else c4.classList.remove('alert-jackpot-glow');
                const c6 = document.getElementById('card-6s'); if(st.s6_5 > 0 || st.s6_6 > 0) c6.classList.add('alert-jackpot-glow'); else c6.classList.remove('alert-jackpot-glow');
                
                calculateProfit();
            }

            function init() {
                const isDark = localStorage.getItem('bingo_v120_dark') !== 'false';
                if(isDark) { document.documentElement.classList.add('dark'); updateThemeUI(true); }
                const s = localStorage.getItem('bingo_v120_matrix');
                if(s) { const d = JSON.parse(s); 
                    for(let i=1; i<=10; i++) { 
                        if(d.s3[i]) d.s3[i].forEach((v, j) => { if(document.getElementById(`3s-g${i}n${j+1}`)) document.getElementById(`3s-g${i}n${j+1}`).value = v; }); 
                        if(d.s4[i]) d.s4[i].forEach((v, j) => { if(document.getElementById(`4s-g${i}n${j+1}`)) document.getElementById(`4s-g${i}n${j+1}`).value = v; }); 
                    }
                    if(d.s6 && d.s6[1]) d.s6[1].forEach((v, j) => { if(document.getElementById(`6s-g1n${j+1}`)) document.getElementById(`6s-g1n${j+1}`).value = v; });
                }
                updateJournalDisplay(); executeComparison();
            }
            window.onload = init;
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(res_3star=res_3star, res_4star=res_4star, vip_6s=vip_6s, p_day=p_day, s_day=s_day, p_20=p_20, s_20=s_20, status=status, latest_win=latest_win, latest_no=latest_no, latest_time=latest_time, active_date=active_date, exclusive=exclusive, recent_history=recent_history)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
