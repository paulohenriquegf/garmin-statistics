"""Smoke test via AppTest: período completo + combos de filtro Ano/Mês/Semana."""
import sys
from streamlit.testing.v1 import AppTest

DADOS = r"C:\Users\paulo\Downloads\d1332fc4-ec15-4bce-b1ce-e6c979982b81_1"


def rodar(modo="Ano / Mês / Semana", ano=None, mes=None, semana=None):
    at = AppTest.from_file("streamlit_dashboard.py", default_timeout=120)
    at.run()
    ti = next(t for t in at.text_input if t.key == "caminho_dados")
    ti.set_value(DADOS)
    at.run()
    rb = next(r for r in at.radio if r.key == "filtro_modo")
    rb.set_value(modo)
    at.run()
    if mes == "__MES__":
        sb = next(s for s in at.selectbox if s.key == "filtro_mes")
        mes = next(o for o in sb.options if "ago" in str(o).lower())
    if ano is not None:
        next(s for s in at.selectbox if s.key == "filtro_ano").select(ano)
        at.run()
    if mes is not None:
        next(s for s in at.selectbox if s.key == "filtro_mes").select(mes)
        at.run()
    if semana is not None:
        next(s for s in at.selectbox if s.key == "filtro_semana").select(semana)
        at.run()
    return at


casos = [
    ("Tudo", {}),
    ("Ano 2026", {"ano": "2026"}),
    ("ago/2026", {"ano": "2026", "mes": "__MES__"}),
]
falhas = 0
for nome, kwargs in casos:
    try:
        at = rodar(**kwargs)
        ex = [e.value for e in at.exception]
        print(f"OK  {nome:12s} excecoes={len(ex)} tabs={len(at.tabs)}")
        if ex:
            falhas += 1
            for e in ex[:3]:
                print("   ", e[:300])
        if nome == "Ano 2026":
            sb = next(s for s in at.selectbox if s.key == "filtro_mes")
            print("    opcoes mes:", sb.options[:15])
    except Exception as exc:  # noqa: BLE001
        falhas += 1
        print(f"ERRO {nome}: {exc!r}")

sys.exit(1 if falhas else 0)
