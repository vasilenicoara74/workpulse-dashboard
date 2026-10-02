@echo off
title WorkPulse Career Dashboard
cd /d "%~dp0"
echo ==========================================
echo 🚀 Pornire WorkPulse pe Laptop / PC...
echo ==========================================
python -c "import flask" 2>nul || (
    echo Instalez dependintele...
    pip install flask
)
echo.
echo Deschide browserul la:
echo 👉 http://localhost:5000
echo ==========================================
start http://localhost:5000
python app.py
pause
