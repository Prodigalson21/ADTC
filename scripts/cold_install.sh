#!/bin/bash
set -e

echo "=========================================="
echo "ADTC COLD INSTALLATION TEST"
echo "=========================================="

START_TIME=$(date +%s)

echo "Step 1: Checking Python version..."
python3 --version

echo ""
echo "Step 2: Creating virtual environment..."
python3 -m venv venv_test
source venv_test/bin/activate

echo ""
echo "Step 3: Installing dependencies..."
pip install flask duckdb psutil --quiet

echo ""
echo "Step 4: Initializing database..."
python3 -c "
from src.database import Database
db = Database('data/shop_cold_test.db')
print('Database initialized')
db.close()
"

echo ""
echo "Step 5: Registering test product..."
python3 -c "
import sys
sys.path.insert(0, '.')
from src.database import Database
import src.business_logic as bl

db = Database('data/shop_cold_test.db')
result = bl.register_product(db, 'mchele', 'kg', 2000, 10.0, 'food')
if result['success']:
    print(f'Product registered: {result[\"name\"]}')
else:
    print(f'Failed to register: {result}')
    sys.exit(1)
db.close()
"

echo ""
echo "Step 6: Running sanity check..."
python3 -c "
import sys
sys.path.insert(0, '.')
from src.agent import Agent
from src.database import Database

db = Database('data/shop_cold_test.db')
agent = Agent(db)
result = agent.process_message('uza 2 kg ya mchele')
if result.get('success'):
    print('Sale processed successfully')
else:
    print(f'Sale failed: {result}')
    sys.exit(1)
db.close()
"

echo ""
echo "Step 7: Testing analytics..."
python3 -c "
from skills.analytics_engine.handler import run_analytics
result = run_analytics('data/shop_cold_test.db', 'sales_by_period', {'period': 'day'})
print(f'Analytics query executed: {len(result[\"labels\"])} data points')
"

echo ""
echo "Step 8: Cleanup..."
rm -rf venv_test data/shop_cold_test.db*
deactivate 2>/dev/null || true

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "COLD INSTALLATION COMPLETE"
echo "=========================================="
echo "Total time: ${DURATION} seconds"

if [ $DURATION -lt 300 ]; then
    echo "PASS: Installation completed in under 5 minutes"
else
    echo "FAIL: Installation took too long"
fi
