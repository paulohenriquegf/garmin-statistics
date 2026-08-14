"""
Tema, cores e helpers de visualização compartilhados.

O problema do "modo escuro com blocos brancos" do app antigo vinha de:
  1. CSS com fundos brancos fixos (linear-gradient #ffffff) — o @media
     (prefers-color-scheme) não acompanha o tema escolhido no menu do Streamlit;
  2. Gráficos Plotly com template padrão (fundo branco, texto escuro).

Solução:
  1. CSS sem cor fixa: sobreposições translúcidas (rgba) e `color: inherit`,
     que funcionam em qualquer tema;
  2. Template Plotly com fundo transparente e cores de texto/grade detectadas
     do tema ativo (st.context.theme quando disponível; senão config.toml).
"""

from __future__ import annotations

import streamlit as st

from garmin_data import DIAS_PT, DIAS_PT_CURTO, DIAS_SEMANA

# Paleta qualitativa legível em fundo claro e escuro
PALETA = ["#1abc9c", "#6ea8fe", "#f5a623", "#ef6c6c", "#b58cda", "#7fd3f5",
          "#e58fb1", "#a3c949", "#f0c987", "#8fa8c8"]

# Cores semânticas fixas (bom contraste nos dois temas)
C_POS = "#2ecc71"    # positivo / bom
C_NEG = "#e57373"    # negativo / atenção
C_NEUTRO = "#90a4ae"

# Escalas sequenciais seguras para os dois temas
SEQ_QUALI = "Set2"
SEQ_VERDE = "tealgrn"
SEQ_VERM = "orrd"
SEQ_AZUL = "blues"
SEQ_DIVERG = "rdBu_r"


# --------------------------------------------------------------------- tema
@st.cache_data(ttl=3600)
def _theme_base_fallback() -> str:
    try:
        base = st.get_option("theme.base")
    except Exception:
        base = None
    return base or "light"


def theme_base() -> str:
    """'dark' ou 'light' conforme o tema efetivamente ativo no Streamlit."""
    try:
        ctx = getattr(st, "context", None)
        if ctx is not None and getattr(ctx, "theme", None) is not None:
            return st.context.theme.base
    except Exception:
        pass
    return _theme_base_fallback()


def theme_colors() -> dict:
    dark = theme_base() == "dark"
    return {
        "texto": "#e8eaed" if dark else "#26292e",
        "texto_suave": "#9aa0a6" if dark else "#5f6368",
        "grade": "rgba(128,128,128,0.18)",
        "zero": "rgba(128,128,128,0.35)",
    }


def inject_css():
    """CSS adaptável a qualquer tema — nenhum fundo de cor fixa."""
    st.markdown(
        """
        <style>
          /* Cards translúcidos: herdam o fundo do tema (claro OU escuro) */
          .kpi-card, .insight-card {
              background-color: rgba(128,128,128,0.08);
              border: 1px solid rgba(128,128,128,0.22);
              border-radius: 12px;
              padding: 14px 16px;
              color: inherit;
          }
          .insight-card p { margin: 0.2rem 0 0 0; }
          .main-header {
              font-size: 2.4rem; font-weight: 800; text-align: center;
              margin-bottom: 0.2rem; color: inherit;
          }
          .sub-header {
              text-align: center; color: inherit; opacity: 0.75;
              margin-bottom: 1.5rem; font-size: 1.05rem;
          }
          /* Métricas do Streamlit sem override de fundo: seguem o tema */
          [data-testid="stMetric"] {
              background-color: rgba(128,128,128,0.07);
              border: 1px solid rgba(128,128,128,0.18);
              border-radius: 10px;
              padding: 12px 14px;
          }
          [data-testid="stMetricValue"] { font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------ plotly
def style_fig(fig, height: int | None = None, legend: bool = True):
    """Aplica o template do tema (fundo transparente, cores adaptativas)."""
    import plotly.graph_objects as go

    c = theme_colors()
    fig.update_layout(
        template="plotly_white" if theme_base() == "light" else "plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=c["texto"], family="sans serif"),
        colorway=PALETA,
        margin=dict(l=10, r=10, t=46, b=10),
        hoverlabel=dict(font=dict(color="#111111"), bgcolor="#f5f5f5"),
        showlegend=legend,
    )
    fig.update_xaxes(gridcolor=c["grade"], zerolinecolor=c["zero"])
    fig.update_yaxes(gridcolor=c["grade"], zerolinecolor=c["zero"])
    if height:
        fig.update_layout(height=height)
    return fig


# ---------------------------------------------------------------- helpers
def fmt_min(v) -> str:
    """Minutos decimais -> 'Xh Ymin'."""
    if v is None or v != v or v == 0:
        return "—"
    v = float(v)
    h, m = divmod(int(round(v)), 60)
    return f"{h}h {m:02d}min" if h else f"{m} min"


def fmt_ritmo(v) -> str:
    """Ritmo min/km decimal -> 'm:ss'."""
    if v is None or v != v or v <= 0:
        return "—"
    m, s = divmod(int(round(v * 60)), 60)
    return f"{m}:{s:02d}"


def fmt_hora_frac(v) -> str:
    """Fração de dia (0-24) -> 'HH:MM'."""
    if v is None or v != v:
        return "—"
    v = float(v) % 24
    return f"{int(v):02d}:{int(round(v % 1 * 60)):02d}"


def media_circular_horario(series) -> float | None:
    """Média circular de horas do dia (trata 23h e 0h como vizinhos). Âncora 20h."""
    s = series.dropna()
    if len(s) == 0:
        return None
    return float((((s - 20) % 24).mean() + 20) % 24)


def ordem_dias_pt() -> list[str]:
    return [DIAS_PT[d] for d in DIAS_SEMANA]


def rotulo_dia(series_dias):
    return series_dias.map(DIAS_PT).fillna(series_dias)


def rotulo_dia_curto(series_dias):
    return series_dias.map(DIAS_PT_CURTO).fillna(series_dias)


def card_titulo_icon(emoji: str, titulo: str) -> str:
    return f"### {emoji} {titulo}"


def kpi(larguras: list, itens: list):
    """Renderiza linha(s) de métricas. itens: (rotulo, valor, delta, delta_color)."""
    cols = st.columns(larguras)
    for col, (rotulo, valor, *resto) in zip(cols, itens):
        delta = resto[0] if resto else None
        dcolor = resto[1] if len(resto) > 1 else "normal"
        with col:
            st.metric(rotulo, valor, delta=delta, delta_color=dcolor)


def linha_resumo_periodo(df_filtrado, df_total, unidade: str = "registros"):
    ini, fim = df_filtrado["date"].min(), df_filtrado["date"].max()
    pct = len(df_filtrado) / max(len(df_total), 1) * 100
    st.caption(
        f"📊 {len(df_filtrado):,} de {len(df_total):,} {unidade} ({pct:.0f}%) | "
        f"{ini.strftime('%d/%m/%Y')} → {fim.strftime('%d/%m/%Y')}".replace(",", ".")
    )
