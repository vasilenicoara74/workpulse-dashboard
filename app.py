import os
import json
import csv
import io
import time
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, Response, send_file
from database import init_db, get_connection

app = Flask(__name__)

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sw.js')
def service_worker():
    return send_file(os.path.join(app.static_folder, 'sw.js'), mimetype='application/javascript')

# ----------------- API STATS (WAR ROOM CAD) -----------------
@app.route('/api/stats')
def api_stats():
    conn = get_connection()
    c = conn.cursor()

    c.execute('SELECT SUM(duration_minutes) as total_min, SUM(CASE WHEN is_overtime = 1 THEN duration_minutes ELSE 0 END) as overtime_min FROM time_entries')
    time_row = c.fetchone()
    total_minutes = time_row['total_min'] or 0
    overtime_minutes = time_row['overtime_min'] or 0

    c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'În Lucru' THEN 1 ELSE 0 END) as active, SUM(CASE WHEN status = 'Finalizat' THEN 1 ELSE 0 END) as completed FROM projects")
    proj_row = c.fetchone()

    c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_highlight = 1 THEN 1 ELSE 0 END) as highlights, COALESCE(SUM(money_saved_est), 0) as total_money_saved FROM achievements")
    ach_row = c.fetchone()

    c.execute("SELECT COUNT(*) as total, COALESCE(SUM(time_lost_hours), 0) as hours_saved FROM blockers")
    blockers_row = c.fetchone()

    # Hours by project
    c.execute('''
        SELECT p.name, p.part_number, p.revision, p.color, p.cad_software, ROUND(SUM(t.duration_minutes) / 60.0, 1) as hours
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        HAVING hours > 0
        ORDER BY hours DESC
    ''')
    project_hours = [{'name': r['name'], 'pn': r['part_number'], 'rev': r['revision'], 'color': r['color'], 'cad': r['cad_software'], 'hours': r['hours']} for r in c.fetchall()]

    # Hours by category
    c.execute('''
        SELECT category, ROUND(SUM(duration_minutes) / 60.0, 1) as hours
        FROM time_entries
        GROUP BY category
        ORDER BY hours DESC
    ''')
    category_hours = [{'category': r['category'], 'hours': r['hours']} for r in c.fetchall()]

    # Last 14 days activity trend
    today = date.today()
    days_labels = []
    days_regular = []
    days_overtime = []

    for i in range(13, -1, -1):
        day_date = (today - timedelta(days=i)).isoformat()
        days_labels.append(day_date[5:])
        c.execute('''
            SELECT 
                ROUND(SUM(CASE WHEN is_overtime = 0 THEN duration_minutes ELSE 0 END) / 60.0, 1) as reg,
                ROUND(SUM(CASE WHEN is_overtime = 1 THEN duration_minutes ELSE 0 END) / 60.0, 1) as ovt
            FROM time_entries
            WHERE date = ?
        ''', (day_date,))
        row = c.fetchone()
        days_regular.append(row['reg'] or 0)
        days_overtime.append(row['ovt'] or 0)

    # Top achievements for review showcase
    c.execute('''
        SELECT a.*, p.name as project_name, p.part_number, p.revision
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        WHERE a.is_highlight = 1
        ORDER BY a.date DESC
        LIMIT 5
    ''')
    top_achievements = [dict(r) for r in c.fetchall()]

    # Top blockers resolved (Scut)
    c.execute('''
        SELECT b.*, p.name as project_name, p.part_number, p.revision
        FROM blockers b
        LEFT JOIN projects p ON b.project_id = p.id
        ORDER BY b.date DESC
        LIMIT 4
    ''')
    recent_blockers = [dict(r) for r in c.fetchall()]

    conn.close()

    return jsonify({
        'total_hours': round(total_minutes / 60.0, 1),
        'overtime_hours': round(overtime_minutes / 60.0, 1),
        'active_projects': proj_row['active'] or 0,
        'completed_projects': proj_row['completed'] or 0,
        'total_projects': proj_row['total'] or 0,
        'total_achievements': ach_row['total'] or 0,
        'highlight_achievements': ach_row['highlights'] or 0,
        'total_money_saved': round(ach_row['total_money_saved'], 0),
        'total_blockers': blockers_row['total'] or 0,
        'blocker_hours_managed': round(blockers_row['hours_saved'] or 0, 1),
        'project_hours': project_hours,
        'category_hours': category_hours,
        'timeline': {
            'labels': days_labels,
            'regular': days_regular,
            'overtime': days_overtime
        },
        'top_achievements': top_achievements,
        'recent_blockers': recent_blockers
    })

# ----------------- PROIECTE & ANSAMBLURI PDM -----------------
@app.route('/api/projects', methods=['GET', 'POST'])
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
            INSERT INTO projects (part_number, revision, name, description, client, cad_software, status, priority, color, target_hours, start_date, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            float(data.get('target_hours', 0) or 0),
            data.get('start_date', date.today().isoformat()),
            data.get('deadline', '')
        ))
        conn.commit()
        project_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': project_id})

    c.execute('''
        SELECT p.*,
               COALESCE(ROUND(SUM(t.duration_minutes) / 60.0, 1), 0) as logged_hours,
               (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status = 'done') as done_tasks,
               (SELECT COUNT(*) FROM achievements WHERE project_id = p.id) as total_achievements,
               (SELECT COUNT(*) FROM blockers WHERE project_id = p.id) as total_blockers
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY CASE p.status WHEN 'În Lucru' THEN 1 WHEN 'Planificat' THEN 2 WHEN 'Finalizat' THEN 3 ELSE 4 END, p.id DESC
    ''')
    projects = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(projects)

# ----------------- 1-TAP QUICK LOGGING (ERGONOMIE PE TELEFON) -----------------
@app.route('/api/time-entries/quick', methods=['POST'])
def api_quick_log():
    conn = get_connection()
    c = conn.cursor()
    data = request.json or {}

    project_id = data.get('project_id')
    if not project_id:
        c.execute('SELECT id, part_number, revision FROM projects WHERE status = "În Lucru" ORDER BY id DESC LIMIT 1')
        first = c.fetchone()
        if first:
            project_id = first['id']
            part_number = first['part_number']
            revision = first['revision']
        else:
            project_id = None
            part_number = 'ASM-001'
            revision = 'Rev A'
    else:
        c.execute('SELECT part_number, revision FROM projects WHERE id = ?', (project_id,))
        p = c.fetchone()
        part_number = p['part_number'] if p else 'ASM-001'
        revision = p['revision'] if p else 'Rev A'

    minutes = int(data.get('duration_minutes', 60))
    category = data.get('category', 'Modelare CAD 3D')
    is_overtime = 1 if data.get('is_overtime') else 0
    desc = data.get('description') or f"Sesiune rapidă: {category}"

    c.execute('''
        INSERT INTO time_entries (project_id, part_number, revision, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (project_id, part_number, revision, date.today().isoformat(), minutes, category, desc, is_overtime))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'minutes': minutes, 'category': category})

# ----------------- PONTAJ COMPLET -----------------
@app.route('/api/time-entries', methods=['GET', 'POST'])
def api_time_entries():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
            part_number = 'GEN-01'
            revision = 'Rev A'
        else:
            project_id = int(project_id)
            c.execute('SELECT part_number, revision FROM projects WHERE id = ?', (project_id,))
            p = c.fetchone()
            part_number = p['part_number'] if p else 'ASM-001'
            revision = p['revision'] if p else 'Rev A'

        entry_date = data.get('date') or date.today().isoformat()
        duration_minutes = int(data.get('duration_minutes', 0))
        if duration_minutes <= 0:
            conn.close()
            return jsonify({'error': 'Durata trebuie să fie mai mare de 0 minute'}), 400

        c.execute('''
            INSERT INTO time_entries (project_id, part_number, revision, date, duration_minutes, category, description, is_overtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            part_number,
            revision,
            entry_date,
            duration_minutes,
            data.get('category', 'Modelare CAD 3D'),
            data.get('description', ''),
            1 if data.get('is_overtime') else 0
        ))
        conn.commit()
        entry_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': entry_id})

    # GET with filters
    limit = int(request.args.get('limit', 60))
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    project_id = request.args.get('project_id', '').strip()

    query = '''
        SELECT t.*, p.name as project_name, p.color as project_color, p.cad_software
        FROM time_entries t
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE 1=1
    '''
    params = []
    if search:
        query += " AND (t.description LIKE ? OR p.name LIKE ? OR t.part_number LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if category:
        query += " AND t.category = ?"
        params.append(category)
    if project_id:
        query += " AND t.project_id = ?"
        params.append(int(project_id))

    query += " ORDER BY t.date DESC, t.id DESC LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    entries = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(entries)

@app.route('/api/time-entries/<int:entry_id>/delete', methods=['POST'])
def api_time_entry_delete(entry_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM time_entries WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- CRONOMETRU LIVE -----------------
@app.route('/api/timer')
def api_timer():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM active_timer WHERE id = 1')
    timer_row = dict(c.fetchone())
    conn.close()

    elapsed = 0
    if timer_row['is_running'] and timer_row['start_timestamp']:
        elapsed = int(time.time() - timer_row['start_timestamp'])

    timer_row['elapsed_seconds'] = elapsed
    return jsonify(timer_row)

@app.route('/api/timer/start', methods=['POST'])
def api_timer_start():
    conn = get_connection()
    c = conn.cursor()
    data = request.json or {}

    project_id = data.get('project_id')
    if project_id in ('', 'null', None):
        project_id = None
    else:
        project_id = int(project_id)

    c.execute('''
        UPDATE active_timer
        SET is_running = 1,
            project_id = ?,
            category = ?,
            description = ?,
            is_overtime = ?,
            start_timestamp = ?
        WHERE id = 1
    ''', (
        project_id,
        data.get('category', 'Modelare CAD 3D'),
        data.get('description', ''),
        1 if data.get('is_overtime') else 0,
        time.time()
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/timer/stop', methods=['POST'])
def api_timer_stop():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM active_timer WHERE id = 1')
    t = c.fetchone()

    if not t['is_running'] or not t['start_timestamp']:
        conn.close()
        return jsonify({'error': 'Niciun timer activ'}), 400

    elapsed_seconds = int(time.time() - t['start_timestamp'])
    duration_minutes = max(1, round(elapsed_seconds / 60))

    part_number = 'ASM-001'
    revision = 'Rev A'
    if t['project_id']:
        c.execute('SELECT part_number, revision FROM projects WHERE id = ?', (t['project_id'],))
        row = c.fetchone()
        if row:
            part_number = row['part_number']
            revision = row['revision']

    c.execute('''
        INSERT INTO time_entries (project_id, part_number, revision, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        t['project_id'],
        part_number,
        revision,
        date.today().isoformat(),
        duration_minutes,
        t['category'] or 'Modelare CAD 3D',
        t['description'] or 'Sesiune activă înregistrată automat via Live Timer',
        t['is_overtime']
    ))

    c.execute('''
        UPDATE active_timer
        SET is_running = 0, start_timestamp = NULL, description = ''
        WHERE id = 1
    ''')

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'duration_minutes': duration_minutes})

# ----------------- REALIZĂRI & ECONOMII MONETARE (BRAG SHEET) -----------------
@app.route('/api/achievements', methods=['GET', 'POST'])
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
def api_achievement_toggle_star(ach_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE achievements SET is_highlight = 1 - is_highlight WHERE id = ?', (ach_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/achievements/<int:ach_id>/delete', methods=['POST'])
def api_achievement_delete(ach_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM achievements WHERE id = ?', (ach_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- SCUT & BLOCAJE TEHNICE -----------------
@app.route('/api/blockers', methods=['GET', 'POST'])
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
            INSERT INTO blockers (project_id, date, title, cause_type, description, solution_applied, time_lost_hours, prevented_risk)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            data.get('date') or date.today().isoformat(),
            title,
            data.get('cause_type', 'Modificare Cerințe Client'),
            description,
            solution,
            float(data.get('time_lost_hours', 0) or 0),
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
def api_blocker_delete(blocker_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM blockers WHERE id = ?', (blocker_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- KANBAN ETAPE PROIECTARE CAD -----------------
@app.route('/api/tasks', methods=['GET', 'POST'])
def api_tasks():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        title = data.get('title', '').strip()
        if not title:
            conn.close()
            return jsonify({'error': 'Titlul sarcinii este obligatoriu'}), 400

        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)

        c.execute('''
            INSERT INTO tasks (project_id, title, stage, status, due_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            project_id,
            title,
            data.get('stage', 'Modelare 3D'),
            data.get('status', 'todo'),
            data.get('due_date', '')
        ))
        conn.commit()
        task_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': task_id})

    c.execute('''
        SELECT t.*, p.name as project_name, p.part_number, p.revision, p.color as project_color
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY CASE t.stage 
            WHEN 'Concept 3D' THEN 1 
            WHEN 'Modelare 3D' THEN 2 
            WHEN 'Simulare FEA' THEN 3 
            WHEN 'Desene 2D & BOM' THEN 4 
            WHEN 'Lansat Atelier' THEN 5 
            WHEN 'Prototip Validat' THEN 6 
            ELSE 7 END, t.id DESC
    ''')
    tasks = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route('/api/tasks/<int:task_id>/move-stage', methods=['POST'])
def api_task_move_stage(task_id):
    conn = get_connection()
    c = conn.cursor()
    data = request.json or {}
    new_stage = data.get('stage', 'Modelare 3D')
    is_done = 1 if new_stage == 'Prototip Validat' else 0

    c.execute('UPDATE tasks SET stage = ?, status = ? WHERE id = ?', (
        new_stage,
        'done' if is_done else 'in_progress',
        task_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'stage': new_stage})

@app.route('/api/tasks/<int:task_id>/delete', methods=['POST'])
def api_task_delete(task_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- CALCULATOR ROI & JUSTIFICARE MĂRIRE -----------------
@app.route('/api/salary-calculator', methods=['GET', 'POST'])
def api_salary_calculator():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        c.execute('''
            UPDATE salary_settings
            SET current_net_salary = ?, target_raise_pct = ?, currency = ?
            WHERE id = 1
        ''', (
            float(data.get('current_net_salary', 6500)),
            float(data.get('target_raise_pct', 20)),
            data.get('currency', 'RON')
        ))
        conn.commit()

    c.execute('SELECT * FROM salary_settings WHERE id = 1')
    settings = dict(c.fetchone())

    c.execute('SELECT COALESCE(SUM(duration_minutes), 0) / 60.0 as overtime_hours FROM time_entries WHERE is_overtime = 1')
    overtime_hours = round(c.fetchone()['overtime_hours'], 1)

    c.execute('SELECT COALESCE(SUM(money_saved_est), 0) as total_savings FROM achievements')
    total_savings = round(c.fetchone()['total_savings'], 0)

    hourly_net = round(settings['current_net_salary'] / 168.0, 2)
    overtime_hourly_rate = round(hourly_net * 1.75, 2)
    overtime_total_value = round(overtime_hours * overtime_hourly_rate, 2)

    requested_raise_monthly = round(settings['current_net_salary'] * (settings['target_raise_pct'] / 100.0), 2)
    requested_raise_yearly = round(requested_raise_monthly * 12, 2)
    new_target_salary = round(settings['current_net_salary'] + requested_raise_monthly, 2)

    # Undeniable ROI ratio
    roi_multiple = round(total_savings / (requested_raise_yearly or 1), 1)

    conn.close()

    return jsonify({
        'current_net_salary': settings['current_net_salary'],
        'target_raise_pct': settings['target_raise_pct'],
        'currency': settings['currency'],
        'hourly_net': hourly_net,
        'overtime_hours': overtime_hours,
        'overtime_hourly_rate': overtime_hourly_rate,
        'overtime_total_value': overtime_total_value,
        'requested_raise_monthly': requested_raise_monthly,
        'requested_raise_yearly': requested_raise_yearly,
        'new_target_salary': new_target_salary,
        'total_savings': total_savings,
        'roi_multiple': roi_multiple
    })

# ----------------- DOSAR DE EVALUARE & EXPORTURI -----------------
@app.route('/api/report')
def api_report():
    conn = get_connection()
    c = conn.cursor()

    start_date = request.args.get('start_date', (date.today() - timedelta(days=90)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())

    c.execute('''
        SELECT 
            ROUND(SUM(duration_minutes) / 60.0, 1) as total_hours,
            ROUND(SUM(CASE WHEN is_overtime = 1 THEN duration_minutes ELSE 0 END) / 60.0, 1) as overtime_hours,
            COUNT(DISTINCT date) as days_worked
        FROM time_entries
        WHERE date BETWEEN ? AND ?
    ''', (start_date, end_date))
    overview = dict(c.fetchone() or {})

    c.execute('''
        SELECT p.name, p.part_number, p.revision, p.client, p.cad_software, p.status, ROUND(SUM(t.duration_minutes) / 60.0, 1) as hours
        FROM projects p
        JOIN time_entries t ON p.id = t.project_id
        WHERE t.date BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY hours DESC
    ''', (start_date, end_date))
    projects_breakdown = [dict(r) for r in c.fetchall()]

    c.execute('''
        SELECT a.*, p.name as project_name, p.part_number, p.revision, p.cad_software
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

    # Sum savings
    c.execute('SELECT COALESCE(SUM(money_saved_est), 0) as period_savings FROM achievements WHERE date BETWEEN ? AND ?', (start_date, end_date))
    period_savings = c.fetchone()['period_savings']

    conn.close()

    return jsonify({
        'start_date': start_date,
        'end_date': end_date,
        'overview': overview,
        'period_savings': period_savings,
        'projects': projects_breakdown,
        'achievements': achievements,
        'blockers': blockers
    })

# Export to CSV
@app.route('/export/csv')
def export_csv():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT t.date, p.part_number, p.revision, p.name as ansamblu, p.cad_software, t.duration_minutes, ROUND(t.duration_minutes/60.0, 2) as ore,
               t.category as etapa_inginerie, t.description as descriere,
               CASE WHEN t.is_overtime = 1 THEN 'DA' ELSE 'NU' END as ore_suplimentare
        FROM time_entries t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY t.date DESC
    ''')
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Part Number', 'Revizie', 'Ansamblu Mecanic', 'Software CAD', 'Minute', 'Ore', 'Etapa Inginerie', 'Descriere Reper', 'Overtime'])
    for r in rows:
        writer.writerow([r['date'], r['part_number'] or '-', r['revision'] or '-', r['ansamblu'] or 'General', r['cad_software'] or '-', r['duration_minutes'], r['ore'], r['etapa_inginerie'], r['descriere'], r['ore_suplimentare']])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=WorkPulse_Inginerie_{date.today().isoformat()}.csv"}
    )

# Export Full Dossier in Markdown
@app.route('/export/markdown')
def export_markdown():
    conn = get_connection()
    c = conn.cursor()

    today_str = date.today().isoformat()
    c.execute("SELECT ROUND(SUM(duration_minutes)/60.0, 1) as tot, ROUND(SUM(CASE WHEN is_overtime=1 THEN duration_minutes ELSE 0 END)/60.0, 1) as ovt FROM time_entries")
    stats = c.fetchone()

    c.execute("SELECT COALESCE(SUM(money_saved_est), 0) as tot_sav FROM achievements")
    tot_sav = c.fetchone()['tot_sav']

    c.execute('''
        SELECT p.name, p.part_number, p.revision, p.cad_software, p.status, ROUND(SUM(t.duration_minutes)/60.0, 1) as hours
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY hours DESC
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
        f"# 📋 Dosar de Performanță Tehnică & Justificare Mărire Salarială (v3.0)",
        f"**Titular:** Inginer Proiectant Mecanic",
        f"**Data Generării:** {today_str}\n",
        f"---",
        f"## 1. 📊 Indicatori Executivi de Volum & Implicare",
        f"- **Total Ore Dedicate Proiectării & Asistenței Tehnice:** {stats['tot'] or 0} ore",
        f"- **Ore Suplimentare (Overtime Asumat):** {stats['ovt'] or 0} ore",
        f"- **Economii Directe Generate (Rebuturi Evitate & Optimizări):** {tot_sav:,.0f} RON",
        f"- **Ansambluri & Proiecte Gestionate:** {len(projects)}\n",
        f"## 2. 🚀 Repartizare Efort pe Ansambluri & Revizii CAD"
    ]

    for p in projects:
        lines.append(f"- **[{p['part_number']} {p['revision']}] {p['name']}** [CAD: {p['cad_software']}] ({p['status']}): {p['hours'] or 0} ore")

    lines.append("\n## 3. 🛡️ Scut de Apărare: Blocaje & Incidente Rezolvate Fără Vina Proiectantului")
    lines.append("*Dovezi clare pentru situații neprevăzute cauzate de clienți, furnizori sau atelier pe care le-am gestionat și deblocat:*\n")

    for b in blockers:
        lines.append(f"### ⚠️ [{b['part_number'] or 'General'}] {b['title']} ({b['date']}) - Tip: {b['cause_type']}")
        lines.append(f"- **Cauză Externă:** {b['description']}")
        lines.append(f"- **Intervenția Inginerească:** {b['solution_applied']}")
        lines.append(f"- **Timp Pierdut Gestionat:** {b['time_lost_hours']} ore")
        if b['prevented_risk']:
            lines.append(f"- **Risc / Cost Prevenit:** {b['prevented_risk']}")
        lines.append("")

    lines.append("## 4. 🏆 Realizări de Impact: Economii de Costuri, Materiale & Rebuturi Evitate")
    lines.append("*Valoare cuantificabilă demonstrată prin cifre și economii:*\n")

    for a in achievements:
        star = "⭐ [TOP ARGUMENT MĂRIRE] " if a['is_highlight'] else ""
        sav = f" [Economie: {a['money_saved_est']:,.0f} RON]" if a['money_saved_est'] > 0 else ""
        lines.append(f"### {star}{a['title']} ({a['date']}){sav}")
        lines.append(f"- **Ansamblu:** [{a['part_number'] or '-'}] {a['project_name'] or 'General'}")
        lines.append(f"- **Categorie:** {a['category']}")
        lines.append(f"- **Rezultat Măsurabil:** {a['impact_value']}")
        if a['feedback_received']:
            lines.append(f"- **Feedback / Aprecieri:** _{a['feedback_received']}_")
        lines.append("")

    lines.append("## 5. 💡 Concluzii Matematice pentru Negocierea Măririi Salariale")
    lines.append("1. **ROI Garantat:** Economiile de material și piesele salvate de la rebut depășesc cu mult costul anual al măririi solicitate.")
    lines.append("2. **Protecția Termenelor de Livrare:** Blocajele cauzate de clienți și furnizori au fost soluționate în medie sub 24h.")
    lines.append("3. **Disponibilitate:** Orele de overtime au asigurat lansarea la timp a reperelor pe mașinile cu comandă numerică și asamblarea prototipului.")
    lines.append("\n---\n*Generat de WorkPulse pe Termux.*")

    md_content = "\n".join(lines)
    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=Dosar_Evaluare_Inginer_Mecanic_{today_str}.md"}
    )

# Save backup directly to Phone Storage
@app.route('/api/backup/save-to-storage', methods=['POST'])
def save_to_storage():
    conn = get_connection()
    c = conn.cursor()

    c.execute('SELECT * FROM projects')
    projects = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM time_entries')
    time_entries = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM achievements')
    achievements = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM blockers')
    blockers = [dict(r) for r in c.fetchall()]

    c.execute('SELECT * FROM tasks')
    tasks = [dict(r) for r in c.fetchall()]

    conn.close()

    backup_data = {
        'version': '3.0-war-room-mechanical',
        'created_at': datetime.now().isoformat(),
        'projects': projects,
        'time_entries': time_entries,
        'achievements': achievements,
        'blockers': blockers,
        'tasks': tasks
    }

    target_dir = os.path.expanduser('~/storage/shared/Download')
    if not os.path.exists(target_dir):
        target_dir = os.path.dirname(os.path.dirname(__file__))

    filename = f"workpulse_war_room_backup_{date.today().isoformat()}.json"
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
