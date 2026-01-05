#!/bin/bash

echo "🏃 Iniciando Garmin Connect Analytics Dashboard..."
echo ""
echo "📦 Verificando dependências..."

# Verificar se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Por favor, instale o Python 3."
    exit 1
fi

# Verificar se pip está instalado
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 não encontrado. Por favor, instale o pip."
    exit 1
fi

# Instalar dependências
echo "📥 Instalando dependências..."
pip3 install -q -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependências instaladas com sucesso!"
    echo ""
    echo "🚀 Iniciando dashboard..."
    echo ""
    echo "📱 O dashboard será aberto no seu navegador em: http://localhost:8501"
    echo ""
    echo "💡 Para parar o dashboard, pressione Ctrl+C"
    echo ""
    streamlit run streamlit_dashboard.py
else
    echo "❌ Erro ao instalar dependências."
    exit 1
fi

