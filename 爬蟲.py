from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn

app = FastAPI()

# --- 1. 核心量化分析邏輯 ---

def get_data_and_analyze():
    """抓取 API 並執行多因子評分，支援自動日期回溯"""
    now = datetime.datetime.now()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://winwin.tw/Bingo',
        'X-Requested-With': 'XMLHttpRequest'
    }

    def fetch_api(date_str):
        """內部輔助函式：根據日期請求 API"""
        target_url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
        try:
            resp = requests.get(target_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    # 第一步：嘗試抓取今天的資料
    today_str = now.strftime("%Y-%m-%d")
    api_data = fetch_api(today_str)

    # 第二步：如果今天沒資料 (例如凌晨時段)，自動抓昨天
    if not api_data or len(api_data) == 0:
        yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        api_data = fetch_api(yesterday_str)
        if api_data:
            print(f"📡 今日無資料，已成功切換至昨日: {yesterday_str}")

    if not api_data or len(api_data) == 0:
        return None, "系統維護中或暫無資料"

    # --- 以下為資料處理與量化分析邏輯 ---
    try:
        # 提取期數範圍
        newest_no = api_data[0].get('No', 'N/A')
        oldest_idx = min(29, len(api_data) - 1)
        oldest_no = api_data[oldest_idx].get('No', 'N/A')
        period_range = f"{newest_no} ~ {oldest_no}"
        
        all_draws = []
        for item in api_data:
            draw_str = item.get('BigShowOrder', '')
            if draw_str:
                nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
                if len(nums) == 20: all_draws.append(nums)
        
        if not all_draws: return None, period_range

        # 量化特徵：連莊池、30期頻率、遺漏值
        repeat_pool = set(all_draws[0])
        counts = Counter([n for d in all_draws[:30] for n in d])
        omission = {i: 999 for i in range(1, 81)}
        for i in range(1, 81):
            for idx, draw in enumerate(all_draws):
                if i in draw:
                    omission[i] = idx
                    break

        analysis_list = []
        for i in range(1, 81):
            freq = counts[i]
            is_repeat = i in repeat_pool
            score = freq * (1.5 if is_repeat else 1.0) # 適應度加權
            analysis_list.append({
                'no': i, 'freq': freq, 'repeat': "是" if is_repeat else "否",
                'omission': omission[i], 'score': score
            })

        # 分組邏輯 (2熱 + 2冷)
        sorted_hot = sorted(analysis_list, key=lambda x: x['score'], reverse=True)
        sorted_cold = sorted(analysis_list, key=lambda x: x['omission'], reverse=True)
        
        used_nums = set()
        group_names = ["第一組 (核心強勢)", "第二組 (潛力遞補)", "第三組 (冷熱平衡)"]
        groups = []

        for name in group_names:
            picks = []
            h_count = 0
            for p in sorted_hot:
                if p['no'] not in used_nums:
                    p['source'] = '熱門'; picks.append(p); used_nums.add(p['no']); h_count += 1
                if h_count == 2: break
            c_count = 0
            for p in sorted_cold:
                if p['no'] not in used_nums:
                    p['source'] = '冷門'; picks.append(p); used_nums.add(p['no']); c_count += 1
                if c_count == 2: break
            
            picks.sort(key=lambda x: x['no'])
            groups.append({'name': name, 'picks': picks, 'nums': [p['no'] for p in picks]})
            
        return groups, period_range
    except Exception as e:
        return None, f"解析錯誤: {e}"

# --- 2. 網頁路由與介面 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    analysis_results, period_range = get_data_and_analyze()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html_content = """
    <html>
    <head>
        <title>賓果量化預測網站</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .hit { color: #ffffff; font-weight: 800; background-color: #ef4444 !important; border-radius: 4px; }
        </style>
    </head>
    <body class="bg-slate-50 p-4 md:p-10">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white p-6 rounded-t-2xl shadow-sm border-b border-slate-100">
                <h1 class="text-2xl font-black text-slate-800">📊 賓果量化分析儀表板</h1>
                <div class="flex flex-col md:flex-row md:justify-between text-sm mt-1">
                    <p class="text-slate-400">分析時間：{{ current_time }}</p>
                    <p class="text-indigo-600 font-bold font-mono">🔢 資料範圍：{{ period_range }}</p>
                </div>
            </div>

            <div class="bg-indigo-600 p-6 shadow-lg text-white">
                <h3 class="font-bold mb-2 flex items-center">🎯 最新開獎號碼比對</h3>
                <textarea id="winningInput" rows="2" 
                    class="w-full p-3 text-slate-900 rounded-lg focus:ring-4 focus:ring-indigo-300" 
                    placeholder="貼入號碼 (支援空格或連號字串)"></textarea>
                <button onclick="checkResults()" 
                    class="mt-4 w-full bg-amber-400 hover:bg-amber-500 text-indigo-900 font-black py-3 rounded-lg shadow-md transition-all">
                    🚀 開始即時比對
                </button>
            </div>

            <div class="bg-white p-6 rounded-b-2xl shadow-sm space-y-10">
                {% if not results %}
                    <p class="text-center text-red-500 font-bold">目前無效資料，已自動嘗試回溯昨日數據，請確認 API 狀態。</p>
                {% else %}
                    {% for group in results %}
                    <div class="group-container">
                        <div class="flex justify-between items-center mb-4">
                            <h2 class="text-lg font-bold text-slate-700 border-l-4 border-indigo-500 pl-3">{{ group.name }}</h2>
                            <span class="hit-badge hidden bg-rose-100 text-rose-600 px-3 py-1 rounded-full text-xs font-black"></span>
                        </div>
                        <div class="overflow-x-auto rounded-xl border border-slate-100 mb-4">
                            <table class="w-full text-sm text-left min-w-[500px]">
                                <thead class="bg-slate-50 text-slate-500 text-xs uppercase">
                                    <tr>
                                        <th class="px-4 py-3">號碼</th><th class="px-4 py-3">來源</th>
                                        <th class="px-4 py-3">頻率</th><th class="px-4 py-3">連莊</th>
                                        <th class="px-4 py-3">遺漏</th><th class="px-4 py-3">綜合分</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    {% for p in group.picks %}
                                    <tr class="hover:bg-slate-50 transition-colors">
                                        <td class="px-4 py-3 font-mono font-bold text-lg num-cell" data-val="{{ p.no }}">{{ "%02d" | format(p.no) }}</td>
                                        <td class="px-4 py-3"><span class="px-2 py-0.5 rounded {{ 'bg-orange-50 text-orange-600' if p.source == '熱門' else 'bg-emerald-50 text-emerald-600' }} text-xs">{{ p.source }}</span></td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.freq }}</td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.repeat }}</td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.omission }}</td>
                                        <td class="px-4 py-3 font-bold text-indigo-600">{{ "%.1f" | format(p.score) }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        <div class="grid grid-cols-2 gap-3 text-center">
                            <div class="bg-slate-50 p-3 rounded-lg border border-slate-100">
                                <p class="text-[10px] text-slate-400 font-bold uppercase">四星組合</p>
                                <p class="text-md font-black text-slate-700">{{ group.nums | join(', ') }}</p>
                            </div>
                            <div class="bg-slate-50 p-3 rounded-lg border border-slate-100">
                                <p class="text-[10px] text-slate-400 font-bold uppercase">三星組合</p>
                                <p class="text-md font-black text-slate-700">{{ group.nums[:3] | join(', ') }}</p>
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                {% endif %}
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
                if (winningNums.length === 0) return alert('請輸入獎號');
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
    return template.render(results=analysis_results, period_range=period_range, current_time=current_time)

if __name__ == "__main__":
    # 提醒：若要部屬到 Render，host 需設為 "0.0.0.0"
    uvicorn.run(app, host="0.0.0.0", port=8000)

