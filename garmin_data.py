"""
Carregamento e preparação dos dados exportados do Garmin Connect (GDPR export).

Fontes cobertas:
  - DI-Connect-Fitness/  *_summarizedActivities.json, *_personalRecord.json, *_gear.json
  - DI-Connect-Aggregator/  UDSFile*.json (bem-estar diário), HydrationLogFile*.json
  - DI-Connect-Wellness/  *_sleepData.json, *_healthStatusData.json, *_fitnessAgeData.json,
                          132899879_userBioMetricProfileData.json, 132899879_heartRateZones.json
  - DI-Connect-Metrics/  MetricsMaxMetData*.json (tendência de VO2 Máx)
  - DI-Connect-User/     user_profile.json

Decisões de negócio (validadas contra os dados reais):
  * `distance` das atividades vem em CENTÍMETROS -> dividir por 100.000 para km.
  * `calories` das atividades vem INFLADO (~4-6x); `bmrCalories` é o valor realista
    de gasto da atividade (calorias ativas + metabolismo basal do período).
    Para o balanço diário, usar activeKilocalories/totalKilocalories do UDS.
  * Timestamps GMT são convertidos para hora local usando o offset inferido de
    startTimeGmt vs startTimeLocal das próprias atividades (fallback: -3h, Brasil).
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DIAS_SEMANA = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DIAS_PT = {
    "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta", "Thursday": "Quinta",
    "Friday": "Sexta", "Saturday": "Sábado", "Sunday": "Domingo",
}
DIAS_PT_CURTO = {k: v[:3] for k, v in DIAS_PT.items()}

TIPOS_ATIVIDADE_PT = {
    "walking": "Caminhada",
    "running": "Corrida",
    "treadmill_running": "Corrida (esteira)",
    "cycling": "Ciclismo",
    "indoor_cycling": "Ciclismo indoor",
    "strength_training": "Musculação",
    "lap_swimming": "Natação",
    "yoga": "Yoga",
    "hiking": "Trilha",
    "gym": "Academia",
    "fitness_equipment": "Fitness",
    "cardio": "Cardio",
    "tennis_v2": "Tênis",
    "other": "Outros",
}

# Tipos cuja distância faz sentido como métrica principal
TIPOS_DISTANCIA = {"Caminhada", "Corrida", "Corrida (esteira)", "Ciclismo", "Ciclismo indoor", "Natação", "Trilha"}
TIPOS_CORRIDA = {"Corrida", "Corrida (esteira)"}


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_dt(series: pd.Series) -> pd.Series:
    """Converte série para datetime, aceitando epoch em ms (numérico) ou string ISO."""
    if series is None:
        return pd.Series(dtype="datetime64[ns]")
    num = pd.to_numeric(series, errors="coerce")
    if num.notna().any() and (num.dropna() > 1e11).all():
        return pd.to_datetime(num, unit="ms", errors="coerce")
    return pd.to_datetime(series, errors="coerce", format="mixed")


class GarminExport:
    """Parser completo de um export do Garmin Connect (pasta extraída ou arquivo .zip)."""

    def __init__(self, path):
        self.src = Path(path)
        self.warnings: list[str] = []
        self.profile: dict = {}
        self.tz_offset_hours: float = -3.0
        self.hr_zone_defs: pd.DataFrame | None = None
        self.activities: pd.DataFrame | None = None
        self.daily: pd.DataFrame | None = None
        self.sleep: pd.DataFrame | None = None
        self.health: pd.DataFrame | None = None
        self.hydration: pd.DataFrame | None = None
        self.fitness_age: pd.DataFrame | None = None
        self.vo2max: pd.DataFrame | None = None
        self.prs: pd.DataFrame | None = None
        self.gear: list[dict] = []
        self.master: pd.DataFrame | None = None

    # ------------------------------------------------------------------ infra
    def _root(self) -> Path:
        """Raiz do export: pasta informada diretamente ou extraída do zip em tmp."""
        if self.src.is_file() and self.src.suffix.lower() == ".zip":
            tmp = Path(tempfile.mkdtemp(prefix="garmin_"))
            with zipfile.ZipFile(self.src) as z:
                z.extractall(tmp)
            return tmp
        return self.src

    def _find(self, root: Path, pattern: str) -> list[Path]:
        return sorted(root.rglob(pattern))

    def _local(self, ts_like: pd.Series) -> pd.Series:
        """GMT -> hora local, com base no offset inferido."""
        return _to_dt(ts_like) + pd.Timedelta(hours=self.tz_offset_hours)

    def _add_period_cols(self, df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df = df.dropna(subset=[col]).copy()
        df["year"] = df[col].dt.year
        df["month"] = df[col].dt.to_period("M").astype(str)
        df["week"] = df[col].dt.to_period("W").astype(str)
        df["weekday"] = df[col].dt.day_name()
        return df

    # ------------------------------------------------------------------ load
    def load(self) -> "GarminExport":
        root = self._root()
        self._load_profile(root)
        self._infer_tz(root)
        self._load_hr_zones(root)
        self._load_activities(root)
        self._load_daily(root)
        self._load_sleep(root)
        self._load_health(root)
        self._load_hydration(root)
        self._load_fitness_age(root)
        self._load_vo2max(root)
        self._load_prs(root)
        self._load_gear(root)
        self._build_master()
        return self

    # ----------------------------------------------------------------- itens
    def _load_profile(self, root: Path):
        files = self._find(root, "user_profile.json") or self._find(root, "*social-profile.json")
        if files:
            try:
                d = _read_json(files[0])
                self.profile["nome"] = f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
                self.profile["genero"] = {"MALE": "Masculino", "FEMALE": "Feminino"}.get(d.get("gender"), d.get("gender"))
                self.profile["nascimento"] = d.get("birthDate")
            except Exception:
                pass
        bio = self._find(root, "*userBioMetricProfileData.json")
        if bio:
            try:
                d = _read_json(bio[0])
                if isinstance(d, list) and d:
                    d = d[0]
                self.profile["altura_m"] = (d.get("height") or 0) / 100 or None
                peso_g = d.get("weight")
                self.profile["peso_kg"] = (peso_g / 1000) if peso_g else None
                self.profile["ftp"] = d.get("functionalThresholdPower")
                if self.profile.get("altura_m") and self.profile.get("peso_kg"):
                    self.profile["bmi"] = self.profile["peso_kg"] / self.profile["altura_m"] ** 2
            except Exception:
                pass
        if self.profile.get("nascimento"):
            try:
                nasc = dt.datetime.strptime(str(self.profile["nascimento"])[:10], "%Y-%m-%d").date()
                hoje = dt.date.today()
                self.profile["idade"] = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
            except Exception:
                pass

    def _infer_tz(self, root: Path):
        files = self._find(root, "*_summarizedActivities.json")
        if files:
            try:
                data = _read_json(files[0])
                acts = data[0]["summarizedActivitiesExport"]
                offs = [
                    (a["startTimeLocal"] - a["startTimeGmt"]) / 3600000
                    for a in acts
                    if a.get("startTimeLocal") and a.get("startTimeGmt")
                ]
                if offs:
                    self.tz_offset_hours = float(pd.Series(offs).mode().iloc[0])
            except Exception:
                pass

    def _load_hr_zones(self, root: Path):
        files = self._find(root, "*_heartRateZones.json")
        if not files:
            return
        try:
            rows = _read_json(files[0])
            df = pd.DataFrame(rows)
            df = df[df["sport"] == "DEFAULT"] if "sport" in df.columns else df
            if len(df):
                self.hr_zone_defs = df.head(1)
        except Exception:
            self.warnings.append("Não foi possível ler as zonas de frequência cardíaca.")

    def _load_activities(self, root: Path):
        files = self._find(root, "*_summarizedActivities.json")
        if not files:
            self.warnings.append("Arquivo de atividades (summarizedActivities) não encontrado.")
            return
        try:
            data = _read_json(files[0])
            acts = data[0]["summarizedActivitiesExport"]
        except Exception as e:
            self.warnings.append(f"Erro ao ler atividades: {e}")
            return
        if not acts:
            return
        df = pd.DataFrame(acts)

        df["start"] = self._local(df["beginTimestamp"])
        df = df.dropna(subset=["start"]).copy()
        df["date"] = df["start"].dt.normalize()
        df = self._add_period_cols(df)
        df["hour"] = df["start"].dt.hour + df["start"].dt.minute / 60

        df["tipo"] = df["activityType"].map(TIPOS_ATIVIDADE_PT).fillna(df["activityType"])
        df["nome"] = df.get("name", pd.Series(["Atividade"] * len(df), index=df.index))

        # durações (ms -> min)
        df["duracao_min"] = df.get("elapsedDuration", df.get("duration", 0)).fillna(0) / 60000
        df["movendo_min"] = df.get("movingDuration", 0).fillna(0) / 60000

        # distância (cm -> km) e ritmo/velocidade derivados
        df["dist_km"] = df.get("distance", 0).fillna(0) / 100000
        mov_h = (df["movendo_min"] / 60).replace(0, np.nan)
        df["ritmo_min_km"] = np.where(df["dist_km"] > 0, mov_h * 60 / df["dist_km"].replace(0, np.nan), np.nan)
        df["velocidade_kmh"] = np.where(mov_h.notna(), df["dist_km"] / mov_h, np.nan)

        # calorias: bmrCalories = valor realista (ver docstring)
        df["kcal"] = df.get("bmrCalories", df.get("calories", 0)).fillna(0)

        # FC
        for c, alias in [("fc_media", "avgHr"), ("fc_max", "maxHr"), ("fc_min", "minHr")]:
            df[c] = pd.to_numeric(df.get(alias), errors="coerce")

        # zonas de FC (ms) -> minutos
        for z in range(7):
            col = f"hrTimeInZone_{z}"
            df[f"z{z}_min"] = pd.to_numeric(df.get(col), errors="coerce").fillna(0) / 60000
        zcols = [f"z{i}_min" for i in range(7)]
        ztot = df[zcols].sum(axis=1).replace(0, np.nan)
        for z in range(7):
            df[f"z{z}_pct"] = df[f"z{z}_min"] / ztot * 100

        # efeito de treino e intensidade
        df["te_label"] = df.get("trainingEffectLabel")
        df["min_moderado"] = pd.to_numeric(df.get("moderateIntensityMinutes"), errors="coerce")
        df["min_vigoroso"] = pd.to_numeric(df.get("vigorousIntensityMinutes"), errors="coerce")
        df["vo2"] = pd.to_numeric(df.get("vO2MaxValue"), errors="coerce")

        # extras
        df["elev_gain_m"] = pd.to_numeric(df.get("elevationGain"), errors="coerce")
        df["passos"] = pd.to_numeric(df.get("steps"), errors="coerce")
        df["agua_ml"] = pd.to_numeric(df.get("waterEstimated"), errors="coerce")
        df["bb_diff"] = pd.to_numeric(df.get("differenceBodyBattery"), errors="coerce")
        df["series"] = pd.to_numeric(df.get("totalSets"), errors="coerce")
        df["reps"] = pd.to_numeric(df.get("totalReps"), errors="coerce")
        df["pot_media"] = pd.to_numeric(df.get("avgPower"), errors="coerce")
        df["pot_norm"] = pd.to_numeric(df.get("normPower"), errors="coerce")
        df["cadencia"] = pd.to_numeric(df.get("avgRunCadence"), errors="coerce")
        df["passada_m"] = pd.to_numeric(df.get("avgStrideLength"), errors="coerce")
        df["gct_ms"] = pd.to_numeric(df.get("avgGroundContactTime"), errors="coerce")
        df["oscilacao_mm"] = pd.to_numeric(df.get("avgVerticalOscillation"), errors="coerce")
        df["swolf"] = pd.to_numeric(df.get("avgSwolf"), errors="coerce")
        df["rpe"] = pd.to_numeric(df.get("workoutRpe"), errors="coerce")

        keep = [
            "activityId", "nome", "tipo", "sportType", "start", "date", "year", "month", "week",
            "weekday", "hour", "duracao_min", "movendo_min", "dist_km", "ritmo_min_km",
            "velocidade_kmh", "kcal", "fc_media", "fc_max", "fc_min", "te_label", "vo2",
            "min_moderado", "min_vigoroso", "elev_gain_m", "passos",
            "agua_ml", "bb_diff", "series", "reps", "pot_media", "pot_norm", "cadencia",
            "passada_m", "gct_ms", "oscilacao_mm", "swolf", "rpe",
        ] + zcols + [f"z{i}_pct" for i in range(7)]
        self.activities = df[[c for c in keep if c in df.columns]]

    def _load_daily(self, root: Path):
        """UDSFile*.json -> uma linha por dia com todo o bem-estar diário."""
        files = self._find(root, "UDSFile*.json")
        if not files:
            return
        rows = {}
        for f in files:
            try:
                data = _read_json(f)
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            for r in data:  # arquivos podem se sobrepor: mantém o mais recente (último lido)
                rows[r.get("calendarDate")] = r
        if not rows:
            return
        recs = []
        for r in rows.values():
            bb = r.get("bodyBattery") or {}
            stats = {s.get("bodyBatteryStatType"): s.get("statsValue") for s in bb.get("bodyBatteryStatList", [])}
            stress = None
            ad = r.get("allDayStress") or {}
            for agg in ad.get("aggregatorList", []):
                if agg.get("type") == "TOTAL":
                    stress = agg
                    break
            recs.append({
                "date": r.get("calendarDate"),
                "passos": r.get("totalSteps"),
                "meta_passos": r.get("dailyStepGoal"),
                "dist_km": (r.get("totalDistanceMeters") or 0) / 1000,
                "pisos_subidos_m": r.get("floorsAscendedInMeters"),
                "min_moderado": r.get("moderateIntensityMinutes"),
                "min_vigoroso": r.get("vigorousIntensityMinutes"),
                "meta_intensidade_semanal": r.get("userIntensityMinutesGoal"),
                "dia_vigoroso": r.get("isVigorousDay"),
                "fc_repouso": r.get("restingHeartRate"),
                "fc_min": r.get("minHeartRate"),
                "fc_max": r.get("maxHeartRate"),
                "kcal_ativa": r.get("activeKilocalories"),
                "kcal_total": r.get("totalKilocalories"),
                "kcal_basal": r.get("bmrKilocalories"),
                "spo2_media": r.get("averageSpo2Value"),
                "spo2_min": r.get("lowestSpo2Value"),
                "respiracao": r.get("respiration"),
                "bb_max": stats.get("HIGHEST"),
                "bb_min": stats.get("LOWEST"),
                "bb_recarga": bb.get("chargedValue"),
                "bb_gasto": bb.get("drainedValue"),
                "estresse_medio": (stress or {}).get("averageStressLevel"),
                "estresse_max": (stress or {}).get("maxStressLevel"),
                "descanso_min": ((stress or {}).get("restDuration") or 0) / 60,
                "baixo_min": ((stress or {}).get("lowDuration") or 0) / 60,
                "medio_min": ((stress or {}).get("mediumDuration") or 0) / 60,
                "alto_min": ((stress or {}).get("highDuration") or 0) / 60,
            })
        df = pd.DataFrame(recs)
        df = self._add_period_cols(df)
        # metas
        if "meta_passos" in df.columns:
            df["atingiu_meta_passos"] = df["passos"] >= df["meta_passos"]
        self.daily = df

    def _load_sleep(self, root: Path):
        files = self._find(root, "*_sleepData.json")
        if not files:
            self.warnings.append("Arquivos de sono (sleepData) não encontrados.")
            return
        recs = []
        for f in files:
            try:
                data = _read_json(f)
            except Exception:
                continue
            if isinstance(data, list):
                recs.extend(data)
        if not recs:
            return
        df = pd.DataFrame(recs)
        df["date"] = pd.to_datetime(df["calendarDate"], errors="coerce")

        df["inicio"] = self._local(df["sleepStartTimestampGMT"])
        df["fim"] = self._local(df["sleepEndTimestampGMT"])
        # hora de dormir/acordar como fração do dia (detecção de coruja/matutino)
        df["hora_dormir"] = df["inicio"].dt.hour + df["inicio"].dt.minute / 60
        df["hora_acordar"] = df["fim"].dt.hour + df["fim"].dt.minute / 60

        for src, dst in [
            ("deepSleepSeconds", "profundo_h"), ("lightSleepSeconds", "leve_h"),
            ("remSleepSeconds", "rem_h"), ("awakeSleepSeconds", "acordado_h"),
            ("unmeasurableSeconds", "nao_mensuravel_h"),
        ]:
            df[dst] = pd.to_numeric(df.get(src), errors="coerce").fillna(0) / 3600
        df["sono_h"] = df["profundo_h"] + df["leve_h"] + df["rem_h"]
        df["cama_h"] = (df["fim"] - df["inicio"]).dt.total_seconds() / 3600
        df["eficiencia_pct"] = np.where(df["cama_h"] > 0, df["sono_h"] / df["cama_h"] * 100, np.nan)
        df["divida_sono_h"] = (7.5 - df["sono_h"]).clip(lower=0)  # alvo 7h30

        # scores e sub-scores
        def score(key):
            return df["sleepScores"].apply(lambda x: x.get(key) if isinstance(x, dict) else None)
        if "sleepScores" in df.columns:
            for k in ["overall", "quality", "duration", "recovery", "deep", "rem", "light",
                      "restfulness", "interruptions"]:
                df[f"score_{k}"] = score(f"{k}Score")

        # SpO2 e demais sinais durante o sono
        spo = df["spo2SleepSummary"].apply(lambda x: x if isinstance(x, dict) else {})
        df["spo2_sono"] = pd.to_numeric(spo.apply(lambda x: x.get("averageSPO2")), errors="coerce")
        df["spo2_sono_min"] = pd.to_numeric(spo.apply(lambda x: x.get("lowestSPO2")), errors="coerce")
        df["fc_sono"] = pd.to_numeric(spo.apply(lambda x: x.get("averageHR")), errors="coerce")
        df["respiracao_media"] = pd.to_numeric(df.get("averageRespiration"), errors="coerce")
        df["estresse_sono"] = pd.to_numeric(df.get("avgSleepStress"), errors="coerce")
        df["momentos_inquietos"] = pd.to_numeric(df.get("restlessMomentCount"), errors="coerce")
        df["despertares"] = pd.to_numeric(df.get("awakeCount"), errors="coerce")

        df = self._add_period_cols(df)
        self.sleep = df.dropna(subset=["date"]).sort_values("date")

    def _load_health(self, root: Path):
        files = self._find(root, "*_healthStatusData.json")
        if not files:
            return
        recs = []
        for f in files:
            try:
                data = _read_json(f)
            except Exception:
                continue
            if isinstance(data, list):
                recs.extend(data)
        if not recs:
            return
        expanded = []
        for r in recs:
            row = {"date": r.get("calendarDate")}
            for m in r.get("metrics", []) or []:
                t = m.get("type", "?")
                row[f"{t}_valor"] = m.get("value")
                row[f"{t}_lim_sup"] = m.get("baselineUpperLimit")
                row[f"{t}_lim_inf"] = m.get("baselineLowerLimit")
                row[f"{t}_status"] = m.get("status")
            expanded.append(row)
        df = pd.DataFrame(expanded)
        self.health = self._add_period_cols(df).sort_values("date")

    def _load_hydration(self, root: Path):
        files = self._find(root, "HydrationLogFile*.json")
        if not files:
            return
        recs = []
        for f in files:
            try:
                data = _read_json(f)
            except Exception:
                continue
            if isinstance(data, list):
                recs.extend(data)
        if not recs:
            return
        df = pd.DataFrame(recs)
        agg = df.groupby("calendarDate").agg(
            agua_ml=("valueInML", "sum"),
            suor_ml=("estimatedSweatLossInML", "sum"),
            registros=("valueInML", "count"),
        ).reset_index().rename(columns={"calendarDate": "date"})
        self.hydration = self._add_period_cols(agg)

    def _load_fitness_age(self, root: Path):
        files = self._find(root, "*_fitnessAgeData.json")
        if not files:
            return
        try:
            data = _read_json(files[0])
        except Exception:
            return
        if not isinstance(data, list) or not data:
            return
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df.get("asOfDateGmt"), errors="coerce")
        cols = {
            "chronologicalAge": "idade_cronologica", "bmi": "bmi", "rhr": "fc_repouso",
            "currentBioAge": "idade_bio", "healthyAllBioAge": "idade_bio_ideal",
            "biometricVo2Max": "vo2_biometrico", "healthyFat": "gordura_saudavel",
        }
        for src, dst in cols.items():
            if src in df.columns:
                df[dst] = pd.to_numeric(df[src], errors="coerce")
        self.fitness_age = self._add_period_cols(df[[
            c for c in ["date", "idade_cronologica", "idade_bio", "idade_bio_ideal", "bmi",
                        "fc_repouso", "vo2_biometrico", "gordura_saudavel"] if c in df.columns
        ]]).sort_values("date")

    def _load_vo2max(self, root: Path):
        files = self._find(root, "MetricsMaxMetData*.json")
        if not files:
            return
        recs = []
        for f in files:
            try:
                data = _read_json(f)
            except Exception:
                continue
            if isinstance(data, list):
                recs.extend(data)
        if not recs:
            return
        df = pd.DataFrame(recs)
        df["date"] = pd.to_datetime(df.get("calendarDate"), errors="coerce")
        df["vo2"] = pd.to_numeric(df.get("vo2MaxValue"), errors="coerce")
        df["esporte"] = df.get("sport")
        self.vo2max = self._add_period_cols(df[["date", "esporte", "vo2"]]).sort_values("date")

    def _load_prs(self, root: Path):
        files = self._find(root, "*_personalRecord.json")
        if not files:
            return
        try:
            data = _read_json(files[0])
            prs = data[0]["personalRecords"]
        except Exception:
            return
        rows = []
        for pr in prs:
            try:
                quando = dt.datetime.strptime(pr["prStartTimeGMT"], "%a %b %d %H:%M:%S GMT %Y")
            except Exception:
                quando = None
            tipo = pr.get("personalRecordType", "?")
            valor = float(pr.get("value") or 0)
            unidade = "—" if valor == 0 else ("km" if "Farthest" in tipo else ("min" if "Best" in tipo else ""))
            valor_fmt = valor / 1000 if unidade == "km" else valor
            rows.append({
                "tipo": tipo,
                "valor": valor_fmt,
                "unidade": unidade,
                "quando": quando,
                "atividade": pr.get("activityId") or 0,
            })
        if rows:
            self.prs = pd.DataFrame(rows).sort_values("quando", na_position="first")

    def _load_gear(self, root: Path):
        files = self._find(root, "*_gear.json")
        if not files:
            return
        try:
            data = _read_json(files[0])
        except Exception:
            return
        acts = self.activities
        for g in data[0].get("gearDTOS", []):
            ids = {a["activityId"] for a in data[0].get("gearActivityDTOs", {}).get(str(g["gearPk"]), [])}
            km = dist = 0.0
            n = 0
            if acts is not None and ids:
                sel = acts[acts["activityId"].isin(ids)]
                km = float(sel["dist_km"].sum())
                n = len(sel)
            self.gear.append({
                "nome": g.get("customMakeModel") or g.get("gearTypeName"),
                "tipo": g.get("gearTypeName"),
                "status": g.get("gearStatusName"),
                "desde": g.get("dateBegin"),
                "vida_max_km": (g.get("maximumMeters") or 0) / 1000,
                "km_usados": km,
                "atividades": n,
            })

    # ----------------------------------------------------------------- master
    def _build_master(self):
        """Tabela diária única (atividades + bem-estar + sono + saúde + hidratação) para correlações."""
        frames = []
        if self.daily is not None and len(self.daily):
            frames.append(self.daily.set_index("date"))
        if self.sleep is not None and len(self.sleep):
            cols = ["sono_h", "profundo_h", "rem_h", "leve_h", "acordado_h", "eficiencia_pct",
                    "score_overall", "hora_dormir", "divida_sono_h", "spo2_sono", "estresse_sono"]
            frames.append(self.sleep.set_index("date")[[c for c in cols if c in self.sleep.columns]])
        if self.health is not None and len(self.health):
            cols = [c for c in self.health.columns if c.endswith("_valor")]
            frames.append(self.health.set_index("date")[cols])
        if self.hydration is not None and len(self.hydration):
            frames.append(self.hydration.set_index("date")[["agua_ml", "suor_ml"]])
        if self.activities is not None and len(self.activities):
            agg = self.activities.groupby("date").agg(
                treino_qtd=("activityId", "count"),
                treino_min=("duracao_min", "sum"),
                treino_km=("dist_km", "sum"),
                treino_kcal=("kcal", "sum"),
                fc_media_treino=("fc_media", "mean"),
                z_alto_min=("z4_min", "sum"),
            )
            frames.append(agg)

        if not frames:
            return
        master = pd.concat(frames, axis=1).sort_index()

        # carga de treino: aguda (7d) vs crônica (média das 4 semanas) -> ACWR
        if "treino_min" in master.columns:
            carga = master["treino_min"].fillna(0)
            aguda = carga.rolling(7, min_periods=3).sum()
            cronica = carga.rolling(28, min_periods=14).sum() / 4
            master["carga_7d_min"] = aguda
            master["acwr"] = aguda / cronica.replace(0, np.nan)

        # variáveis defasadas (efeito do dia no dia seguinte)
        for col in ["treino_min", "treino_kcal", "sono_h", "estresse_medio", "carga_7d_min"]:
            if col in master.columns:
                master[f"{col}_ontem"] = master[col].shift(1)

        # médias móveis de 7 dias para suavizar tendências
        for col in ["sono_h", "estresse_medio", "fc_repouso", "passos"]:
            if col in master.columns:
                master[f"{col}_mm7"] = master[col].rolling(7, min_periods=3).mean()

        master.index.name = "date"
        self.master = master
