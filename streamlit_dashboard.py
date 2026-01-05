import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import zipfile
import tempfile
from pathlib import Path

# Configuração da página
st.set_page_config(
    page_title="Garmin Connect - Dashboard de Análise",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado para melhorar o visual
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
        padding: 20px;
        border-radius: 10px;
        color: #111;
        box-shadow: 0 6px 12px rgba(16,24,40,0.06);
        border: 1px solid rgba(16,24,40,0.06);
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 3px 6px rgba(16,24,40,0.04);
        color: #111;
        border: 1px solid rgba(16,24,40,0.04);
    }
    .sidebar .sidebar-content {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }

    /* Ajustes para modo escuro (melhor contraste e bordas sutis) */
    @media (prefers-color-scheme: dark) {
        .metric-card {
            background: linear-gradient(135deg, #2b2f3a 0%, #1b1e26 100%);
            color: #e6e6e6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.6);
            border: 1px solid rgba(255,255,255,0.06);
        }
        .stMetric {
            background-color: #151619;
            color: #e6e6e6;
            box-shadow: 0 2px 4px rgba(0,0,0,0.6);
            border: 1px solid rgba(255,255,255,0.04);
        }
        .sidebar .sidebar-content {
            background: linear-gradient(180deg, #2b2f3a 0%, #1b1e26 100%);
        }
    }

    /* For older browsers or Streamlit themes that don't set prefers-color-scheme,
       provide an explicit light-mode override as well */
    @media (prefers-color-scheme: light), (prefers-color-scheme: no-preference) {
        .metric-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
            color: #111;
            box-shadow: 0 6px 12px rgba(16,24,40,0.06);
            border: 1px solid rgba(16,24,40,0.06);
        }
        .stMetric {
            background-color: #ffffff;
            color: #111;
            box-shadow: 0 3px 6px rgba(16,24,40,0.04);
            border: 1px solid rgba(16,24,40,0.04);
        }
    }
</style>
""", unsafe_allow_html=True)


class GarminDataAnalyzer:
    """Classe para processar e analisar dados do Garmin Connect"""
    
    def __init__(self, zip_file):
        self.zip_file = zip_file
        self.temp_dir = tempfile.mkdtemp()
        self.activities_df = None
        self.sleep_df = None
        self.health_df = None
        self.hydration_df = None
        self.user_profile = None
        
    def extract_zip(self):
        """Extrai o arquivo ZIP"""
        with zipfile.ZipFile(self.zip_file, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
            
    def find_files(self, pattern):
        """Encontra arquivos por padrão"""
        return list(Path(self.temp_dir).rglob(pattern))
    
    def safe_parse_timestamp(self, series, column_name="timestamp"):
        """Converte timestamps de forma segura, lidando com diferentes formatos"""
        try:
            # Verificar se todos os valores são nulos
            if series.isna().all():
                return pd.to_datetime(series, errors='coerce')
            
            # Primeiro, tentar converter valores numéricos como milissegundos
            # Isso funciona para int, float, ou strings numéricas
            numeric_series = pd.to_numeric(series, errors='coerce')
            
            # Se conseguiu converter para numérico (e não são todos nulos)
            if not numeric_series.isna().all():
                # Verificar se os valores parecem timestamps em milissegundos
                # (valores muito grandes, típicos de timestamps)
                max_value = numeric_series.max()
                if max_value > 1000000000000:  # Típico de timestamps em ms
                    return pd.to_datetime(numeric_series, unit='ms', errors='coerce')
                elif max_value > 1000000000:  # Pode ser timestamp em segundos
                    return pd.to_datetime(numeric_series, unit='s', errors='coerce')
            
            # Se não é numérico, tentar converter como string (ISO format, etc)
            # Pandas automaticamente detecta formatos ISO como "2025-09-25T01:00:34.0"
            result = pd.to_datetime(series, errors='coerce')
            
            return result
            
        except Exception as e:
            st.warning(f"Aviso ao converter {column_name}: {str(e)}")
            return pd.to_datetime(series, errors='coerce')
    
    def load_activities(self):
        """Carrega dados de atividades"""
        try:
            files = self.find_files("*_summarizedActivities.json")
            if not files:
                return None
            
            with open(files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            activities = data[0]['summarizedActivitiesExport']
            
            if not activities:
                return None
            
            df = pd.DataFrame(activities)
            
            # Converter timestamps de forma segura
            # Atividades usam timestamps em milissegundos (números)
            if 'startTimeLocal' in df.columns:
                df['startTimeLocal'] = self.safe_parse_timestamp(df['startTimeLocal'], 'startTimeLocal')
            elif 'startTimeGmt' in df.columns:
                df['startTimeLocal'] = self.safe_parse_timestamp(df['startTimeGmt'], 'startTimeGmt')
            elif 'beginTimestamp' in df.columns:
                df['startTimeLocal'] = self.safe_parse_timestamp(df['beginTimestamp'], 'beginTimestamp')
            else:
                st.error("Coluna de data não encontrada nas atividades")
                return None
            
            # Debug: verificar conversão
            if df['startTimeLocal'].notna().any():
                min_date = df['startTimeLocal'].min()
                max_date = df['startTimeLocal'].max()
                if pd.notna(min_date) and pd.notna(max_date):
                    st.success(f"✅ Atividades carregadas: {len(df)} registros de {min_date.strftime('%d/%m/%Y')} até {max_date.strftime('%d/%m/%Y')}")
            
            # Remover linhas com datas inválidas
            df = df.dropna(subset=['startTimeLocal'])
            
            if len(df) == 0:
                return None
            
            df['date'] = df['startTimeLocal'].dt.date
            df['month'] = df['startTimeLocal'].dt.to_period('M')
            df['week'] = df['startTimeLocal'].dt.to_period('W')
            df['year'] = df['startTimeLocal'].dt.year
            df['weekday'] = df['startTimeLocal'].dt.day_name()
            df['hour'] = df['startTimeLocal'].dt.hour
            
            # Converter duração para minutos com verificação
            # No Garmin, elapsedDuration e movingDuration vêm em MILISSEGUNDOS
            # Preferir elapsedDuration (tempo total) ou usar duration como fallback
            if 'elapsedDuration' in df.columns:
                df['duration_seconds'] = df['elapsedDuration'].fillna(0) / 1000
                df['duration_minutes'] = df['duration_seconds'] / 60
            elif 'duration' in df.columns:
                df['duration_seconds'] = df['duration'].fillna(0) / 1000
                df['duration_minutes'] = df['duration_seconds'] / 60
            else:
                df['duration_seconds'] = 0
                df['duration_minutes'] = 0
            
            # Converter distância para km com verificação
            # No Garmin, distance vem em CENTÍMETROS
            if 'distance' in df.columns:
                df['distance_meters'] = df['distance'].fillna(0) / 100
                df['distance_km'] = df['distance_meters'] / 1000
            else:
                df['distance_meters'] = 0
                df['distance_km'] = 0
            
            # Preencher valores nulos em colunas importantes
            # No Garmin, bmrCalories contém as calorias reais da atividade
            # (o campo 'calories' geralmente tem valores inflados/incorretos)
            if 'bmrCalories' in df.columns:
                df['bmrCalories'] = df['bmrCalories'].fillna(0)
                df['activeCalories'] = df['bmrCalories']  # Usar bmrCalories como calorias ativas
            elif 'calories' in df.columns:
                df['calories'] = df['calories'].fillna(0)
                df['activeCalories'] = df['calories']
            else:
                df['activeCalories'] = 0
                
            if 'avgHr' in df.columns:
                df['avgHr'] = df['avgHr'].fillna(0)
            else:
                df['avgHr'] = 0
            
            # Traduzir tipos de atividade
            activity_translations = {
                'walking': 'Caminhada',
                'running': 'Corrida',
                'cycling': 'Ciclismo',
                'swimming': 'Natação',
                'strength_training': 'Musculação',
                'yoga': 'Yoga',
                'hiking': 'Trilha',
                'gym': 'Academia',
                'fitness_equipment': 'Equipamento Fitness',
                'cardio': 'Cardio',
                'other': 'Outros'
            }
            
            if 'activityType' in df.columns:
                df['activityType'] = df['activityType'].replace(activity_translations)
                # Manter original se não foi traduzido
                df['activityType'] = df['activityType'].fillna('Outros')
            else:
                df['activityType'] = 'Atividade'
            
            self.activities_df = df
            return df
            
        except Exception as e:
            st.error(f"Erro ao carregar atividades: {str(e)}")
            import traceback
            st.error(f"Detalhes: {traceback.format_exc()}")
            return None
    
    def load_sleep(self):
        """Carrega dados de sono"""
        try:
            files = self.find_files("*_sleepData.json")
            if not files:
                return None
            
            all_sleep = []
            for file in files:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_sleep.extend(data)
            
            if not all_sleep:
                return None
            
            df = pd.DataFrame(all_sleep)
            
            # Converter timestamps de forma segura
            df['calendarDate'] = pd.to_datetime(df['calendarDate'], errors='coerce')
            
            if 'sleepStartTimestampGMT' in df.columns:
                df['sleepStartTimestampGMT'] = self.safe_parse_timestamp(
                    df['sleepStartTimestampGMT'], 
                    'sleepStartTimestampGMT'
                )
            
            if 'sleepEndTimestampGMT' in df.columns:
                df['sleepEndTimestampGMT'] = self.safe_parse_timestamp(
                    df['sleepEndTimestampGMT'], 
                    'sleepEndTimestampGMT'
                )
            
            # Converter segundos para horas (com verificação de existência)
            if 'deepSleepSeconds' in df.columns:
                df['deepSleepHours'] = df['deepSleepSeconds'].fillna(0) / 3600
            else:
                df['deepSleepHours'] = 0
                
            if 'lightSleepSeconds' in df.columns:
                df['lightSleepHours'] = df['lightSleepSeconds'].fillna(0) / 3600
            else:
                df['lightSleepHours'] = 0
                
            if 'remSleepSeconds' in df.columns:
                df['remSleepHours'] = df['remSleepSeconds'].fillna(0) / 3600
            else:
                df['remSleepHours'] = 0
                
            if 'awakeSleepSeconds' in df.columns:
                df['awakeHours'] = df['awakeSleepSeconds'].fillna(0) / 3600
            else:
                df['awakeHours'] = 0
            
            df['totalSleepHours'] = df['deepSleepHours'] + df['lightSleepHours'] + df['remSleepHours']
            
            # Remover linhas com datas inválidas
            df = df.dropna(subset=['calendarDate'])
            
            if len(df) == 0:
                return None
            
            # Debug: verificar conversão
            if df['calendarDate'].notna().any():
                min_date = df['calendarDate'].min()
                max_date = df['calendarDate'].max()
                if pd.notna(min_date) and pd.notna(max_date):
                    st.success(f"✅ Dados de sono carregados: {len(df)} registros de {min_date.strftime('%d/%m/%Y')} até {max_date.strftime('%d/%m/%Y')}")
            
            # Adicionar períodos temporais
            df['month'] = df['calendarDate'].dt.to_period('M')
            df['week'] = df['calendarDate'].dt.to_period('W')
            df['year'] = df['calendarDate'].dt.year
            df['weekday'] = df['calendarDate'].dt.day_name()
            
            # Extrair sleep scores se existirem
            if 'sleepScores' in df.columns:
                df['overallScore'] = df['sleepScores'].apply(
                    lambda x: x.get('overallScore') if isinstance(x, dict) else None
                )
                df['qualityScore'] = df['sleepScores'].apply(
                    lambda x: x.get('qualityScore') if isinstance(x, dict) else None
                )
                df['recoveryScore'] = df['sleepScores'].apply(
                    lambda x: x.get('recoveryScore') if isinstance(x, dict) else None
                )
                df['durationScore'] = df['sleepScores'].apply(
                    lambda x: x.get('durationScore') if isinstance(x, dict) else None
                )
                df['deepScore'] = df['sleepScores'].apply(
                    lambda x: x.get('deepScore') if isinstance(x, dict) else None
                )
                df['remScore'] = df['sleepScores'].apply(
                    lambda x: x.get('remScore') if isinstance(x, dict) else None
                )
            
            # Preencher valores faltantes
            if 'awakeCount' not in df.columns:
                df['awakeCount'] = 0
            else:
                df['awakeCount'] = df['awakeCount'].fillna(0)
            
            self.sleep_df = df
            return df
            
        except Exception as e:
            st.error(f"Erro ao carregar dados de sono: {str(e)}")
            import traceback
            st.error(f"Detalhes: {traceback.format_exc()}")
            return None
    
    def load_health(self):
        """Carrega dados de saúde"""
        try:
            files = self.find_files("*_healthStatusData.json")
            if not files:
                return None
            
            all_health = []
            for file in files:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_health.extend(data)
            
            if not all_health:
                return None
            
            # Expandir métricas
            metrics_expanded = []
            for record in all_health:
                metrics_dict = {
                    'calendarDate': record.get('calendarDate'),
                    'createTimestampUTC': record.get('createTimestampUTC'),
                    'updateTimestampUTC': record.get('updateTimestampUTC')
                }
                
                # Extrair métricas por tipo
                if 'metrics' in record and isinstance(record['metrics'], list):
                    for metric in record['metrics']:
                        if isinstance(metric, dict):
                            metric_type = metric.get('type', 'unknown')
                            metrics_dict[f'{metric_type}_value'] = metric.get('value')
                            metrics_dict[f'{metric_type}_baseline_upper'] = metric.get('baselineUpperLimit')
                            metrics_dict[f'{metric_type}_baseline_lower'] = metric.get('baselineLowerLimit')
                            metrics_dict[f'{metric_type}_percentage'] = metric.get('percentage')
                            metrics_dict[f'{metric_type}_status'] = metric.get('status')
                
                metrics_expanded.append(metrics_dict)
            
            df = pd.DataFrame(metrics_expanded)
            df['calendarDate'] = pd.to_datetime(df['calendarDate'], errors='coerce')
            
            # Remover linhas com datas inválidas
            df = df.dropna(subset=['calendarDate'])
            
            if len(df) == 0:
                return None
            
            df['month'] = df['calendarDate'].dt.to_period('M')
            df['week'] = df['calendarDate'].dt.to_period('W')
            df['year'] = df['calendarDate'].dt.year
            df['weekday'] = df['calendarDate'].dt.day_name()
            
            self.health_df = df
            return df
            
        except Exception as e:
            st.error(f"Erro ao carregar dados de saúde: {str(e)}")
            import traceback
            st.error(f"Detalhes: {traceback.format_exc()}")
            return None
    
    def load_hydration(self):
        """Carrega dados de hidratação"""
        try:
            files = self.find_files("HydrationLogFile*.json")
            if not files:
                return None
            
            all_hydration = []
            for file in files:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_hydration.extend(data)
            
            if not all_hydration:
                return None
            
            df = pd.DataFrame(all_hydration)
            
            # Converter timestamps se existirem
            if 'timestampGMT' in df.columns:
                df['timestamp'] = self.safe_parse_timestamp(df['timestampGMT'], 'timestampGMT')
                df['date'] = df['timestamp'].dt.date
                df['month'] = df['timestamp'].dt.to_period('M')
                df['week'] = df['timestamp'].dt.to_period('W')
            
            self.hydration_df = df
            return df
            
        except Exception as e:
            st.error(f"Erro ao carregar dados de hidratação: {str(e)}")
            import traceback
            st.error(f"Detalhes: {traceback.format_exc()}")
            return None
    
    def load_body_battery_and_stress(self):
        """Carrega dados de Body Battery e Estresse dos arquivos UDS"""
        try:
            files = self.find_files("UDSFile*.json")
            if not files:
                return None, None
            
            all_data = []
            for file in files:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_data.extend(data)
            
            if not all_data:
                return None, None
            
            # Processar Body Battery
            body_battery_records = []
            stress_records = []
            
            for record in all_data:
                calendar_date = record.get('calendarDate')
                
                # Body Battery
                if 'bodyBattery' in record and record['bodyBattery']:
                    bb_data = record['bodyBattery']
                    bb_record = {
                        'calendarDate': calendar_date,
                        'chargedValue': bb_data.get('chargedValue'),
                        'drainedValue': bb_data.get('drainedValue'),
                        'bodyBatteryVersion': bb_data.get('bodyBatteryVersion')
                    }
                    
                    # Extrair estatísticas
                    if 'bodyBatteryStatList' in bb_data:
                        for stat in bb_data['bodyBatteryStatList']:
                            stat_type = stat.get('bodyBatteryStatType')
                            if stat_type:
                                bb_record[f'{stat_type.lower()}_value'] = stat.get('statsValue')
                                bb_record[f'{stat_type.lower()}_timestamp'] = stat.get('statTimestamp')
                    
                    body_battery_records.append(bb_record)
                
                # Estresse
                if 'allDayStress' in record and record['allDayStress']:
                    stress_data = record['allDayStress']
                    
                    if 'aggregatorList' in stress_data:
                        for agg in stress_data['aggregatorList']:
                            stress_record = {
                                'calendarDate': calendar_date,
                                'type': agg.get('type'),
                                'averageStressLevel': agg.get('averageStressLevel'),
                                'maxStressLevel': agg.get('maxStressLevel'),
                                'restDuration': agg.get('restDuration', 0) / 60,  # Converter para minutos
                                'activityDuration': agg.get('activityDuration', 0) / 60,
                                'lowDuration': agg.get('lowDuration', 0) / 60,
                                'mediumDuration': agg.get('mediumDuration', 0) / 60,
                                'highDuration': agg.get('highDuration', 0) / 60,
                                'totalDuration': agg.get('totalDuration', 0) / 60
                            }
                            stress_records.append(stress_record)
            
            # Criar DataFrames
            bb_df = None
            if body_battery_records:
                bb_df = pd.DataFrame(body_battery_records)
                bb_df['calendarDate'] = pd.to_datetime(bb_df['calendarDate'], errors='coerce')
                bb_df = bb_df.dropna(subset=['calendarDate'])
                bb_df['month'] = bb_df['calendarDate'].dt.to_period('M')
                bb_df['week'] = bb_df['calendarDate'].dt.to_period('W')
                bb_df['year'] = bb_df['calendarDate'].dt.year
                bb_df['weekday'] = bb_df['calendarDate'].dt.day_name()
            
            stress_df = None
            if stress_records:
                stress_df = pd.DataFrame(stress_records)
                stress_df['calendarDate'] = pd.to_datetime(stress_df['calendarDate'], errors='coerce')
                stress_df = stress_df.dropna(subset=['calendarDate'])
                stress_df['month'] = stress_df['calendarDate'].dt.to_period('M')
                stress_df['week'] = stress_df['calendarDate'].dt.to_period('W')
                stress_df['year'] = stress_df['calendarDate'].dt.year
                stress_df['weekday'] = stress_df['calendarDate'].dt.day_name()
            
            return bb_df, stress_df
            
        except Exception as e:
            st.error(f"Erro ao carregar dados de Body Battery e Estresse: {str(e)}")
            import traceback
            st.error(f"Detalhes: {traceback.format_exc()}")
            return None, None
    
    def load_all_data(self):
        """Carrega todos os dados"""
        self.extract_zip()
        self.load_activities()
        self.load_sleep()
        self.load_health()
        self.load_hydration()
        
        # Carregar Body Battery e Estresse
        self.body_battery_df, self.stress_df = self.load_body_battery_and_stress()


def create_activities_overview(df):
    """Cria visão geral das atividades"""
    st.header("📊 Visão Geral das Atividades")
    
    if df is None or len(df) == 0:
        st.warning("Nenhuma atividade encontrada nos dados")
        return
    
    # Filtros de período
    st.subheader("🔍 Filtros de Período")
    
    col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
    
    with col_filter1:
        # Filtro de ano
        anos_disponiveis = ['Todos'] + sorted(df['year'].unique().tolist(), reverse=True)
        ano_selecionado = st.selectbox("📅 Ano", anos_disponiveis, key="overview_year")
    
    with col_filter2:
        # Filtro de mês
        if ano_selecionado != 'Todos':
            df_ano = df[df['year'] == ano_selecionado]
            meses_disponiveis = ['Todos'] + sorted(df_ano['month'].astype(str).unique().tolist(), reverse=True)
        else:
            meses_disponiveis = ['Todos'] + sorted(df['month'].astype(str).unique().tolist(), reverse=True)
        mes_selecionado = st.selectbox("📆 Mês", meses_disponiveis, key="overview_month")
    
    with col_filter3:
        # Filtro de semana (mais útil quando mês está selecionado)
        if mes_selecionado != 'Todos':
            df_filtrado = df[df['month'].astype(str) == mes_selecionado] if ano_selecionado == 'Todos' else df[(df['year'] == ano_selecionado) & (df['month'].astype(str) == mes_selecionado)]
            semanas_disponiveis = ['Todas'] + sorted(df_filtrado['week'].astype(str).unique().tolist(), reverse=True)
        else:
            semanas_disponiveis = ['Todas']
        semana_selecionada = st.selectbox("📅 Semana", semanas_disponiveis, key="overview_week")
    
    with col_filter4:
        # Filtro de tipo de atividade
        tipos_disponiveis = ['Todos'] + sorted(df['activityType'].unique().tolist())
        tipo_selecionado = st.selectbox("🏃 Tipo de Atividade", tipos_disponiveis, key="overview_type")
    
    # Aplicar filtros
    df_filtered = df.copy()
    
    if ano_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['year'] == ano_selecionado]
    
    if mes_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['month'].astype(str) == mes_selecionado]
    
    if semana_selecionada != 'Todas':
        df_filtered = df_filtered[df_filtered['week'].astype(str) == semana_selecionada]
    
    if tipo_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['activityType'] == tipo_selecionado]
    
    # Mostrar período selecionado
    if len(df_filtered) > 0:
        periodo_inicio = df_filtered['startTimeLocal'].min().strftime('%d/%m/%Y')
        periodo_fim = df_filtered['startTimeLocal'].max().strftime('%d/%m/%Y')
        
        # Calcular percentual do total
        percentual = (len(df_filtered) / len(df)) * 100
        
        col_info1, col_info2 = st.columns([2, 1])
        with col_info1:
            st.info(f"📊 Mostrando **{len(df_filtered)}** de **{len(df)}** atividades ({percentual:.1f}%) | Período: {periodo_inicio} até {periodo_fim}")
        
        with col_info2:
            if st.button("🔄 Limpar Filtros", key="clear_filters_overview"):
                st.rerun()
    else:
        st.warning("⚠️ Nenhuma atividade encontrada com os filtros selecionados")
        return
    
    st.markdown("---")
    
    # Métricas principais (usando dados filtrados)
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_activities = len(df_filtered)
        st.metric("Total de Atividades", f"{total_activities}")
    
    with col2:
        total_distance = df_filtered['distance_km'].sum()
        st.metric("Distância Total", f"{total_distance:.1f} km")
    
    with col3:
        if 'activeCalories' in df_filtered.columns:
            active_calories = df_filtered['activeCalories'].sum()
            st.metric("Calorias", f"{active_calories:_.0f}".replace('_', '.'))
        else:
            total_calories = df_filtered['calories'].sum()
            st.metric("Calorias", f"{total_calories:_.0f}".replace('_', '.'))
    
    with col4:
        total_time = df_filtered['duration_minutes'].sum()
        st.metric("Tempo Total", f"{total_time/60:.1f}h")
    
    with col5:
        avg_hr = df_filtered[df_filtered['avgHr'] > 0]['avgHr'].mean() if (df_filtered['avgHr'] > 0).any() else 0
        st.metric("FC Média", f"{avg_hr:.0f} bpm" if avg_hr > 0 else "N/A")
    
    st.markdown("---")
    
    # Gráficos em linha
    col1, col2 = st.columns(2)
    
    with col1:
        # Atividades por tipo
        if 'activityType' in df_filtered.columns:
            activity_counts = df_filtered['activityType'].value_counts()
            fig = px.pie(
                values=activity_counts.values,
                names=activity_counts.index,
                title="Distribuição por Tipo de Atividade",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Atividades por dia da semana
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_map = {
            'Monday': 'Segunda',
            'Tuesday': 'Terça',
            'Wednesday': 'Quarta',
            'Thursday': 'Quinta',
            'Friday': 'Sexta',
            'Saturday': 'Sábado',
            'Sunday': 'Domingo'
        }
        
        weekday_counts = df_filtered['weekday'].value_counts().reindex(weekday_order, fill_value=0)
        weekday_counts.index = weekday_counts.index.map(weekday_map)
        
        fig = px.bar(
            x=weekday_counts.index,
            y=weekday_counts.values,
            title="Atividades por Dia da Semana",
            labels={'x': 'Dia', 'y': 'Quantidade'},
            color=weekday_counts.values,
            color_continuous_scale='Viridis'
        )
        st.plotly_chart(fig, use_container_width=True)


def create_activities_temporal_analysis(df):
    """Cria análise temporal das atividades"""
    st.header("📈 Análise Temporal das Atividades")
    
    # Filtros
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        time_period = st.selectbox(
            "Selecione o período:",
            ["Diário", "Semanal", "Mensal", "Anual"],
            key="temporal_period"
        )
    
    with col2:
        # Filtro por tipo de atividade
        tipos_disponiveis = ['Todos'] + sorted(df['activityType'].unique().tolist())
        tipo_selecionado = st.selectbox(
            "🏃 Tipo de Atividade:",
            tipos_disponiveis,
            key="temporal_type"
        )
    
    with col3:
        # Mostrar info do filtro
        if tipo_selecionado != 'Todos':
            st.info(f"Filtrando: {tipo_selecionado}")
    
    # Aplicar filtro de tipo
    if tipo_selecionado != 'Todos':
        df = df[df['activityType'] == tipo_selecionado].copy()
        
        if len(df) == 0:
            st.warning(f"⚠️ Nenhuma atividade do tipo '{tipo_selecionado}' encontrada")
            return
    
    # Decidir qual coluna de calorias usar
    calorie_col = 'activeCalories' if 'activeCalories' in df.columns else 'calories'
    
    # Função para criar lista de atividades
    def get_activities_list(group):
        activities = []
        for _, row in group.iterrows():
            act_name = row.get('name', row.get('activityType', 'Atividade'))
            act_time = row['startTimeLocal'].strftime('%H:%M') if 'startTimeLocal' in row else ''
            activities.append(f"{act_time} {act_name}" if act_time else act_name)
        return '<br>'.join(activities[:5]) + ('<br>...' if len(activities) > 5 else '')
    
    # Preparar dados baseado no período
    if time_period == "Diário":
        grouped = df.groupby('date').agg({
            'activityId': 'count',
            'distance_km': 'sum',
            calorie_col: 'sum',
            'duration_minutes': 'sum',
            'avgHr': 'mean'
        }).reset_index()
        
        # Adicionar lista de atividades
        activities_list = df.groupby('date').apply(get_activities_list).reset_index()
        activities_list.columns = ['date', 'activities_detail']
        grouped = grouped.merge(activities_list, left_on='date', right_on='date', how='left')
        
        grouped.columns = ['Data', 'Atividades', 'Distância (km)', 'Calorias', 'Duração (min)', 'FC Média', 'Detalhes']
        x_col = 'Data'
        
    elif time_period == "Semanal":
        grouped = df.groupby('week').agg({
            'activityId': 'count',
            'distance_km': 'sum',
            calorie_col: 'sum',
            'duration_minutes': 'sum',
            'avgHr': 'mean'
        }).reset_index()
        
        # Adicionar lista de atividades
        activities_list = df.groupby('week').apply(get_activities_list).reset_index()
        activities_list.columns = ['week', 'activities_detail']
        grouped = grouped.merge(activities_list, left_on='week', right_on='week', how='left')
        
        grouped['week'] = grouped['week'].astype(str)
        grouped.columns = ['Semana', 'Atividades', 'Distância (km)', 'Calorias', 'Duração (min)', 'FC Média', 'Detalhes']
        x_col = 'Semana'
        
    elif time_period == "Mensal":
        grouped = df.groupby('month').agg({
            'activityId': 'count',
            'distance_km': 'sum',
            calorie_col: 'sum',
            'duration_minutes': 'sum',
            'avgHr': 'mean'
        }).reset_index()
        
        # Adicionar lista de atividades
        activities_list = df.groupby('month').apply(get_activities_list).reset_index()
        activities_list.columns = ['month', 'activities_detail']
        grouped = grouped.merge(activities_list, left_on='month', right_on='month', how='left')
        
        grouped['month'] = grouped['month'].astype(str)
        grouped.columns = ['Mês', 'Atividades', 'Distância (km)', 'Calorias', 'Duração (min)', 'FC Média', 'Detalhes']
        x_col = 'Mês'
        
    else:  # Anual
        grouped = df.groupby('year').agg({
            'activityId': 'count',
            'distance_km': 'sum',
            calorie_col: 'sum',
            'duration_minutes': 'sum',
            'avgHr': 'mean'
        }).reset_index()
        
        # Adicionar lista de atividades
        activities_list = df.groupby('year').apply(get_activities_list).reset_index()
        activities_list.columns = ['year', 'activities_detail']
        grouped = grouped.merge(activities_list, left_on='year', right_on='year', how='left')
        
        grouped.columns = ['Ano', 'Atividades', 'Distância (km)', 'Calorias', 'Duração (min)', 'FC Média', 'Detalhes']
        x_col = 'Ano'
    
    # Criar gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.line(
            grouped,
            x=x_col,
            y='Distância (km)',
            title=f"Distância Total - {time_period}",
            markers=True,
            line_shape='spline',
            custom_data=['Atividades', 'Calorias', 'Duração (min)', 'Detalhes']
        )
        fig.update_traces(
            line_color='#00C9FF', 
            marker=dict(size=8),
            hovertemplate='<b>%{x}</b><br>' +
                         'Distância: %{y:.1f} km<br>' +
                         'Atividades: %{customdata[0]}<br>' +
                         'Calorias: %{customdata[1]:.0f}<br>' +
                         'Duração: %{customdata[2]:.0f} min<br>' +
                         '<br><b>Detalhes:</b><br>%{customdata[3]}<extra></extra>'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(
            grouped,
            x=x_col,
            y='Calorias',
            title=f"Calorias - {time_period}",
            color='Calorias',
            color_continuous_scale='Reds',
            custom_data=['Atividades', 'Distância (km)', 'Duração (min)', 'Detalhes']
        )
        fig.update_traces(
            hovertemplate='<b>%{x}</b><br>' +
                         'Calorias: %{y:.0f}<br>' +
                         'Atividades: %{customdata[0]}<br>' +
                         'Distância: %{customdata[1]:.1f} km<br>' +
                         'Duração: %{customdata[2]:.0f} min<br>' +
                         '<br><b>Detalhes:</b><br>%{customdata[3]}<extra></extra>'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    col3, col4 = st.columns(2)
    
    with col3:
        fig = px.area(
            grouped,
            x=x_col,
            y='Duração (min)',
            title=f"Tempo de Treino - {time_period}",
            color_discrete_sequence=['#92FE9D'],
            custom_data=['Atividades', 'Distância (km)', 'Calorias', 'Detalhes']
        )
        fig.update_traces(
            hovertemplate='<b>%{x}</b><br>' +
                         'Duração: %{y:.0f} min<br>' +
                         'Atividades: %{customdata[0]}<br>' +
                         'Distância: %{customdata[1]:.1f} km<br>' +
                         'Calorias: %{customdata[2]:.0f}<br>' +
                         '<br><b>Detalhes:</b><br>%{customdata[3]}<extra></extra>'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col4:
        fig = px.line(
            grouped,
            x=x_col,
            y='FC Média',
            title=f"Frequência Cardíaca Média - {time_period}",
            markers=True,
            line_shape='spline',
            custom_data=['Atividades', 'Distância (km)', 'Calorias', 'Duração (min)', 'Detalhes']
        )
        fig.update_traces(
            line_color='#FF6B6B', 
            marker=dict(size=8),
            hovertemplate='<b>%{x}</b><br>' +
                         'FC Média: %{y:.0f} bpm<br>' +
                         'Atividades: %{customdata[0]}<br>' +
                         'Distância: %{customdata[1]:.1f} km<br>' +
                         'Calorias: %{customdata[2]:.0f}<br>' +
                         'Duração: %{customdata[3]:.0f} min<br>' +
                         '<br><b>Detalhes:</b><br>%{customdata[4]}<extra></extra>'
        )
        st.plotly_chart(fig, use_container_width=True)


def create_activities_detailed_analysis(df):
    """Cria análise detalhada das atividades"""
    st.header("🔍 Análise Detalhada das Atividades")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if 'activityType' in df.columns:
            activity_types = ['Todos'] + list(df['activityType'].unique())
            selected_type = st.selectbox("Tipo de Atividade:", activity_types)
    
    with col2:
        years = ['Todos'] + sorted(df['year'].unique().tolist(), reverse=True)
        selected_year = st.selectbox("Ano:", years)
    
    with col3:
        months = ['Todos'] + sorted(df['month'].astype(str).unique().tolist(), reverse=True)
        selected_month = st.selectbox("Mês:", months)
    
    # Aplicar filtros
    filtered_df = df.copy()
    
    if selected_type != 'Todos':
        filtered_df = filtered_df[filtered_df['activityType'] == selected_type]
    
    if selected_year != 'Todos':
        filtered_df = filtered_df[filtered_df['year'] == selected_year]
    
    if selected_month != 'Todos':
        filtered_df = filtered_df[filtered_df['month'].astype(str) == selected_month]
    
    st.markdown("---")
    
    # Estatísticas filtradas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Atividades", len(filtered_df))
    
    with col2:
        st.metric("Distância Total", f"{filtered_df['distance_km'].sum():.1f} km")
    
    with col3:
        if 'activeCalories' in filtered_df.columns:
            active_cal = filtered_df['activeCalories'].sum()
            st.metric("Calorias", f"{active_cal:_.0f}".replace('_', '.'))
        else:
            st.metric("Calorias", f"{filtered_df['calories'].sum():_.0f}".replace('_', '.'))
    
    with col4:
        total_time = filtered_df['duration_minutes'].sum()
        st.metric("Tempo Total", f"{total_time/60:.1f}h")
    
    # Gráficos avançados
    col1, col2 = st.columns(2)
    
    with col1:
        # Distribuição de duração
        fig = px.histogram(
            filtered_df,
            x='duration_minutes',
            title="Distribuição de Duração das Atividades",
            labels={'duration_minutes': 'Duração (minutos)', 'count': 'Frequência'},
            color_discrete_sequence=['#667eea'],
            nbins=30
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Scatter: Distância vs Calorias
        calorie_col = 'activeCalories' if 'activeCalories' in filtered_df.columns else 'calories'
        
        fig = px.scatter(
            filtered_df,
            x='distance_km',
            y=calorie_col,
            title="Relação: Distância vs Calorias",
            labels={'distance_km': 'Distância (km)', calorie_col: 'Calorias'},
            color='duration_minutes',
            size='duration_minutes',
            color_continuous_scale='Viridis',
            hover_data=['activityType', 'avgHr']
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Gráficos adicionais
    st.markdown("---")
    
    # Evolução temporal e FC
    col1, col2 = st.columns(2)
    
    with col1:
        # Evolução temporal das atividades
        if len(filtered_df) > 1:
            temporal_df = filtered_df.sort_values('startTimeLocal')
            temporal_df['data_formatada'] = temporal_df['startTimeLocal'].dt.strftime('%d/%m')
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=temporal_df['data_formatada'],
                y=temporal_df['distance_km'],
                name='Distância (km)',
                mode='lines+markers',
                line=dict(color='#00C9FF', width=2),
                marker=dict(size=8)
            ))
            
            fig.update_layout(
                title="Evolução: Distância por Atividade",
                xaxis_title="Data",
                yaxis_title="Distância (km)",
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Análise de Frequência Cardíaca
        if 'avgHr' in filtered_df.columns and (filtered_df['avgHr'] > 0).any():
            hr_data = filtered_df[filtered_df['avgHr'] > 0]
            
            fig = px.box(
                hr_data,
                y='avgHr',
                x='activityType' if selected_type == 'Todos' else None,
                title="Distribuição de Frequência Cardíaca",
                labels={'avgHr': 'FC Média (bpm)', 'activityType': 'Tipo'},
                color='activityType' if selected_type == 'Todos' else None,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    
    # Performance por tipo de atividade
    if selected_type == 'Todos' and len(filtered_df['activityType'].unique()) > 1:
        st.subheader("📊 Performance por Tipo de Atividade")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Calorias por tipo
            cal_by_type = filtered_df.groupby('activityType').agg({
                'activeCalories' if 'activeCalories' in filtered_df.columns else 'calories': 'mean'
            }).reset_index()
            cal_by_type.columns = ['Tipo', 'Calorias Médias']
            cal_by_type = cal_by_type.sort_values('Calorias Médias', ascending=True)
            
            fig = px.bar(
                cal_by_type,
                y='Tipo',
                x='Calorias Médias',
                title="Calorias Médias por Tipo",
                orientation='h',
                color='Calorias Médias',
                color_continuous_scale='Reds'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Duração média por tipo
            dur_by_type = filtered_df.groupby('activityType')['duration_minutes'].mean().reset_index()
            dur_by_type.columns = ['Tipo', 'Duração Média (min)']
            dur_by_type = dur_by_type.sort_values('Duração Média (min)', ascending=True)
            
            fig = px.bar(
                dur_by_type,
                y='Tipo',
                x='Duração Média (min)',
                title="Duração Média por Tipo",
                orientation='h',
                color='Duração Média (min)',
                color_continuous_scale='Greens'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Mapa de calor: Hora do dia vs Dia da semana
    if len(filtered_df) > 0:
        st.subheader("🕐 Mapa de Calor: Quando Você Treina?")
        
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_map = {
            'Monday': 'Seg',
            'Tuesday': 'Ter',
            'Wednesday': 'Qua',
            'Thursday': 'Qui',
            'Friday': 'Sex',
            'Saturday': 'Sáb',
            'Sunday': 'Dom'
        }
        
        heatmap_data = filtered_df.groupby(['weekday', 'hour']).size().reset_index(name='count')
        heatmap_pivot = heatmap_data.pivot(index='weekday', columns='hour', values='count').fillna(0)
        heatmap_pivot = heatmap_pivot.reindex(weekday_order)
        heatmap_pivot.index = heatmap_pivot.index.map(weekday_map)
        
        fig = px.imshow(
            heatmap_pivot,
            title="Atividades por Dia da Semana e Hora",
            labels=dict(x="Hora do Dia", y="Dia da Semana", color="Quantidade"),
            color_continuous_scale='YlOrRd',
            aspect='auto'
        )
        st.plotly_chart(fig, use_container_width=True)
    

def create_sleep_analysis(df):
    """Cria análise de sono"""
    st.header("😴 Análise de Sono")
    
    if df is None or len(df) == 0:
        st.warning("Dados de sono não disponíveis")
        return
    
    # Filtros de período
    st.subheader("🔍 Filtros de Período")
    
    col_filter1, col_filter2, col_filter3 = st.columns(3)
    
    with col_filter1:
        # Filtro de ano
        anos_disponiveis = ['Todos'] + sorted(df['year'].unique().tolist(), reverse=True)
        ano_selecionado = st.selectbox("📅 Ano", anos_disponiveis, key="sleep_year")
    
    with col_filter2:
        # Filtro de mês
        if ano_selecionado != 'Todos':
            df_ano = df[df['year'] == ano_selecionado]
            meses_disponiveis = ['Todos'] + sorted(df_ano['month'].astype(str).unique().tolist(), reverse=True)
        else:
            meses_disponiveis = ['Todos'] + sorted(df['month'].astype(str).unique().tolist(), reverse=True)
        mes_selecionado = st.selectbox("📆 Mês", meses_disponiveis, key="sleep_month")
    
    with col_filter3:
        # Filtro de semana
        if mes_selecionado != 'Todos':
            df_filtrado = df[df['month'].astype(str) == mes_selecionado] if ano_selecionado == 'Todos' else df[(df['year'] == ano_selecionado) & (df['month'].astype(str) == mes_selecionado)]
            semanas_disponiveis = ['Todas'] + sorted(df_filtrado['week'].astype(str).unique().tolist(), reverse=True)
        else:
            semanas_disponiveis = ['Todas']
        semana_selecionada = st.selectbox("📅 Semana", semanas_disponiveis, key="sleep_week")
    
    # Aplicar filtros
    df_filtered = df.copy()
    
    if ano_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['year'] == ano_selecionado]
    
    if mes_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['month'].astype(str) == mes_selecionado]
    
    if semana_selecionada != 'Todas':
        df_filtered = df_filtered[df_filtered['week'].astype(str) == semana_selecionada]
    
    # Mostrar período selecionado
    if len(df_filtered) > 0:
        periodo_inicio = df_filtered['calendarDate'].min().strftime('%d/%m/%Y')
        periodo_fim = df_filtered['calendarDate'].max().strftime('%d/%m/%Y')
        
        # Calcular percentual do total
        percentual = (len(df_filtered) / len(df)) * 100
        
        col_info1, col_info2 = st.columns([2, 1])
        with col_info1:
            st.info(f"📊 Mostrando **{len(df_filtered)}** de **{len(df)}** noites ({percentual:.1f}%) | Período: {periodo_inicio} até {periodo_fim}")
        
        with col_info2:
            if st.button("🔄 Limpar Filtros", key="clear_filters_sleep"):
                st.rerun()
    else:
        st.warning("⚠️ Nenhum registro de sono encontrado com os filtros selecionados")
        return
    
    st.markdown("---")
    
    # Métricas principais (usando dados filtrados)
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        avg_sleep = df_filtered['totalSleepHours'].mean()
        st.metric("Sono Médio", f"{avg_sleep:.1f}h" if avg_sleep > 0 else "N/A")
    
    with col2:
        avg_deep = df_filtered['deepSleepHours'].mean()
        st.metric("Sono Profundo", f"{avg_deep:.1f}h" if avg_deep > 0 else "N/A")
    
    with col3:
        avg_rem = df_filtered['remSleepHours'].mean()
        st.metric("Sono REM", f"{avg_rem:.1f}h" if avg_rem > 0 else "N/A")
    
    with col4:
        avg_awake = df_filtered['awakeCount'].mean()
        st.metric("Despertares", f"{avg_awake:.1f}" if avg_awake > 0 else "N/A")
    
    with col5:
        if 'overallScore' in df_filtered.columns and df_filtered['overallScore'].notna().any():
            avg_score = df_filtered['overallScore'].dropna().mean()
            st.metric("Score Médio", f"{avg_score:.0f}" if avg_score > 0 else "N/A")
        else:
            st.metric("Score Médio", "N/A")
    
    st.markdown("---")
    
    # Gráficos de sono
    col1, col2 = st.columns(2)
    
    with col1:
        # Evolução do sono
        sleep_trend = df_filtered.sort_values('calendarDate')[['calendarDate', 'totalSleepHours']]
        fig = px.line(
            sleep_trend,
            x='calendarDate',
            y='totalSleepHours',
            title="Evolução do Sono",
            labels={'calendarDate': 'Data', 'totalSleepHours': 'Horas de Sono'},
            markers=True
        )
        fig.add_hline(y=7, line_dash="dash", line_color="green", 
                     annotation_text="Meta: 7h")
        fig.update_traces(line_color='#4B0082')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Distribuição das fases do sono
        sleep_phases = pd.DataFrame({
            'Fase': ['Sono Profundo', 'Sono Leve', 'Sono REM', 'Acordado'],
            'Horas': [
                df_filtered['deepSleepHours'].mean(),
                df_filtered['lightSleepHours'].mean(),
                df_filtered['remSleepHours'].mean(),
                df_filtered['awakeHours'].mean()
            ]
        })
        
        fig = px.bar(
            sleep_phases,
            x='Fase',
            y='Horas',
            title="Distribuição Média das Fases do Sono",
            color='Fase',
            color_discrete_map={
                'Sono Profundo': '#1E3A8A',
                'Sono Leve': '#60A5FA',
                'Sono REM': '#A78BFA',
                'Acordado': '#FCA5A5'
            }
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Análise semanal
    col1, col2 = st.columns(2)
    
    with col1:
        # Sono por dia da semana
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_map = {
            'Monday': 'Segunda',
            'Tuesday': 'Terça',
            'Wednesday': 'Quarta',
            'Thursday': 'Quinta',
            'Friday': 'Sexta',
            'Saturday': 'Sábado',
            'Sunday': 'Domingo'
        }
        
        weekday_sleep = df_filtered.groupby('weekday')['totalSleepHours'].mean().reindex(weekday_order)
        weekday_sleep.index = weekday_sleep.index.map(weekday_map)
        
        fig = px.bar(
            x=weekday_sleep.index,
            y=weekday_sleep.values,
            title="Sono Médio por Dia da Semana",
            labels={'x': 'Dia', 'y': 'Horas de Sono'},
            color=weekday_sleep.values,
            color_continuous_scale='Blues'
        )
        fig.update_traces(hovertemplate='<b>%{x}</b><br>Sono: %{y:.1f}h<extra></extra>')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Score de sono ao longo do tempo
        if 'overallScore' in df_filtered.columns and df_filtered['overallScore'].notna().any():
            score_trend = df_filtered.dropna(subset=['overallScore']).sort_values('calendarDate')[['calendarDate', 'overallScore']]
            if len(score_trend) > 0:
                fig = px.line(
                    score_trend,
                    x='calendarDate',
                    y='overallScore',
                    title="Evolução do Score de Sono",
                    labels={'calendarDate': 'Data', 'overallScore': 'Score'},
                    markers=True
                )
                fig.update_traces(line_color='#10B981', marker=dict(size=8))
                st.plotly_chart(fig, use_container_width=True)
    
    # Análise de respiração
    if 'averageRespiration' in df_filtered.columns and df_filtered['averageRespiration'].notna().any():
        st.subheader("📊 Análise Respiratória Durante o Sono")
        
        col1, col2 = st.columns(2)
        
        with col1:
            avg_resp = df_filtered['averageRespiration'].dropna().mean()
            
            if avg_resp > 0:
                fig = go.Figure()
                fig.add_trace(go.Indicator(
                    mode="gauge+number",
                    value=avg_resp,
                    title={'text': "Respiração Média (rpm)"},
                    gauge={
                        'axis': {'range': [None, 25]},
                        'bar': {'color': "#00C9FF"},
                        'steps': [
                            {'range': [0, 12], 'color': "lightgray"},
                            {'range': [12, 20], 'color': "gray"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 20
                        }
                    }
                ))
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            resp_data = df_filtered.dropna(subset=['averageRespiration']).sort_values('calendarDate')[['calendarDate', 'averageRespiration']]
            if len(resp_data) > 0:
                fig = px.line(
                    resp_data,
                    x='calendarDate',
                    y='averageRespiration',
                    title="Evolução da Respiração Média",
                    labels={'calendarDate': 'Data', 'averageRespiration': 'Respiração (rpm)'},
                    markers=True
                )
                fig.update_traces(line_color='#FF6B6B')
                st.plotly_chart(fig, use_container_width=True)


def create_health_analysis(df, body_battery_df=None, stress_df=None):
    """Cria análise de saúde"""
    st.header("💗 Análise de Saúde")
    
    if df is None or len(df) == 0:
        st.warning("Dados de saúde não disponíveis")
        return
    
    st.markdown("""
    Esta seção mostra suas **métricas de saúde** coletadas pelo Garmin, incluindo:
    - **HRV** (Variabilidade da Frequência Cardíaca): Indicador de estresse e recuperação
    - **HR** (Frequência Cardíaca em Repouso): Medida de saúde cardiovascular
    - **SPO2** (Saturação de Oxigênio): Percentual de oxigênio no sangue
    - **Temperatura da Pele**: Variação em relação à sua linha de base
    - **Respiração**: Taxa respiratória em repouso
    """)
    
    st.markdown("---")
    
    # Filtros de período
    st.subheader("🔍 Filtros de Período")
    
    col_filter1, col_filter2, col_filter3 = st.columns(3)
    
    with col_filter1:
        # Filtro de ano
        anos_disponiveis = ['Todos'] + sorted(df['year'].unique().tolist(), reverse=True)
        ano_selecionado = st.selectbox("📅 Ano", anos_disponiveis, key="health_year")
    
    with col_filter2:
        # Filtro de mês
        if ano_selecionado != 'Todos':
            df_ano = df[df['year'] == ano_selecionado]
            meses_disponiveis = ['Todos'] + sorted(df_ano['month'].astype(str).unique().tolist(), reverse=True)
        else:
            meses_disponiveis = ['Todos'] + sorted(df['month'].astype(str).unique().tolist(), reverse=True)
        mes_selecionado = st.selectbox("📆 Mês", meses_disponiveis, key="health_month")
    
    with col_filter3:
        # Filtro de semana
        if mes_selecionado != 'Todos':
            df_filtrado = df[df['month'].astype(str) == mes_selecionado] if ano_selecionado == 'Todos' else df[(df['year'] == ano_selecionado) & (df['month'].astype(str) == mes_selecionado)]
            semanas_disponiveis = ['Todas'] + sorted(df_filtrado['week'].astype(str).unique().tolist(), reverse=True)
        else:
            semanas_disponiveis = ['Todas']
        semana_selecionada = st.selectbox("📅 Semana", semanas_disponiveis, key="health_week")
    
    # Aplicar filtros
    df_filtered = df.copy()
    
    if ano_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['year'] == ano_selecionado]
    
    if mes_selecionado != 'Todos':
        df_filtered = df_filtered[df_filtered['month'].astype(str) == mes_selecionado]
    
    if semana_selecionada != 'Todas':
        df_filtered = df_filtered[df_filtered['week'].astype(str) == semana_selecionada]
    
    # Aplicar filtros em Body Battery e Estresse
    bb_filtered = None
    if body_battery_df is not None and len(body_battery_df) > 0:
        bb_filtered = body_battery_df.copy()
        if ano_selecionado != 'Todos':
            bb_filtered = bb_filtered[bb_filtered['year'] == ano_selecionado]
        if mes_selecionado != 'Todos':
            bb_filtered = bb_filtered[bb_filtered['month'].astype(str) == mes_selecionado]
        if semana_selecionada != 'Todas':
            bb_filtered = bb_filtered[bb_filtered['week'].astype(str) == semana_selecionada]
    
    stress_filtered = None
    if stress_df is not None and len(stress_df) > 0:
        stress_filtered = stress_df.copy()
        if ano_selecionado != 'Todos':
            stress_filtered = stress_filtered[stress_filtered['year'] == ano_selecionado]
        if mes_selecionado != 'Todos':
            stress_filtered = stress_filtered[stress_filtered['month'].astype(str) == mes_selecionado]
        if semana_selecionada != 'Todas':
            stress_filtered = stress_filtered[stress_filtered['week'].astype(str) == semana_selecionada]
    
    # Mostrar período selecionado
    if len(df_filtered) > 0:
        periodo_inicio = df_filtered['calendarDate'].min().strftime('%d/%m/%Y')
        periodo_fim = df_filtered['calendarDate'].max().strftime('%d/%m/%Y')
        
        # Calcular percentual do total
        percentual = (len(df_filtered) / len(df)) * 100
        
        col_info1, col_info2 = st.columns([2, 1])
        with col_info1:
            st.info(f"📊 Mostrando **{len(df_filtered)}** de **{len(df)}** registros ({percentual:.1f}%) | Período: {periodo_inicio} até {periodo_fim}")
        
        with col_info2:
            if st.button("🔄 Limpar Filtros", key="clear_filters_health"):
                st.rerun()
    else:
        st.warning("⚠️ Nenhum registro de saúde encontrado com os filtros selecionados")
        return
    
    st.markdown("---")
    
    # Body Battery (movido para o início)
    if bb_filtered is not None and len(bb_filtered) > 0:
        st.subheader("🔋 Body Battery")
        
        st.markdown("""
        O **Body Battery** mede sua energia corporal em uma escala de 0-100, 
        mostrando quanto você se recupera durante o descanso e quanto energia você gasta durante atividades.
        """)
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if 'highest_value' in bb_filtered.columns and bb_filtered['highest_value'].notna().any():
                avg_highest = bb_filtered['highest_value'].mean()
                st.metric("Valor Máximo Médio", f"{avg_highest:.0f}")
            else:
                st.metric("Valor Máximo Médio", "N/A")
        
        with col2:
            if 'lowest_value' in bb_filtered.columns and bb_filtered['lowest_value'].notna().any():
                avg_lowest = bb_filtered['lowest_value'].mean()
                st.metric("Valor Mínimo Médio", f"{avg_lowest:.0f}")
            else:
                st.metric("Valor Mínimo Médio", "N/A")
        
        with col3:
            if 'chargedValue' in bb_filtered.columns and bb_filtered['chargedValue'].notna().any():
                avg_charged = bb_filtered['chargedValue'].mean()
                st.metric("Recarga Média", f"+{avg_charged:.0f}")
            else:
                st.metric("Recarga Média", "N/A")
        
        with col4:
            if 'drainedValue' in bb_filtered.columns and bb_filtered['drainedValue'].notna().any():
                avg_drained = bb_filtered['drainedValue'].mean()
                st.metric("Gasto Médio", f"-{avg_drained:.0f}")
            else:
                st.metric("Gasto Médio", "N/A")
        
        # Gráficos
        col1, col2 = st.columns(2)
        
        with col1:
            # Evolução do Body Battery (valores máximo e mínimo diários)
            if 'highest_value' in bb_filtered.columns and 'lowest_value' in bb_filtered.columns:
                fig = go.Figure()
                
                # Área entre máximo e mínimo
                fig.add_trace(go.Scatter(
                    x=bb_filtered['calendarDate'],
                    y=bb_filtered['highest_value'],
                    mode='lines',
                    name='Máximo',
                    line=dict(color='#10B981', width=0),
                    showlegend=False
                ))
                
                fig.add_trace(go.Scatter(
                    x=bb_filtered['calendarDate'],
                    y=bb_filtered['lowest_value'],
                    mode='lines',
                    name='Mínimo',
                    line=dict(color='#10B981', width=0),
                    fillcolor='rgba(16, 185, 129, 0.3)',
                    fill='tonexty',
                    showlegend=False
                ))
                
                # Linhas de máximo e mínimo
                fig.add_trace(go.Scatter(
                    x=bb_filtered['calendarDate'],
                    y=bb_filtered['highest_value'],
                    mode='lines+markers',
                    name='Máximo Diário',
                    line=dict(color='#10B981', width=2),
                    marker=dict(size=6)
                ))
                
                fig.add_trace(go.Scatter(
                    x=bb_filtered['calendarDate'],
                    y=bb_filtered['lowest_value'],
                    mode='lines+markers',
                    name='Mínimo Diário',
                    line=dict(color='#EF4444', width=2),
                    marker=dict(size=6)
                ))
                
                # Linhas de referência
                fig.add_hline(y=75, line_dash="dash", line_color="green", 
                             annotation_text="Alto (75)", annotation_position="right")
                fig.add_hline(y=50, line_dash="dash", line_color="orange", 
                             annotation_text="Moderado (50)", annotation_position="right")
                fig.add_hline(y=25, line_dash="dash", line_color="red", 
                             annotation_text="Baixo (25)", annotation_position="right")
                
                fig.update_layout(
                    title="Evolução do Body Battery",
                    xaxis_title="Data",
                    yaxis_title="Body Battery (0-100)",
                    hovermode='x unified',
                    yaxis=dict(range=[0, 100])
                )
                
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Gráfico de Carga vs Descarga
            if 'chargedValue' in bb_filtered.columns and 'drainedValue' in bb_filtered.columns:
                fig = go.Figure()
                
                fig.add_trace(go.Bar(
                    x=bb_filtered['calendarDate'],
                    y=bb_filtered['chargedValue'],
                    name='Recarga',
                    marker_color='#10B981'
                ))
                
                fig.add_trace(go.Bar(
                    x=bb_filtered['calendarDate'],
                    y=-bb_filtered['drainedValue'],
                    name='Gasto',
                    marker_color='#EF4444'
                ))
                
                fig.update_layout(
                    title="Recarga vs Gasto de Energia",
                    xaxis_title="Data",
                    yaxis_title="Energia",
                    barmode='relative',
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
        
        # Análise por dia da semana
        if 'weekday' in bb_filtered.columns:
            weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            weekday_map = {
                'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta',
                'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
            }
            
            col1, col2 = st.columns(2)
            
            with col1:
                if 'highest_value' in bb_filtered.columns:
                    weekday_bb = bb_filtered.groupby('weekday')['highest_value'].mean().reindex(weekday_order)
                    weekday_bb.index = weekday_bb.index.map(weekday_map)
                    
                    fig = px.bar(
                        x=weekday_bb.index,
                        y=weekday_bb.values,
                        title="Body Battery Máximo Médio por Dia da Semana",
                        labels={'x': 'Dia', 'y': 'Body Battery'},
                        color=weekday_bb.values,
                        color_continuous_scale='Greens'
                    )
                    fig.update_traces(hovertemplate='<b>%{x}</b><br>Body Battery: %{y:.0f}<extra></extra>')
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                if 'chargedValue' in bb_filtered.columns:
                    weekday_charge = bb_filtered.groupby('weekday')['chargedValue'].mean().reindex(weekday_order)
                    weekday_charge.index = weekday_charge.index.map(weekday_map)
                    
                    fig = px.bar(
                        x=weekday_charge.index,
                        y=weekday_charge.values,
                        title="Recarga Média por Dia da Semana",
                        labels={'x': 'Dia', 'y': 'Recarga'},
                        color=weekday_charge.values,
                        color_continuous_scale='Blues'
                    )
                    fig.update_traces(hovertemplate='<b>%{x}</b><br>Recarga: +%{y:.0f}<extra></extra>')
                    st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # Estresse (movido para logo após Body Battery)
    if stress_filtered is not None and len(stress_filtered) > 0:
        st.subheader("😰 Análise de Estresse")
        
        st.markdown("""
        O **nível de estresse** é medido em uma escala de 0-100, onde:
        - **0-25**: Descanso
        - **26-50**: Baixo estresse
        - **51-75**: Médio estresse
        - **76-100**: Alto estresse
        """)
        
        # Filtrar dados TOTAL (todos os períodos do dia)
        stress_total = stress_filtered[stress_filtered['type'] == 'TOTAL'].copy()
        
        if len(stress_total) > 0:
            # Métricas principais
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_stress = stress_total['averageStressLevel'].mean()
                st.metric("Estresse Médio", f"{avg_stress:.0f}")
            
            with col2:
                max_stress = stress_total['maxStressLevel'].mean()
                st.metric("Estresse Máximo Médio", f"{max_stress:.0f}")
            
            with col3:
                rest_time = stress_total['restDuration'].mean()
                st.metric("Tempo de Descanso", f"{rest_time:.0f} min/dia")
            
            with col4:
                activity_time = stress_total['activityDuration'].mean()
                st.metric("Tempo em Atividade", f"{activity_time:.0f} min/dia")
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                # Evolução do estresse
                stress_data = stress_total[['calendarDate', 'averageStressLevel']].copy()
                
                fig = px.line(
                    stress_data,
                    x='calendarDate',
                    y='averageStressLevel',
                    title="Evolução do Nível de Estresse",
                    labels={'calendarDate': 'Data', 'averageStressLevel': 'Nível de Estresse'},
                    markers=True
                )
                
                # Linhas de referência
                fig.add_hline(y=25, line_dash="dash", line_color="green", 
                             annotation_text="Descanso (25)")
                fig.add_hline(y=50, line_dash="dash", line_color="orange", 
                             annotation_text="Médio (50)")
                fig.add_hline(y=75, line_dash="dash", line_color="red", 
                             annotation_text="Alto (75)")
                
                fig.update_traces(line_color='#F97316')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Distribuição do tempo por nível de estresse
                avg_durations = {
                    'Descanso': stress_total['restDuration'].mean(),
                    'Baixo': stress_total['lowDuration'].mean(),
                    'Médio': stress_total['mediumDuration'].mean(),
                    'Alto': stress_total['highDuration'].mean(),
                    'Atividade': stress_total['activityDuration'].mean()
                }
                
                fig = go.Figure(data=[go.Pie(
                    labels=list(avg_durations.keys()),
                    values=list(avg_durations.values()),
                    marker=dict(colors=['#10B981', '#FCD34D', '#F59E0B', '#EF4444', '#3B82F6']),
                    hole=0.4
                )])
                
                fig.update_layout(
                    title="Distribuição Média do Tempo por Nível de Estresse",
                    annotations=[dict(text='Tempo<br>Diário', x=0.5, y=0.5, font_size=14, showarrow=False)]
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Análise por dia da semana
            if 'weekday' in stress_total.columns:
                weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                weekday_map = {
                    'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta',
                    'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
                }
                
                weekday_stress = stress_total.groupby('weekday')['averageStressLevel'].mean().reindex(weekday_order)
                weekday_stress.index = weekday_stress.index.map(weekday_map)
                
                fig = px.bar(
                    x=weekday_stress.index,
                    y=weekday_stress.values,
                    title="Nível de Estresse Médio por Dia da Semana",
                    labels={'x': 'Dia', 'y': 'Nível de Estresse'},
                    color=weekday_stress.values,
                    color_continuous_scale='RdYlGn_r'
                )
                fig.update_traces(hovertemplate='<b>%{x}</b><br>Estresse: %{y:.0f}<extra></extra>')
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # Métricas principais (usando dados filtrados)
    st.subheader("📊 Métricas Atuais")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    metric_configs = [
        ('HRV', 'HRV', 'ms', col1, '#FF6B6B'),
        ('HR', 'FC Repouso', 'bpm', col2, '#4ECDC4'),
        ('SPO2', 'SpO₂', '%', col3, '#45B7D1'),
        ('SKIN_TEMP_C', 'Temp. Pele', '°C', col4, '#FFA07A'),
        ('RESPIRATION', 'Respiração', 'rpm', col5, '#98D8C8')
    ]
    
    for metric_key, label, unit, col, color in metric_configs:
        with col:
            value_col = f'{metric_key}_value'
            if value_col in df_filtered.columns and df_filtered[value_col].notna().any():
                latest_value = df_filtered[value_col].dropna().iloc[-1]
                avg_value = df_filtered[value_col].mean()
                delta = latest_value - avg_value
                
                # Formatar temperatura com + ou -
                if metric_key == 'SKIN_TEMP_C':
                    st.metric(label, f"{latest_value:+.1f}{unit}", f"{delta:+.1f}{unit}")
                else:
                    st.metric(label, f"{latest_value:.1f} {unit}", f"{delta:+.1f}")
            else:
                st.metric(label, "N/A", "")
    
    st.markdown("---")
    
    # Gráficos de evolução
    st.subheader("📈 Evolução das Métricas")
    
    # HRV e Frequência Cardíaca
    col1, col2 = st.columns(2)
    
    with col1:
        if 'HRV_value' in df_filtered.columns and df_filtered['HRV_value'].notna().any():
            hrv_data = df_filtered[['calendarDate', 'HRV_value', 'HRV_baseline_upper', 'HRV_baseline_lower']].dropna(subset=['HRV_value'])
            
            fig = go.Figure()
            
            # Linha principal
            fig.add_trace(go.Scatter(
                x=hrv_data['calendarDate'],
                y=hrv_data['HRV_value'],
                mode='lines+markers',
                name='HRV',
                line=dict(color='#FF6B6B', width=2),
                marker=dict(size=6)
            ))
            
            # Linhas de base
            if 'HRV_baseline_upper' in hrv_data.columns and hrv_data['HRV_baseline_upper'].notna().any():
                fig.add_trace(go.Scatter(
                    x=hrv_data['calendarDate'],
                    y=hrv_data['HRV_baseline_upper'],
                    mode='lines',
                    name='Limite Superior',
                    line=dict(color='rgba(255,107,107,0.3)', dash='dash')
                ))
            
            if 'HRV_baseline_lower' in hrv_data.columns and hrv_data['HRV_baseline_lower'].notna().any():
                fig.add_trace(go.Scatter(
                    x=hrv_data['calendarDate'],
                    y=hrv_data['HRV_baseline_lower'],
                    mode='lines',
                    name='Limite Inferior',
                    line=dict(color='rgba(255,107,107,0.3)', dash='dash')
                ))
            
            fig.update_layout(
                title="Variabilidade da Frequência Cardíaca (HRV)",
                xaxis_title="Data",
                yaxis_title="HRV (ms)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'HR_value' in df_filtered.columns and df_filtered['HR_value'].notna().any():
            hr_data = df_filtered[['calendarDate', 'HR_value', 'HR_baseline_upper', 'HR_baseline_lower']].dropna(subset=['HR_value'])
            
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=hr_data['calendarDate'],
                y=hr_data['HR_value'],
                mode='lines+markers',
                name='FC Repouso',
                line=dict(color='#4ECDC4', width=2),
                marker=dict(size=6)
            ))
            
            if 'HR_baseline_upper' in hr_data.columns and hr_data['HR_baseline_upper'].notna().any():
                fig.add_trace(go.Scatter(
                    x=hr_data['calendarDate'],
                    y=hr_data['HR_baseline_upper'],
                    mode='lines',
                    name='Limite Superior',
                    line=dict(color='rgba(78,205,196,0.3)', dash='dash')
                ))
            
            if 'HR_baseline_lower' in hr_data.columns and hr_data['HR_baseline_lower'].notna().any():
                fig.add_trace(go.Scatter(
                    x=hr_data['calendarDate'],
                    y=hr_data['HR_baseline_lower'],
                    mode='lines',
                    name='Limite Inferior',
                    line=dict(color='rgba(78,205,196,0.3)', dash='dash')
                ))
            
            fig.update_layout(
                title="Frequência Cardíaca em Repouso",
                xaxis_title="Data",
                yaxis_title="FC (bpm)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    # SpO2 e Temperatura
    col1, col2 = st.columns(2)
    
    with col1:
        if 'SPO2_value' in df_filtered.columns and df_filtered['SPO2_value'].notna().any():
            spo2_data = df_filtered[['calendarDate', 'SPO2_value']].dropna(subset=['SPO2_value'])
            
            fig = px.line(
                spo2_data,
                x='calendarDate',
                y='SPO2_value',
                title="Saturação de Oxigênio (SpO₂)",
                labels={'calendarDate': 'Data', 'SPO2_value': 'SpO₂ (%)'},
                markers=True
            )
            
            # Adicionar linha de referência
            fig.add_hline(y=95, line_dash="dash", line_color="green", 
                         annotation_text="Normal: ≥95%")
            
            fig.update_traces(line_color='#45B7D1', marker=dict(size=6))
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'SKIN_TEMP_C_value' in df_filtered.columns and df_filtered['SKIN_TEMP_C_value'].notna().any():
            temp_data = df_filtered[['calendarDate', 'SKIN_TEMP_C_value']].dropna(subset=['SKIN_TEMP_C_value'])
            
            fig = px.line(
                temp_data,
                x='calendarDate',
                y='SKIN_TEMP_C_value',
                title="Variação da Temperatura da Pele",
                labels={'calendarDate': 'Data', 'SKIN_TEMP_C_value': 'Variação (°C)'},
                markers=True
            )
            
            # Adicionar linha de referência
            fig.add_hline(y=0, line_dash="dash", line_color="gray", 
                         annotation_text="Linha de Base")
            
            fig.update_traces(line_color='#FFA07A', marker=dict(size=6))
            st.plotly_chart(fig, use_container_width=True)
    
    # Taxa Respiratória
    if 'RESPIRATION_value' in df_filtered.columns and df_filtered['RESPIRATION_value'].notna().any():
        st.subheader("🫁 Taxa Respiratória")
        
        resp_data = df_filtered[['calendarDate', 'RESPIRATION_value']].dropna(subset=['RESPIRATION_value'])
        
        fig = px.line(
            resp_data,
            x='calendarDate',
            y='RESPIRATION_value',
            title="Evolução da Taxa Respiratória em Repouso",
            labels={'calendarDate': 'Data', 'RESPIRATION_value': 'Respiração (rpm)'},
            markers=True
        )
        
        # Adicionar faixa normal
        fig.add_hrect(y0=12, y1=20, line_width=0, fillcolor="green", opacity=0.1,
                      annotation_text="Faixa Normal", annotation_position="top left")
        
        fig.update_traces(line_color='#98D8C8', marker=dict(size=6))
        st.plotly_chart(fig, use_container_width=True)
    
    # Análise de tendências
    st.markdown("---")
    st.subheader("📊 Resumo Estatístico")
    
    col1, col2, col3 = st.columns(3)
    
    stats_data = []
    for metric_key, label, unit, _, _ in metric_configs:
        value_col = f'{metric_key}_value'
        if value_col in df_filtered.columns and df_filtered[value_col].notna().any():
            values = df_filtered[value_col].dropna()
            stats_data.append({
                'Métrica': label,
                'Média': f"{values.mean():.1f} {unit}",
                'Mínimo': f"{values.min():.1f} {unit}",
                'Máximo': f"{values.max():.1f} {unit}",
                'Desvio Padrão': f"{values.std():.1f} {unit}"
            })
    
    if stats_data:
        stats_df = pd.DataFrame(stats_data)
        st.dataframe(stats_df, use_container_width=True, hide_index=True)


def create_correlation_analysis(activities_df, sleep_df, body_battery_df=None, stress_df=None, health_df=None):
    """Cria análise de correlação completa entre todos os dados"""
    st.header("🔗 Análise de Correlações e Padrões")
    
    st.markdown("""
    Esta seção analisa **relações e padrões** entre suas atividades, sono, energia e estresse,
    ajudando você a entender como cada aspecto impacta o outro.
    """)
    
    if activities_df is None or sleep_df is None:
        st.warning("Dados insuficientes para análise de correlação")
        return
    
    if len(activities_df) == 0 or len(sleep_df) == 0:
        st.warning("Dados insuficientes para análise de correlação")
        return
    
    st.markdown("---")
    
    # === 1. PREPARAR DADOS CONSOLIDADOS ===
    try:
        # Agregar atividades por data
        calorie_col = 'activeCalories' if 'activeCalories' in activities_df.columns else 'calories'
        
        agg_dict = {
            'activityId': 'count',
            'distance_km': 'sum',
            calorie_col: 'sum',
            'duration_minutes': 'sum'
        }
        
        # Adicionar averageHR apenas se existir
        if 'averageHR' in activities_df.columns:
            agg_dict['averageHR'] = 'mean'
        
        activities_daily = activities_df.groupby('date').agg(agg_dict).reset_index()
        
        # Renomear colunas dinamicamente
        col_names = ['date', 'num_activities', 'distance', 'calories', 'duration']
        if 'averageHR' in activities_df.columns:
            col_names.append('avg_hr')
        
        activities_daily.columns = col_names
        
        # Dados de sono
        sleep_daily = sleep_df[['calendarDate', 'totalSleepHours', 'deepSleepHours', 'remSleepHours', 'awakeCount']].copy()
        sleep_daily['date'] = sleep_daily['calendarDate'].dt.date
        if 'overallScore' in sleep_df.columns:
            sleep_daily['sleepScore'] = sleep_df['overallScore']
        sleep_daily = sleep_daily.dropna(subset=['totalSleepHours'])
        sleep_daily = sleep_daily.drop(columns=['calendarDate'])  # Remover para evitar duplicatas
        
        # Merge básico
        merged = pd.merge(activities_daily, sleep_daily, on='date', how='outer')
        
        # Body Battery
        if body_battery_df is not None and len(body_battery_df) > 0:
            bb_daily = body_battery_df[['calendarDate', 'chargedValue', 'drainedValue', 'highest_value', 'lowest_value']].copy()
            bb_daily['date'] = bb_daily['calendarDate'].dt.date
            bb_daily = bb_daily.drop(columns=['calendarDate'])  # Remover para evitar duplicatas
            merged = pd.merge(merged, bb_daily, on='date', how='outer')
        
        # Estresse
        if stress_df is not None and len(stress_df) > 0:
            stress_total = stress_df[stress_df['type'] == 'TOTAL'].copy()
            stress_daily = stress_total[['calendarDate', 'averageStressLevel', 'restDuration']].copy()
            stress_daily['date'] = stress_daily['calendarDate'].dt.date
            stress_daily = stress_daily.drop(columns=['calendarDate'])  # Remover para evitar duplicatas
            merged = pd.merge(merged, stress_daily, on='date', how='outer')
        
        # Saúde (HRV, FC em repouso)
        if health_df is not None and len(health_df) > 0:
            health_cols = ['calendarDate']
            if 'HRV_value' in health_df.columns:
                health_cols.append('HRV_value')
            if 'HR_value' in health_df.columns:
                health_cols.append('HR_value')
            
            health_daily = health_df[health_cols].copy()
            health_daily['date'] = health_daily['calendarDate'].dt.date
            health_daily = health_daily.drop(columns=['calendarDate'])  # Remover para evitar duplicatas
            merged = pd.merge(merged, health_daily, on='date', how='outer')
        
        merged = merged.dropna(subset=['date'])
        
        if len(merged) < 5:
            st.warning("Dados insuficientes para análise de correlação (necessário ao menos 5 dias com dados)")
            return
            
    except Exception as e:
        st.error(f"Erro ao processar dados para correlação: {str(e)}")
        return
    
    # === 2. ATIVIDADE VS SONO ===
    st.subheader("🏃 Atividade vs 😴 Sono")
    
    activity_sleep_data = merged.dropna(subset=['calories', 'totalSleepHours', 'deepSleepHours'])
    
    if len(activity_sleep_data) >= 5:
        col1, col2 = st.columns(2)
        
        with col1:
            fig = px.scatter(
                activity_sleep_data,
                x='duration',
                y='totalSleepHours',
                title="Duração do Treino vs Horas de Sono",
                labels={'duration': 'Duração do Treino (min)', 'totalSleepHours': 'Horas de Sono'},
                color='calories',
                size='distance',
                color_continuous_scale='Viridis'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.scatter(
                activity_sleep_data,
                x='calories',
                y='deepSleepHours',
                title="Calorias vs Sono Profundo",
                labels={'calories': 'Calorias', 'deepSleepHours': 'Sono Profundo (h)'},
                color='totalSleepHours',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # === 3. BODY BATTERY E RECUPERAÇÃO ===
    if body_battery_df is not None and 'chargedValue' in merged.columns:
        st.subheader("🔋 Energy e Recuperação")
        
        bb_data = merged.dropna(subset=['chargedValue', 'totalSleepHours', 'deepSleepHours'])
        
        if len(bb_data) >= 5:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.scatter(
                    bb_data,
                    x='totalSleepHours',
                    y='chargedValue',
                    title="Horas de Sono vs Recarga de Energia",
                    labels={'totalSleepHours': 'Horas de Sono', 'chargedValue': 'Recarga (Body Battery)'},
                    color='deepSleepHours',
                    color_continuous_scale='Greens'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.scatter(
                    bb_data,
                    x='calories',
                    y='drainedValue',
                    title="Calorias vs Gasto de Energia",
                    labels={'calories': 'Calorias Gastas', 'drainedValue': 'Descarga (Body Battery)'},
                    color='duration',
                    color_continuous_scale='Reds'
                )
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # === 4. ESTRESSE E ATIVIDADE ===
    if stress_df is not None and 'averageStressLevel' in merged.columns:
        st.subheader("😰 Estresse vs Atividade")
        
        stress_data = merged.dropna(subset=['averageStressLevel', 'calories'])
        
        if len(stress_data) >= 5:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.scatter(
                    stress_data,
                    x='calories',
                    y='averageStressLevel',
                    title="Atividade vs Nível de Estresse",
                    labels={'calories': 'Calorias Gastas', 'averageStressLevel': 'Nível de Estresse'},
                    color='duration',
                    color_continuous_scale='Oranges'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.scatter(
                    stress_data,
                    x='restDuration',
                    y='totalSleepHours',
                    title="Tempo de Descanso vs Sono",
                    labels={'restDuration': 'Tempo de Descanso (min)', 'totalSleepHours': 'Horas de Sono'},
                    color='averageStressLevel',
                    color_continuous_scale='RdYlGn_r'
                )
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # === 5. HRV E RECUPERAÇÃO ===
    if health_df is not None and 'HRV_value' in merged.columns:
        st.subheader("❤️ HRV e Recuperação")
        
        hrv_data = merged.dropna(subset=['HRV_value', 'totalSleepHours'])
        
        if len(hrv_data) >= 5:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.scatter(
                    hrv_data,
                    x='totalSleepHours',
                    y='HRV_value',
                    title="Sono vs HRV (Variabilidade Cardíaca)",
                    labels={'totalSleepHours': 'Horas de Sono', 'HRV_value': 'HRV (ms)'},
                    color='deepSleepHours',
                    color_continuous_scale='Purples'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                if 'averageStressLevel' in hrv_data.columns:
                    fig = px.scatter(
                        hrv_data,
                        x='averageStressLevel',
                        y='HRV_value',
                        title="Estresse vs HRV",
                        labels={'averageStressLevel': 'Nível de Estresse', 'HRV_value': 'HRV (ms)'},
                        color='totalSleepHours',
                        color_continuous_scale='RdYlGn'
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # === 6. MATRIZ DE CORRELAÇÃO ===
    st.subheader("📊 Matriz de Correlação Geral")
    
    # Selecionar colunas disponíveis para correlação
    corr_cols = []
    corr_labels = {}
    
    if 'duration' in merged.columns:
        corr_cols.append('duration')
        corr_labels['duration'] = 'Duração Treino'
    if 'calories' in merged.columns:
        corr_cols.append('calories')
        corr_labels['calories'] = 'Calorias'
    if 'distance' in merged.columns:
        corr_cols.append('distance')
        corr_labels['distance'] = 'Distância'
    if 'totalSleepHours' in merged.columns:
        corr_cols.append('totalSleepHours')
        corr_labels['totalSleepHours'] = 'Sono Total'
    if 'deepSleepHours' in merged.columns:
        corr_cols.append('deepSleepHours')
        corr_labels['deepSleepHours'] = 'Sono Profundo'
    if 'chargedValue' in merged.columns:
        corr_cols.append('chargedValue')
        corr_labels['chargedValue'] = 'BB Recarga'
    if 'drainedValue' in merged.columns:
        corr_cols.append('drainedValue')
        corr_labels['drainedValue'] = 'BB Descarga'
    if 'averageStressLevel' in merged.columns:
        corr_cols.append('averageStressLevel')
        corr_labels['averageStressLevel'] = 'Estresse'
    if 'HRV_value' in merged.columns:
        corr_cols.append('HRV_value')
        corr_labels['HRV_value'] = 'HRV'
    if 'HR_value' in merged.columns:
        corr_cols.append('HR_value')
        corr_labels['HR_value'] = 'FC Repouso'
    
    corr_data = merged[corr_cols].dropna()
    
    if len(corr_data) >= 3 and len(corr_cols) >= 3:
        try:
            corr_matrix = corr_data.corr()
            
            # Renomear índices e colunas para labels mais legíveis
            corr_matrix_display = corr_matrix.rename(index=corr_labels, columns=corr_labels)
            
            fig = px.imshow(
                corr_matrix_display,
                title="Correlação entre Todas as Métricas",
                color_continuous_scale='RdBu_r',
                aspect='auto',
                labels=dict(color="Correlação"),
                zmin=-1,
                zmax=1,
                text_auto='.2f'
            )
            fig.update_layout(height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            # === 7. INSIGHTS AUTOMÁTICOS ===
            st.markdown("---")
            st.subheader("💡 Insights Principais")
            
            # Explicação sobre correlação
            with st.expander("ℹ️ Como interpretar as correlações?"):
                st.markdown("""
                **O que é correlação?**
                
                A correlação mede a **relação** entre duas variáveis em uma escala de **-1 a +1**:
                
                - **+1.00 a +0.70**: Correlação positiva muito forte (quando uma sobe, a outra também sobe)
                - **+0.69 a +0.40**: Correlação positiva moderada
                - **+0.39 a +0.20**: Correlação positiva fraca
                - **+0.19 a -0.19**: Sem correlação significativa
                - **-0.20 a -0.39**: Correlação negativa fraca
                - **-0.40 a -0.69**: Correlação negativa moderada (quando uma sobe, a outra desce)
                - **-0.70 a -1.00**: Correlação negativa muito forte
                
                **Exemplos práticos:**
                - ✅ Correlação positiva: "Mais sono → Mais energia (Body Battery)"
                - ❌ Correlação negativa: "Mais estresse → Menos sono"
                - ℹ️ Sem correlação: As variáveis não se influenciam diretamente
                
                ⚠️ **Importante**: Correlação não significa causa! Apenas indica que as variáveis tendem a mudar juntas.
                """)
            
            st.markdown("")
            
            # Encontrar correlações mais fortes
            corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    corr_pairs.append({
                        'var1': corr_labels.get(corr_matrix.columns[i], corr_matrix.columns[i]),
                        'var2': corr_labels.get(corr_matrix.columns[j], corr_matrix.columns[j]),
                        'corr': corr_matrix.iloc[i, j]
                    })
            
            corr_pairs_df = pd.DataFrame(corr_pairs)
            corr_pairs_df['abs_corr'] = corr_pairs_df['corr'].abs()
            corr_pairs_df = corr_pairs_df.sort_values('abs_corr', ascending=False)
            
            # Mostrar top 5 correlações
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**🔝 Principais Relações Encontradas:**")
                st.markdown("*As 5 correlações mais fortes nos seus dados*")
                st.markdown("")
                
                for idx, row in corr_pairs_df.head(5).iterrows():
                    corr_val = row['corr']
                    
                    # Determinar força e direção
                    if abs(corr_val) >= 0.7:
                        strength = "muito forte"
                        emoji = "🔥"
                    elif abs(corr_val) >= 0.4:
                        strength = "moderada"
                        emoji = "💪"
                    elif abs(corr_val) >= 0.2:
                        strength = "fraca"
                        emoji = "👍"
                    else:
                        strength = "muito fraca"
                        emoji = "ℹ️"
                    
                    direction = "positiva" if corr_val > 0 else "negativa"
                    
                    # Explicação da relação
                    if corr_val > 0:
                        explanation = "Quando uma aumenta, a outra tende a aumentar"
                        color = "success"
                    else:
                        explanation = "Quando uma aumenta, a outra tende a diminuir"
                        color = "error"
                    
                    if abs(corr_val) >= 0.2:
                        if color == "success":
                            st.success(f"{emoji} **{row['var1']} ↔️ {row['var2']}**  \n"
                                     f"Correlação: **{corr_val:.2f}** ({strength} {direction})  \n"
                                     f"_{explanation}_")
                        else:
                            st.error(f"{emoji} **{row['var1']} ↔️ {row['var2']}**  \n"
                                   f"Correlação: **{corr_val:.2f}** ({strength} {direction})  \n"
                                   f"_{explanation}_")
                    else:
                        st.info(f"{emoji} **{row['var1']} ↔️ {row['var2']}**  \n"
                               f"Correlação: **{corr_val:.2f}** ({strength})  \n"
                               f"_Pouca ou nenhuma relação detectada_")
            
            with col2:
                st.markdown("**🎯 Recomendações Personalizadas:**")
                st.markdown("*Baseadas nos padrões encontrados*")
                st.markdown("")
                
                # Recomendações baseadas em correlações
                recommendations = []
                
                # Sono e Body Battery
                if 'totalSleepHours' in corr_matrix.columns and 'chargedValue' in corr_matrix.columns:
                    corr_val = corr_matrix.loc['totalSleepHours', 'chargedValue']
                    if corr_val > 0.4:
                        recommendations.append({
                            'emoji': '💤',
                            'title': 'Sono é sua melhor recarga!',
                            'text': f'Seus dados mostram forte relação ({corr_val:.2f}) entre horas de sono e energia. Priorize dormir bem para ter mais Body Battery.'
                        })
                    elif corr_val > 0.2:
                        recommendations.append({
                            'emoji': '💤',
                            'title': 'Sono ajuda na energia',
                            'text': f'Há uma relação moderada ({corr_val:.2f}) entre sono e energia. Tente dormir mais consistentemente.'
                        })
                
                # Atividade e Sono Profundo
                if 'calories' in corr_matrix.columns and 'deepSleepHours' in corr_matrix.columns:
                    corr_val = corr_matrix.loc['calories', 'deepSleepHours']
                    if corr_val > 0.4:
                        recommendations.append({
                            'emoji': '🏃',
                            'title': 'Exercício melhora seu sono!',
                            'text': f'Correlação forte ({corr_val:.2f}) entre atividade e sono profundo. Treinar ajuda você a dormir melhor!'
                        })
                    elif corr_val > 0.2:
                        recommendations.append({
                            'emoji': '🏃',
                            'title': 'Mantenha-se ativo',
                            'text': f'Atividade física tem relação positiva ({corr_val:.2f}) com sono profundo. Continue treinando!'
                        })
                
                # Estresse e Sono
                if 'averageStressLevel' in corr_matrix.columns and 'totalSleepHours' in corr_matrix.columns:
                    corr_val = corr_matrix.loc['averageStressLevel', 'totalSleepHours']
                    if corr_val < -0.4:
                        recommendations.append({
                            'emoji': '😰',
                            'title': 'Estresse prejudica seu sono',
                            'text': f'Correlação negativa forte ({corr_val:.2f}): mais estresse = menos sono. Pratique técnicas de relaxamento!'
                        })
                    elif corr_val < -0.2:
                        recommendations.append({
                            'emoji': '😰',
                            'title': 'Gerencie o estresse',
                            'text': f'Estresse tem relação negativa ({corr_val:.2f}) com sono. Considere meditação ou respiração.'
                        })
                
                # HRV e Sono
                if 'HRV_value' in corr_matrix.columns and 'totalSleepHours' in corr_matrix.columns:
                    corr_val = corr_matrix.loc['HRV_value', 'totalSleepHours']
                    if corr_val > 0.4:
                        recommendations.append({
                            'emoji': '❤️',
                            'title': 'Sono = melhor recuperação',
                            'text': f'HRV alto com mais sono ({corr_val:.2f}). Seu corpo se recupera melhor quando você descansa!'
                        })
                    elif corr_val > 0.2:
                        recommendations.append({
                            'emoji': '❤️',
                            'title': 'Descanse para recuperar',
                            'text': f'HRV melhora com sono ({corr_val:.2f}). Priorize o descanso para otimizar recuperação.'
                        })
                
                # Body Battery e Atividade
                if 'drainedValue' in corr_matrix.columns and 'calories' in corr_matrix.columns:
                    corr_val = corr_matrix.loc['drainedValue', 'calories']
                    if corr_val > 0.4:
                        recommendations.append({
                            'emoji': '🔋',
                            'title': 'Balance treino e descanso',
                            'text': f'Atividade intensa gasta muita energia ({corr_val:.2f}). Certifique-se de recuperar adequadamente!'
                        })
                
                if not recommendations:
                    recommendations.append({
                        'emoji': '📊',
                        'title': 'Continue monitorando',
                        'text': 'Ainda não há correlações fortes suficientes. Com mais dados, padrões mais claros surgirão!'
                    })
                
                for rec in recommendations:
                    st.markdown(f"**{rec['emoji']} {rec['title']}**")
                    st.markdown(f"_{rec['text']}_")
                    st.markdown("")
                    
        except Exception as e:
            st.error(f"Erro ao calcular correlação: {str(e)}")
    else:
        st.warning("Dados insuficientes para matriz de correlação completa")


def create_summary_dashboard(activities_df, sleep_df, health_df, body_battery_df=None, stress_df=None):
    """Cria dashboard resumido com todas as métricas principais"""
    st.header("🎯 Dashboard Resumido")
    
    # Período de análise
    if activities_df is not None and len(activities_df) > 0:
        min_date = activities_df['startTimeLocal'].min()
        max_date = activities_df['startTimeLocal'].max()
        
        # Verificar se as datas são válidas (não são NaT)
        if pd.notna(min_date) and pd.notna(max_date):
            st.info(f"📅 Período analisado: {min_date.strftime('%d/%m/%Y')} até {max_date.strftime('%d/%m/%Y')}")
        else:
            st.warning("⚠️ Datas das atividades não puderam ser processadas corretamente")
    
    # Cards de métricas principais
    st.markdown("### 📈 Visão Geral")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if activities_df is not None and len(activities_df) > 0:
            total_act = len(activities_df)
            st.metric("🏃 Atividades", f"{total_act}")
        else:
            st.metric("🏃 Atividades", "0")
    
    with col2:
        if sleep_df is not None and len(sleep_df) > 0:
            avg_sleep = sleep_df['totalSleepHours'].mean()
            st.metric("😴 Sono Médio", f"{avg_sleep:.1f}h")
        else:
            st.metric("😴 Sono Médio", "N/A")
    
    with col3:
        if body_battery_df is not None and len(body_battery_df) > 0 and 'highest_value' in body_battery_df.columns:
            avg_bb = body_battery_df['highest_value'].mean()
            st.metric("🔋 Body Battery", f"{avg_bb:.0f}")
        else:
            st.metric("🔋 Body Battery", "N/A")
    
    with col4:
        if stress_df is not None and len(stress_df) > 0:
            stress_total = stress_df[stress_df['type'] == 'TOTAL']
            if len(stress_total) > 0:
                avg_stress = stress_total['averageStressLevel'].mean()
                st.metric("😰 Estresse", f"{avg_stress:.0f}")
            else:
                st.metric("😰 Estresse", "N/A")
        else:
            st.metric("😰 Estresse", "N/A")
    
    with col5:
        if health_df is not None and len(health_df) > 0 and 'HRV_value' in health_df.columns:
            avg_hrv = health_df['HRV_value'].dropna().mean()
            if not pd.isna(avg_hrv):
                st.metric("❤️ HRV", f"{avg_hrv:.0f} ms")
            else:
                st.metric("❤️ HRV", "N/A")
        else:
            st.metric("❤️ HRV", "N/A")
    
    st.markdown("---")
    
    # Atividades
    if activities_df is not None:
        st.subheader("🏃 Resumo de Atividades")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_act = len(activities_df)
            st.metric("Total de Atividades", f"{total_act}")
        
        with col2:
            total_dist = activities_df['distance_km'].sum()
            st.metric("Distância Total", f"{total_dist:.0f} km")
        
        with col3:
            if 'activeCalories' in activities_df.columns:
                active_cal = activities_df['activeCalories'].sum()
                st.metric("Calorias", f"{active_cal:_.0f}".replace('_', '.'))
            else:
                total_cal = activities_df['calories'].sum()
                st.metric("Calorias", f"{total_cal:_.0f}".replace('_', '.'))
        
        with col4:
            avg_duration = activities_df['duration_minutes'].mean()
            st.metric("Duração Média", f"{avg_duration:.0f} min")
        
        # Gráfico de tendência
        monthly_activities = activities_df.groupby('month').agg({
            'activityId': 'count',
            'distance_km': 'sum'
        }).reset_index()
        monthly_activities['month'] = monthly_activities['month'].astype(str)
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(
            go.Bar(x=monthly_activities['month'], y=monthly_activities['activityId'], 
                   name="Quantidade", marker_color='lightblue'),
            secondary_y=False,
        )
        
        fig.add_trace(
            go.Scatter(x=monthly_activities['month'], y=monthly_activities['distance_km'],
                      name="Distância (km)", mode='lines+markers', line=dict(color='red', width=3)),
            secondary_y=True,
        )
        
        fig.update_xaxes(title_text="Mês")
        fig.update_yaxes(title_text="Quantidade de Atividades", secondary_y=False)
        fig.update_yaxes(title_text="Distância (km)", secondary_y=True)
        fig.update_layout(title_text="Evolução Mensal das Atividades")
        
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Sono
    if sleep_df is not None:
        st.subheader("😴 Resumo de Sono")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_sleep = sleep_df['totalSleepHours'].mean()
            st.metric("Sono Médio", f"{avg_sleep:.1f}h")
        
        with col2:
            avg_deep = sleep_df['deepSleepHours'].mean()
            st.metric("Sono Profundo", f"{avg_deep:.1f}h")
        
        with col3:
            avg_rem = sleep_df['remSleepHours'].mean()
            st.metric("Sono REM", f"{avg_rem:.1f}h")
        
        with col4:
            if 'overallScore' in sleep_df.columns:
                avg_score = sleep_df['overallScore'].mean()
                st.metric("Score Médio", f"{avg_score:.0f}")
        
        # Gráfico de tendência mensal
        monthly_sleep = sleep_df.groupby('month').agg({
            'totalSleepHours': 'mean',
            'deepSleepHours': 'mean',
            'remSleepHours': 'mean'
        }).reset_index()
        monthly_sleep['month'] = monthly_sleep['month'].astype(str)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=monthly_sleep['month'], y=monthly_sleep['totalSleepHours'],
                                mode='lines+markers', name='Total', line=dict(color='#4B0082', width=3)))
        fig.add_trace(go.Scatter(x=monthly_sleep['month'], y=monthly_sleep['deepSleepHours'],
                                mode='lines+markers', name='Profundo', line=dict(color='#1E3A8A')))
        fig.add_trace(go.Scatter(x=monthly_sleep['month'], y=monthly_sleep['remSleepHours'],
                                mode='lines+markers', name='REM', line=dict(color='#A78BFA')))
        
        fig.update_layout(
            title="Evolução Mensal do Sono",
            xaxis_title="Mês",
            yaxis_title="Horas",
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Body Battery e Estresse
    col_bb, col_stress = st.columns(2)
    
    with col_bb:
        if body_battery_df is not None and len(body_battery_df) > 0:
            st.subheader("🔋 Body Battery")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if 'highest_value' in body_battery_df.columns:
                    avg_high = body_battery_df['highest_value'].mean()
                    st.metric("Máximo Médio", f"{avg_high:.0f}")
            
            with col2:
                if 'chargedValue' in body_battery_df.columns:
                    avg_charge = body_battery_df['chargedValue'].mean()
                    st.metric("Recarga Média", f"+{avg_charge:.0f}")
            
            # Mini gráfico
            if 'highest_value' in body_battery_df.columns and 'lowest_value' in body_battery_df.columns:
                bb_recent = body_battery_df.tail(14).sort_values('calendarDate')
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=bb_recent['calendarDate'],
                    y=bb_recent['highest_value'],
                    mode='lines+markers',
                    name='Máximo',
                    line=dict(color='#10B981', width=2),
                    marker=dict(size=6)
                ))
                fig.add_trace(go.Scatter(
                    x=bb_recent['calendarDate'],
                    y=bb_recent['lowest_value'],
                    mode='lines+markers',
                    name='Mínimo',
                    line=dict(color='#EF4444', width=2),
                    marker=dict(size=6)
                ))
                fig.update_layout(
                    title="Últimos 14 dias",
                    xaxis_title="",
                    yaxis_title="Body Battery",
                    height=250,
                    margin=dict(l=10, r=10, t=40, b=10)
                )
                st.plotly_chart(fig, use_container_width=True)
    
    with col_stress:
        if stress_df is not None and len(stress_df) > 0:
            st.subheader("😰 Estresse")
            
            stress_total = stress_df[stress_df['type'] == 'TOTAL']
            
            if len(stress_total) > 0:
                col1, col2 = st.columns(2)
                
                with col1:
                    avg_stress = stress_total['averageStressLevel'].mean()
                    st.metric("Nível Médio", f"{avg_stress:.0f}")
                
                with col2:
                    rest_time = stress_total['restDuration'].mean()
                    st.metric("Descanso/dia", f"{rest_time:.0f} min")
                
                # Mini gráfico
                stress_recent = stress_total.tail(14).sort_values('calendarDate')
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=stress_recent['calendarDate'],
                    y=stress_recent['averageStressLevel'],
                    mode='lines+markers',
                    name='Estresse',
                    line=dict(color='#F97316', width=2),
                    marker=dict(size=6),
                    fill='tozeroy',
                    fillcolor='rgba(249, 115, 22, 0.1)'
                ))
                fig.add_hline(y=50, line_dash="dash", line_color="orange", line_width=1)
                fig.update_layout(
                    title="Últimos 14 dias",
                    xaxis_title="",
                    yaxis_title="Nível",
                    height=250,
                    margin=dict(l=10, r=10, t=40, b=10)
                )
                st.plotly_chart(fig, use_container_width=True)
    
    # Estatísticas gerais
    st.markdown("---")
    st.subheader("📊 Estatísticas Gerais")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if activities_df is not None:
            st.write("**Top 5 Atividades por Distância**")
            top_activities = activities_df.nlargest(5, 'distance_km')[['startTimeLocal', 'activityType', 'distance_km', 'duration_minutes']]
            top_activities['startTimeLocal'] = top_activities['startTimeLocal'].dt.strftime('%d/%m/%Y')
            top_activities.columns = ['Data', 'Tipo', 'Distância (km)', 'Duração (min)']
            st.dataframe(top_activities, hide_index=True, use_container_width=True)
    
    with col2:
        if sleep_df is not None:
            st.write("**Melhores Noites de Sono**")
            
            # Verificar se tem score disponível
            if 'overallScore' in sleep_df.columns and sleep_df['overallScore'].notna().any():
                # Ordenar por score
                top_sleep = sleep_df.dropna(subset=['overallScore']).nlargest(5, 'overallScore')[
                    ['calendarDate', 'overallScore', 'totalSleepHours', 'deepSleepHours']
                ]
                top_sleep['calendarDate'] = top_sleep['calendarDate'].dt.strftime('%d/%m/%Y')
                top_sleep.columns = ['Data', 'Score', 'Total (h)', 'Profundo (h)']
            else:
                # Fallback: ordenar por horas totais
                top_sleep = sleep_df.nlargest(5, 'totalSleepHours')[['calendarDate', 'totalSleepHours', 'deepSleepHours']]
                top_sleep['calendarDate'] = top_sleep['calendarDate'].dt.strftime('%d/%m/%Y')
                top_sleep.columns = ['Data', 'Total (h)', 'Profundo (h)']
            
            st.dataframe(top_sleep, hide_index=True, use_container_width=True)


def main():
    """Função principal do dashboard"""
    
    # Header
    st.markdown('<h1 class="main-header">⚡ Garmin Connect Analytics</h1>', unsafe_allow_html=True)
    st.markdown("### Dashboard Completo de Análise de Atividades, Sono e Saúde")
    
    # Sidebar
    with st.sidebar:
        st.image("https://www.garmin.com/assets/images/garmin-icon.png", width=100)
        st.title("📁 Upload de Dados")
        st.markdown("---")
        
        uploaded_file = st.file_uploader(
            "Faça upload do arquivo ZIP do Garmin Connect",
            type=['zip'],
            help="Exporte seus dados do Garmin Connect e faça upload do arquivo ZIP"
        )
        
        st.markdown("---")
        st.markdown("### ℹ️ Sobre")
        st.info(
            """
            Este dashboard analisa seus dados exportados do Garmin Connect, incluindo:
            
            - 🏃 Atividades físicas
            - 😴 Dados de sono
            - 💗 Métricas de saúde
            - 💧 Hidratação
            - 🔗 Correlações
            
            **📥 Como exportar seus dados do Garmin:**
            
            1. Acesse: https://www.garmin.com/en-US/account/datamanagement/
            2. Login → Export Your Data → Request Data Export
            3. Aguarde o email (pode demorar minutos ou horas)
            4. Baixe o arquivo ZIP do link no email
            
            **📱 Como usar o dashboard:**
            
            1. Faça upload do arquivo ZIP
            2. Explore as 7 abas de análise!
            """
        )
        
        st.markdown("---")
        st.markdown("Desenvolvido com ❤️ usando Streamlit")
    
    # Processar dados quando arquivo é carregado
    if uploaded_file is not None:
        with st.spinner("🔄 Processando seus dados... Isso pode levar alguns instantes."):
            # Criar analisador
            analyzer = GarminDataAnalyzer(uploaded_file)
            analyzer.load_all_data()
        
        st.success("✅ Dados carregados com sucesso!")
        
        # Menu de navegação
        st.markdown("---")
        
        tabs = st.tabs([
            "📊 Resumo",
            "🏃 Atividades - Visão Geral",
            "📈 Atividades - Análise Completa",
            "😴 Sono",
            "💗 Saúde",
            "🔗 Correlações"
        ])
        
        with tabs[0]:
            create_summary_dashboard(analyzer.activities_df, analyzer.sleep_df, analyzer.health_df, analyzer.body_battery_df, analyzer.stress_df)
        
        with tabs[1]:
            if analyzer.activities_df is not None:
                create_activities_overview(analyzer.activities_df)
            else:
                st.warning("Dados de atividades não disponíveis")
        
        with tabs[2]:
            if analyzer.activities_df is not None:
                # Combinar análise temporal e detalhada
                create_activities_temporal_analysis(analyzer.activities_df)
                st.markdown("---")
                st.markdown("---")
                create_activities_detailed_analysis(analyzer.activities_df)
            else:
                st.warning("Dados de atividades não disponíveis")
        
        with tabs[3]:
            create_sleep_analysis(analyzer.sleep_df)
        
        with tabs[4]:
            create_health_analysis(analyzer.health_df, analyzer.body_battery_df, analyzer.stress_df)
        
        with tabs[5]:
            create_correlation_analysis(analyzer.activities_df, analyzer.sleep_df, analyzer.body_battery_df, analyzer.stress_df, analyzer.health_df)
        
    else:
        # Tela inicial
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.image("https://www.garmin.com/assets/images/garmin-icon.png", width=200)
            st.markdown(
                """
                <div style='text-align: center; padding: 20px;'>
                    <h2>Bem-vindo ao Dashboard Garmin Analytics!</h2>
                    <p style='font-size: 18px;'>
                        Para começar, faça upload do seu arquivo ZIP do Garmin Connect 
                        usando o menu lateral à esquerda.
                    </p>
                    <br>
                    <p style='font-size: 14px; color: #666;'>
                        💡 <b>Dica:</b> Acesse garmin.com/account/datamanagement 
                        para exportar seus dados.
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        st.markdown("---")
        
        # Informações sobre o que será analisado
        st.subheader("🎯 O que você vai descobrir:")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            #### 🏃 Atividades
            - Total de atividades e tipos
            - Distância percorrida
            - Calorias queimadas
            - Análise temporal
            - Frequência cardíaca
            - Padrões de treino
            """)
        
        with col2:
            st.markdown("""
            #### 😴 Sono
            - Qualidade do sono
            - Fases do sono (REM, profundo, leve)
            - Score de sono
            - Padrões respiratórios
            - Despertares noturnos
            - Tendências semanais
            """)
        
        with col3:
            st.markdown("""
            #### 💗 Saúde
            - Métricas de saúde
            - Correlações
            - Tendências temporais
            - Análises avançadas
            - Insights personalizados
            """)


if __name__ == "__main__":
    main()

