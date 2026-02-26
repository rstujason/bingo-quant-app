from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import requests
from collections import Counter
import datetime
import uvicorn

app = FastAPI()

# --- 1. 核心量化分析邏輯 ---

def get_data_and_analyze():
    """抓取 API 並執行多因子評分"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"https://winwin.tw/Bingo/GetBingoData?date={today}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://winwin.tw/Bingo',
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        api_data = resp.json()
        
        all_draws = []
        for item in api_data:
            draw_str = item.get('BigShowOrder', '') # 取得獎號欄位
            if draw_str:
                nums = [int(n) for n in draw_str.split(',') if n.strip().isdigit()]
                if len(nums) == 20: all_draws.append(nums)
        
        if not all_draws: return None

        # 特徵提取：連莊池、30期頻率、遺漏值
        repeat_pool = set(all_draws[0])
        counts = Counter([n for d in all_draws[:30] for n in d])
        omission = {i: 999 for i in range(1, 81)}
        for i in range(1, 81):
            for idx, draw in enumerate(all_draws):
                if i in draw:
                    omission[i] = idx
                    break

        # 建立 1-80 號評分表
        analysis_list = []
        for i in range(1, 81):
            freq = counts[i]
            is_repeat = i in repeat_pool
            # 適應度分數 = 頻率 * 連莊權重(1.5)
            score = freq * (1.5 if is_repeat else 1.0)
            analysis_list.append({
                'no': i, 'freq': freq, 'repeat': "是" if is_repeat else "否",
                'omission': omission[i], 'score': score
            })

        # 分組邏輯：三組排他性組合 (2熱 + 2冷)
        sorted_hot = sorted(analysis_list, key=lambda x: x['score'], reverse=True)
        sorted_cold = sorted(analysis_list, key=lambda x: x['omission'], reverse=True)
        
        used_nums = set()
        group_names = ["第一組 (核心強勢)", "第二組 (潛力遞補)", "第三組 (冷熱平衡)"]
        groups = []

        for name in group_names:
            picks = []
            # 挑選 2 熱
            h_count = 0
            for p in sorted_hot:
                if p['no'] not in used_nums:
                    p['source'] = '熱門'; picks.append(p); used_nums.add(p['no']); h_count += 1
                if h_count == 2: break
            # 挑選 2 冷
            c_count = 0
            for p in sorted_cold:
                if p['no'] not in used_nums:
                    p['source'] = '冷門'; picks.append(p); used_nums.add(p['no']); c_count += 1
                if c_count == 2: break
            
            picks.sort(key=lambda x: x['no'])
            groups.append({'name': name, 'picks': picks, 'nums': [p['no'] for p in picks]})
            
        return groups
    except Exception as e:
        print(f"Error: {e}")
        return None

# --- 2. 網頁路由與介面 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    analysis_results = get_data_and_analyze()
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
                <p class="text-slate-400 text-sm mt-1">分析時間：{{ current_time }}</p>
            </div>

            <div class="bg-indigo-600 p-6 shadow-lg text-white">
                <h3 class="font-bold mb-2 flex items-center">
                    <span class="mr-2">🎯</span> 最新開獎號碼比對
                </h3>
                <textarea id="winningInput" rows="2" 
                    class="w-full p-3 text-slate-900 rounded-lg border-none focus:ring-4 focus:ring-indigo-300 transition-all" 
                    placeholder="貼入號碼 (支援空格或連號字串，如 021516...)"></textarea>
                <button onclick="checkResults()" 
                    class="mt-4 w-full bg-amber-400 hover:bg-amber-500 text-indigo-900 font-black py-3 rounded-lg shadow-md transform active:scale-95 transition-all">
                    🚀 開始即時比對
                </button>
            </div>

            <div class="bg-white p-6 rounded-b-2xl shadow-sm space-y-10">
                {% if not results %}
                    <p class="text-center text-red-500 font-bold">目前抓不到資料，請檢查網路或稍後再試。</p>
                {% else %}
                    {% for group in results %}
                    <div class="group-container" data-group="{{ group.name }}">
                        <div class="flex justify-between items-center mb-4">
                            <h2 class="text-lg font-bold text-slate-700 border-l-4 border-indigo-500 pl-3">{{ group.name }}</h2>
                            <span class="hit-badge hidden bg-rose-100 text-rose-600 px-3 py-1 rounded-full text-xs font-black"></span>
                        </div>
                        
                        <div class="overflow-hidden rounded-xl border border-slate-100 mb-4">
                            <table class="w-full text-sm text-left">
                                <thead class="bg-slate-50 text-slate-500 font-medium">
                                    <tr>
                                        <th class="px-4 py-3">號碼</th>
                                        <th class="px-4 py-3">來源</th>
                                        <th class="px-4 py-3">頻率</th>
                                        <th class="px-4 py-3">連莊</th>
                                        <th class="px-4 py-3">遺漏</th>
                                        <th class="px-4 py-3">綜合分</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    {% for p in group.picks %}
                                    <tr class="hover:bg-slate-50 transition-colors">
                                        <td class="px-4 py-3 font-mono font-bold text-lg num-cell" data-val="{{ p.no }}">
                                            {{ "%02d" | format(p.no) }}
                                        </td>
                                        <td class="px-4 py-3">
                                            <span class="px-2 py-0.5 rounded {{ 'bg-orange-50 text-orange-600' if p.source == '熱門' else 'bg-emerald-50 text-emerald-600' }} text-xs">
                                                {{ p.source }}
                                            </span>
                                        </td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.freq }}</td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.repeat }}</td>
                                        <td class="px-4 py-3 text-slate-600">{{ p.omission }}</td>
                                        <td class="px-4 py-3 font-bold text-indigo-600">{{ "%.1f" | format(p.score) }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <div class="grid grid-cols-2 gap-3">
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

                <button onclick="location.reload()" class="w-full mt-4 text-slate-400 text-sm hover:text-indigo-500 transition-colors">
                    數據不準？按此重新抓取 API
                </button>
            </div>
        </div>

        <script>
            function checkResults() {
                let input = document.getElementById('winningInput').value.trim();
                let winningNums = [];

                // 智慧解析：判斷是否為連號字串 (如 021516...)
                if (!input.includes(' ') && !input.includes(',') && input.length >= 20) {
                    for (let i = 0; i < input.length; i += 2) {
                        let num = parseInt(input.substring(i, i + 2));
                        if (!isNaN(num)) winningNums.push(num);
                    }
                } else {
                    let matches = input.match(/\d+/g);
                    if (matches) winningNums = matches.map(Number);
                }

                if (winningNums.length === 0) {
                    alert('請輸入有效獎號！');
                    return;
                }

                // 執行比對
                document.querySelectorAll('.num-cell').forEach(cell => cell.classList.remove('hit'));
                document.querySelectorAll('.hit-badge').forEach(b => b.classList.add('hidden'));

                document.querySelectorAll('.group-container').forEach(container => {
                    let hits = 0;
                    const cells = container.querySelectorAll('.num-cell');
                    cells.forEach(cell => {
                        const val = parseInt(cell.getAttribute('data-val'));
                        if (winningNums.includes(val)) {
                            cell.classList.add('hit');
                            hits++;
                        }
                    });

                    const badge = container.querySelector('.hit-badge');
                    if (hits > 0) {
                        badge.innerText = `命中 ${hits} 碼`;
                        badge.classList.remove('hidden');
                    }
                });
            }
        </script>
    </body>
    </html>
    """
    from jinja2 import Template
    template = Template(html_content)
    return template.render(results=analysis_results, current_time=current_time)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)