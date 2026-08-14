"""
Garmin Connect Analytics — dashboard analítico completo.

Estrutura:
  streamlit_dashboard.py  -> UI, abas e views
  garmin_data.py          -> parser do export (GDPR) do Garmin
  viz.py                  -> tema adaptável (claro/escuro), helpers de gráfico

Como usar:
  * Faça upload do ZIP exportado do Garmin Connect, OU
  * Informe o caminho local da pasta extraída no campo da barra lateral.
"""

import datetime as dt
import io
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import garmin_data as gd
from garmin_data import GarminExport
from viz import (
    C_NEG, C_NEUTRO, C_POS, GLOSSARIO, PALETA, SEQ_AZUL, SEQ_DIVERG, SEQ_VERDE,
    SEQ_VERM, card_titulo_icon, explica, fmt_hora_frac, fmt_min, fmt_ritmo,
    inject_css, kpi, linha_resumo_periodo, media_circular_horario,
    ordem_dias_pt, rotulo_dia, rotulo_dia_curto, style_fig, theme_base,
)

# Trendlines do Plotly (lowess/ols) dependem de statsmodels; sem ele, omite a
# linha de tendência em vez de quebrar o app (ex.: ambiente sem a dependência).
try:
    import statsmodels  # noqa: F401
    TREND_SUAVE = "lowess"
    TREND_RETA = "ols"
except ImportError:
    TREND_SUAVE = None
    TREND_RETA = None

st.set_page_config(
    page_title="Garmin Connect Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


# ============================================================== carregamento
@st.cache_data(ttl=600, show_spinner=False)
def _load_zip_bytes(data: bytes) -> GarminExport:
    tmp = Path(tempfile.mkdtemp(prefix="garmin_zip_")) / "export.zip"
    tmp.write_bytes(data)
    return GarminExport(tmp).load()


@st.cache_data(ttl=600, show_spinner=False)
def _load_folder(path: str, mtime: float) -> GarminExport:
    return GarminExport(path).load()


def carregar_dados() -> GarminExport | None:
    with st.sidebar:
        uploaded = st.file_uploader("📤 Upload do ZIP do Garmin Connect", type=["zip"])
        try:
            if uploaded is not None:
                with st.spinner("🔄 Processando export…"):
                    return _load_zip_bytes(uploaded.getvalue())
            # Alternativa sem UI para uso local/testes: variável de ambiente
            # GARMIN_DADOS apontando para a pasta extraída ou para o ZIP.
            caminho = os.environ.get("GARMIN_DADOS")
            if caminho and Path(caminho).is_dir():
                with st.spinner("🔄 Processando export…"):
                    mt = max(f.stat().st_mtime for f in Path(caminho).rglob("*") if f.is_file())
                    return _load_folder(caminho, mt)
            if caminho and caminho.lower().endswith(".zip") and Path(caminho).is_file():
                with st.spinner("🔄 Processando export…"):
                    return _load_zip_bytes(Path(caminho).read_bytes())
        except Exception as e:
            st.error(f"Erro ao carregar dados: {e}")
    return None


g = carregar_dados()
if g is None:
    st.markdown("<h1 class='main-header'>⚡ Garmin Connect Analytics</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='sub-header'>Análise completa de atividades, sono, saúde e recuperação</p>",
        unsafe_allow_html=True,
    )

    col_intro, col_export = st.columns([3, 2])
    with col_intro:
        st.markdown("### 🚀 Como começar")
        st.markdown(
            "Use a **barra lateral à esquerda** para carregar seus dados de uma das duas formas:\n\n"
            "1. 📤 **Upload do ZIP** exportado do Garmin Connect, ou\n"
            "2. 📁 **Caminho da pasta** extraída no seu computador"
        )
        st.markdown("### 🎯 O que você vai descobrir")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                "#### 🏃 Atividades\n"
                "- Volume, distância e calorias\n"
                "- Zonas cardíacas do treino\n"
                "- Efeito aeróbico/anaeróbico\n"
                "- Ritmo e dinâmica de corrida\n"
                "- Volume de musculação"
            )
        with c2:
            st.markdown(
                "#### 😴 Sono\n"
                "- Fases (profundo, leve, REM)\n"
                "- Score e sub-scores\n"
                "- Eficiência e horário de dormir\n"
                "- Dívida de sono acumulada\n"
                "- SpO₂ e estresse noturno"
            )
        with c3:
            st.markdown(
                "#### 💗 Saúde\n"
                "- HRV e FC de repouso\n"
                "- Body Battery e estresse\n"
                "- Passos e intensidade diária\n"
                "- Idade fisiológica e VO₂ Máx\n"
                "- Recordes e equipamentos"
            )

    with col_export:
        st.markdown("### 📥 Como exportar seus dados do Garmin")
        st.markdown(
            "1. Acesse **garmin.com/pt-BR/account/datamanagement/**\n"
            "   (ou: Conta → Gerenciamento de dados)\n"
            "2. Clique em **Exportar seus dados** → *Solicitar exportação*\n"
            "3. Aguarde o e-mail da Garmin — pode levar de **minutos a horas**\n"
            "4. Baixe o ZIP pelo link do e-mail\n"
            "5. Faça upload do ZIP aqui na barra lateral"
        )
        st.info(
            "💡 O ZIP traz todo o seu histórico: atividades, sono, bem-estar diário, "
            "recordes e equipamentos. O dashboard processa tudo automaticamente.",
            icon="💡",
        )
    st.stop()

for w in g.warnings:
    st.warning(w)

# --------------------------------------------------------- contexto global
_idx = g.master.index if (g.master is not None and len(g.master)) else pd.DatetimeIndex([])
TODAS_DATAS = pd.Series(pd.DatetimeIndex(_idx))
DATA_MIN = TODAS_DATAS.min() if len(TODAS_DATAS) else pd.Timestamp("2025-01-01")
DATA_MAX = TODAS_DATAS.max() if len(TODAS_DATAS) else pd.Timestamp.today()

MESES_PT = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
            7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}


def _fmt_periodo(p):
    """Rótulo amigável para um Period (mês ou semana)."""
    if p == "Todos" or p == "Todas":
        return p
    if hasattr(p, "start_time"):
        if p.freqstr.startswith("M"):
            return f"{MESES_PT[p.month]}/{p.year}"
        ini = p.start_time
        return f"sem. {ini.strftime('%d/%m')}"
    return str(p)


with st.sidebar:
    st.markdown("### 📅 Período (todas as abas)")
    modo_filtro = st.radio(
        "Modo", ["Ano / Mês / Semana", "Intervalo de datas"],
        horizontal=True, label_visibility="collapsed", key="filtro_modo",
    )

    if modo_filtro == "Ano / Mês / Semana":
        anos = ["Todos"] + sorted(TODAS_DATAS.dt.year.unique().tolist(), reverse=True)
        ano_sel = st.selectbox("📅 Ano", anos, key="filtro_ano")

        base = TODAS_DATAS if ano_sel == "Todos" else TODAS_DATAS[TODAS_DATAS.dt.year == int(ano_sel)]
        meses = ["Todos"] + sorted(base.dt.to_period("M").unique().tolist(), reverse=True)
        mes_sel = st.selectbox("📆 Mês", meses, format_func=_fmt_periodo, key="filtro_mes")

        if mes_sel != "Todos":
            base = base[base.dt.to_period("M") == mes_sel]
        semanas = ["Todas"] + sorted(base.dt.to_period("W").unique().tolist(), reverse=True)
        sem_sel = st.selectbox("🗓️ Semana", semanas, format_func=_fmt_periodo, key="filtro_semana")

        if sem_sel != "Todas":
            P_INI, P_FIM = sem_sel.start_time.normalize(), sem_sel.end_time.normalize()
        elif mes_sel != "Todos":
            P_INI, P_FIM = mes_sel.start_time.normalize(), mes_sel.end_time.normalize()
        elif ano_sel != "Todos":
            P_INI = pd.Timestamp(int(ano_sel), 1, 1)
            P_FIM = pd.Timestamp(int(ano_sel), 12, 31) + pd.Timedelta(hours=23, minutes=59)
        else:
            P_INI, P_FIM = DATA_MIN.normalize(), DATA_MAX.normalize()
    else:
        periodo = st.date_input(
            "Intervalo",
            value=(DATA_MIN.date(), DATA_MAX.date()),
            min_value=DATA_MIN.date(),
            max_value=DATA_MAX.date(),
            help="Aplica a todas as abas.",
        )
        if len(periodo) == 2:
            P_INI = pd.Timestamp(periodo[0])
            P_FIM = pd.Timestamp(periodo[1]) + pd.Timedelta(hours=23, minutes=59)
        else:
            P_INI, P_FIM = DATA_MIN.normalize(), DATA_MAX.normalize()

    st.caption(f"Analisando: **{P_INI.strftime('%d/%m/%Y')} → {P_FIM.strftime('%d/%m/%Y')}**")
    if st.button("🔄 Limpar filtros", key="limpar_filtros"):
        st.session_state.filtro_ano = "Todos"
        st.session_state.filtro_mes = "Todos"
        st.session_state.filtro_semana = "Todas"
        st.rerun()

    if g.profile:
        p = g.profile
        st.markdown("### 👤 Perfil")
        altura = f"{p['altura_m']:.2f} m" if p.get("altura_m") else "—"
        peso = f"{p['peso_kg']:.1f} kg" if p.get("peso_kg") else "—"
        st.markdown(
            f"**{p.get('nome', '—')}**"
            + (f" · {p['idade']} anos" if p.get("idade") else "")
            + f"\n\n{altura} · {peso}"
            + (f" · IMC {p['bmi']:.1f}" if p.get("bmi") else "")
        )
    st.markdown("---")
    st.markdown("---")
    with st.expander("ℹ️ Como exportar dados do Garmin"):
        st.markdown(
            "1. Acesse **garmin.com/pt-BR/account/datamanagement/**\n"
            "2. **Exportar seus dados** → *Solicitar exportação*\n"
            "3. Aguarde o e-mail da Garmin (minutos a horas)\n"
            "4. Baixe o ZIP e faça o upload na barra lateral"
        )
    st.caption("Desenvolvido com Streamlit + Plotly")


def no_periodo(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not len(df) or "date" not in df.columns:
        return df
    return df[(df["date"] >= P_INI) & (df["date"] <= P_FIM)].copy()


# ============================================================= insights auto
def gerar_insights(g: GarminExport) -> list[dict]:
    """Motor de insights: varre os dados e devolve achados acionáveis."""
    out = []
    m = g.master

    if m is not None and len(m):
        ult = m.iloc[-30:]
        ant = m.iloc[-60:-30]

        def _cmp(col, rotulo, fmt="{:+.1f}", menor_e_melhor=False, limiar=3.0):
            if col in ult.columns and col in ant.columns:
                a, b = ult[col].mean(), ant[col].mean()
                if pd.notna(a) and pd.notna(b) and b != 0:
                    d = (a - b) / abs(b) * 100
                    if abs(d) >= limiar:
                        bom = (d < 0) if menor_e_melhor else (d > 0)
                        out.append({
                            "emoji": "📈" if bom else "📉",
                            "titulo": f"{rotulo}: {d:+.0f}% nos últimos 30 dias",
                            "texto": f"Média de {b:.1f} → {a:.1f} comparando os dois últimos meses.",
                            "bom": bom,
                        })

        _cmp("sono_h", "Horas de sono", menor_e_melhor=False)
        _cmp("fc_repouso", "FC de repouso", menor_e_melhor=True)
        _cmp("estresse_medio", "Estresse médio", menor_e_melhor=True)
        _cmp("passos", "Passos diários")

        if "acwr" in m.columns:
            acwr = m["acwr"].iloc[-1]
            if pd.notna(acwr):
                if acwr > 1.3:
                    out.append({
                        "emoji": "⚠️", "bom": False, "titulo": f"Carga de treino alta (ACWR {acwr:.2f})",
                        "texto": "Aumento de volume muito rápido vs média de 4 semanas — risco de lesão. Considere uma semana de carga menor.",
                    })
                elif acwr < 0.8:
                    out.append({
                        "emoji": "🛋️", "bom": None, "titulo": f"Carga de treino baixa (ACWR {acwr:.2f})",
                        "texto": "Volume bem abaixo da média das últimas 4 semanas — destreino ou descanso planejado.",
                    })
                else:
                    out.append({
                        "emoji": "✅", "bom": True, "titulo": f"Carga de treino equilibrada (ACWR {acwr:.2f})",
                        "texto": "Progressão de volume dentro da faixa ideal (0,8–1,3).",
                    })

        # dia seguinte: treino pesado → sono/estresse?
        for alvo, rot in [("estresse_medio", "estresse"), ("sono_h", "sono"), ("bb_min", "energia mínima")]:
            par = m[[f"treino_min_ontem", alvo]].dropna()
            if len(par) >= 20:
                r = par["treino_min_ontem"].corr(par[alvo])
                if pd.notna(r) and abs(r) >= 0.25:
                    dir_txt = "aumenta" if r > 0 else "diminui"
                    out.append({
                        "emoji": "🔬", "bom": None,
                        "titulo": f"Treinar mais → {rot} do dia seguinte {dir_txt} (r={r:.2f})",
                        "texto": "Relação defasada de 1 dia nos seus dados.",
                    })

    if g.sleep is not None and len(g.sleep):
        s = no_periodo(g.sleep)
        divida = s["divida_sono_h"].mean()
        if pd.notna(divida) and divida > 0.5:
            out.append({
                "emoji": "😴", "bom": False,
                "titulo": f"Dívida média de sono: {divida:.1f} h/noite (alvo 7h30)",
                "texto": f"Equivale a {divida * 7:.0f} h de sono perdidas por semana.",
            })
        consist = s["hora_dormir"].std()
        if pd.notna(consist) and consist > 1.2:
            out.append({
                "emoji": "🌗", "bom": False,
                "titulo": f"Horário de dormir irregular (±{consist:.1f} h)",
                "texto": "Regularidade de horário é um dos maiores preditores de qualidade do sono.",
            })

    if g.daily is not None and len(g.daily):
        d = no_periodo(g.daily)
        if len(d) and "atingiu_meta_passos" in d.columns:
            taxa = d["atingiu_meta_passos"].mean() * 100
            out.append({
                "emoji": "👟", "bom": taxa >= 60,
                "titulo": f"Meta de passos atingida em {taxa:.0f}% dos dias",
                "texto": f"Média de {d['passos'].mean():,.0f} passos/dia.".replace(",", "."),
            })

    return out


# ==================================================================== views
def view_resumo():
    st.header("🎯 Resumo Geral")
    a = no_periodo(g.activities)
    s = no_periodo(g.sleep)
    d = no_periodo(g.daily)

    # --- KPIs principais
    kcal_atv = d["kcal_ativa"].mean() if d is not None and len(d) else None

    itens = [
        ("🏃 Atividades", f"{len(a):,}".replace(",", ".") if a is not None else "0", None),
        ("⏱️ Tempo de treino", fmt_min(a["duracao_min"].sum()) if a is not None and len(a) else "—",
         f"{a['duracao_min'].mean():.0f} min médios" if a is not None and len(a) else None),
        ("📏 Distância", f"{a['dist_km'].sum():,.0f} km".replace(",", ".") if a is not None and len(a) else "—", None),
        ("😴 Sono médio", f"{s['sono_h'].mean():.1f} h" if s is not None and len(s) else "—",
         f"score {s['score_overall'].mean():.0f}" if s is not None and s["score_overall"].notna().any() else None),
        ("❤️ FC repouso", f"{d['fc_repouso'].mean():.0f} bpm" if d is not None and d["fc_repouso"].notna().any() else "—", None),
        ("😰 Estresse", f"{d['estresse_medio'].mean():.0f}" if d is not None and d["estresse_medio"].notna().any() else "—", None),
        ("👟 Passos/dia", f"{d['passos'].mean():,.0f}".replace(",", ".") if d is not None and d["passos"].notna().any() else "—", None),
        ("🔥 kcal ativas/dia", f"{kcal_atv:.0f}" if kcal_atv is not None and pd.notna(kcal_atv) else "—", None),
    ]
    kpi([1] * 8, itens)
    explica(
        "**FC de repouso**: quanto menor, melhor o condicionamento (60–100 normal; atletas 40–60) · "
        "**Estresse**: índice 0–100, abaixo de 50 é saudável · **kcal ativas**: gasto por movimento, "
        "a parte que você controla. Definições completas na aba 📖 Glossário."
    )
    st.markdown("---")

    # --- evolução (granularidade adaptativa ao período filtrado)
    if a is not None and len(a):
        span_dias = (P_FIM - P_INI).days
        freq, rotulo = ("W", "Evolução semanal") if span_dias <= 120 else ("M", "Evolução mensal")
        per = a["start"].dt.to_period(freq)
        mensal = a.groupby(per).agg(qtd=("activityId", "count"), min=("duracao_min", "sum"),
                                    km=("dist_km", "sum"), kcal=("kcal", "sum")).reset_index()
        mensal["start"] = mensal["start"].map(
            lambda p: f"{MESES_PT[p.month]}/{p.year}" if freq == "M" else p.start_time.strftime("%d/%m/%y")
        )
        st.subheader(rotulo)
        fig = go.Figure()
        fig.add_bar(x=mensal["start"], y=mensal["min"], name="Minutos", marker_color=PALETA[1])
        fig.add_scatter(x=mensal["start"], y=mensal["km"], name="Distância (km)", yaxis="y2",
                        mode="lines+markers", line=dict(color=PALETA[2], width=3))
        fig.update_layout(
            yaxis=dict(title="Minutos"),
            yaxis2=dict(title="km", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # --- últimos 30 dias: energia vs estresse vs sono
    if d is not None and len(d):
        # Janela ancorada no ÚLTIMO DIA COM DADOS (o export pode terminar
        # antes do fim do período filtrado, o que deixava o gráfico vazio).
        fim_dados = d["date"].max()
        ini_jan = max(fim_dados - pd.Timedelta(days=30), P_INI)
        dd = d[d["date"] >= ini_jan]
        dd = dd[dd[["bb_max", "bb_min", "estresse_medio"]].notna().any(axis=1)]
        ss = (s[s["date"] >= ini_jan][["date", "sono_h"]].dropna(subset=["sono_h"])
              if s is not None and len(s) else None)
        if len(dd) or (ss is not None and len(ss)):
            st.subheader("Energia, estresse e sono — fim do período selecionado")
            fig = go.Figure()
            if len(dd) and dd["bb_max"].notna().any():
                fig.add_bar(x=dd["date"], y=dd["bb_max"], name="BB máx", marker_color=C_POS, opacity=0.55,
                            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Pico de energia: %{y:.0f}<extra></extra>")
            if len(dd) and dd["bb_min"].notna().any():
                fig.add_bar(x=dd["date"], y=dd["bb_min"], name="BB mín", marker_color=C_NEG, opacity=0.55,
                            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Energia mínima: %{y:.0f}<extra></extra>")
            if len(dd) and dd["estresse_medio"].notna().any():
                fig.add_scatter(x=dd["date"], y=dd["estresse_medio"], name="Estresse", mode="lines",
                                line=dict(color=PALETA[3], width=2), yaxis="y2",
                                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Estresse médio: %{y:.0f}<extra></extra>")
            if ss is not None and len(ss):
                fig.add_scatter(x=ss["date"], y=ss["sono_h"], name="Sono (h)", mode="lines",
                                line=dict(color=PALETA[0], width=2, dash="dot"), yaxis="y2",
                                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Sono: %{y:.1f} h<extra></extra>")
            fig.update_layout(
                yaxis=dict(title="Body Battery", range=[0, 100]),
                yaxis2=dict(title="Estresse / Sono h", overlaying="y", side="right"),
                barmode="overlay", legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(style_fig(fig), use_container_width=True)
            explica(
                "Últimos 30 dias **com registro** dentro do período filtrado. Barras = Body Battery "
                "do dia (pico × mínimo); linhas = estresse médio e horas de sono."
            )
        else:
            st.info("Sem dados de energia, estresse ou sono nos últimos 30 dias do período selecionado.")

    # --- insights
    st.subheader("💡 Destaques dos seus dados")
    ins = gerar_insights(g)
    ins = ins[:6] if ins else []
    if ins:
        cols = st.columns(min(len(ins), 3))
        for i, item in enumerate(ins):
            with cols[i % 3]:
                cor = "#2ecc7133" if item["bom"] else ("#e5737333" if item["bom"] is False else "#90a4ae33")
                st.markdown(
                    f"<div class='insight-card' style='border-left:4px solid "
                    f"{'#2ecc71' if item['bom'] else ('#e57373' if item['bom'] is False else '#90a4ae')}'>"
                    f"<b>{item['emoji']} {item['titulo']}</b><p>{item['texto']}</p></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Sem destaques automáticos neste período.")


def view_atividades():
    st.header("🏃 Atividades")
    a = no_periodo(g.activities)
    if a is None or not len(a):
        st.warning("Nenhuma atividade no período.")
        return
    linha_resumo_periodo(a, g.activities, "atividades")

    tipos = ["Todos"] + sorted(a["tipo"].unique())
    tipo = st.selectbox("Tipo de atividade", tipos)
    af = a[a["tipo"] == tipo] if tipo != "Todos" else a

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Atividades", f"{len(af):,}".replace(",", "."))
    with c2:
        st.metric("Tempo total", fmt_min(af["duracao_min"].sum()))
    with c3:
        st.metric("Distância", f"{af['dist_km'].sum():,.0f} km".replace(",", "."))
    with c4:
        st.metric("Calorias", f"{af['kcal'].sum():,.0f}".replace(",", "."))
    with c5:
        hr = af.loc[af["fc_media"] > 0, "fc_media"]
        st.metric("FC média", f"{hr.mean():.0f} bpm" if len(hr) else "—")

    explica(
        "**FC média/máx** = batimentos por minuto durante o treino (comparar com o esforço, não com outras pessoas) · "
        "**kcal** = gasto energético real da atividade. O mapa de calor mostra quando você costuma treinar."
    )

    col1, col2 = st.columns(2)
    with col1:
        cont = af["tipo"].value_counts()
        fig = px.pie(values=cont.values, names=cont.index, hole=0.45,
                     color_discrete_sequence=PALETA, title="Distribuição por tipo")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    with col2:
        por_dia = af.groupby("weekday").size().reindex(gd.DIAS_SEMANA, fill_value=0)
        fig = px.bar(x=ordem_dias_pt(), y=por_dia.values, title="Atividades por dia da semana",
                     labels={"x": "", "y": "Quantidade"}, color_discrete_sequence=[PALETA[1]])
        st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("🕐 Quando você treina (hora × dia)")
    hm = af.groupby(["weekday", af["hour"].round(0)]).size().reset_index(name="n")
    hm["weekday"] = rotulo_dia_curto(hm["weekday"])
    piv = hm.pivot(index="weekday", columns="hour", values="n")
    piv = piv.reindex([rotulo_dia_curto(pd.Series([d]))[0] for d in gd.DIAS_SEMANA])
    fig = px.imshow(piv, aspect="auto", color_continuous_scale=SEQ_VERDE,
                    labels=dict(x="Hora do dia", y="", color="Atividades"))
    st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("📊 Comparativo por tipo de atividade")
    resumo = af.groupby("tipo").agg(
        qtd=("activityId", "count"),
        tempo_min=("duracao_min", "sum"),
        km=("dist_km", "sum"),
        kcal=("kcal", "sum"),
        kcal_medio=("kcal", "mean"),
        fc_media=("fc_media", "mean"),
    ).sort_values("tempo_min", ascending=False).reset_index()
    resumo["tempo_medio_min"] = (resumo["tempo_min"] / resumo["qtd"]).round(0)
    resumo = resumo[["tipo", "qtd", "tempo_min", "tempo_medio_min", "km", "kcal", "kcal_medio", "fc_media"]]
    resumo.columns = ["Tipo", "Qtd", "Tempo (min)", "Tempo médio", "km", "kcal", "kcal médio", "FC média"]
    st.dataframe(resumo.round(1), use_container_width=True, hide_index=True)

    st.subheader("🔎 Volume por período")
    span_dias = (P_FIM - P_INI).days
    freq = "D" if span_dias <= 60 else "W"
    rot = "dia" if freq == "D" else "semana"
    per = af["start"].dt.to_period(freq)
    sem = af.groupby(per).agg(minutos=("duracao_min", "sum"), qtd=("activityId", "count"),
                              kcal=("kcal", "sum")).reset_index()
    sem["start"] = sem["start"].dt.strftime("%d/%m/%y")
    fig = go.Figure()
    fig.add_bar(x=sem["start"], y=sem["minutos"], name=f"Minutos/{rot}", marker_color=PALETA[0])
    fig.add_scatter(x=sem["start"], y=sem["kcal"], name=f"kcal/{rot}", yaxis="y2",
                    mode="lines", line=dict(color=PALETA[3], width=2))
    fig.update_layout(yaxis=dict(title="Minutos"), yaxis2=dict(title="kcal", overlaying="y", side="right"),
                      legend=dict(orientation="h", y=1.12))
    st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("Listagem completa")
    lst = af.sort_values("start", ascending=False)[
        ["start", "nome", "tipo", "duracao_min", "dist_km", "kcal", "fc_media", "fc_max", "te_label"]
    ].copy()
    lst["start"] = lst["start"].dt.strftime("%d/%m/%Y %H:%M")
    lst.columns = ["Início", "Nome", "Tipo", "Duração", "km", "kcal", "FC méd", "FC máx", "Efeito"]
    lst[["Duração", "km", "kcal", "FC méd", "FC máx"]] = lst[["Duração", "km", "kcal", "FC méd", "FC máx"]].round(1)
    st.dataframe(lst, use_container_width=True, hide_index=True, height=380)


def view_performance():
    st.header("⚡ Performance & Carga de Treino")
    a = no_periodo(g.activities)
    if a is None or not len(a):
        st.warning("Nenhuma atividade no período.")
        return

    # --- zonas cardíacas
    st.subheader("❤️ Distribuição de treino por zona cardíaca")
    explica(
        "Zonas de FC = faixas de intensidade em % da sua FC máxima (método HR_MAX). "
        "**Z1–Z2** constroem base aeróbica (leve) · **Z3** ritmo moderado · **Z4** limiar (forte sustentável) · "
        "**Z5** VO₂ (máximo curto). A distribuição mostra qual 'motor' você tem treinado."
    )
    zcols = [f"z{i}_min" for i in range(7)]
    zlabels = ["Abaixo Z1", "Z1 (leve)", "Z2 (aeróbico)", "Z3 (tempo)", "Z4 (limiar)", "Z5 (VO2)", "Acima Z5"]
    zsum = a[zcols].sum()
    if zsum.sum() > 0:
        c1, c2 = st.columns([2, 3])
        with c1:
            pct = zsum / zsum.sum() * 100
            fig = go.Figure(go.Pie(labels=zlabels, values=zsum.values, hole=0.45,
                                   marker=dict(colors=[C_NEUTRO, "#6ea8fe", "#1abc9c", "#f5a623", "#ef6c6c", "#c0392b", "#8e44ad"])))
            fig.update_traces(textinfo="percent")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with c2:
            defs = g.hr_zone_defs
            if defs is not None:
                r = defs.iloc[0]
                st.markdown(
                    f"**Suas zonas** (método {r.get('trainingMethod','—')}, FC máx {r.get('maxHeartRateUsed','—')} bpm):\n\n"
                    f"| Zona | FC (bpm) | Tempo no período |\n|---|---|---|\n"
                    f"| Abaixo Z1 | < {r.get('zone1Floor','—')} | {fmt_min(zsum.iloc[0])} |\n"
                    f"| Z1 | {r.get('zone1Floor','—')}–{r.get('zone2Floor','—')} | {fmt_min(zsum.iloc[1])} |\n"
                    f"| Z2 | {r.get('zone2Floor','—')}–{r.get('zone3Floor','—')} | {fmt_min(zsum.iloc[2])} |\n"
                    f"| Z3 | {r.get('zone3Floor','—')}–{r.get('zone4Floor','—')} | {fmt_min(zsum.iloc[3])} |\n"
                    f"| Z4 | {r.get('zone4Floor','—')}–{r.get('zone5Floor','—')} | {fmt_min(zsum.iloc[4])} |\n"
                    f"| Z5 | ≥ {r.get('zone5Floor','—')} | {fmt_min(zsum.iloc[5])} |"
                )
            tempo_zona = pd.DataFrame({"Zona": zlabels, "Minutos": zsum.values})
            fig = px.bar(tempo_zona, x="Zona", y="Minutos", color_discrete_sequence=[PALETA[1]])
            fig.update_traces(hovertemplate="Zona %{x}: %{y:.0f} min<extra></extra>")
            st.plotly_chart(style_fig(fig), use_container_width=True)

    # --- efeito de treino
    if a["te_label"].notna().any():
        st.subheader("🧪 Efeito de treino (aeróbico/anaeróbico)")
        explica(
            "O **efeito de treino** classifica o estímulo da sessão: RECOVERY (recuperação ativa), "
            "AEROBIC_BASE (resistência), TEMPO (ritmo), LIMIAR e ANAEROBIC (potência curta). "
            "Semana ideal mistura base aeróbica com 1–2 sessões de intensidade."
        )
        te = a.dropna(subset=["te_label"])
        cont = te["te_label"].value_counts()
        c1, c2 = st.columns([2, 3])
        with c1:
            fig = px.pie(values=cont.values, names=cont.index, hole=0.45,
                         color_discrete_sequence=PALETA, title="Tipos de estímulo")
            fig.update_traces(textinfo="percent")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with c2:
            fig = px.scatter(te, x="start", y="fc_media", color="te_label", size="duracao_min",
                             hover_data=["nome", "kcal"], labels={"start": "", "fc_media": "FC média"},
                             color_discrete_sequence=PALETA)
            st.plotly_chart(style_fig(fig), use_container_width=True)

    # --- corrida
    corridas = a[a["tipo"].isin(gd.TIPOS_CORRIDA) & (a["dist_km"] > 0)]
    st.subheader("🏃‍♂️ Corrida")
    explica(
        "**Ritmo** em min/km — quanto MENOR, mais rápido. A tendência desconta variações de distância; "
        "evoluir é correr o mesmo ritmo com FC média menor."
    )
    if len(corridas):
        corridas = corridas.sort_values("start")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Corridas", len(corridas))
        with c2:
            st.metric("Volume", f"{corridas['dist_km'].sum():.0f} km")
        with c3:
            melhor = corridas.loc[corridas["ritmo_min_km"].idxmin()]
            st.metric("Melhor ritmo", fmt_ritmo(melhor["ritmo_min_km"]),
                      f"{melhor['dist_km']:.1f} km em {melhor['start'].strftime('%d/%m/%y')}")
        with c4:
            longa = corridas.loc[corridas["dist_km"].idxmax()]
            st.metric("Mais longa", f"{longa['dist_km']:.1f} km")

        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(corridas, x="start", y="ritmo_min_km", trendline=TREND_SUAVE,
                             color=corridas["dist_km"].round(1).astype(str),
                             labels={"start": "", "ritmo_min_km": "ritmo (min/km)", "color": "km"},
                             color_discrete_sequence=PALETA,
                             title="Evolução do ritmo (menor = mais rápido)")
            fig.update_traces(
                selector=dict(mode="markers"),
                customdata=np.stack([
                    corridas["start"].dt.strftime("%d/%m/%Y"),
                    corridas["ritmo_min_km"].map(fmt_ritmo),
                    corridas["dist_km"].round(2).map("{:.1f} km".format),
                    corridas["duracao_min"].map(fmt_min),
                ], axis=-1),
                hovertemplate=("<b>%{customdata[0]}</b><br>Ritmo: %{customdata[1]} /km"
                               "<br>%{customdata[2]} · %{customdata[3]}<extra></extra>"),
            )
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with col2:
            fig = px.scatter(corridas, x="dist_km", y="fc_media", trendline=TREND_RETA,
                             labels={"dist_km": "distância (km)", "fc_media": "FC média"},
                             color_discrete_sequence=[PALETA[0]],
                             title="Desgaste: distância × FC média")
            st.plotly_chart(style_fig(fig), use_container_width=True)

        # dinâmica de corrida
        din = ["cadencia", "passada_m", "gct_ms", "oscilacao_mm"]
        din_disp = [c for c in din if corridas[c].notna().sum() >= 3]
        if din_disp:
            with st.expander("🔬 Dinâmica de corrida (cadência, contato, oscilação)", expanded=False):
                explica(
                    "**Cadência**: passos/min, referência 170–180 · **GCT**: tempo do pé no chá, "
                    "menor = mais eficiente (< 300 ms bom) · **Oscilação vertical**: quanto o corpo 'quica', "
                    "menor = menos energia desperdiçada."
                )
                cols = st.columns(2)
                for i, c in enumerate(din_disp):
                    with cols[i % 2]:
                        un = {"cadencia": "passos/min", "passada_m": "m", "gct_ms": "ms", "oscilacao_mm": "mm"}[c]
                        tmp = corridas.dropna(subset=[c])
                        fig = px.scatter(tmp, x="start", y=c, trendline=TREND_SUAVE,
                                         labels={"start": "", c: un}, color_discrete_sequence=[PALETA[(i + 1) % len(PALETA)]])
                        st.plotly_chart(style_fig(fig, height=280), use_container_width=True)
    else:
        st.info("Sem corridas com distância registrada no período.")

    # --- força
    forca = a[(a["tipo"] == "Musculação") & a["series"].notna()]
    if len(forca):
        st.subheader("🏋️ Musculação — volume semanal")
        fs = forca.groupby("week").agg(series=("series", "sum"), reps=("reps", "sum")).reset_index()
        fig = go.Figure()
        fig.add_bar(x=fs["week"], y=fs["series"], name="Séries", marker_color=PALETA[4])
        fig.add_scatter(x=fs["week"], y=fs["reps"], name="Repetições", yaxis="y2", mode="lines",
                        line=dict(color=PALETA[2], width=2))
        fig.update_layout(yaxis=dict(title="Séries"), yaxis2=dict(title="Reps", overlaying="y", side="right"),
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # --- carga e ACWR
    st.subheader("📐 Carga de treino e ACWR (risco de lesão)")
    if g.master is not None and "acwr" in g.master.columns:
        m = g.master[(g.master.index >= P_INI) & (g.master.index <= P_FIM)]
        fig = go.Figure()
        fig.add_bar(x=m.index, y=m["carga_7d_min"], name="Carga 7 dias (min)", marker_color=PALETA[1],
                    opacity=0.6,
                    hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Carga 7 dias: %{y:.0f} min<extra></extra>")
        fig.add_scatter(x=m.index, y=m["acwr"], name="ACWR", yaxis="y2", mode="lines",
                        line=dict(color=PALETA[3], width=2),
                        hovertemplate=("<b>%{x|%d/%m/%Y}</b><br>ACWR: %{y:.2f}"
                                       "<br>(0,8–1,3 = seguro)<extra></extra>"))
        fig.add_hrect(y0=0.8, y1=1.3, line_width=0, fillcolor=C_POS, opacity=0.15,
                      yref="y2", annotation_text="zona ideal 0,8–1,3")
        fig.update_layout(
            yaxis=dict(title="Minutos (7d)"),
            yaxis2=dict(title="ACWR", overlaying="y", side="right", range=[0, 2.5]),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(style_fig(fig), use_container_width=True)
        st.caption("ACWR = carga aguda (7 dias) ÷ crônica (média de 4 semanas). "
                   "Acima de ~1,3 indica aumento abrupto de volume; abaixo de ~0,8, destreino.")


def view_sono():
    st.header("😴 Sono")
    s = no_periodo(g.sleep)
    if s is None or not len(s):
        st.warning("Sem dados de sono no período.")
        return
    linha_resumo_periodo(s, g.sleep, "noites")

    media_dormir = media_circular_horario(s["hora_dormir"])
    media_acordar = media_circular_horario(s["hora_acordar"])
    kpi([1] * 6, [
        ("Sono total", f"{s['sono_h'].mean():.1f} h", None),
        ("Profundo", f"{s['profundo_h'].mean():.1f} h",
         f"{s['profundo_h'].mean() / s['sono_h'].mean() * 100:.0f}% do total"),
        ("REM", f"{s['rem_h'].mean():.1f} h",
         f"{s['rem_h'].mean() / s['sono_h'].mean() * 100:.0f}% do total"),
        ("Eficiência", f"{s['eficiencia_pct'].mean():.0f}%", None),
        ("Score médio", f"{s['score_overall'].mean():.0f}" if s["score_overall"].notna().any() else "—", None),
        ("Horário de dormir", fmt_hora_frac(media_dormir),
         f"acorda ~{fmt_hora_frac(media_acordar)}"),
    ])
    explica(
        "**Eficiência**: % do tempo na cama efetivamente dormindo (≥ 85% é bom) · "
        "**Profundo**: reparo físico, ideal 13–23% do sono · **REM**: memória/aprendizado, ideal 20–25% · "
        "**Score**: nota 0–100 do Garmin (> 80 ótimo)."
    )

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_scatter(x=s["date"], y=s["sono_h"], mode="markers", name="Sono (h)",
                        marker=dict(color=PALETA[1], size=6),
                        hovertemplate="<b>%{x|%d/%m/%Y}</b><br>%{y:.1f} h de sono<extra></extra>")
        mm = s.set_index("date")["sono_h"].rolling(7, min_periods=3).mean()
        fig.add_scatter(x=mm.index, y=mm, mode="lines", name="Média móvel 7d",
                        line=dict(color=PALETA[0], width=3))
        fig.add_hline(y=7.5, line_dash="dash", line_color=C_POS, annotation_text="alvo 7h30")
        fig.update_layout(title="Horas de sono por noite")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    with col2:
        fig = go.Figure()
        base = np.zeros(len(s))
        ordem = [("leve_h", "Leve", "#6ea8fe"), ("profundo_h", "Profundo", "#1e3a8a"),
                 ("rem_h", "REM", "#b58cda")]
        for col, nome, cor in ordem:
            fig.add_bar(x=s["date"], y=s[col], name=nome, base=base, marker_color=cor,
                        hovertemplate="<b>%{x|%d/%m/%Y}</b><br>" + nome + ": %{y:.1f} h<extra></extra>")
            base = base + s[col].fillna(0).values
        fig.update_layout(barmode="stack", title="Composição do sono")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("🌗 Consistência do horário de dormir")
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.scatter(x=s["date"], y=s["hora_dormir"] % 24, trendline=TREND_SUAVE,
                         labels={"x": "", "y": "hora"}, color_discrete_sequence=[PALETA[5]])
        fig.update_traces(
            selector=dict(mode="markers"),
            customdata=s["hora_dormir"].map(fmt_hora_frac),
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Dormiu às %{customdata}<extra></extra>",
        )
        fig.update_yaxes(tickformat=":.0f", ticksuffix="h")
        fig.add_hline(y=media_circular_horario(s["hora_dormir"]) % 24, line_dash="dash", line_color=C_POS)
        st.plotly_chart(style_fig(fig), use_container_width=True)
    with c2:
        por_dia = s.groupby("weekday")["sono_h"].mean().reindex(gd.DIAS_SEMANA)
        fig = px.bar(x=ordem_dias_pt(), y=por_dia.values, color=por_dia.values,
                     color_continuous_scale=SEQ_AZUL, labels={"x": "", "y": "h"}, title="Sono médio por dia da semana")
        st.plotly_chart(style_fig(fig), use_container_width=True)
    st.caption(f"Desvio-padrão do horário de dormir: **±{s['hora_dormir'].std():.1f} h** — "
               "quanto menor, mais estável o ritmo circadiano.")

    st.subheader("📉 Saldo de sono por noite (alvo 7h30)")
    div = s[["date", "divida_sono_h"]].dropna()
    if len(div):
        fig = go.Figure()
        fig.add_bar(
            x=div["date"], y=-div["divida_sono_h"],
            marker_color=[
                C_NEG if v > 0.5 else (C_POS if v < -0.5 else C_NEUTRO)
                for v in div["divida_sono_h"]
            ],
            name="Saldo da noite",
            hovertemplate=("<b>%{x|%d/%m/%Y}</b><br>%{y:+.1f} h vs alvo"
                           "<br>(negativo = noite com dívida)<extra></extra>"),
        )
        fig.add_scatter(
            x=div["date"], y=(-div["divida_sono_h"]).rolling(7, min_periods=3).mean(),
            mode="lines", line=dict(color=PALETA[1], width=3), name="Média móvel 7 noites",
            hovertemplate="Média 7 noites: %{y:+.1f} h<extra></extra>",
        )
        fig.add_hline(y=0, line_dash="dot", line_color=C_NEUTRO)
        fig.update_yaxes(title="horas vs alvo (+ sobra / − dívida)")
        st.plotly_chart(style_fig(fig), use_container_width=True)
        explica(
            "Cada barra é uma noite: **acima de zero** dormiu além da meta (sobra), **abaixo** ficou "
            "devendo. A linha azul é a tendência de 7 noites — caindo = privação se acumulando."
        )

    # sub-scores e sinais noturnos
    score_cols = [c for c in ["score_quality", "score_duration", "score_recovery", "score_deep",
                              "score_rem", "score_restfulness", "score_interruptions"] if c in s.columns]
    if s[score_cols].notna().any().any():
        st.subheader("🧩 Onde o seu sono perde pontos")
        explica("Cada componente é avaliado de 0–100 — a barra mais baixa é o elo mais fraco da sua noite.")
        medias = s[score_cols].mean().sort_values()
        nomes = {"score_quality": "Qualidade", "score_duration": "Duração", "score_recovery": "Recuperação",
                 "score_deep": "Profundo", "score_rem": "REM", "score_restfulness": "Descanso",
                 "score_interruptions": "Interrupções"}
        fig = px.bar(x=[nomes.get(c, c) for c in medias.index], y=medias.values,
                     color=medias.values, color_continuous_scale=SEQ_VERM, range_color=[40, 100],
                     labels={"x": "", "y": "score"}, title="Score médio por componente (menor = ponto fraco)")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    sinais = [("spo2_sono", "SpO₂ durante o sono", "%", 90), ("estresse_sono", "Estresse durante o sono", "", 40),
              ("despertares", "Despertares por noite", "", 5), ("momentos_inquietos", "Momentos inquietos", "", 60)]
    disp = [(c, t, u, ref) for c, t, u, ref in sinais if c in s.columns and s[c].notna().any()]
    if disp:
        st.subheader("🩺 Sinais noturnos")
        explica(
            "**SpO₂** noturna normal ≥ 95% (mínimos abaixo de 90% com frequência merecem atenção médica) · "
            "**estresse durante o sono** abaixo de ~30 indica descanso de verdade."
        )
        cols = st.columns(len(disp))
        for col, (c, t, u, ref) in zip(cols, disp):
            with col:
                st.metric(t, f"{s[c].mean():.1f}{u}", f"mín {s[c].min():.0f}" if pd.notna(s[c].min()) else None)


def view_saude():
    st.header("💗 Saúde & Energia")
    d = no_periodo(g.daily)
    h = no_periodo(g.health)

    # ---------- HRV e FC repouso (diário + status)
    if h is not None and len(h):
        st.subheader("❤️‍🔥 HRV e FC de repouso")
        explica(
            "**HRV** = variação entre um batimento e outro: quanto MAIOR, melhor a recuperação. "
            "A faixa tracejada é a SUA linha de base — compare-se com ela, não com outras pessoas. "
            "**FC de repouso**: quanto menor, melhor o condicionamento."
        )
        c1, c2 = st.columns(2)
        with c1:
            if "HRV_valor" in h.columns and h["HRV_valor"].notna().any():
                fig = go.Figure()
                fig.add_scatter(x=h["date"], y=h["HRV_valor"], mode="markers", name="HRV",
                                marker=dict(color=PALETA[3], size=6))
                if "HRV_lim_sup" in h.columns:
                    fig.add_scatter(x=h["date"], y=h["HRV_lim_sup"], mode="lines", name="base sup.",
                                    line=dict(color=C_NEUTRO, dash="dash", width=1))
                    fig.add_scatter(x=h["date"], y=h["HRV_lim_inf"], mode="lines", name="base inf.",
                                    line=dict(color=C_NEUTRO, dash="dash", width=1))
                mm = h.set_index("date")["HRV_valor"].rolling(7, min_periods=3).mean()
                fig.add_scatter(x=mm.index, y=mm, mode="lines", name="média 7d",
                                line=dict(color=PALETA[0], width=3))
                fig.update_layout(title="HRV (ms) — maior = melhor recuperação")
                st.plotly_chart(style_fig(fig), use_container_width=True)
        with c2:
            fig = go.Figure()
            if d is not None and len(d) and d["fc_repouso"].notna().any():
                fig.add_scatter(x=d["date"], y=d["fc_repouso"], mode="markers", name="FC repouso",
                                marker=dict(color=PALETA[1], size=6))
                mm = d.set_index("date")["fc_repouso"].rolling(7, min_periods=3).mean()
                fig.add_scatter(x=mm.index, y=mm, mode="lines", name="média 7d",
                                line=dict(color=PALETA[0], width=3))
                fig.update_layout(title="FC de repouso (bpm) — menor = melhor condicionamento")
                st.plotly_chart(style_fig(fig), use_container_width=True)

        # painel de status (fora da linha de base)
        status_cols = [c for c in h.columns if c.endswith("_status")]
        if status_cols:
            nomes = {"HRV": "HRV", "HR": "FC repouso", "SPO2": "SpO₂",
                     "SKIN_TEMP_C": "Temp. pele", "RESPIRATION": "Respiração"}
            linhas = []
            for c in status_cols:
                pref = c[:-7]
                vc = f"{pref}_valor"
                if vc not in h.columns:
                    continue
                vals = h[vc].dropna()
                if not len(vals):
                    continue
                fora = (h[c] == "ABOVE_BASELINE").sum() + (h[c] == "BELOW_BASELINE").sum()
                linhas.append({
                    "Métrica": nomes.get(pref, pref),
                    "Atual": round(float(vals.iloc[-1]), 1),
                    "Média": round(float(vals.mean()), 1),
                    "Mín": round(float(vals.min()), 1),
                    "Máx": round(float(vals.max()), 1),
                    "Dias fora da base": int(fora),
                })
            if linhas:
                explica(
                    "'Dias fora da base' conta leituras acima/abaixo da sua própria média pessoal — "
                    "muitos dias fora indicam mudança de estado (doença, estresse, supercompensação)."
                )
                st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)

    # ---------- SpO2, temperatura, respiração
    extra = [("SPO2_valor", "🫁 SpO₂ (%)", 95), ("SKIN_TEMP_C_valor", "🌡️ Variação temp. pele (°C)", 0),
             ("RESPIRATION_valor", "🫁 Respiração (rpm)", 15)]
    disp = [(c, t, ref) for c, t, ref in extra if h is not None and c in h.columns and h[c].notna().any()]
    if disp:
        cols = st.columns(len(disp))
        for col, (c, t, ref) in zip(cols, disp):
            with col:
                fig = px.scatter(h, x="date", y=c, trendline=TREND_SUAVE, labels={"date": "", c: ""},
                                 color_discrete_sequence=[PALETA[2]])
                fig.add_hline(y=ref, line_dash="dash", line_color=C_NEUTRO)
                fig.update_layout(title=t)
                st.plotly_chart(style_fig(fig, height=260), use_container_width=True)

    # ---------- Body Battery
    if d is not None and len(d) and d["bb_max"].notna().any():
        st.subheader("🔋 Body Battery")
        explica(
            "Energia corporal 0–100: a **recarga** vem do sono e do descanso; o **gasto** vem de estresse "
            "e atividade. Pico alto + gasto controlado = boa gestão de energia."
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Pico médio", f"{d['bb_max'].mean():.0f}")
        with c2:
            st.metric("Mínimo médio", f"{d['bb_min'].mean():.0f}")
        with c3:
            st.metric("Recarga média", f"+{d['bb_recarga'].mean():.0f}")
        with c4:
            st.metric("Gasto médio", f"−{d['bb_gasto'].mean():.0f}")

        fig = go.Figure()
        fig.add_scatter(x=d["date"], y=d["bb_max"], mode="lines", line=dict(width=0), showlegend=False)
        fig.add_scatter(x=d["date"], y=d["bb_min"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor="rgba(26,188,156,0.25)", showlegend=False)
        fig.add_scatter(x=d["date"], y=d["bb_max"], mode="lines", name="pico", line=dict(color=C_POS, width=1.5))
        fig.add_scatter(x=d["date"], y=d["bb_min"], mode="lines", name="mínimo", line=dict(color=C_NEG, width=1.5))
        fig.update_layout(yaxis=dict(title="BB", range=[0, 100]), title="Energia diária (faixa pico–mínimo)")
        st.plotly_chart(style_fig(fig), use_container_width=True)

        rec_sem = d.groupby("weekday")[["bb_recarga", "bb_gasto"]].mean().reindex(gd.DIAS_SEMANA)
        fig = go.Figure()
        fig.add_bar(x=ordem_dias_pt(), y=rec_sem["bb_recarga"], name="recarga", marker_color=C_POS)
        fig.add_bar(x=ordem_dias_pt(), y=-rec_sem["bb_gasto"], name="gasto", marker_color=C_NEG)
        fig.update_layout(barmode="relative", title="Recarga × gasto por dia da semana",
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # ---------- Estresse
    if d is not None and len(d) and d["estresse_medio"].notna().any():
        st.subheader("😰 Estresse")
        explica(
            "Escala 0–100 derivada do sistema nervoso: **0–25** descanso · **26–50** baixo · "
            "**51–75** médio · **76–100** alto."
        )
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_scatter(x=d["date"], y=d["estresse_medio"], mode="markers", name="média diária",
                            marker=dict(color=PALETA[3], size=6))
            mm = d.set_index("date")["estresse_medio"].rolling(7, min_periods=3).mean()
            fig.add_scatter(x=mm.index, y=mm, mode="lines", name="média 7d", line=dict(color=PALETA[0], width=3))
            fig.add_hline(y=25, line_dash="dash", line_color=C_POS, annotation_text="baixo")
            fig.add_hline(y=50, line_dash="dash", line_color=PALETA[2], annotation_text="médio")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with c2:
            dur = d[["descanso_min", "baixo_min", "medio_min", "alto_min"]].mean()
            fig = go.Figure(go.Pie(labels=["Descanso", "Baixo", "Médio", "Alto"], values=dur.values,
                                   hole=0.45, marker=dict(colors=[C_POS, "#f5a623", "#ef6c6c", "#c0392b"])))
            fig.update_traces(textinfo="percent")
            fig.update_layout(title="Distribuição do dia por nível de estresse")
            st.plotly_chart(style_fig(fig), use_container_width=True)

    # ---------- Passos, pisos e intensidade
    if d is not None and len(d) and d["passos"].notna().any():
        st.subheader("👟 Passos, pisos e intensidade")
        kpi([1] * 4, [
            ("Passos/dia", f"{d['passos'].mean():,.0f}".replace(",", "."),
             f"{d['atingiu_meta_passos'].mean() * 100:.0f}% da meta" if "atingiu_meta_passos" in d.columns else None),
            ("Meta de passos", f"{d['meta_passos'].mean():,.0f}".replace(",", "."), None),
            ("Pisos/dia", f"{d['pisos_subidos_m'].mean() / 3:.1f}", None),
            ("Intensidade/dia", f"{(d['min_moderado'].fillna(0) + 2 * d['min_vigoroso'].fillna(0)).mean():.0f} min",
             "meta OMS: ~30 min/dia"),
        ])
        fig = go.Figure()
        fig.add_bar(x=d["date"], y=d["passos"], name="passos", marker_color=PALETA[1])
        if "meta_passos" in d.columns:
            fig.add_scatter(x=d["date"], y=d["meta_passos"], name="meta", mode="lines",
                            line=dict(color=PALETA[3], dash="dash", width=2))
        fig.update_layout(title="Passos diários × meta")
        st.plotly_chart(style_fig(fig), use_container_width=True)

        sem_int = d.copy()
        sem_int["semana"] = sem_int["date"].dt.to_period("W").astype(str)
        sem_int = sem_int.groupby("semana").agg(
            min_tot=("min_moderado", lambda x: x.fillna(0).sum()),
            min_vig=("min_vigoroso", lambda x: x.fillna(0).sum()),
        )
        sem_int["ponderada"] = sem_int["min_tot"] + 2 * sem_int["min_vig"]
        meta_sem = d["meta_intensidade_semanal"].dropna().iloc[-1] if "meta_intensidade_semanal" in d and d["meta_intensidade_semanal"].notna().any() else 350
        fig = go.Figure()
        fig.add_bar(x=sem_int.index, y=sem_int["ponderada"], marker_color=PALETA[0], name="min/sem (vigoroso ×2)")
        fig.add_hline(y=meta_sem, line_dash="dash", line_color=C_POS, annotation_text=f"meta {meta_sem:.0f} min")
        fig.update_layout(title="Minutos de intensidade por semana")
        st.plotly_chart(style_fig(fig), use_container_width=True)
        explica(
            "Minutos de intensidade somam moderado + 2× vigoroso. A OMS recomenda "
            "150–300 min moderados (ou 75–150 vigorosos) por semana."
        )

    # ---------- Energia diária (calorias) e hidratação
    if d is not None and len(d) and d["kcal_total"].notna().any():
        st.subheader("🔥 Balanço calórico e 💧 hidratação")
        explica(
            "Calorias **basais** = o que o corpo gasta só por existir (fixas) · calorias **ativas** = "
            "exercício e movimento (a única parte que você controla). "
            "O **suor** é a perda estimada por treino — repo o equivalente em água."
        )
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_bar(x=d["date"], y=d["kcal_basal"], name="basal", marker_color=C_NEUTRO)
            fig.add_bar(x=d["date"], y=d["kcal_ativa"], name="ativa", marker_color=PALETA[2])
            fig.update_layout(barmode="stack", title="Calorias diárias (basal + ativa)",
                              legend=dict(orientation="h", y=1.12))
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with c2:
            hid = no_periodo(g.hydration)
            if hid is not None and len(hid):
                fig = go.Figure()
                fig.add_bar(x=hid["date"], y=hid["agua_ml"] / 1000, name="registrar (L)", marker_color=PALETA[0])
                fig.add_scatter(x=hid["date"], y=hid["suor_ml"] / 1000, name="suor estimado (L)",
                                mode="markers", marker=dict(color=PALETA[3], size=6))
                fig.update_layout(title="Hidratação registrada × perda por suor",
                                  legend=dict(orientation="h", y=1.12))
                st.plotly_chart(style_fig(fig), use_container_width=True)
                st.caption(f"Média de suor por treino: **{hid['suor_ml'].mean():.0f} ml** "
                           f"(estimativa do Garmin por atividade).")
            else:
                st.info("Sem registros de hidratação no período.")


def view_correlacoes():
    st.header("🔗 Correlações & Padrões")
    m = g.master
    if m is None or len(m) < 10:
        st.warning("Dados insuficientes para correlações.")
        return
    m = m[(m.index >= P_INI) & (m.index <= P_FIM)]

    rotulos = {
        "treino_min": "Treino (min)", "treino_km": "Treino (km)", "treino_kcal": "Treino kcal",
        "passos": "Passos", "fc_repouso": "FC repouso", "estresse_medio": "Estresse",
        "sono_h": "Sono (h)", "profundo_h": "Sono profundo", "rem_h": "Sono REM",
        "eficiencia_pct": "Eficiência sono", "score_overall": "Score sono",
        "bb_max": "BB pico", "bb_min": "BB mín", "bb_recarga": "BB recarga",
        "HRV_valor": "HRV", "agua_ml": "Água (ml)", "spo2_media": "SpO₂",
        "divida_sono_h": "Dívida sono", "acwr": "ACWR",
    }
    colunas = [c for c in rotulos if c in m.columns and m[c].notna().sum() >= 10]
    if len(colunas) < 2:
        st.warning("Período muito curto para análise de correlação — selecione pelo menos um mês.")
        return

    st.subheader("📊 Matriz de correlação (Pearson)")
    corr = m[colunas].corr()
    corr.index = [rotulos[c] for c in colunas]
    corr.columns = [rotulos[c] for c in colunas]
    fig = px.imshow(corr, color_continuous_scale=SEQ_DIVERG, zmin=-1, zmax=1, text_auto=".2f",
                    aspect="auto")
    fig.update_layout(height=max(500, 45 * len(colunas)))
    st.plotly_chart(style_fig(fig), use_container_width=True)

    with st.expander("ℹ️ Como interpretar"):
        st.markdown(
            "Correlação varia de **−1 a +1**: valores próximos de ±0,4 já indicam relação moderada; "
            "acima de ±0,7, forte. **Correlação não é causa** — indica apenas que as variáveis "
            "andam juntas nos seus dados."
        )

    # top pares
    pares = []
    for i in range(len(colunas)):
        for j in range(i + 1, len(colunas)):
            v = corr.iloc[i, j]
            if pd.notna(v):
                pares.append((corr.index[i], corr.index[j], v))
    pares = sorted(pares, key=lambda x: -abs(x[2]))[:8]
    st.subheader("🔝 Relações mais fortes")
    c1, c2 = st.columns(2)
    for i, (v1, v2, r) in enumerate(pares[:6]):
        with (c1 if i % 2 == 0 else c2):
            emoji = "🔥" if abs(r) >= 0.6 else ("💪" if abs(r) >= 0.35 else "•")
            cor = C_POS if (r > 0) else C_NEG
            st.markdown(
                f"<div class='insight-card' style='border-left:4px solid {cor}'>"
                f"<b>{emoji} {v1} ↔ {v2}: r = {r:+.2f}</b>"
                f"<p>{'Sobem juntos' if r > 0 else 'Um sobe, o outro desce'} "
                f"(|r| {'≥ 0,6 — forte' if abs(r) >= 0.6 else '≥ 0,35 — moderada'})</p></div>",
                unsafe_allow_html=True,
            )

    # análise defasada
    st.subheader("⏭️ Efeito no dia seguinte (defasagem de 1 dia)")
    lags = [("treino_min_ontem", "Treino de ontem"), ("sono_h_ontem", "Sono de ontem"),
            ("estresse_medio_ontem", "Estresse de ontem")]
    alvos = [("bb_min", "BB mínimo hoje"), ("estresse_medio", "Estresse hoje"),
             ("sono_h", "Sono hoje"), ("fc_repouso", "FC repouso hoje"), ("score_overall", "Score de sono hoje")]
    linhas = []
    for lag_c, lag_n in lags:
        if lag_c not in m.columns:
            continue
        for alvo_c, alvo_n in alvos:
            if alvo_c not in m.columns:
                continue
            par = m[[lag_c, alvo_c]].dropna()
            if len(par) >= 20:
                r = par[lag_c].corr(par[alvo_c])
                if pd.notna(r):
                    linhas.append({"Ontem": lag_n, "Hoje": alvo_n, "r": round(r, 2), "n": len(par)})
    if linhas:
        lg = pd.DataFrame(linhas).sort_values("r", key=abs, ascending=False)
        fig = px.bar(lg, x="r", y=lg["Ontem"] + " → " + lg["Hoje"], orientation="h",
                     color="r", color_continuous_scale=SEQ_DIVERG, range_color=[-0.5, 0.5],
                     labels={"y": "", "x": "correlação"})
        fig.update_layout(height=max(350, 28 * len(lg)))
        st.plotly_chart(style_fig(fig), use_container_width=True)
        st.caption("Ex.: 'Sono de ontem → BB mínimo hoje' com r alto confirma que dormir bem recarrega a energia do dia seguinte.")

    # scatter interativo
    st.subheader("🔬 Explorador de dispersão")
    opcoes = {rotulos[c]: c for c in colunas}
    cc1, cc2 = st.columns(2)
    with cc1:
        x_lbl = st.selectbox("Eixo X", list(opcoes), index=0)
    with cc2:
        default_y = list(opcoes).index("Sono (h)") if "Sono (h)" in opcoes else 1
        y_lbl = st.selectbox("Eixo Y", list(opcoes), index=default_y)
    fig = px.scatter(m.reset_index(), x=opcoes[x_lbl], y=opcoes[y_lbl], trendline=TREND_RETA,
                     labels={"date": "Data", "index": "Data"})
    st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("💡 Todos os insights automáticos")
    for it in gerar_insights(g):
        st.markdown(f"**{it['emoji']} {it['titulo']}** — {it['texto']}")


def view_perfil():
    st.header("🏆 Perfil, Recordes & Equipamentos")

    # perfil
    p = g.profile
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown("<div class='kpi-card'>", unsafe_allow_html=True)
        st.markdown(f"### 👤 {p.get('nome', '—')}")
        altura = f"{p['altura_m']:.2f} m" if p.get("altura_m") else "—"
        peso = f"{p['peso_kg']:.1f} kg" if p.get("peso_kg") else "—"
        imc = f"IMC {p['bmi']:.1f}" if p.get("bmi") else ""
        idade = f"{p['idade']} anos ·" if p.get("idade") else ""
        st.markdown(
            f"{idade} {p.get('genero', '')}  \n{altura} · {peso}  \n{imc}"
            + (f"  \nFTP {p['ftp']} W" if p.get("ftp") else "")
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # fitness age
    fa = no_periodo(g.fitness_age)
    if fa is not None and len(fa) and "idade_bio" in fa.columns:
        st.subheader("🧬 Idade fisiológica (Fitness Age)")
        explica(
            "Idade que o corpo 'tem' segundo VO₂, IMC e FC de repouso. **Menor que a cronológica** = "
            "corpo mais jovem que a idade; a linha verde mostra o possível com hábitos ideais."
        )
        ult = fa.iloc[-1]
        delta = ult["idade_bio"] - ult["idade_cronologica"]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Idade cronológica", f"{ult['idade_cronologica']:.0f} anos")
        with c2:
            st.metric("Idade fisiológica", f"{ult['idade_bio']:.1f} anos",
                      f"{delta:+.1f} anos", delta_color="inverse")
        with c3:
            st.metric("Potencial (estilo de vida saudável)", f"{ult['idade_bio_ideal']:.1f} anos")
        fig = go.Figure()
        fig.add_scatter(x=fa["date"], y=fa["idade_bio"], mode="lines", name="Idade fisiológica",
                        line=dict(color=PALETA[0], width=3))
        fig.add_scatter(x=fa["date"], y=fa["idade_cronologica"], mode="lines", name="Cronológica",
                        line=dict(color=C_NEUTRO, dash="dash"))
        fig.add_scatter(x=fa["date"], y=fa["idade_bio_ideal"], mode="lines", name="Ideal possível",
                        line=dict(color=C_POS, dash="dot"))
        fig.update_layout(title="Evolução da idade fisiológica")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # VO2
    vo2 = no_periodo(g.vo2max) if g.vo2max is not None else None
    if vo2 is not None and len(vo2):
        st.subheader("🫁 VO₂ Máx (capacidade aeróbica)")
        fig = px.scatter(vo2, x="date", y="vo2", color="esporte",
                         labels={"date": "", "vo2": "ml/kg/min"}, color_discrete_sequence=PALETA)
        st.plotly_chart(style_fig(fig, height=300), use_container_width=True)
        st.caption("Referência (homens 30-39): ruim <39 · média 41-45 · boa 47-51 · excelente ≥52 ml/kg/min.")

    # PRs
    if g.prs is not None and len(g.prs):
        st.subheader("🏅 Recordes pessoais")
        prs = g.prs.copy()
        prs["quando"] = prs["quando"].dt.strftime("%d/%m/%Y")
        prs.columns = ["Recorde", "Valor", "Unidade", "Data", "Atividade"]
        prs["Valor"] = prs["Valor"].round(2)
        st.dataframe(prs.drop(columns=["Atividade"]), use_container_width=True, hide_index=True)

    # gear
    if g.gear:
        st.subheader("👟 Equipamentos")
        for eq in g.gear:
            pct = min(eq["km_usados"] / eq["vida_max_km"] * 100, 100) if eq["vida_max_km"] else None
            st.markdown(f"**{eq['nome']}** ({eq['tipo'].lower()}, desde {eq['desde']}) — "
                        f"{eq['km_usados']:.0f} km em {eq['atividades']} atividades"
                        + (f" · vida útil {pct:.0f}%" if pct is not None else ""))
            if pct is not None:
                st.progress(min(pct / 100, 1.0), text=f"vida útil estimada: {eq['vida_max_km']:.0f} km")


def view_glossario():
    st.header("📖 Glossário — como interpretar cada métrica")
    st.markdown(
        "Guia de referência das métricas usadas neste dashboard. "
        "A regra de ouro: **compare-se com o seu próprio histórico** — as faixas de referência "
        "são populacionais e servem apenas de norte."
    )
    df = pd.DataFrame(GLOSSARIO)
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    st.subheader("🎚️ Regras rápidas: maior ou menor é melhor?")
    maior = ["HRV", "VO₂ Máx", "Eficiência do sono", "Score de sono", "Body Battery (pico)", "SpO₂", "Cadência (até ~185)"]
    menor = ["FC de repouso", "Ritmo (min/km)", "GCT", "Oscilação vertical", "Idade fisiológica", "Estresse", "Dívida de sono", "SWOLF"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ✅ Quanto MAIOR, melhor\n" + "\n".join(f"- {t}" for t in maior))
    with c2:
        st.markdown("#### 🎯 Quanto MENOR, melhor\n" + "\n".join(f"- {t}" for t in menor))


# ==================================================================== main
st.markdown("<h1 class='main-header'>⚡ Garmin Connect Analytics</h1>", unsafe_allow_html=True)
st.markdown(
    f"<p class='sub-header'>{P_INI.strftime('%d/%m/%Y')} → {P_FIM.strftime('%d/%m/%Y')} · "
    f"tema {theme_base()} (os gráficos acompanham)</p>",
    unsafe_allow_html=True,
)

abas = st.tabs([
    "🎯 Resumo",
    "🏃 Atividades",
    "⚡ Performance & Carga",
    "😴 Sono",
    "💗 Saúde & Energia",
    "🔗 Correlações",
    "🏆 Perfil & Recordes",
    "📖 Glossário",
])
with abas[0]:
    view_resumo()
with abas[1]:
    view_atividades()
with abas[2]:
    view_performance()
with abas[3]:
    view_sono()
with abas[4]:
    view_saude()
with abas[5]:
    view_correlacoes()
with abas[6]:
    view_perfil()
with abas[7]:
    view_glossario()
