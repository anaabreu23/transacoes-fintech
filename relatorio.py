"""Gera um relatório HTML a partir dos CSVs do exercício."""

from __future__ import annotations

import argparse
import base64
import html
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RISCO_CLIENTE = {
    "C100": "Baixo",
    "C101": "Alto",
    "C102": "Médio",
    "C103": "Alto",
    "C104": "Baixo",
}

COLUNAS_TRANSACOES = {"id_cliente", "data_transacao", "valor", "origem", "estado_cliente"}
COLUNAS_COTACOES = {"data", "cotacao_usd", "volume_negociado"}
DIAS_PT = {
    "Monday": "segunda-feira",
    "Tuesday": "terça-feira",
    "Wednesday": "quarta-feira",
    "Thursday": "quinta-feira",
    "Friday": "sexta-feira",
    "Saturday": "sábado",
    "Sunday": "domingo",
}


def ler_arquivo(caminho: Path, encoding: str) -> pd.DataFrame:
    return pd.read_csv(caminho, encoding=encoding)


def ajustar_fuso(datas: pd.Series) -> pd.Series:
    datas = pd.to_datetime(datas, errors="coerce")
    fuso = datas.dt.tz
    if fuso is None:
        return datas.dt.tz_localize("America/Sao_Paulo")
    return datas.dt.tz_convert("America/Sao_Paulo")


def preparar_dados(brutos: pd.DataFrame, cotacoes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    faltantes = COLUNAS_TRANSACOES - set(brutos.columns)
    if faltantes:
        raise ValueError("Colunas faltantes em transacoes.csv: " + ", ".join(sorted(faltantes)))
    faltantes = COLUNAS_COTACOES - set(cotacoes.columns)
    if faltantes:
        raise ValueError("Colunas faltantes em cotacoes.csv: " + ", ".join(sorted(faltantes)))

    dados = brutos.copy()
    dados["valor"] = pd.to_numeric(dados["valor"], errors="coerce")
    dados["data_transacao"] = ajustar_fuso(dados["data_transacao"])
    if dados["data_transacao"].isna().any():
        raise ValueError("Existem datas de transação inválidas.")

    mediana_estado = dados.groupby("estado_cliente")["valor"].transform("median")
    dados["valor"] = dados["valor"].fillna(mediana_estado)
    dados = dados.drop_duplicates(keep="first").reset_index(drop=True)
    dados["plataforma"] = "Mobile"
    dados["dia_semana"] = dados["data_transacao"].dt.day_name().map(DIAS_PT)
    dados["mes"] = dados["data_transacao"].dt.month
    dados["nivel_risco"] = dados["id_cliente"].map(RISCO_CLIENTE).fillna("Não mapeado")

    filtro_setembro = dados.loc[
        (dados["mes"] == 9)
        & ((dados["estado_cliente"] == "SP") | (dados["estado_cliente"] == "RJ"))
        & (dados["valor"] > 5000)
    ].copy()

    resumo_risco = pd.pivot_table(
        dados,
        index="mes",
        columns="nivel_risco",
        values="valor",
        aggfunc="sum",
        margins=True,
        margins_name="Total",
        fill_value=0,
    )

    por_estado = dados.groupby("estado_cliente")["valor"]
    desvio = por_estado.transform("std", ddof=0).replace(0, np.nan)
    dados["z_score"] = (dados["valor"] - por_estado.transform("mean")) / desvio
    anomalias = dados.loc[dados["z_score"] > 2.5].copy()

    diario = (
        dados.set_index("data_transacao")["valor"]
        .resample("D")
        .sum()
        .rename("total_diario")
        .to_frame()
    )
    diario["media_movel_7d"] = diario["total_diario"].rolling(7, min_periods=1).mean()

    cot = cotacoes.copy()
    cot["data"] = ajustar_fuso(cot["data"]).dt.normalize()
    cot["cotacao_usd"] = pd.to_numeric(cot["cotacao_usd"], errors="coerce")
    cot["volume_negociado"] = pd.to_numeric(cot["volume_negociado"], errors="coerce")
    cot = cot.dropna(subset=["data"]).drop_duplicates(subset=["data"], keep="first")
    diario = diario.join(cot.set_index("data")[["cotacao_usd", "volume_negociado"]], how="left")

    return {
        "transacoes": dados,
        "filtro_setembro": filtro_setembro,
        "resumo_risco": resumo_risco,
        "anomalias": anomalias,
        "diario": diario,
    }


def reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def criar_grafico(diario: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(diario.index, diario["total_diario"], label="Total diário", color="#2864a0")
    ax.plot(diario.index, diario["media_movel_7d"], label="Média móvel (7 dias)", color="#e28b27")
    ax.set_ylim(bottom=0)
    ax.set_title("Valor das transações por dia")
    ax.set_xlabel("Data")
    ax.set_ylabel("Valor (R$)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()

    imagem = BytesIO()
    fig.savefig(imagem, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(imagem.getvalue()).decode("ascii")


def tabela_html(tabela: pd.DataFrame, dinheiro: bool = False) -> str:
    exibicao = tabela.copy()
    if dinheiro:
        exibicao = exibicao.map(lambda valor: reais(valor) if pd.notna(valor) else "—")
    return exibicao.to_html(classes="dados", border=0, na_rep="—", escape=True)


def salvar_relatorio(resultados: dict[str, pd.DataFrame], destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    transacoes = resultados["transacoes"]
    anomalias = resultados["anomalias"]
    diario = resultados["diario"]

    transacoes.to_csv(destino / "transacoes_tratadas.csv", index=False, encoding="utf-8-sig")
    anomalias.to_csv(destino / "anomalias.csv", index=False, encoding="utf-8-sig")
    resultados["filtro_setembro"].to_csv(
        destino / "filtro_setembro.csv", index=False, encoding="utf-8-sig"
    )
    resultados["resumo_risco"].to_csv(destino / "resumo_risco.csv", encoding="utf-8-sig")

    imagem = criar_grafico(diario)
    volume = reais(transacoes["valor"].sum())
    ticket = reais(transacoes["valor"].median())
    corpo = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatório de transações</title>
  <style>
    body {{ margin: 0; background: #f4f6f8; color: #202833; font: 15px/1.5 Arial, sans-serif; }}
    main {{ max-width: 1180px; margin: 32px auto; padding: 0 20px; }}
    h1 {{ margin-bottom: 4px; }} h2 {{ margin-top: 32px; }}
    .resumo {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 22px 0; }}
    .cartao {{ background: white; border: 1px solid #dfe4ea; border-radius: 8px; padding: 16px 20px; min-width: 180px; }}
    .cartao strong {{ display: block; font-size: 21px; }}
    .grafico, .tabela {{ background: white; border: 1px solid #dfe4ea; border-radius: 8px; padding: 14px; overflow-x: auto; }}
    .grafico img {{ display: block; width: 100%; height: auto; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5e9ee; padding: 8px 10px; text-align: left; white-space: nowrap; }}
    th {{ background: #f7f8fa; }}
    .nota {{ color: #596675; }}
  </style>
</head>
<body><main>
  <h1>Relatório de transações</h1>
  <p class="nota">Dados tratados e consolidados a partir dos arquivos fornecidos.</p>
  <section class="resumo">
    <div class="cartao">Registros após limpeza<strong>{len(transacoes):,}</strong></div>
    <div class="cartao">Volume total<strong>{html.escape(volume)}</strong></div>
    <div class="cartao">Ticket mediano<strong>{html.escape(ticket)}</strong></div>
    <div class="cartao">Anomalias (Z &gt; 2,5)<strong>{len(anomalias):,}</strong></div>
  </section>
  <h2>Movimentação diária</h2>
  <div class="grafico"><img alt="Total diário e média móvel de sete dias" src="data:image/png;base64,{imagem}"></div>
  <h2>Soma por mês e nível de risco</h2>
  <div class="tabela">{tabela_html(resultados['resumo_risco'], dinheiro=True)}</div>
  <h2>Filtro de setembro: SP ou RJ, acima de R$ 5.000</h2>
  <div class="tabela">{tabela_html(resultados['filtro_setembro'])}</div>
  <h2>Possíveis anomalias por estado</h2>
  <p class="nota">Z-Score calculado por estado; a tabela inclui os registros acima de 2,5.</p>
  <div class="tabela">{tabela_html(anomalias)}</div>
</main></body></html>"""
    (destino / "relatorio.html").write_text(corpo, encoding="utf-8")


def executar() -> None:
    parser = argparse.ArgumentParser(description="Cria um relatório HTML dos CSVs financeiros.")
    parser.add_argument("transacoes", type=Path, help="Caminho do transacoes.csv (Latin-1)")
    parser.add_argument("cotacoes", type=Path, help="Caminho do cotacoes.csv (UTF-8)")
    parser.add_argument("--saida", type=Path, default=Path("relatorio_saida"), help="Pasta dos arquivos gerados")
    args = parser.parse_args()

    try:
        transacoes = ler_arquivo(args.transacoes, "latin1")
        cotacoes = ler_arquivo(args.cotacoes, "utf-8")
        resultados = preparar_dados(transacoes, cotacoes)
        salvar_relatorio(resultados, args.saida)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as erro:
        parser.error(str(erro))

    print(f"Relatório criado em: {(args.saida / 'relatorio.html').resolve()}")
    print(f"Transações tratadas: {len(resultados['transacoes'])}")
    print(f"Possíveis anomalias: {len(resultados['anomalias'])}")


if __name__ == "__main__":
    executar()
