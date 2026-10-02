# -*- coding: utf-8 -*-
"""
WorkPulse - AI Engineering Copilot (Gemini-Style Mechanical Assistant)
Provides intelligent deliverable polishing, ISO mechanical standards,
and performance appraisal prep tailored for Mechanical Design Engineers.
"""

import os
import re
import json
import urllib.request
import urllib.error

SYSTEM_PROMPT = """Ești AI Copilot pentru Ingineri Proiectanți Mecanici integrat în WorkPulse.
Răspunde întotdeauna în limba română, tehnic, clar, concis și fără divagații teoretice inutile.
Ești expert în:
- Modelare 3D CAD (SolidWorks, Autodesk Inventor, Catia, Creo, AutoCAD)
- Desene de execuție 2D, cotare toleranțe ISO (ISO 2768, ISO 1101, GD&T, ajustaje H7/g6, H7/p6)
- Tehnologii de fabricație: Tablă (debitare laser, abkant, factor K, rază îndoire), Prelucrare CNC, Sudură, Profile Aluminiu
- Nomenclatoare BOM, standardizare organe de asamblare (ISO/DIN)
- Modificări tehnice ECO/ECN și asistență atelier/montaj
- Pregătirea dosarului de evaluare anuală pentru mărire salarială (argumente axate pe livrabile, calitate și zero rebuturi).
Formatul răspunsurilor trebuie să fie scurt, aerisit, cu bullet points ușor de citit pe telefon.
"""

def polish_deliverable_description(raw_text, activity_type="Modelare CAD 3D", part_number="ASM-001", process="Tablă Sheet Metal"):
    """
    Transforms informal/raw engineer notes into polished, professional engineering deliverable statements.
    """
    raw = (raw_text or "").strip()
    if not raw:
        return "Finalizat livrabilele tehnice conform cerințelor de proiectare și specificațiilor din tema de proiectare."
    
    # Check if Gemini API key exists
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        try:
            prompt = f"Reformulează următoarea notiță brută de lucru a unui inginer proiectant mecanic într-o descriere tehnică impecabilă, profesională, axată pe livrabil (maxim 2-3 fraze clare, fără introduceri):\nNotiță: \"{raw}\"\nTip activitate: {activity_type}\nReper: {part_number}\nProces fabricație: {process}"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]}]
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as res:
                resp_data = json.loads(res.read().decode('utf-8'))
                text = resp_data['candidates'][0]['content']['parts'][0]['text'].strip()
                return text
        except Exception:
            pass

    # Intelligent mechanical engineering rule-based engine
    raw_lower = raw.lower()
    prefix = ""
    details = []

    if "desen" in raw_lower or "2d" in raw_lower or "dxf" in raw_lower:
        prefix = f"Elaborat și verificat desenele de execuție 2D pentru [{part_number}]."
        details.append("Definit cotarea completă, toleranțele dimensionale conform ISO 2768-mK și rugozitățile suprafețelor funcționale.")
        details.append("Exportat fișierele de producție (PDF și DXF debitare) și sincronizat BOM-ul cu modelul 3D.")
    elif "coliziun" in raw_lower or "interfer" in raw_lower or "verificat" in raw_lower:
        prefix = f"Efectuat analiza cinematică și verificarea de coliziuni 3D în ansamblul [{part_number}]."
        details.append("Identificat și eliminat interferențele geometrice înainte de lansarea în fabricație, prevenind riscul de rebut în atelier.")
    elif "ecn" in raw_lower or "modific" in raw_lower or "client" in raw_lower:
        prefix = f"Implementat modificarea tehnică ECN pe ansamblul [{part_number}]."
        details.append(f"Adaptat geometria conform noilor cerințe ({process}), actualizat arborele de modelare 3D și revizuit planșele de execuție fără decalarea termenului de livrare.")
    elif "atelier" in raw_lower or "montaj" in raw_lower or "proba" in raw_lower:
        prefix = f"Asigurat asistență tehnică directă în atelierul de montaj pentru [{part_number}]."
        details.append("Validat prima piesă (First Article Inspection), probat îmbinările și clarificat cotele funcționale cu echipa de asamblare.")
    elif "tabl" in raw_lower or "sheet" in raw_lower or "abkant" in raw_lower or "îndoi" in raw_lower or "indoi" in raw_lower:
        prefix = f"Proiectat componentele din tablă ({process}) pentru [{part_number}]."
        details.append("Calculat desfașurata ținând cont de factorul K și sculele abkant din atelier; prevăzut decupaje de descărcare la colțuri.")
    elif "bom" in raw_lower or "nomenclator" in raw_lower or "surub" in raw_lower:
        prefix = f"Finalizat și structurat nomenclatorul de materiale (BOM) pentru ansamblul [{part_number}]."
        details.append("Standardizat organele de asamblare pe clase de rezistență ISO și verificat codurile de achiziție cu specificațiile de proiect.")
    else:
        # General mechanical CAD deliverable
        first_letter = raw[0].upper() + raw[1:] if len(raw) > 1 else raw.upper()
        prefix = f"Proiectat și validat componentele ansamblului [{part_number}]: {first_letter}."
        details.append(f"Verificat integritatea geometrică, alinierea reperelor și respectarea normelor tehnologice ({process}).")

    result = f"{prefix} {' '.join(details)}"
    return result

def handle_chat_message(user_message, history=None):
    """
    Handles conversational interactions with the Mechanical Engineering AI Copilot.
    """
    msg = (user_message or "").strip()
    if not msg:
        return "Salut! Sunt asistentul tău AI pentru proiectare mecanică. Cu ce te pot ajuta astăzi (formulare sarcini, toleranțe ISO, sfaturi DFM sau pregătire evaluare)?"

    # Check if Gemini API key exists
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        try:
            formatted_contents = [{"role": "user", "parts": [{"text": SYSTEM_PROMPT}]}]
            if history:
                for h in history[-4:]:
                    r = "user" if h.get("sender") == "user" else "model"
                    formatted_contents.append({"role": r, "parts": [{"text": h.get("text", "")}]})
            formatted_contents.append({"role": "user", "parts": [{"text": msg}]})

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = {"contents": formatted_contents}
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=6) as res:
                resp_data = json.loads(res.read().decode('utf-8'))
                return resp_data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            pass

    # Built-in High-Level Mechanical Engineering Intelligence
    m_lower = msg.lower()

    if "evaluare" in m_lower or "marire" in m_lower or "salariu" in m_lower or "negoci" in m_lower:
        return """### 🎯 Strategie Evaluare & Mărire Salarială (Fără pontat ore)
Conducerea apreciază **livrabilele fără erori** și **rebuturile prevenite**:
1. **Calitate & Zero Rebuturi:** Amintește coliziunile 3D prinse în fază de modelare, înainte să ajungă piesele la debitare sau mașina CNC.
2. **Reactivitate ECN:** Subliniază viteza cu care ai preluat și rezolvat modificările venite de la clienți sau atelier.
3. **Standardizare BOM:** Arată cum ai redus diversitatea de șuruburi/piulițe sau grosimi de tablă pe proiecte.
4. **Asistență Atelier:** Faptul că ești prezent la prima probă de montaj oferă siguranță întregii echipe."""

    elif "toleran" in m_lower or "ajustaj" in m_lower or "h7" in m_lower or "g6" in m_lower:
        return """### 📐 Ghid Rapid Ajustaje ISO Uzuale
- **Alezaj rulment în carcasă:** `H7` (uz general) sau `J7` (sarcină alternantă).
- **Arbore rulment (fus de rulment):** `k5` / `m5` (rulmenți mici) sau `k6` / `m6` (rulmenți mari).
- **Ghidaj cilindric liber (mișcare axială/rotativă):** `H7 / g6` sau `H8 / f7` (lejer).
- **Centrare fixă (știfturi de poziționare):** `H7 / h6` (glisant la mână) sau `H7 / p6` (presat ușor).
- **Toleranțe generale nespecificate:** `ISO 2768-mK` (finețe medie pentru debitare/frezare)."""

    elif "tabl" in m_lower or "abkant" in m_lower or "factor k" in m_lower or "indoire" in m_lower:
        return """### 📏 Reguli de Aur Îndoire Tablă (Sheet Metal)
- **Factor K uzual:**
  - $K \\approx 0.33$ pentru $R < s$ (îndoiri ascuțite)
  - $K \\approx 0.40 - 0.42$ pentru $R = s$ (standard atelier)
  - $K \\approx 0.50$ pentru $R \\ge 2s$
- **Raza minimă de îndoire interioară:** Recomandat $R_{min} \\ge 1 \\times s$ (pentru Oțel S235/DC01) și $\\ge 1.5 \\times s$ pentru Aluminiu.
- **Distanța minimă gaură - margine de îndoire:** $L_{min} \\ge 2 \\times s + R$ (pentru a evita ovalizarea găurilor la îndoire)."""

    elif "filet" in m_lower or "surub" in m_lower or "pas" in m_lower:
        return """### 🔩 Filete Metrice & Clase de Rezistență
- **Pași filet standard (ISO):**
  - M5 x 0.8 | M6 x 1.0 | M8 x 1.25 | M10 x 1.5 | M12 x 1.75 | M16 x 2.0
- **Alezaj pentru tarodare:** $D_{gaura} = D_{filet} - Pas$ (ex: pt M8 se dă gaură de $8 - 1.25 = 6.8$ mm).
- **Clasă de rezistență:**
  - `8.8` (Standard general industrie, rezistență rupere 800 MPa).
  - `10.9` (Sarcini mari, șasiuri, ansambluri dinamice solicitate)."""

    elif "cnc" in m_lower or "frezare" in m_lower or "strunjire" in m_lower:
        return """### ⚙️ Reguli DFM Prelucrări Mecanice (CNC)
1. **Raze interioare buzunare:** Evită colțurile ascuțite la 90° în fundul cavităților; lasă rază de minim $R \\ge 1.5 - 2$ mm compatibilă cu frezele uzuale.
2. **Adâncimea cavităților:** Recomandat maxim $3 - 4 \\times D_{freză}$ pentru a evita vibrațiile și ruperea sculei.
3. **Degajări pentru rectificare/strunjire:** Folosește degajări standardizate conform DIN 509 (Form E sau F)."""

    else:
        return f"""Am notat întrebarea ta tehnică: *„{msg}”*.
Ca inginer proiectant, îți recomand să ții cont de standardele ISO de desen și posibilitățile tehnologice ale atelierului tău (abkant, debitare, CNC). 
Dacă vrei să reformulezi un livrabil pentru jurnalul tabelar, trimite-mi textul simplu și îl transform instant într-o descriere tehnică de impact!"""
