from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn
import itertools

app = FastAPI()

# --- 1. 核心量化與特性分析邏輯 ---

def get_data_and_analyze():
    """執行全策略分析並加入組合特性分類"""
    now = datetime.datetime.now()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://winwin.tw/Bingo',
        'X-Requested-With': 'XMLHttpRequest'
    }

    def fetch_api(date_str):
        target_url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
        try:
            resp = requests.get(target_url, headers=headers, timeout=10)
            return resp.json() if resp.status_code == 200 else None
        except: return None

    # 自動日期回溯邏輯
    api_data = fetch_api(now.strftime("%Y-%m-%d"))
    if not api_data:
        api_data = fetch_api((now - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))

    if not api_data: return None, "無資料", "穩定"

    period_range = f"{api_data[0].get('No', 'N/A')} ~ {api_data[min(29, len(api_data)-1)].get('No', 'N/A')}"
    
    all_draws = []
    for item in api_data:
        draw_str = item.get('BigShowOrder', '')
        if draw_str:
            nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
            if len(nums) == 20: all_draws.append(nums)
    if not all_draws: return None, period_range, "等待數據"

    # --- 策略 A: 奇偶回歸與權重 ---
    recent_20 = all_draws[:20]
    total_nums_20 = [n for d in recent_20 for n in d]
    o_count = len([n for n in total_nums_20 if n % 2 != 0])
    e_count = 400 - o_count
    
    odd_weight = 1.2 if e_count > o_count else 1.0
    even_weight = 1.2 if o_count > e_count else 1.0
    parity_status = f"奇{o_count} : 偶{e_count}"

    # --- 策略 B: 拖牌矩陣計算 ---
    co_occurrence = Counter()
    for draw in all_draws[:50]:
        for pair in itertools.combinations(sorted(draw), 2):
            co_occurrence[pair] += 1
    
    last_draw = all_draws[0]
    drag_scores = Counter()
    for num in range(1, 81):
        for last_num in last_draw:
            pair = tuple(sorted((num, last_num)))
            drag_scores[num] += co_occurrence.get(pair, 0)

    # --- 策略 C: 綜合評分與反向熱度 ---
    short_term_heat = Counter([n for d in all_draws[:15] for n in d])
    long_term_freq = Counter([n for d in all_draws[:50] for n in d])
    repeat_pool = set(all_draws[0])
    
    analysis_list = []
    for i in range(1, 81):
        score = long_term_freq[i] * 1.0
        if i in repeat_pool: score += 5.0
        score *= (odd_weight if i % 2 != 0 else even_weight)
        score -= (short_term_heat[i] * 2.0)
        score += (drag_scores[i] * 0.1)
        
        analysis_list.append({
            'no': i, 'repeat': "是" if i in repeat_pool else "否",
            'score': score, 'drag': drag_scores[i], 'omission': next((idx for idx, d in enumerate(all_draws) if i in d), 99)
        })

    # --- 策略 D: 組合生成與特性描述 ---
    sorted_candidates = sorted(analysis_list, key=lambda x: x['score'], reverse=True)
    used_nums = set()
    groups = []
    group_names = ["第一組 (核心)", "第二組 (潛力)", "第三組 (平衡)"]

    for name in group_names:
        current_picks = []
        for p in sorted_candidates:
            if p['no'] not in used_nums and len(current_picks) < 4:
                sections = Counter([(n['no']-1)//20 for n in current_picks] + [(p['no']-1)//20])
                if any(c > 2 for c in sections.values()): continue
                current_picks.append(p)
                used_nums.add(p['no'])
        
        # --- 新增：組合特性分析邏輯 ---
        p_nums = [p['no'] for p in current_picks]
        drag_vals = [p['drag'] for p in current_picks]
        avg_drag = sum(drag_vals) / 4
        drag_diff = max(drag_vals) - min(drag_vals)
        
        # 分類邏輯
        if avg_drag > 50 and drag_diff < 30:
            type_desc = "趨勢追蹤型"
            type_color = "text-emerald-600"
        elif avg_drag < 30:
            type_desc = "機率補償型"
            type_color = "text-rose-600"
        elif drag_diff > 40:
            type_desc = "冷熱平衡型"
            type_color = "text-amber-600"
        else:
            type_desc = "穩健中庸型"
            type_color = "text-indigo-600"

        groups.append({
            'name': name,
            'picks': current_picks,
            'nums': p_nums,
            'diagnosis': {
                'type_desc': type_desc,
                'type_color': type_color,
                'parity': f"{len([n for n in p_nums if n % 2 != 0])}奇{len([n for n in p_nums if n % 2 == 0])}偶",
                'sections': f"覆蓋 {len(set([(n-1)//20 for n in p_nums]))} 區間",
                'avg_drag': f"{avg_drag:.1f}"
            }
        })
            
    return groups, period_range, parity_status

# --- 2. 網頁前端 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    results, period_range, parity_status = get_data_and_analyze()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html_content = """
    <html>
    <head>
        <title>量化預測系統 V3.6</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .hit { color: white; background-color: #ef4444 !important; font-weight: bold; border-radius: 8px; box-shadow: 0 4px 10px rgba(239, 68, 68, 0.4); }
        </style>
    </head>
    <body class="bg-slate-50 p-4 md:p-10 font-sans text-slate-900">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white p-6 rounded-t-3xl shadow-sm border-b border-slate-100">
                <div class="flex flex-col md:flex-row md:justify-between items-center">
                    <div class="text-center md:text-left">
                        <h1 class="text-2xl font-black text-slate-800">📊 賓果策略量化儀表板</h1>
                        <p class="text-slate-400 text-[10px] mt-1 uppercase tracking-widest font-bold">Version 3.6 | Strategy Diagnosis</p>
                    </div>
                    <button onclick="location.reload()" class="mt-4 md:mt-0 flex items-center bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-xl font-bold text-sm transition-all active:scale-95 shadow-lg shadow-indigo-100">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                        更新最新數據
                    </button>
                </div>
                <div class="mt-6 flex justify-between text-[10px] font-mono border-t border-slate-50 pt-4 text-slate-400">
                    <span>🕒 {{ current_time }}</span>
                    <span class="text-indigo-500 font-bold">🔢 範圍: {{ period_range }}</span>
                </div>
            </div>

            <div class="bg-slate-900 p-6 shadow-xl text-white">
                <h3 class="font-bold mb-3 flex items-center text-xs opacity-70 italic">🎯 快速對獎 (支援 021516... 格式)</h3>
                <textarea id="winningInput" rows="2" 
                    class="w-full p-4 text-slate-900 rounded-xl border-none focus:ring-4 focus:ring-indigo-500 font-mono text-sm" 
                    placeholder="請貼入獎號..."></textarea>
                <button onclick="checkResults()" 
                    class="mt-4 w-full bg-indigo-500 hover:bg-indigo-600 text-white font-black py-4 rounded-xl shadow-lg transition-all tracking-widest">
                    執行組合核對
                </button>
            </div>

            <div class="bg-white p-6 rounded-b-3xl shadow-sm space-y-12 mb-10">
                {% if not results %}
                    <p class="text-center py-20 text-slate-400">數據加載中...</p>
                {% else %}
                    {% for group in results %}
                    <div class="group-container">
                        <div class="flex justify-between items-center mb-4">
                            <h2 class="text-lg font-black text-slate-700 flex items-center">
                                <span class="w-2 h-6 bg-indigo-500 rounded-full mr-3"></span>
                                {{ group.name }}
                                <span class="ml-3 text-xs font-bold px-2 py-0.5 rounded-md bg-slate-100 {{ group.diagnosis.type_color }}">
                                    {{ group.diagnosis.type_desc }}
                                </span>
                            </h2>
                            <span class="hit-badge hidden bg-rose-500 text-white px-3 py-1 rounded-full text-[10px] font-black"></span>
                        </div>
                        
                        <div class="overflow-x-auto rounded-2xl border border-slate-100 mb-4">
                            <table class="w-full text-sm text-left min-w-[500px]">
                                <thead class="bg-slate-50 text-slate-400 text-[10px] uppercase font-bold">
                                    <tr>
                                        <th class="px-5 py-4">號碼</th>
                                        <th class="px-5 py-4 text-center">拖牌能量</th>
                                        <th class="px-4 py-4 text-center">歷史連莊</th>
                                        <th class="px-5 py-4 text-right">量化得分</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-50">
                                    {% for p in group.picks %}
                                    <tr class="hover:bg-slate-50 transition-colors">
                                        <td class="px-5 py-4 font-mono font-bold text-xl num-cell" data-val="{{ p.no }}">
                                            {{ "%02d" | format(p.no) }}
                                        </td>
                                        <td class="px-5 py-4 text-center text-indigo-400 font-bold">{{ p.drag }}</td>
                                        <td class="px-4 py-4 text-center {{ 'text-emerald-500 font-black' if p.repeat == '是' else 'text-slate-200' }}">{{ p.repeat }}</td>
                                        <td class="px-5 py-4 font-black text-indigo-600 text-right italic">{{ "%.1f" | format(p.score) }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <div class="bg-slate-50 rounded-2xl p-4 border border-slate-100 grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                            <div class="text-center md:border-r border-slate-200">
                                <p class="text-[9px] text-slate-400 font-bold uppercase">奇偶比例</p>
                                <p class="text-xs font-black text-slate-600 mt-1">{{ group.diagnosis.parity }}</p>
                            </div>
                            <div class="text-center md:border-r border-slate-200">
                                <p class="text-[9px] text-slate-400 font-bold uppercase">空間分佈</p>
                                <p class="text-xs font-black text-slate-600 mt-1">{{ group.diagnosis.sections }}</p>
                            </div>
                            <div class="text-center">
                                <p class="text-[9px] text-slate-400 font-bold uppercase">平均拖牌強度</p>
                                <p class="text-xs font-black text-indigo-600 mt-1">{{ group.diagnosis.avg_drag }}</p>
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-4">
                            <div class="bg-indigo-600 p-4 rounded-2xl shadow-lg shadow-indigo-100">
                                <p class="text-[9px] text-indigo-200 font-bold uppercase mb-1">四星推薦組合</p>
                                <p class="text-lg font-black text-white tracking-widest">{{ group.nums | join(', ') }}</p>
                            </div>
                            <div class="bg-white p-4 rounded-2xl border-2 border-indigo-600">
                                <p class="text-[9px] text-indigo-400 font-bold uppercase mb-1">三星推薦組合</p>
                                <p class="text-lg font-black text-indigo-600 tracking-widest">{{ group.nums[:3] | join(', ') }}</p>
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                {% endif %}
            </div>
            
            <div class="text-center mb-10 bg-indigo-50 py-3 rounded-full border border-indigo-100">
                <p class="text-[10px] text-indigo-600 font-bold">📊 當前補償壓力：{{ parity_status }}</p>
            </div>
        </div>

        <script>
            function checkResults() {
                let input = document.getElementById('winningInput').value.trim();
                let winningNums = [];
                if (!input.includes(' ') && !input.includes(',') && input.length >= 20) {
                    for (let i = 0; i < input.length; i += 2) {
                        let num = parseInt(input.substring(i, i + 2));
                        if (!isNaN(num)) winningNums.push(num);
                    }
                } else {
                    let matches = input.match(/\d+/g);
                    if (matches) winningNums = matches.map(Number);
                }
                if (winningNums.length === 0) return alert('請輸入號碼');
                document.querySelectorAll('.num-cell').forEach(c => c.classList.remove('hit'));
                document.querySelectorAll('.hit-badge').forEach(b => b.classList.add('hidden'));
                document.querySelectorAll('.group-container').forEach(container => {
                    let hits = 0;
                    container.querySelectorAll('.num-cell').forEach(cell => {
                        if (winningNums.includes(parseInt(cell.getAttribute('data-val')))) {
                            cell.classList.add('hit'); hits++;
                        }
                    });
                    const badge = container.querySelector('.hit-badge');
                    if (hits > 0) { badge.innerText = `命中 ${hits} 碼`; badge.classList.remove('hidden'); }
                });
            }
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(results=results, period_range=period_range, parity_status=parity_status, current_time=current_time)


if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)


