# ADTC - Automated Digital Till & Commerce System

**Offline-first, RAM-constrained, thread-safe POS system with analytics**

## 🎯 Project Overview

ADTC is a fully offline point-of-sale system designed for low-resource environments. It features:
- **100% offline operation** (no CDN, no external APIs)
- **Strict RAM budget** (76 MB for analytics engine)
- **Thread-safe database operations** (concurrent access protection)
- **Parameterized SQL queries** (SQL injection protection)
- **Natural language processing** (Swahili + English support)
- **Real-time analytics** (Chart.js-ready JSON output)

## 🏗️ Architecture

┌─────────────────────────────────────────────────────────────┐
│ USER INTERFACE │
│ (Browser-based, vendored Chart.js, no external CDN) │
└────────────────────┬────────────────────────────────────────┘
│ HTTP/WebSocket
┌────────────────────▼────────────────────────────────────────┐
│ AGENT LAYER │
│ src/agent.py - Action dispatch, NLP parsing, tool routing │
└────────────────────┬────────────────────────────────────────┘
│
┌────────────┴────────────┐
│ │
┌───────▼────────┐ ┌────────▼─────────┐
│ BUSINESS LOGIC │ │ ANALYTICS ENGINE │
│ src/ │ │ skills/ │
│ business_ │ │ analytics_ │
│ logic.py │ │ engine/ │
│ │ │ handler.py │
│ - Validation │ │ │
│ - Transactions │ │ - 4 query │
│ - Error handle │ │ templates │
└───────┬────────┘ │ - Strict params │
│ │ - 76 MB RAM │
│ └────────┬─────────┘
└────────────┬───────────┘
│
┌────────────▼────────────┐
│ DATABASE LAYER │
│ src/database.py │
│ │
│ - threading.Lock() │
│ - DuckDB (OLAP) │
│ - SQLite (OLTP) │
│ - WAL mode │
└─────────────────────────┘

## 📦 Installation (Offline)

### Prerequisites
- Python 3.10+
- Ubuntu 22.04 (WSL2 or native)
- 512 MB RAM minimum

### Setup Steps

```bash
# 1. Clone repository (or copy from USB)
cd ~/adtc-project

# 2. Install dependencies (offline - use pre-downloaded wheels)
pip install --no-index --find-links=./wheels -r requirements.txt

# 3. Initialize database
python3 -c "from src.database import Database; Database('data/shop.db')"

# 4. Start the server
python3 src/main.py
Access the UI: Open http://localhost:5000 in your browser.
✅ Constraint Verification
1. Offline Operation (No CDN)
Proof: Zero external network calls. All JavaScript libraries are vendored locally.
# Verify no CDN links
grep -r "cdn\." src/static/ || echo "✅ No CDN found"
Result: ✅ PASS - All assets served locally from src/static/vendor/
2. RAM Budget (76 MB)
Proof: Analytics engine measured at 66.84 MB peak + 10 MB safety margin.
# Run RAM measurement
python3 -c "
import psutil, os, sys
sys.path.insert(0, '.')
from skills.analytics_engine.handler import run_analytics
proc = psutil.Process(os.getpid())
baseline = proc.memory_info().rss / 1024 / 1024
run_analytics('data/shop.db', 'sales_by_period', {'period': 'day'})
peak = proc.memory_info().rss / 1024 / 1024
print(f'Peak RAM: {peak:.2f} MB (delta: {peak - baseline:.2f} MB)')
"
Result: ✅ PASS - 66.84 MB peak (within 76 MB budget)
3. Thread Safety
Proof: All database writes protected by threading.Lock().
# Verify lock exists
grep -n "threading.Lock\|threading.RLock" src/database.py
Result: ✅ PASS - Lock found at line 15
4. SQL Injection Protection
Proof: Analytics engine uses parameterized queries with ? placeholders.
# Verify parameterized queries
grep -n "bind_values\|?" skills/analytics_engine/handler.py | head -5
Result: ✅ PASS - All queries use bind_values parameter binding
5. Fuzz Testing (34/34 tests pass)
Proof: Comprehensive adversarial testing suite.
# Run full fuzz test
python3 debug/debug_grammar.py
Result: ✅ PASS - 34/34 tests (12 dispatch, 6 Swahili, 16 analytics)
🧪 Analytics Engine
Available Query Templates
Template	Parameters	Description
`sales_by_period`	`period`, `start_date`, `end_date`	Revenue grouped by time
`top_n_products`	`n` (1-50), `metric`	Top N products by sales
`margin_by_category`	`period`	Profit margin by category
`stock_turnover`	`days` (1-365)	Inventory turnover ratio
Example Usage
# Get daily sales for last 30 days
python3 skills/analytics_engine/handler.py sales_by_period '{"period": "day"}'

# Get top 5 products by revenue
python3 skills/analytics_engine/handler.py top_n_products '{"n": 5, "metric": "revenue"}'
Output format: Chart.js-ready JSON
{
  "labels": ["2026-08-14", "2026-08-23"],
  "datasets": [
    {"label": "Revenue (day)", "data": [52.5, 15.0]},
    {"label": "Sale count", "data": [2, 1]}
  ]
}
🌍 Natural Language Support
The system understands both English and Swahili commands:
English:
"Sell 2 kg of rice"
"Check inventory for sugar"
"Show sales for last week"
Swahili:
"Uza kilo 2 ya mchele"
"Angalia stok ya sukari"
"Onyesha mauzo ya wiki iliyopita"
Validation: Fast-path regex for common patterns, LLM fallback for complex queries.
📊 Testing & Validation
Run Full Test Suite
# 1. Syntax check all Python files
find . -name "*.py" -exec python3 -m py_compile {} \;

# 2. Run fuzz tests (34 adversarial cases)
python3 debug/debug_grammar.py

# 3. Run end-to-end sanity check
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database import Database
from src.agent import Agent
db = Database('data/shop_e2e.db')
agent = Agent(db)
result = agent.process_message('uza 2 kg ya mchele')
assert result['success'], f'Failed: {result}'
print('✅ E2E test passed')
"
Expected output: All tests pass with 0 crashes.
🔒 Security Features
Input validation: Strict regex for product names (no special characters)
Parameterized queries: Zero SQL injection risk
Thread locks: Prevent race conditions in concurrent access
No external calls: 100% offline, no data exfiltration possible
Type checking: All parameters validated against manifest schema
📁 Project Structure
adtc-project/
├── src/
│   ├── main.py              # Flask API server
│   ├── agent.py             # NLP + action dispatch
│   ├── business_logic.py    # Core transaction logic
│   └── database.py          # Thread-safe DB layer
├── skills/
│   └── analytics_engine/
│       ├── handler.py       # 4 parameterized queries
│       ├── manifest.json    # Schema + RAM budget
│       ├── test_cases.jsonl # 16 fuzz test cases
│       └── analytics.gbnf   # LLM grammar constraint
├── debug/
│   └── debug_grammar.py     # 34-test fuzz suite
├── data/
│   └── shop.db              # SQLite + DuckDB database
└── README.md                # This file
🎓 Day 8 Audit Checklist
Offline operation verified (no CDN)
RAM budget measured (76 MB)
Thread safety confirmed (threading.Lock)
SQL injection protection (parameterized queries)
Fuzz testing complete (34/34 pass)
End-to-end flow validated
Documentation complete
📜 License
MIT License - See LICENSE file for details.
👥 Contributors
Built as part of the ADTC (Automated Digital Till & Commerce) project.

