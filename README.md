# Relatório de transações

Esta versão roda no terminal e salva um relatório HTML independente, além dos CSVs com os resultados.

## Executar

Com Python 3.10 ou mais recente:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python criar_dados.py
python relatorio.py transacoes.csv cotacoes.csv
```

Abra `relatorio_saida/relatorio.html` no navegador. A pasta também recebe `transacoes_tratadas.csv`, `anomalias.csv`, `filtro_setembro.csv` e `resumo_risco.csv`.

O script lê as transações em Latin-1 e as cotações em UTF-8, preenche valores ausentes pela mediana do estado, remove duplicatas e ajusta o fuso para `America/Sao_Paulo`. Os níveis de risco estão no dicionário `RISCO_CLIENTE` em `relatorio.py`.

Para escolher outra pasta de saída, use `--saida caminho/da/pasta`.
