@echo off
echo 🏃 Iniciando Garmin Connect Analytics Dashboard...
echo.
echo 📦 Verificando dependências...
echo.

REM Instalar dependências
echo 📥 Instalando dependências...
pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo ✅ Dependências instaladas com sucesso!
    echo.
    echo 🚀 Iniciando dashboard...
    echo.
    echo 📱 O dashboard será aberto no seu navegador em: http://localhost:8501
    echo.
    echo 💡 Para parar o dashboard, pressione Ctrl+C
    echo.
    streamlit run streamlit_dashboard.py
) else (
    echo ❌ Erro ao instalar dependências.
    pause
    exit /b 1
)

