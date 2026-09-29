Relatório de transações
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python criar_dados.py
python relatorio.py transacoes.csv cotacoes.csv

