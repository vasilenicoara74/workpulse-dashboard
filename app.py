import os
import json
import csv
import io
import secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response, send_file, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, get_connection
from ai_copilot import handle_chat_message, polish_deliverable_description

app = Flask(__name__)

# Persistent Secret Key for Sessions
SECRET_FILE = os.path.join(os.path.dirname(__file__), '.secret_key')
if not os.path.exists(SECRET_FILE):
    with open(SECRET_FILE, 'w') as f:
        f.write(secrets.token_hex(32))
with open(SECRET_FILE, 'r') as f:
    app.secret_key = f.read().strip()

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(days=60)

# In-memory brute-force rate limiter (IP -> [fail_timestamps])
FAILED_LOGINS = {}

init_db()

# Cybersecurity Response Headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# Auth Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Autentificare necesară'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sw.js')
def service_worker():
    return send_file(os.path.join(app.static_folder, 'sw.js'), mimetype='application/javascript')

# ----------------- CYBERSECURITY & AUTH -----------------
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    ip = request.remote_addr or '127.0.0.1'
    now = datetime.now()
    
    # Clean old failed attempts (> 15 min)
    if ip in FAILED_LOGINS:
        FAILED_LOGINS[ip] = [t for t in FAILED_LOGINS[ip] if now - t < timedelta(minutes=15)]
        if len(FAILED_LOGINS[ip]) >= 5:
            return jsonify({'error': 'Prea multe încercări eșuate. Cont blocat temporar 15 minute.'}), 429

    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember = data.get('remember', True)

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()

    if user and check_password_hash(user['password_hash'], password):
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        if remember:
            session.permanent = True

        c.execute('UPDATE users SET last_login = ? WHERE id = ?', (now.isoformat(), user['id']))
        conn.commit()
        conn.close()

        if ip in FAILED_LOGINS:
            del FAILED_LOGINS[ip]

        return jsonify({'success': True, 'username': user['username'], 'role': user['role']})

    conn.close()
    if ip not in FAILED_LOGINS:
        FAILED_LOGINS[ip] = []
    FAILED_LOGINS[ip].append(now)

    remaining = max(0, 5 - len(FAILED_LOGINS[ip]))
    return jsonify({'error': f'Utilizator sau parolă incorectă. Încercări rămase: {remaining}'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/me')
def api_auth_me():
    if session.get('user_id'):
        return jsonify({
            'authenticated': True,
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role')
        })
    return jsonify({'authenticated': False})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.json or {}
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '').strip()

    if len(new_pwd) < 4:
        return jsonify({'error': 'Parola nouă trebuie să aibă minim 4 caractere'}), 400

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()

    if not user or not check_password_hash(user['password_hash'], old_pwd):
        conn.close()
        return jsonify({'error': 'Parola actuală este incorectă'}), 400

    new_hash = generate_password_hash(new_pwd)
    c.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Parola a fost schimbată cu succes!'})

# ----------------- JURNAL ACTIVITĂȚI TABELAR (PE ZILE / LUNI / ANI) -----------------
MONTH_NAMES = {
    1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
    5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
    9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie'
}

@app.route('/api/daily-logs', methods=['GET', 'POST'])
@login_required
def api_daily_logs():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        entry_date = data.get('date') or date.today().isoformat()
        try:
            d_obj = datetime.strptime(entry_date, '%Y-%m-%d').date()
        except Exception:
            d_obj = date.today()
            entry_date = d_obj.isoformat()

        project_id = data.get('project_id')
        part_number = data.get('part_number', '').strip()
        revision = data.get('revision', '').strip()

        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)
            c.execute('SELECT part_number, revision FROM projects WHERE id = ?', (project_id,))
            p = c.fetchone()
            if p:
                if not part_number:
                    part_number = p['part_number']
                if not revision:
                    revision = p['revision']

        if not part_number:
            part_number = 'ASM-001'
        if not revision:
            revision = 'Rev 0'

        desc = data.get('description', '').strip()
        if not desc:
            conn.close()
            return jsonify({'error': 'Descrierea activității este obligatorie'}), 400

        drawings_count = int(data.get('drawings_count', 1) or 1)
        manufacturing_process = data.get('manufacturing_process', 'Tablă Sheet Metal')
        material = data.get('material', 'Oțel')
        ecn_source = data.get('ecn_source', '')

        c.execute('''
            INSERT INTO daily_logs (project_id, part_number, revision, date, year, month, activity_type, description, status_tag, is_highlight, drawings_count, manufacturing_process, material, ecn_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            part_number,
            revision,
            entry_date,
            d_obj.year,
            d_obj.month,
            data.get('activity_type', 'Modelare CAD 3D'),
            desc,
            data.get('status_tag', 'Finalizat'),
            1 if data.get('is_highlight') else 0,
            drawings_count,
            manufacturing_process,
            material,
            ecn_source
        ))
        conn.commit()
        log_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': log_id})

    # GET filters
    year = request.args.get('year')
    month = request.args.get('month')
    project_id = request.args.get('project_id')
    search = request.args.get('search', '').strip()

    query = '''
        SELECT d.*, p.name as project_name, p.color as project_color, p.cad_software
        FROM daily_logs d
        LEFT JOIN projects p ON d.project_id = p.id
        WHERE 1=1
    '''
    params = []

    activity_type = request.args.get('activity_type')
    status_tag = request.args.get('status_tag')
    highlight_only = request.args.get('highlight_only')

    if year and year != 'all':
        query += " AND d.year = ?"
        params.append(int(year))
    if month and month != 'all':
        query += " AND d.month = ?"
        params.append(int(month))
    if project_id and project_id != 'all':
        query += " AND d.project_id = ?"
        params.append(int(project_id))
    if activity_type and activity_type != 'all':
        query += " AND d.activity_type = ?"
        params.append(activity_type)
    if status_tag and status_tag != 'all':
        query += " AND d.status_tag = ?"
        params.append(status_tag)
    if highlight_only in ('1', 'true', True):
        query += " AND d.is_highlight = 1"
    if search:
        query += " AND (d.description LIKE ? OR d.part_number LIKE ? OR p.name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY d.date DESC, d.id DESC"

    c.execute(query, params)
    logs = [dict(r) for r in c.fetchall()]

    # Available months in DB
    c.execute('''
        SELECT DISTINCT year, month
        FROM daily_logs
        ORDER BY year DESC, month DESC
    ''')
    available_months = []
    for r in c.fetchall():
        y, m = r['year'], r['month']
        available_months.append({
            'year': y,
            'month': m,
            'label': f"{MONTH_NAMES.get(m, m)} {y}"
        })

    # Summary metrics for selected filter
    unique_dates = len(set(l['date'] for l in logs))
    unique_projects = len(set(l['project_id'] for l in logs if l['project_id']))
    highlights_count = sum(1 for l in logs if l['is_highlight'])

    conn.close()

    return jsonify({
        'logs': logs,
        'available_months': available_months,
        'summary': {
            'total_entries': len(logs),
            'unique_days': unique_dates,
            'unique_projects': unique_projects,
            'highlights': highlights_count
        }
    })

@app.route('/api/daily-logs/<int:log_id>/toggle-star', methods=['POST'])
@login_required
def api_daily_log_toggle_star(log_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE daily_logs SET is_highlight = 1 - is_highlight WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/daily-logs/<int:log_id>/delete', methods=['POST'])
@login_required
def api_daily_log_delete(log_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM daily_logs WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/daily-logs/<int:log_id>', methods=['GET'])
@login_required
def api_daily_log_get(log_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT d.*, p.name as project_name, p.cad_software, p.client
        FROM daily_logs d
        LEFT JOIN projects p ON d.project_id = p.id
        WHERE d.id = ?
    ''', (log_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Înregistrarea nu a fost găsită'}), 404
    return jsonify(dict(row))

@app.route('/api/daily-logs/<int:log_id>/update', methods=['POST'])
@login_required
def api_daily_log_update(log_id):
    data = request.json or {}
    conn = get_connection()
    c = conn.cursor()

    c.execute('SELECT * FROM daily_logs WHERE id = ?', (log_id,))
    existing = c.fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Înregistrarea nu există'}), 404

    entry_date = data.get('date') or existing['date']
    try:
        d_obj = datetime.strptime(entry_date, '%Y-%m-%d').date()
    except Exception:
        d_obj = date.today()
        entry_date = d_obj.isoformat()

    part_number = data.get('part_number', '').strip() or existing['part_number']
    revision = data.get('revision', '').strip() or existing['revision']

    desc = data.get('description', '').strip() or existing['description']
    activity_type = data.get('activity_type') or existing['activity_type']
    status_tag = data.get('status_tag') or existing['status_tag']
    is_highlight = 1 if data.get('is_highlight') else 0
    drawings_count = int(data.get('drawings_count', existing['drawings_count'] if 'drawings_count' in existing.keys() else 1) or 1)
    manufacturing_process = data.get('manufacturing_process') or (existing['manufacturing_process'] if 'manufacturing_process' in existing.keys() else 'Tablă Sheet Metal')
    material = data.get('material') or (existing['material'] if 'material' in existing.keys() else 'Oțel')
    ecn_source = data.get('ecn_source') or (existing['ecn_source'] if 'ecn_source' in existing.keys() else '')

    c.execute('''
        UPDATE daily_logs
        SET project_id = ?, part_number = ?, revision = ?, date = ?, year = ?, month = ?,
            activity_type = ?, description = ?, status_tag = ?, is_highlight = ?,
            drawings_count = ?, manufacturing_process = ?, material = ?, ecn_source = ?
        WHERE id = ?
    ''', (
        project_id, part_number, revision, entry_date, d_obj.year, d_obj.month,
        activity_type, desc, status_tag, is_highlight,
        drawings_count, manufacturing_process, material, ecn_source, log_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- PROIECTE PDM -----------------
@app.route('/api/projects', methods=['GET', 'POST'])
@login_required
def api_projects():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name', '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'Numele ansamblului este obligatoriu'}), 400

        c.execute('''
            INSERT INTO projects (part_number, revision, name, description, client, cad_software, status, priority, color, start_date, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('part_number', 'ASM-001').strip() or 'ASM-001',
            data.get('revision', 'Rev A').strip() or 'Rev A',
            name,
            data.get('description', ''),
            data.get('client', ''),
            data.get('cad_software', 'SolidWorks'),
            data.get('status', 'În Lucru'),
            data.get('priority', 'Medie'),
            data.get('color', '#2563eb'),
            data.get('start_date', date.today().isoformat()),
            data.get('deadline', '')
        ))
        conn.commit()
        project_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': project_id})

    c.execute('''
        SELECT p.*,
               (SELECT COUNT(DISTINCT date) FROM daily_logs WHERE project_id = p.id) as days_active,
               (SELECT COUNT(*) FROM daily_logs WHERE project_id = p.id) as total_entries,
               (SELECT COUNT(*) FROM achievements WHERE project_id = p.id) as total_achievements,
               (SELECT COUNT(*) FROM blockers WHERE project_id = p.id) as total_blockers
        FROM projects p
        ORDER BY CASE p.status WHEN 'În Lucru' THEN 1 WHEN 'Planificat' THEN 2 WHEN 'Finalizat' THEN 3 ELSE 4 END, p.id DESC
    ''')
    projects = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(projects)

# ----------------- SCUT & BLOCAJE (PROBLEME LA EVALUARE) -----------------
@app.route('/api/blockers', methods=['GET', 'POST'])
@login_required
def api_blockers():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        solution = data.get('solution_applied', '').strip()

        if not title or not description:
            conn.close()
            return jsonify({'error': 'Titlul și Descrierea sunt obligatorii'}), 400

        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)

        c.execute('''
            INSERT INTO blockers (project_id, date, title, cause_type, description, solution_applied, time_lost_days, prevented_risk)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            data.get('date') or date.today().isoformat(),
            title,
            data.get('cause_type', 'Modificare Cerințe Client'),
            description,
            solution,
            float(data.get('time_lost_days', 1) or 1),
            data.get('prevented_risk', '')
        ))
        conn.commit()
        bid = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': bid})

    c.execute('''
        SELECT b.*, p.name as project_name, p.part_number, p.revision, p.color as project_color
        FROM blockers b
        LEFT JOIN projects p ON b.project_id = p.id
        ORDER BY b.date DESC, b.id DESC
    ''')
    blockers = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(blockers)

@app.route('/api/blockers/<int:blocker_id>/delete', methods=['POST'])
@login_required
def api_blocker_delete(blocker_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM blockers WHERE id = ?', (blocker_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- REALIZĂRI & BRAG SHEET -----------------
@app.route('/api/achievements', methods=['GET', 'POST'])
@login_required
def api_achievements():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        title = data.get('title', '').strip()
        impact = data.get('impact_value', '').strip()
        if not title or not impact:
            conn.close()
            return jsonify({'error': 'Titlul și Rezultatul / Impactul sunt obligatorii!'}), 400

        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)

        c.execute('''
            INSERT INTO achievements (project_id, date, title, impact_value, money_saved_est, category, feedback_received, is_highlight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            data.get('date') or date.today().isoformat(),
            title,
            impact,
            float(data.get('money_saved_est', 0) or 0),
            data.get('category', 'Optimizare Proiectare & Cost'),
            data.get('feedback_received', ''),
            1 if data.get('is_highlight') else 0
        ))
        conn.commit()
        ach_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': ach_id})

    c.execute('''
        SELECT a.*, p.name as project_name, p.part_number, p.revision, p.color as project_color, p.cad_software
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        ORDER BY a.is_highlight DESC, a.date DESC, a.id DESC
    ''')
    achievements = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(achievements)

@app.route('/api/achievements/<int:ach_id>/toggle-star', methods=['POST'])
@login_required
def api_achievement_toggle_star(ach_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE achievements SET is_highlight = 1 - is_highlight WHERE id = ?', (ach_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/achievements/<int:ach_id>/delete', methods=['POST'])
@login_required
def api_achievement_delete(ach_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM achievements WHERE id = ?', (ach_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- CALCULATOR ROI & JUSTIFICARE MĂRIRE (DEZACTIVAT) -----------------
@app.route('/api/salary-calculator', methods=['GET', 'POST'])
@login_required
def api_salary_calculator():
    return jsonify({
        'status': 'disabled',
        'message': 'Modul monetar dezactivat conform configurării de inginerie mecanică.'
    })

# ----------------- AI ENGINEERING COPILOT (CHATBOT & SUGGESTIONS) -----------------
@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.json or {}
    message = data.get('message', '').strip()
    history = data.get('history', [])
    reply = handle_chat_message(message, history)
    return jsonify({'reply': reply})

@app.route('/api/ai/suggest', methods=['POST'])
@login_required
def api_ai_suggest():
    data = request.json or {}
    raw_text = data.get('raw_text', '').strip()
    activity_type = data.get('activity_type', 'Modelare CAD 3D')
    part_number = data.get('part_number', 'ASM-001')
    process = data.get('manufacturing_process', 'Tablă Sheet Metal')
    
    refined = polish_deliverable_description(raw_text, activity_type, part_number, process)
    return jsonify({'refined': refined})

# ----------------- ANALYTICS & STATISTICI INGINEREȘTI -----------------
@app.route('/api/analytics')
@login_required
def api_analytics():
    conn = get_connection()
    c = conn.cursor()

    period = request.args.get('period', 'all')
    project_id = request.args.get('project_id', 'all')

    today = date.today()
    start_date = None
    if period == '1m':
        start_date = (today - timedelta(days=30)).isoformat()
    elif period == '3m':
        start_date = (today - timedelta(days=90)).isoformat()
    elif period == '6m':
        start_date = (today - timedelta(days=180)).isoformat()
    elif period == '1y':
        start_date = (today - timedelta(days=365)).isoformat()

    where_clauses = []
    params = []
    if start_date:
        where_clauses.append("d.date >= ?")
        params.append(start_date)
    if project_id and project_id != 'all':
        where_clauses.append("d.project_id = ?")
        params.append(int(project_id))
    
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # 1. Activity Type Distribution
    c.execute(f'''
        SELECT d.activity_type, COUNT(*) as count
        FROM daily_logs d
        {where_sql}
        GROUP BY d.activity_type
        ORDER BY count DESC
    ''', params)
    activity_distribution = [dict(r) for r in c.fetchall()]

    # 2. Monthly Trend
    c.execute(f'''
        SELECT d.year, d.month, 
               COUNT(*) as total_deliverables,
               COALESCE(SUM(d.drawings_count), COUNT(*)) as total_drawings,
               COUNT(DISTINCT d.date) as active_days,
               SUM(CASE WHEN d.is_highlight = 1 THEN 1 ELSE 0 END) as highlights
        FROM daily_logs d
        {where_sql}
        GROUP BY d.year, d.month
        ORDER BY d.year ASC, d.month ASC
    ''', params)
    monthly_trends = []
    for r in c.fetchall():
        m_label = f"{MONTH_NAMES.get(r['month'], r['month'])[:3]} {r['year']}"
        monthly_trends.append({
            'year': r['year'],
            'month': r['month'],
            'label': m_label,
            'total_deliverables': r['total_deliverables'],
            'total_drawings': r['total_drawings'],
            'active_days': r['active_days'],
            'highlights': r['highlights'] or 0
        })

    # 3. Project Effort Breakdown
    c.execute('''
        SELECT p.id, p.part_number, p.revision, p.name, p.cad_software, p.color, p.status,
               COUNT(d.id) as log_count,
               COALESCE(SUM(d.drawings_count), 0) as drawings_count,
               COUNT(DISTINCT d.date) as days_spent,
               SUM(CASE WHEN d.is_highlight = 1 THEN 1 ELSE 0 END) as highlights_count
        FROM projects p
        LEFT JOIN daily_logs d ON p.id = d.project_id
        GROUP BY p.id
        ORDER BY days_spent DESC, log_count DESC
    ''')
    project_efforts = [dict(r) for r in c.fetchall()]

    # 4. Blocker breakdown
    c.execute('''
        SELECT cause_type, COUNT(*) as count, COALESCE(SUM(time_lost_days), 0) as total_impact_days
        FROM blockers
        GROUP BY cause_type
        ORDER BY total_impact_days DESC
    ''')
    blocker_breakdown = [dict(r) for r in c.fetchall()]

    # 5. Manufacturing process breakdown
    c.execute('''
        SELECT manufacturing_process, COUNT(*) as count
        FROM daily_logs
        WHERE manufacturing_process IS NOT NULL AND manufacturing_process != ''
        GROUP BY manufacturing_process
        ORDER BY count DESC
    ''')
    mfg_breakdown = [dict(r) for r in c.fetchall()]

    # 6. Overall Engineering KPIs
    c.execute(f'''
        SELECT COUNT(DISTINCT d.date) as total_active_days,
               COUNT(*) as total_deliverables,
               COALESCE(SUM(d.drawings_count), 0) as total_drawings,
               SUM(CASE WHEN d.is_highlight = 1 THEN 1 ELSE 0 END) as total_highlights
        FROM daily_logs d
        {where_sql}
    ''', params)
    kpi_raw = dict(c.fetchone() or {})

    c.execute('SELECT COUNT(*) as cnt FROM projects')
    total_projects = c.fetchone()['cnt']

    c.execute('SELECT COUNT(*) as cnt, COALESCE(SUM(time_lost_days), 0) as tot_impact FROM blockers')
    blk_stats = c.fetchone()
    total_blockers = blk_stats['cnt']
    total_blocker_days = blk_stats['tot_impact']

    conn.close()

    total_active_days = kpi_raw.get('total_active_days') or 0
    total_deliverables = kpi_raw.get('total_deliverables') or 0
    total_drawings = kpi_raw.get('total_drawings') or 0
    total_highlights = kpi_raw.get('total_highlights') or 0
    avg_per_day = round(total_deliverables / (total_active_days or 1), 1)

    score = min(100, int((total_active_days * 4) + (total_highlights * 10) + (total_deliverables * 2)))
    if score == 0 and total_deliverables > 0: score = 50

    return jsonify({
        'kpis': {
            'total_active_days': total_active_days,
            'total_deliverables': total_deliverables,
            'total_drawings': total_drawings,
            'total_highlights': total_highlights,
            'total_projects': total_projects,
            'total_blockers': total_blockers,
            'total_blocker_days': total_blocker_days,
            'avg_per_day': avg_per_day,
            'score': score
        },
        'activity_distribution': activity_distribution,
        'monthly_trends': monthly_trends,
        'project_efforts': project_efforts,
        'blocker_breakdown': blocker_breakdown,
        'mfg_breakdown': mfg_breakdown
    })

# ----------------- RAPORT DE EVALUARE & EXPORTURI -----------------
@app.route('/api/report')
@login_required
def api_report():
    conn = get_connection()
    c = conn.cursor()

    start_date = request.args.get('start_date', (date.today() - timedelta(days=90)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())

    c.execute('''
        SELECT COUNT(DISTINCT date) as active_days, 
               COUNT(*) as total_actions,
               COALESCE(SUM(drawings_count), COUNT(*)) as total_drawings,
               SUM(CASE WHEN is_highlight = 1 THEN 1 ELSE 0 END) as total_highlights
        FROM daily_logs
        WHERE date BETWEEN ? AND ?
    ''', (start_date, end_date))
    overview = dict(c.fetchone() or {})

    c.execute('''
        SELECT p.name, p.part_number, p.revision, p.client, p.cad_software, p.status, 
               COUNT(d.id) as log_count, 
               COALESCE(SUM(d.drawings_count), 0) as drawings_count,
               COUNT(DISTINCT d.date) as days_spent
        FROM projects p
        JOIN daily_logs d ON p.id = d.project_id
        WHERE d.date BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY days_spent DESC
    ''', (start_date, end_date))
    projects_breakdown = [dict(r) for r in c.fetchall()]

    c.execute('''
        SELECT a.*, p.name as project_name, p.part_number, p.revision
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        WHERE a.date BETWEEN ? AND ?
        ORDER BY a.is_highlight DESC, a.date DESC
    ''', (start_date, end_date))
    achievements = [dict(r) for r in c.fetchall()]

    c.execute('''
        SELECT b.*, p.name as project_name, p.part_number, p.revision
        FROM blockers b
        LEFT JOIN projects p ON b.project_id = p.id
        WHERE b.date BETWEEN ? AND ?
        ORDER BY b.date DESC
    ''', (start_date, end_date))
    blockers = [dict(r) for r in c.fetchall()]

    conn.close()

    return jsonify({
        'start_date': start_date,
        'end_date': end_date,
        'overview': overview,
        'projects': projects_breakdown,
        'achievements': achievements,
        'blockers': blockers
    })

# Export CSV
@app.route('/export/csv')
@login_required
def export_csv():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT d.date, d.part_number, d.revision, p.name as ansamblu, p.cad_software,
               d.activity_type, d.drawings_count, d.manufacturing_process, d.material, d.ecn_source,
               d.description, d.status_tag,
               CASE WHEN d.is_highlight = 1 THEN 'DA' ELSE 'NU' END as realizare_cheie
        FROM daily_logs d
        LEFT JOIN projects p ON d.project_id = p.id
        ORDER BY d.date DESC
    ''')
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Part Number', 'Revizie', 'Ansamblu Mecanic', 'Software CAD', 'Tip Activitate', 'Planșe 2D / Piese', 'Proces Fabricație', 'Material', 'Sursă ECN', 'Ce am Livrat / Lucrat', 'Stare', 'Realizare Cheie'])
    for r in rows:
        writer.writerow([
            r['date'], 
            r['part_number'] or '-', 
            r['revision'] or '-', 
            r['ansamblu'] or 'General', 
            r['cad_software'] or '-', 
            r['activity_type'], 
            r['drawings_count'] or 1,
            r['manufacturing_process'] or '-',
            r['material'] or '-',
            r['ecn_source'] or '-',
            r['description'], 
            r['status_tag'], 
            r['realizare_cheie']
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=WorkPulse_Jurnal_Mecanic_{date.today().isoformat()}.csv"}
    )

# Export Markdown Dossier
@app.route('/export/markdown')
@login_required
def export_markdown():
    conn = get_connection()
    c = conn.cursor()

    today_str = date.today().isoformat()
    c.execute("SELECT COUNT(DISTINCT date) as days, COUNT(*) as cnt, COALESCE(SUM(drawings_count), COUNT(*)) as tot_drawings, SUM(CASE WHEN is_highlight=1 THEN 1 ELSE 0 END) as highlights FROM daily_logs")
    stats = c.fetchone()

    c.execute('''
        SELECT p.name, p.part_number, p.revision, p.cad_software, p.status, COUNT(DISTINCT d.date) as days, COALESCE(SUM(d.drawings_count), 0) as drawings
        FROM projects p
        LEFT JOIN daily_logs d ON p.id = d.project_id
        GROUP BY p.id
        ORDER BY days DESC
    ''')
    projects = c.fetchall()

    c.execute('''
        SELECT a.*, p.name as project_name, p.part_number, p.revision
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        ORDER BY a.is_highlight DESC, a.date DESC
    ''')
    achievements = c.fetchall()

    c.execute('''
        SELECT b.*, p.name as project_name, p.part_number, p.revision
        FROM blockers b
        LEFT JOIN projects p ON b.project_id = p.id
        ORDER BY b.date DESC
    ''')
    blockers = c.fetchall()
    conn.close()

    lines = [
        f"# 📋 Dosar de Activitate Tehnică & Evaluare Salarială",
        f"**Titular:** Inginer Proiectant Mecanic",
        f"**Data Raport:** {today_str}\n",
        f"---",
        f"## 1. 📊 Indicatori Tehnici de Performanță",
        f"- **Zile Active de Proiectare:** {stats['days'] or 0} zile",
        f"- **Livrabile & Sarcini Finalizate:** {stats['cnt'] or 0}",
        f"- **Planșe 2D & Modele 3D Verificate:** {stats['tot_drawings'] or 0}",
        f"- **Realizări Tehnice Cheie ⭐:** {stats['highlights'] or 0}\n",
        f"## 2. 🚀 Ansambluri & Proiecte PDM Gestionate"
    ]

    for p in projects:
        lines.append(f"- **[{p['part_number']} {p['revision']}] {p['name']}** [CAD: {p['cad_software']}] ({p['status']}): {p['days'] or 0} zile active, {p['drawings'] or 0} planșe")

    lines.append("\n## 3. 🛡️ Scut de Apărare: Blocaje & Incidente Rezolvate Fără Vina Proiectantului")
    for b in blockers:
        lines.append(f"### ⚠️ [{b['part_number'] or 'P/N'}] {b['title']} ({b['date']}) - {b['cause_type']}")
        lines.append(f"- **Situație:** {b['description']}")
        lines.append(f"- **Soluția Inginerească:** {b['solution_applied']}")
        if b['prevented_risk']:
            lines.append(f"- **Risc / Rebut Prevenit:** {b['prevented_risk']}")
        lines.append("")

    lines.append("## 4. 🏆 Realizări Tehnice Majore & Optimizări DFM")
    for a in achievements:
        star = "⭐ [TOP ARGUMENT MĂRIRE] " if a['is_highlight'] else ""
        lines.append(f"### {star}{a['title']} ({a['date']})")
        lines.append(f"- **Ansamblu:** [{a['part_number'] or '-'}] {a['project_name'] or 'General'}")
        lines.append(f"- **Rezultat Tehnic:** {a['impact_value']}")
        if a['feedback_received']:
            lines.append(f"- **Feedback:** _{a['feedback_received']}_")
        lines.append("")

    lines.append("---\n*Generat de WorkPulse pe Termux.*")

    md_content = "\n".join(lines)
    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=Dosar_Evaluare_Mecanic_{today_str}.md"}
    )

# Save backup directly to Phone Storage
@app.route('/api/backup/save-to-storage', methods=['POST'])
@login_required
def save_to_storage():
    conn = get_connection()
    c = conn.cursor()

    c.execute('SELECT * FROM projects')
    projects = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM daily_logs')
    daily_logs = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM achievements')
    achievements = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM blockers')
    blockers = [dict(r) for r in c.fetchall()]

    conn.close()

    backup_data = {
        'version': '4.0-secure-table-mechanical',
        'created_at': datetime.now().isoformat(),
        'projects': projects,
        'daily_logs': daily_logs,
        'achievements': achievements,
        'blockers': blockers
    }

    target_dir = os.path.expanduser('~/storage/shared/Download')
    if not os.path.exists(target_dir):
        target_dir = os.path.dirname(os.path.dirname(__file__))

    filename = f"workpulse_secure_backup_{date.today().isoformat()}.json"
    full_path = os.path.join(target_dir, filename)

    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    return jsonify({
        'success': True,
        'filename': filename,
        'saved_path': full_path,
        'message': f'Salvat în telefon la: {full_path}'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
