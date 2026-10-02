#!/bin/bash
# Pornire aplicatie WorkPulse Dashboard
cd "$(dirname "$0")"

echo "=========================================="
echo "🚀 Pornire WorkPulse Dashboard & Pontaj..."
echo "=========================================="

# Verificare si instalare dependinte daca lipsesc
python3 -c "import flask" 2>/dev/null || {
    echo "Instalez Flask..."
    pip install flask
}

# Deschidere server local
echo ""
echo "📱 Deschide browserul telefonului la:"
echo "   👉 http://127.0.0.1:5000"
echo "   👉 http://localhost:5000"
echo ""
echo "Pentru oprire apasă CTRL + C"
echo "=========================================="

python3 app.py
