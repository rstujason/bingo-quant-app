from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools
import json

app = FastAPI()

# --- 1. 核心量化分析邏輯 (V10.4：全中文化穩定版) ---

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
        return [], [], "0:0", "0:0", "0:0", "0:0", {}, [], "N/A", "--:--", target_date, []

    all_draws = []
    recent_history = [] 
    for item in full_raw_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: 
                all_draws.append(nums)
                if len(recent_history) < 10:
                    raw_date = item.get('OpenDate', '')
                    d_time = raw_date[11:16] if 'T' in raw_date else '--:--'
                    recent_history.append({"no": item.get('No'), "time": d_time, "nums": nums})
    
    latest_no = full_raw_data[0].get('No', 'N/A')
    raw_latest_date = full_raw_data[0].get('OpenDate', '')
    latest_time = raw_latest_date[11:16] if 'T' in raw_latest_date else '--:--'
    latest_win_nums = all_draws[0] if all_draws else []
    
    co_occ = Counter()
    for d in all_draws[:100]: 
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

    def generate_squads_smart(pool, size, count, exclusive, used_nos_ref):
        squads = []
        fingerprints = []
        sorted_seeds = sorted(pool, key=lambda x: x['score'], reverse=True)[:count]
        for i, seed in enumerate(sorted_seeds):
            seed_no = seed['no']
            avoid = used_nos_ref if exclusive else {seed_no}
            all_partners = sorted([p for p in pool if p['no'] not in avoid and p['no'] != seed_no], 
                                 key=lambda x: (get_synergy(seed_no, x['no']), x['score']), reverse=True)
            p_idx = size - 1
            cur_squad = sorted([seed_no] + [p['no'] for p in all_partners[:p_idx]])
            while cur_squad in fingerprints and p_idx < len(all_partners):
                cur_squad = sorted([seed_no] + [p['no'] for p in all_partners[:p_idx-1]] + [all_partners[p_idx]['no']])
                p_idx += 1
            fingerprints.append(cur_squad)
            if exclusive:
                for n in cur_squad: used_nos_ref.add(n)
            squads.append({"id": i+1, "picks": cur_squad})
        return squads

    global_used = set()
    res_3star = generate_squads_smart(all_analysis, 3, 10, mode_exclusive, global_used)
    res_4star = generate_squads_smart(all_analysis, 4, 10, mode_exclusive, global_used)

    today_draws = [[int(x) for x in item.get('BigShowOrder','').split(',') if x.strip().isdigit()] for item in data_today if item.get('BigShowOrder','')]
    today_balls = [n for d in today_draws if len(d)==20 for n in d]
    p_day = f"{len([n for n in today_balls if n%2!=0])}:{len(today_balls)-len([n for n in today_balls if n%2!=0])}"
    s_day = f"{len([n for n in today_balls if n<=40])}:{len(today_balls)-len([n for n in today_balls if n<=40])}"

    return (res_3star, res_4star, p_day, s_day, f"{o_20}:{e_20}", f"{s_20}:{b_20}", status, latest_win_nums, latest_no, latest_time, target_date, recent_history)

# --- 2. 網頁前端 (全中文化 UI) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None, exclusive: bool = True):
    (res_3star, res_4star, p_day, s_day, p_20, s_20, status, latest_win, latest_no, latest_time, active_date, recent_history) = get_data_and_analyze(date, exclusive)
    
    html_content = """
    <html>
    <head>
        <title>賓狗正式版v1.0</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
            body { font-family: 'Noto Sans TC', sans-serif; }
            .hit-g1 { background-color: #ef4444 !important; color: white !important; }
            .hit-g2 { background-color: #f97316 !important; color: white !important; }
            .hit-g3 { background-color: #f59e0b !important; color: white !important; }
            .hit-g4 { background-color: #84cc16 !important; color: white !important; }
            .hit-g5 { background-color: #10b981 !important; color: white !important; }
            .hit-g6 { background-color: #06b6d4 !important; color: white !important; }
            .hit-g7 { background-color: #3b82f6 !important; color: white !important; }
            .hit-g8 { background-color: #6366f1 !important; color: white !important; }
            .hit-g9 { background-color: #8b5cf6 !important; color: white !important; }
            .hit-g10 { background-color: #d946ef !important; color: white !important; }
            .latest-ball { background: #f1f5f9; color: #475569; font-weight: 900; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 11px; border: 1px solid #e2e8f0; }
            .stat-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); padding: 8px; border-radius: 12px; text-align: center; }
            .alert-gold { animation: gold-blink 1s infinite alternate; }
            @keyframes gold-blink { from { background: #1e293b; } to { background: #f59e0b; } }
            .dist-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 3px; background: #fefce8; padding: 10px; border-radius: 16px; border: 2px solid #fde047; }
            .dist-ball { background: #ffffff; color: #64748b; font-weight: 900; font-size: 9px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 6px; border: 1px solid #e2e8f0; }
            .active-3s { background: #f59e0b !important; color: white !important; box-shadow: 0 0 8px #f59e0b; }
            .active-4s { background: #6366f1 !important; color: white !important; box-shadow: 0 0 8px #6366f1; }
            .profit-input { background: #f8fafc; border: 1px solid #e2e8f0; color: #1e293b; text-align: center; border-radius: 8px; font-weight: 900; width: 100%; height: 32px; }
            .timer-pill { background: #0f172a; color: #38bdf8; font-size: 8px; font-weight: 900; padding: 2px 8px; border-radius: 20px; }
            .switch { position: relative; display: inline-block; width: 40px; height: 20px; }
            .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 20px; }
            .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
            input:checked + .slider { background-color: #6366f1; }
            input:checked + .slider:before { transform: translateX(20px); }
            .ball-hit { background-color: #fbbf24 !important; color: #451a03 !important; font-weight: 900; border-color: #f59e0b; }
            .hit-pill { background: #f1f5f9; color: #64748b; padding: 1px 6px; border-radius: 4px; font-size: 8px; font-weight: 900; border: 1px solid #e2e8f0; }
            .hit-pill-jackpot { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
            .bt-miss-normal { background: #1e293b; color: #94a3b8; }
            .bt-miss-alert { background: #be123c; color: white; animation: pulse-red 1s infinite alternate; }
            @keyframes pulse-red { from { transform: scale(1); } to { transform: scale(1.05); } }
        </style>
    </head>
    <body class="bg-slate-50 text-slate-900 pb-20 text-[12px]">
        <div class="max-w-6xl mx-auto p-4 md:p-8">
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-indigo-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-indigo-400">
                    <div class="flex justify-between items-center mb-4 text-[10px] font-black uppercase">奇偶監控{% if status.odd or status.even %}<span class="bg-green-500 text-[8px] px-2 py-0.5 rounded ml-2 animate-pulse">補償機制已啟動</span>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日全日累計</p><p class="text-lg font-black tracking-tighter">奇 {{ p_day }} 偶</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline underline-offset-4">最近 20 期</p><p class="text-xl font-black text-amber-300">{{ p_20 }}</p></div>
                    </div>
                </div>
                <div class="bg-emerald-700 text-white p-6 rounded-[2rem] shadow-xl border-2 border-emerald-400">
                    <div class="flex justify-between items-center mb-4 text-[10px] font-black uppercase">大小監控{% if status.small or status.big %}<span class="bg-green-500 text-[8px] px-2 py-0.5 rounded ml-2 animate-pulse">補償機制已啟動</span>{% endif %}</div>
                    <div class="grid grid-cols-2 gap-4 border-t border-white/10 pt-4 text-center italic">
                        <div><p class="text-[8px] opacity-60">今日全日累計</p><p class="text-lg font-black tracking-tighter">小 {{ s_day }} 大</p></div>
                        <div class="border-l border-white/10"><p class="text-[8px] text-amber-300 font-bold underline underline-offset-4">最近 20 期</p><p class="text-xl font-black text-amber-300">{{ s_20 }}</p></div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-10">
                <div class="lg:col-span-3 bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                    <div class="flex justify-between items-center mb-6 border-b pb-4 italic text-slate-400">
                        <div class="flex items-center gap-3">
                            <h3 class="text-xs font-black uppercase tracking-widest">📢 最新開獎: <span class="text-indigo-600 font-mono tracking-normal">{{ latest_no }} <span class="text-slate-400">({{ latest_time }})</span></span></h3>
                            <div class="timer-pill" id="reload-timer">自動刷新: 7:00</div>
                        </div>
                        <button onclick="location.reload()" class="bg-indigo-500 text-white px-4 py-1.5 rounded-xl text-[10px] font-black shadow-lg active:scale-95 transition-transform">立即刷新數據</button>
                    </div>
                    <div class="space-y-6 text-center">
                        <div><p class="text-[9px] font-black text-amber-500 mb-2 uppercase tracking-widest underline underline-offset-4">三星策略即時追蹤</p>
                            <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-3s" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                        </div>
                        <div><p class="text-[9px] font-black text-indigo-500 mb-2 uppercase tracking-widest underline underline-offset-4">四星策略即時追蹤</p>
                            <div class="flex flex-wrap gap-2 justify-center">{% for n in latest_win %}<div class="latest-ball ball-4s" data-val="{{ n }}">{{ "%02d" | format(n) }}</div>{% endfor %}</div>
                        </div>
                    </div>
                </div>
                <div class="bg-slate-900 p-5 rounded-3xl shadow-xl border-4 border-slate-800 text-white">
                    <h4 class="text-center text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-4 italic">戰報分析中心</h4>
                    <div class="space-y-4">
                        <div class="bg-slate-800/50 p-3 rounded-2xl border border-slate-700">
                            <p class="text-[7px] font-black text-amber-500 mb-2 uppercase tracking-widest">三星統計</p>
                            <div class="grid grid-cols-2 gap-2">
                                <div class="stat-card"><p class="text-[6px] text-slate-400 uppercase">中 2</p><p class="text-lg font-black" id="count-3s-2">0</p></div>
                                <div class="stat-card" id="alert-3s-all"><p class="text-[6px] text-slate-400 uppercase">全中 (3)</p><p class="text-lg font-black text-amber-400" id="count-3s-3">0</p></div>
                            </div>
                        </div>
                        <div class="bg-slate-800/50 p-3 rounded-2xl border border-slate-700">
                            <p class="text-[7px] font-black text-indigo-400 mb-2 uppercase tracking-widest">四星統計</p>
                            <div class="grid grid-cols-3 gap-1">
                                <div class="stat-card"><p class="text-[6px] text-slate-400 uppercase">中 2</p><p class="text-md font-black" id="count-4s-2">0</p></div>
                                <div class="stat-card"><p class="text-[6px] text-slate-400 uppercase">中 3</p><p class="text-md font-black" id="count-4s-3">0</p></div>
                                <div class="stat-card" id="alert-4s-all"><p class="text-[6px] text-slate-400 uppercase">全中 (4)</p><p class="text-md font-black text-amber-400" id="count-4s-4">0</p></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-emerald-900/90 p-8 rounded-[3rem] shadow-2xl text-white mb-10 border-4 border-emerald-800">
                <div class="flex justify-between items-center mb-8 border-b border-emerald-700 pb-4">
                    <div class="flex items-center gap-3"><div class="w-2 h-6 bg-emerald-400 rounded-full"></div><h3 class="text-[11px] font-black uppercase tracking-[0.3em] italic">今日實戰總計 (Daily Journal)</h3></div>
                    <button onclick="resetDailyJournal()" class="text-[8px] bg-red-900/50 px-3 py-1 rounded-full font-black uppercase">清空今日日誌</button>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="bg-black/10 p-5 rounded-3xl text-center border border-white/5"><p class="text-[9px] text-emerald-300 uppercase font-black mb-1">今日總投入成本</p><p class="text-2xl font-mono font-black" id="day-total-cost">$ 0</p></div>
                    <div class="bg-black/10 p-5 rounded-3xl text-center border border-white/5"><p class="text-[9px] text-emerald-300 uppercase font-black mb-1">今日累積總獎金</p><p class="text-2xl font-mono font-black" id="day-total-prize">$ 0</p></div>
                    <div class="bg-emerald-500 text-emerald-950 p-5 rounded-3xl text-center shadow-lg border-2 border-emerald-400"><p class="text-[9px] uppercase font-black mb-1 italic">今日整日純利結算</p><p class="text-3xl font-mono font-black" id="day-net-profit">$ 0</p></div>
                </div>
            </div>

            <div class="bg-white p-8 rounded-[3.5rem] shadow-xl border border-slate-200 mb-10">
                <div class="flex justify-between items-center mb-6">
                    <div class="flex items-center gap-2"><span class="text-lg">💰</span><h3 class="text-sm font-black text-slate-800 italic uppercase">本場場次規劃 (Investment Planner)</h3></div>
                    <button onclick="postToDailyJournal()" class="bg-emerald-600 text-white px-6 py-2 rounded-2xl text-[10px] font-black shadow-lg uppercase transition-all active:scale-95">存入今日日誌系統</button>
                </div>
                <div class="grid grid-cols-3 gap-4 mb-8 text-center">
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-100"><p class="text-[9px] text-slate-400 font-black mb-1">本場成本 (Cost)</p><p class="text-xl font-black text-rose-500" id="display-total-cost">-$ 0</p></div>
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-100"><p class="text-[9px] text-slate-400 font-black mb-1">本場獎金 (Prize)</p><p class="text-xl font-black text-indigo-600" id="display-total-prize">+$ 0</p></div>
                    <div class="bg-indigo-50 p-4 rounded-2xl border-2 border-indigo-100 shadow-inner"><p class="text-[9px] text-indigo-600 font-black mb-1 italic">本場純利 (Net Profit)</p><p class="text-xl font-black text-indigo-700" id="display-net-profit">$ 0</p></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div class="space-y-3 border-r pr-6">
                        <div><label class="text-[8px] font-black text-slate-400">單注倍數 (Multiplier)</label><input type="number" id="in-multiplier" class="profit-input" value="1" oninput="calculateProfit()"></div>
                        <div><label class="text-[8px] font-black text-slate-400">追號期數 (Periods)</label><input type="number" id="in-periods" class="profit-input" value="1" oninput="calculateProfit()"></div>
                        <div><label class="text-[8px] font-black text-slate-400">購買組數 (Sets)</label><input type="number" id="in-sets" class="profit-input" value="10" oninput="calculateProfit()"></div>
                    </div>
                    <div class="space-y-4 px-2 text-center">
                        <p class="text-[9px] font-black text-amber-500 uppercase italic border-b">三星中獎紀錄 (50, 1k)</p>
                        <div class="grid grid-cols-2 gap-2 mt-2">
                            <div><label class="text-[8px] text-slate-400">三中二 (次)</label><input type="number" id="in-3h2" class="profit-input" placeholder="0" oninput="calculateProfit()"></div>
                            <div><label class="text-[8px] text-slate-400">三中三 (次)</label><input type="number" id="in-3h3" class="profit-input" placeholder="0" oninput="calculateProfit()"></div>
                        </div>
                    </div>
                    <div class="md:col-span-2 space-y-4 px-2 text-center">
                        <p class="text-[9px] font-black text-indigo-500 uppercase italic border-b">四星中獎紀錄 (25, 150, 2k)</p>
                        <div class="grid grid-cols-3 gap-2 mt-2">
                            <div><label class="text-[8px] text-slate-400">四中二 (次)</label><input type="number" id="in-4h2" class="profit-input" placeholder="0" oninput="calculateProfit()"></div>
                            <div><label class="text-[8px] text-slate-400">四中三 (次)</label><input type="number" id="in-4h3" class="profit-input" placeholder="0" oninput="calculateProfit()"></div>
                            <div><label class="text-[8px] text-slate-400">四中四 (次)</label><input type="number" id="in-4h4" class="profit-input" placeholder="0" oninput="calculateProfit()"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10 text-center">
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100"><h3 class="text-[10px] font-black text-amber-600 uppercase mb-4 italic">📡 三星號碼佈陣分佈圖</h3><div class="dist-grid">{% for i in range(1, 81) %}<div class="dist-ball" id="dist3s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div></div>
                <div class="bg-white p-6 rounded-[2.5rem] shadow-sm border border-slate-100"><h3 class="text-[10px] font-black text-indigo-600 uppercase mb-4 italic">📡 四星號碼佈陣分佈圖</h3><div class="dist-grid">{% for i in range(1, 81) %}<div class="dist-ball" id="dist4s-{{i}}">{{ "%02d" | format(i) }}</div>{% endfor %}</div></div>
            </div>

            <div class="space-y-8 mb-10">
                <div class="bg-slate-900 p-8 rounded-[3.5rem] shadow-2xl border-4 border-slate-800">
                    <div class="flex justify-between items-center mb-6 px-2 text-amber-400 uppercase italic font-black"><h3 class="text-[10px] tracking-widest">三星對獎矩陣 (3-Star Matrix)</h3><div class="flex gap-2"><button onclick="loadAll('3s')" class="bg-green-700 text-white px-4 py-1 rounded-md text-[8px] uppercase">一鍵裝載</button><button onclick="clearMatrix('3s')" class="bg-red-900 text-white px-4 py-1 rounded-md text-[8px] uppercase">清除欄位</button></div></div>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">{% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-slate-500 italic uppercase">組合 {{ i }}</p><div class="flex gap-1">{% for j in range(1, 4) %}<input type="text" id="3s-g{{i}}n{{j}}" class="w-full h-8 text-center text-sm font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}</div>
                </div>
                <div class="bg-slate-900 p-8 rounded-[3.5rem] shadow-2xl border-4 border-slate-800">
                    <div class="flex justify-between items-center mb-6 px-2 text-indigo-400 uppercase italic font-black"><h3 class="text-[10px] tracking-widest">四星對獎矩陣 (4-Star Matrix)</h3><div class="flex gap-2"><button onclick="loadAll('4s')" class="bg-indigo-700 text-white px-4 py-1 rounded-md text-[8px] uppercase">一鍵裝載</button><button onclick="clearMatrix('4s')" class="bg-red-900 text-white px-4 py-1 rounded-md text-[8px] uppercase">清除欄位</button></div></div>
                    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">{% for i in range(1, 11) %}<div class="bg-slate-800/50 p-2 rounded-xl border border-slate-700 text-center"><p class="text-[7px] text-indigo-300 italic uppercase">小隊 {{ i }}</p><div class="flex gap-1">{% for j in range(1, 5) %}<input type="text" id="4s-g{{i}}n{{j}}" class="w-full h-8 text-center text-xs font-black bg-slate-900 rounded border border-slate-600 text-white" oninput="saveAndCompare()">{% endfor %}</div></div>{% endfor %}</div>
                </div>
            </div>

            <div class="mb-20">
                <div class="flex justify-between items-center mb-6 px-2 border-b pb-4"><h2 class="text-sm font-black text-slate-800 uppercase italic border-l-4 border-indigo-500 pl-3">🚀 智慧量化策略小隊 (V10.4)</h2><div class="flex items-center gap-2"><span class="text-[9px] font-black text-slate-500 uppercase">高覆蓋率模式開關</span><label class="switch"><input type="checkbox" id="exclusive-toggle" {% if exclusive %}checked{% endif %} onchange="toggleExclusive()"><span class="slider"></span></label></div></div>
                <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10">
                    {% for sq in res_3star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black uppercase">組別 {{ sq.id }} (3S)<div class="flex justify-center gap-1 my-2">{% for n in sq.picks %}<span class="bg-slate-900 text-white px-1.5 rounded">{{ "%02d" | format(n) }}</span>{% endfor %}</div><button onclick='quickFill("3s", {{ sq.id }}, {{ sq.picks | tojson }})' class="w-full bg-amber-50 text-amber-600 py-1 rounded italic font-black uppercase">裝載</button></div>{% endfor %}
                    {% for sq in res_4star %}<div class="bg-white p-3 rounded-2xl shadow-sm border border-slate-100 text-center text-[9px] font-black uppercase text-indigo-400">小隊 {{ sq.id }} (4S)<div class="flex justify-center gap-1 my-2">{% for n in sq.picks %}<span class="bg-slate-900 text-white px-1 rounded">{{ "%02d" | format(n) }}</span>{% endfor %}</div><button onclick='quickFill("4s", {{ sq.id }}, {{ sq.picks | tojson }})' class="w-full bg-indigo-50 text-indigo-600 py-1 rounded italic font-black uppercase">裝載</button></div>{% endfor %}
                </div>

                <div class="bg-white p-8 rounded-[3.5rem] shadow-xl border border-slate-200">
                    <div class="flex justify-between items-center mb-6 border-b pb-4">
                        <h3 class="text-sm font-black text-slate-800 uppercase italic tracking-widest">🕰️ 過去 10 期歷史回測戰果明細</h3>
                        <div class="flex gap-4">
                            <div id="bt-box-3s" class="bt-miss-normal px-4 py-1.5 rounded-xl text-[9px] font-black uppercase transition-all">三星連黑期數: <span id="bt-count-3s">0</span></div>
                            <div id="bt-box-4s" class="bt-miss-normal px-4 py-1.5 rounded-xl text-[9px] font-black uppercase transition-all">四星連黑期數: <span id="bt-count-4s">0</span></div>
                        </div>
                    </div>
                    <div class="overflow-hidden rounded-3xl border border-slate-100">
                        <table class="w-full text-left text-[10px]">
                            <thead class="bg-slate-900 text-white text-[9px] uppercase font-black tracking-widest">
                                <tr><th class="p-4">開獎期數與時間</th><th class="p-4">開獎號碼 (命中分析)</th><th class="p-4 text-right">命中明細與理論獎金</th></tr>
                            </thead>
                            <tbody id="backtest-body" class="font-mono italic"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const server3S = {{ res_3star | tojson }};
            const server4S = {{ res_4star | tojson }};
            const recentHistory = {{ recent_history | tojson }};
            const winNums = {{ latest_win | tojson }};

            // --- 🕰️ 中文回測邏輯 ---
            function runBacktest() {
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const m3S = []; const m4S = [];
                for(let i=1; i<=10; i++) {
                    const s3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n>0);
                    const s4 = [1,2,3,4].map(j => Number(document.getElementById(`4s-g${i}n${j}`).value)).filter(n => n>0);
                    if(s3.length === 3) m3S.push(s3); if(s4.length === 4) m4S.push(s4);
                }
                let html = ""; let m3 = 0, m4 = 0; let f3 = false, f4 = false;
                recentHistory.forEach((draw) => {
                    let pPrize = 0; let details = []; let hS = { s3h2:0, s3h3:0, s4h2:0, s4h3:0, s4h4:0 };
                    let hasJack3 = false, hasJack4 = false;
                    m3S.forEach(sq => { const h = sq.filter(n => draw.nums.includes(n)).length; if(h===2){ hS.s3h2++; pPrize+=50; } else if(h===3){ hS.s3h3++; pPrize+=1000; hasJack3=true; } });
                    m4S.forEach(sq => { const h = sq.filter(n => draw.nums.includes(n)).length; if(h===2){ hS.s4h2++; pPrize+=25; } else if(h===3){ hS.s4h3++; pPrize+=150; } else if(h===4){ hS.s4h4++; pPrize+=2000; hasJack4=true; } });
                    if(!f3) { if(!hasJack3) m3++; else f3 = true; }
                    if(!f4) { if(!hasJack4) m4++; else f4 = true; }
                    if(hS.s3h2 > 0) details.push(`<span class="hit-pill">3中2 x${hS.s3h2}</span>`);
                    if(hS.s3h3 > 0) details.push(`<span class="hit-pill hit-pill-jackpot">3中3 x${hS.s3h3}</span>`);
                    if(hS.s4h2 > 0) details.push(`<span class="hit-pill">4中2 x${hS.s4h2}</span>`);
                    if(hS.s4h3 > 0) details.push(`<span class="hit-pill">4中3 x${hS.s4h3}</span>`);
                    if(hS.s4h4 > 0) details.push(`<span class="hit-pill hit-pill-jackpot">4中4 x${hS.s4h4}</span>`);
                    const finalP = pPrize * multi;
                    html += `<tr class="history-row border-b border-slate-50"><td class="p-4 font-black text-indigo-600">${draw.no} <span class="text-slate-300 font-normal">(${draw.time})</span></td><td class="p-4"><div class="flex flex-wrap gap-1">`;
                    draw.nums.forEach(n => { const hit = m3S.some(s => s.includes(n)) || m4S.some(s => s.includes(n)); html += `<span class="w-6 h-6 flex items-center justify-center rounded-full text-[8px] ${hit ? 'ball-hit' : 'bg-slate-100 text-slate-400'}">${n.toString().padStart(2,'0')}</span>`; });
                    html += `</div></td><td class="p-4 text-right"><div class="flex flex-wrap justify-end gap-1 mb-1">${details.join('')}</div><p class="font-black text-xs ${finalP>0?'text-indigo-600':'text-slate-200'}">$ ${finalP.toLocaleString()}</p></td></tr>`;
                });
                document.getElementById('backtest-body').innerHTML = html;
                document.getElementById('bt-count-3s').innerText = m3; document.getElementById('bt-count-4s').innerText = m4;
                document.getElementById('bt-box-3s').className = m3>5 ? "bt-miss-alert px-4 py-1.5 rounded-xl text-[9px] font-black transition-all" : "bt-miss-normal px-4 py-1.5 rounded-xl text-[9px] font-black transition-all";
                document.getElementById('bt-box-4s').className = m4>5 ? "bt-miss-alert px-4 py-1.5 rounded-xl text-[9px] font-black transition-all" : "bt-miss-normal px-4 py-1.5 rounded-xl text-[9px] font-black transition-all";
            }

            // --- 💰 財務中心 ---
            function calculateProfit() {
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const periods = parseInt(document.getElementById('in-periods').value) || 1;
                const sets = parseInt(document.getElementById('in-sets').value) || 0;
                const cost = sets * periods * multi * 25;
                const prize = ( (parseInt(document.getElementById('in-3h2').value)||0)*50 + (parseInt(document.getElementById('in-3h3').value)||0)*1000 + (parseInt(document.getElementById('in-4h2').value)||0)*25 + (parseInt(document.getElementById('in-4h3').value)||0)*150 + (parseInt(document.getElementById('in-4h4').value)||0)*2000 ) * multi;
                const net = prize - cost;
                document.getElementById('display-total-cost').innerText = "-$ " + cost.toLocaleString();
                document.getElementById('display-total-prize').innerText = "+$ " + prize.toLocaleString();
                const nd = document.getElementById('display-net-profit'); nd.innerText = (net>=0?"+$ ": "-$ ")+Math.abs(net).toLocaleString();
                nd.className = net>=0?"text-xl font-black text-indigo-700":"text-xl font-black text-rose-500";
                const pData = { multi, periods, sets, s3h2: document.getElementById('in-3h2').value, s3h3: document.getElementById('in-3h3').value, s4h2: document.getElementById('in-4h2').value, s4h3: document.getElementById('in-4h3').value, s4h4: document.getElementById('in-4h4').value };
                localStorage.setItem('bingo_profit_v104', JSON.stringify(pData)); runBacktest(); 
            }

            function postToDailyJournal() {
                let log = JSON.parse(localStorage.getItem('bingo_journal_v104') || '{"cost":0, "prize":0}');
                const multi = parseInt(document.getElementById('in-multiplier').value) || 1;
                const cost = (parseInt(document.getElementById('in-sets').value) || 0) * (parseInt(document.getElementById('in-periods').value) || 1) * multi * 25;
                const prize = ( (parseInt(document.getElementById('in-3h2').value)||0)*50 + (parseInt(document.getElementById('in-3h3').value)||0)*1000 + (parseInt(document.getElementById('in-4h2').value)||0)*25 + (parseInt(document.getElementById('in-4h3').value)||0)*150 + (parseInt(document.getElementById('in-4h4').value)||0)*2000 ) * multi;
                log.cost += cost; log.prize += prize;
                localStorage.setItem('bingo_journal_v104', JSON.stringify(log)); updateJournalDisplay(); alert("數據已存入今日實戰日誌！");
            }

            function updateJournalDisplay() {
                const log = JSON.parse(localStorage.getItem('bingo_journal_v104') || '{"cost":0, "prize":0}');
                const net = log.prize - log.cost;
                document.getElementById('day-total-cost').innerText = "$ " + log.cost.toLocaleString();
                document.getElementById('day-total-prize').innerText = "$ " + log.prize.toLocaleString();
                const nd = document.getElementById('day-net-profit'); nd.innerText = (net>=0?"+$ ": "-$ ")+Math.abs(net).toLocaleString();
                nd.className = net>=0?"text-3xl font-mono font-black text-emerald-950":"text-3xl font-mono font-black text-rose-900";
            }

            function loadAll(t) { (t === '3s' ? server3S : server4S).forEach(sq => { sq.picks.forEach((n, idx) => { const el = document.getElementById(`${t}-g${sq.id}n${idx+1}`); if(el) el.value = n.toString().padStart(2, '0'); }); }); saveAndCompare(); }
            function clearMatrix(t) { const sz = (t === '3s') ? 3 : 4; for(let i=1; i<=10; i++) { for(let j=1; j<=sz; j++) document.getElementById(`${t}-g${i}n${j}`).value = ""; } saveAndCompare(); }
            function quickFill(t, id, ns) { ns.forEach((n, j) => document.getElementById(`${t}-g${id}n${j+1}`).value = n.toString().padStart(2, '0')); saveAndCompare(); }
            function toggleExclusive() { window.location.href = `/?exclusive=${document.getElementById('exclusive-toggle').checked}`; }
            function saveAndCompare() {
                const d = { s3: {}, s4: {} };
                for(let i=1; i<=10; i++) { d.s3[i] = [1,2,3].map(j => document.getElementById(`3s-g${i}n${j}`).value); d.s4[i] = [1,2,3,4].map(j => document.getElementById(`4s-g${i}n${j}`).value); }
                localStorage.setItem('bingo_v104_matrix', JSON.stringify(d)); executeComparison(); runBacktest();
            }
            function executeComparison() {
                document.querySelectorAll('.latest-ball').forEach(el => { for(let i=1; i<=10; i++) el.classList.remove(`hit-g${i}`); });
                document.querySelectorAll('.dist-ball').forEach(el => el.classList.remove('active-3s', 'active-4s'));
                let st = { s3_2: 0, s3_3: 0, s4_2: 0, s4_3: 0, s4_4: 0 }; let u3 = new Set(), u4 = new Set();
                for(let i=1; i<=10; i++) {
                    const sq3 = [1,2,3].map(j => Number(document.getElementById(`3s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h3 = 0; sq3.forEach(n => { if(winNums.includes(n)) { h3++; document.querySelector(`.ball-3s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } u3.add(n); });
                    if(h3 === 2) st.s3_2++; else if(h3 === 3 && sq3.length === 3) st.s3_3++;
                    const sq4 = [1,2,3,4].map(j => Number(document.getElementById(`4s-g${i}n${j}`).value)).filter(n => n > 0);
                    let h4 = 0; sq4.forEach(n => { if(winNums.includes(n)) { h4++; document.querySelector(`.ball-4s[data-val="${n}"]`)?.classList.add(`hit-g${i}`); } u4.add(n); });
                    if(h4 === 2) st.s4_2++; else if(h4 === 3) st.s4_3++; else if(h4 === 4 && sq4.length === 4) st.s4_4++;
                }
                u3.forEach(n => { if(n>=1 && n<=80) document.getElementById('dist3s-'+n)?.classList.add('active-3s'); });
                u4.forEach(n => { if(n>=1 && n<=80) document.getElementById('dist4s-'+n)?.classList.add('active-4s'); });
                document.getElementById('count-3s-2').innerText = st.s3_2; document.getElementById('count-3s-3').innerText = st.s3_3;
                document.getElementById('count-4s-2').innerText = st.s4_2; document.getElementById('count-4s-3').innerText = st.s4_3; document.getElementById('count-4s-4').innerText = st.s4_4;
                if(st.s3_3 > 0) document.getElementById('alert-3s-all').classList.add('alert-gold'); else document.getElementById('alert-3s-all').classList.remove('alert-gold');
                if(st.s4_4 > 0) document.getElementById('alert-4s-all').classList.add('alert-gold'); else document.getElementById('alert-4s-all').classList.remove('alert-gold');
            }
            function resetDailyJournal() { if(confirm("確定要清空今日實戰總計數據嗎？")) { localStorage.setItem('bingo_journal_v104', '{"cost":0, "prize":0}'); updateJournalDisplay(); } }

            let timeLeft = 420;
            setInterval(() => {
                const min = Math.floor(timeLeft / 60); const sec = timeLeft % 60;
                document.getElementById('reload-timer').innerText = `自動刷新: ${min}:${sec.toString().padStart(2, '0')}`;
                if (timeLeft <= 0) { location.reload(); }
                timeLeft--;
            }, 1000);

            function init() {
                const s = localStorage.getItem('bingo_v104_matrix');
                if(s) { const d = JSON.parse(s); for(let i=1; i<=10; i++) { if(d.s3[i]) d.s3[i].forEach((v, j) => { const el = document.getElementById(`3s-g${i}n${j+1}`); if(el) el.value = v; }); if(d.s4[i]) d.s4[i].forEach((v, j) => { const el = document.getElementById(`4s-g${i}n${j+1}`); if(el) el.value = v; }); } }
                const sp = localStorage.getItem('bingo_profit_v104');
                if(sp) { const d = JSON.parse(sp); document.getElementById('in-multiplier').value = d.multi; document.getElementById('in-periods').value = d.periods; document.getElementById('in-sets').value = d.sets; ['3h2','3h3','4h2','4h3','4h4'].forEach(k => { const el = document.getElementById('in-'+k); if(el) el.value = d['s'+k]||""; }); calculateProfit(); }
                updateJournalDisplay(); executeComparison(); runBacktest();
            }
            window.onload = init;
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(res_3star=res_3star, res_4star=res_4star, p_day=p_day, s_day=s_day, p_20=p_20, s_20=s_20, status=status, latest_win=latest_win, latest_no=latest_no, latest_time=latest_time, active_date=active_date, exclusive=exclusive, recent_history=recent_history)

if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)











