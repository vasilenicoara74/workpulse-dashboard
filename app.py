import os
import json
import csv
import io
import time
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, Response, send_file
from database import init_db, get_connection

app = Flask(__name__)

# Initialize database on startup
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sw.js')
def service_worker():
    return send_file(os.path.join(app.static_folder, 'sw.js'), mimetype='application/javascript')

# ----------------- API STATS -----------------
@app.route('/api/stats')
def api_stats():
    conn = get_connection()
    c = conn.cursor()

    # Total minutes and overtime
    c.execute('SELECT SUM(duration_minutes) as total_min, SUM(CASE WHEN is_overtime = 1 THEN duration_minutes ELSE 0 END) as overtime_min FROM time_entries')
    time_row = c.fetchone()
    total_minutes = time_row['total_min'] or 0
    overtime_minutes = time_row['overtime_min'] or 0

    # Project counts
    c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'În Lucru' THEN 1 ELSE 0 END) as active, SUM(CASE WHEN status = 'Finalizat' THEN 1 ELSE 0 END) as completed FROM projects")
    proj_row = c.fetchone()

    # Achievements count
    c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_highlight = 1 THEN 1 ELSE 0 END) as highlights FROM achievements")
    ach_row = c.fetchone()

    # Hours by project
    c.execute('''
        SELECT p.name, p.color, ROUND(SUM(t.duration_minutes) / 60.0, 1) as hours
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        HAVING hours > 0
        ORDER BY hours DESC
    ''')
    project_hours = [{'name': r['name'], 'color': r['color'], 'hours': r['hours']} for r in c.fetchall()]

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
        days_labels.append(day_date[5:]) # MM-DD
        
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
        SELECT a.*, p.name as project_name
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        WHERE a.is_highlight = 1
        ORDER BY a.date DESC
        LIMIT 5
    ''')
    top_achievements = [dict(r) for r in c.fetchall()]

    conn.close()

    return jsonify({
        'total_hours': round(total_minutes / 60.0, 1),
        'overtime_hours': round(overtime_minutes / 60.0, 1),
        'active_projects': proj_row['active'] or 0,
        'completed_projects': proj_row['completed'] or 0,
        'total_projects': proj_row['total'] or 0,
        'total_achievements': ach_row['total'] or 0,
        'highlight_achievements': ach_row['highlights'] or 0,
        'project_hours': project_hours,
        'category_hours': category_hours,
        'timeline': {
            'labels': days_labels,
            'regular': days_regular,
            'overtime': days_overtime
        },
        'top_achievements': top_achievements
    })

# ----------------- PROJECTS -----------------
@app.route('/api/projects', methods=['GET', 'POST'])
def api_projects():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name', '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'Numele proiectului este obligatoriu'}), 400

        c.execute('''
            INSERT INTO projects (name, description, client, status, priority, color, target_hours, start_date, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name,
            data.get('description', ''),
            data.get('client', ''),
            data.get('status', 'În Lucru'),
            data.get('priority', 'Medie'),
            data.get('color', '#3b82f6'),
            float(data.get('target_hours', 0) or 0),
            data.get('start_date', date.today().isoformat()),
            data.get('deadline', '')
        ))
        conn.commit()
        project_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': project_id})

    # GET
    c.execute('''
        SELECT p.*,
               COALESCE(ROUND(SUM(t.duration_minutes) / 60.0, 1), 0) as logged_hours,
               (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status = 'done') as done_tasks,
               (SELECT COUNT(*) FROM achievements WHERE project_id = p.id) as total_achievements
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY CASE p.status WHEN 'În Lucru' THEN 1 WHEN 'Planificat' THEN 2 WHEN 'Finalizat' THEN 3 ELSE 4 END, p.id DESC
    ''')
    projects = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(projects)

@app.route('/api/projects/<int:project_id>', methods=['PUT', 'POST'])
def api_project_update(project_id):
    conn = get_connection()
    c = conn.cursor()
    data = request.json or {}

    c.execute('''
        UPDATE projects
        SET name = ?, description = ?, client = ?, status = ?, priority = ?, color = ?, target_hours = ?, start_date = ?, deadline = ?
        WHERE id = ?
    ''', (
        data.get('name'),
        data.get('description'),
        data.get('client'),
        data.get('status'),
        data.get('priority'),
        data.get('color'),
        float(data.get('target_hours', 0) or 0),
        data.get('start_date'),
        data.get('deadline'),
        project_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/projects/<int:project_id>/delete', methods=['POST'])
def api_project_delete(project_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- TIME TRACKING -----------------
@app.route('/api/time-entries', methods=['GET', 'POST'])
def api_time_entries():
    conn = get_connection()
    c = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)

        entry_date = data.get('date') or date.today().isoformat()
        duration_minutes = int(data.get('duration_minutes', 0))
        if duration_minutes <= 0:
            conn.close()
            return jsonify({'error': 'Durata trebuie să fie mai mare de 0 minute'}), 400

        c.execute('''
            INSERT INTO time_entries (project_id, date, duration_minutes, category, description, is_overtime)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            entry_date,
            duration_minutes,
            data.get('category', 'Dezvoltare'),
            data.get('description', ''),
            1 if data.get('is_overtime') else 0
        ))
        conn.commit()
        entry_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': entry_id})

    # GET
    limit = int(request.args.get('limit', 50))
    c.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color
        FROM time_entries t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY t.date DESC, t.id DESC
        LIMIT ?
    ''', (limit,))
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

# ----------------- TIMER STATE -----------------
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
        data.get('category', 'Dezvoltare'),
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

    # Save to time_entries
    c.execute('''
        INSERT INTO time_entries (project_id, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        t['project_id'],
        date.today().isoformat(),
        duration_minutes,
        t['category'] or 'Dezvoltare',
        t['description'] or 'Activitate înregistrată via Live Timer',
        t['is_overtime']
    ))

    # Reset timer
    c.execute('''
        UPDATE active_timer
        SET is_running = 0, start_timestamp = NULL, description = ''
        WHERE id = 1
    ''')

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'duration_minutes': duration_minutes})

# ----------------- ACHIEVEMENTS & BRAG DOCUMENT (FOR APPRAISAL) -----------------
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
            return jsonify({'error': 'Titlul și Valoarea / Impactul sunt obligatorii!'}), 400

        project_id = data.get('project_id')
        if project_id in ('', 'null', None):
            project_id = None
        else:
            project_id = int(project_id)

        c.execute('''
            INSERT INTO achievements (project_id, date, title, impact_value, category, feedback_received, is_highlight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            data.get('date') or date.today().isoformat(),
            title,
            impact,
            data.get('category', 'Eficiență & Valoare'),
            data.get('feedback_received', ''),
            1 if data.get('is_highlight') else 0
        ))
        conn.commit()
        ach_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': ach_id})

    # GET
    c.execute('''
        SELECT a.*, p.name as project_name, p.color as project_color
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

# ----------------- TASKS -----------------
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
            INSERT INTO tasks (project_id, title, status, due_date)
            VALUES (?, ?, ?, ?)
        ''', (
            project_id,
            title,
            data.get('status', 'todo'),
            data.get('due_date', '')
        ))
        conn.commit()
        task_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': task_id})

    c.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY CASE t.status WHEN 'todo' THEN 1 WHEN 'in_progress' THEN 2 ELSE 3 END, t.id DESC
    ''')
    tasks = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
def api_task_toggle(task_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    row = c.fetchone()
    if row:
        new_status = 'done' if row['status'] != 'done' else 'todo'
        c.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:task_id>/delete', methods=['POST'])
def api_task_delete(task_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ----------------- APPRAISAL DOSSIER & EXPORTS -----------------
@app.route('/api/report')
def api_report():
    conn = get_connection()
    c = conn.cursor()

    start_date = request.args.get('start_date', (date.today() - timedelta(days=90)).isoformat())
    end_date = request.args.get('end_date', date.today().isoformat())

    # Total hours in period
    c.execute('''
        SELECT 
            ROUND(SUM(duration_minutes) / 60.0, 1) as total_hours,
            ROUND(SUM(CASE WHEN is_overtime = 1 THEN duration_minutes ELSE 0 END) / 60.0, 1) as overtime_hours,
            COUNT(DISTINCT date) as days_worked
        FROM time_entries
        WHERE date BETWEEN ? AND ?
    ''', (start_date, end_date))
    overview = dict(c.fetchone() or {})

    # Hours by project in period
    c.execute('''
        SELECT p.name, p.client, p.status, ROUND(SUM(t.duration_minutes) / 60.0, 1) as hours
        FROM projects p
        JOIN time_entries t ON p.id = t.project_id
        WHERE t.date BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY hours DESC
    ''', (start_date, end_date))
    projects_breakdown = [dict(r) for r in c.fetchall()]

    # Achievements in period
    c.execute('''
        SELECT a.*, p.name as project_name
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        WHERE a.date BETWEEN ? AND ?
        ORDER BY a.is_highlight DESC, a.date DESC
    ''', (start_date, end_date))
    achievements = [dict(r) for r in c.fetchall()]

    conn.close()

    return jsonify({
        'start_date': start_date,
        'end_date': end_date,
        'overview': overview,
        'projects': projects_breakdown,
        'achievements': achievements
    })

# Export to CSV
@app.route('/export/csv')
def export_csv():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT t.date, p.name as proiect, t.duration_minutes, ROUND(t.duration_minutes/60.0, 2) as ore,
               t.category as categorie, t.description as descriere,
               CASE WHEN t.is_overtime = 1 THEN 'DA' ELSE 'NU' END as ore_suplimentare
        FROM time_entries t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY t.date DESC
    ''')
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Proiect', 'Minute', 'Ore', 'Categorie', 'Descriere', 'Ore Suplimentare'])
    for r in rows:
        writer.writerow([r['date'], r['proiect'] or 'Nespecificat', r['duration_minutes'], r['ore'], r['categorie'], r['descriere'], r['ore_suplimentare']])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=WorkPulse_Pontaj_{date.today().isoformat()}.csv"}
    )

# Export Full Performance Dossier in Markdown
@app.route('/export/markdown')
def export_markdown():
    conn = get_connection()
    c = conn.cursor()

    today_str = date.today().isoformat()
    c.execute("SELECT ROUND(SUM(duration_minutes)/60.0, 1) as tot, ROUND(SUM(CASE WHEN is_overtime=1 THEN duration_minutes ELSE 0 END)/60.0, 1) as ovt FROM time_entries")
    stats = c.fetchone()

    c.execute('''
        SELECT p.name, p.status, ROUND(SUM(t.duration_minutes)/60.0, 1) as hours
        FROM projects p
        LEFT JOIN time_entries t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY hours DESC
    ''')
    projects = c.fetchall()

    c.execute('''
        SELECT a.*, p.name as project_name
        FROM achievements a
        LEFT JOIN projects p ON a.project_id = p.id
        ORDER BY a.is_highlight DESC, a.date DESC
    ''')
    achievements = c.fetchall()
    conn.close()

    lines = [
        f"# 📋 Dosar de Performanță & Argumentare Mărire Salarială",
        f"**Generat automat:** {today_str}",
        f"**Aplicație:** WorkPulse Career Dashboard\n",
        f"---",
        f"## 1. 📊 Indicatori Cheie de Volum & Implicare",
        f"- **Total Ore Lucrate Înregistrate:** {stats['tot'] or 0} ore",
        f"- **Ore Suplimentare (Overtime):** {stats['ovt'] or 0} ore",
        f"- **Proiecte Implicate:** {len(projects)}\n",
        f"## 2. 🚀 Distribuție Efort pe Proiecte"
    ]

    for p in projects:
        lines.append(f"- **{p['name']}** ({p['status']}): {p['hours'] or 0} ore")

    lines.append("\n## 3. 🏆 Realizări de Impact & Valoare Adusă Companiei")
    lines.append("*Notă: Aceste puncte demonstrează ROI-ul (Return on Investment) și valoarea cuantificabilă adusă echipei.*\n")

    for a in achievements:
        star = "⭐ [TOP ARGUMENT MĂRIRE] " if a['is_highlight'] else ""
        lines.append(f"### {star}{a['title']} ({a['date']})")
        lines.append(f"- **Proiect:** {a['project_name'] or 'General / Echipă'}")
        lines.append(f"- **Categorie:** {a['category']}")
        lines.append(f"- **Rezultat Cuantificabil & Impact:** {a['impact_value']}")
        if a['feedback_received']:
            lines.append(f"- **Feedback / Aprecieri:** _{a['feedback_received']}_")
        lines.append("")

    lines.append("## 4. 💡 Argumente Cheie pentru Negocierea Măririi Salariale")
    lines.append("1. **Rezultate Măsurabile:** Toate proiectele au fost livrate cu impact direct asupra vitezei și calității.")
    lines.append("2. **Disponibilitate și Loialitate:** Orele suplimentare înregistrate demonstrează intervenții rapide în momente critice.")
    lines.append("3. **Autonomie și Mentorat:** Am redus blocajele din echipă și am accelerat integrarea noilor colegi.")
    lines.append("\n---\n*Generat de WorkPulse pe Termux.*")

    md_content = "\n".join(lines)
    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=Dosar_Evaluare_Marire_{today_str}.md"}
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

    c.execute('SELECT * FROM tasks')
    tasks = [dict(r) for r in c.fetchall()]

    conn.close()

    backup_data = {
        'version': 1.0,
        'created_at': datetime.now().isoformat(),
        'projects': projects,
        'time_entries': time_entries,
        'achievements': achievements,
        'tasks': tasks
    }

    # Target directory on phone
    target_dir = os.path.expanduser('~/storage/shared/Download')
    if not os.path.exists(target_dir):
        # Fallback to local downloads
        target_dir = os.path.dirname(os.path.dirname(__file__))

    filename = f"workpulse_backup_{date.today().isoformat()}.json"
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
    # Listen on all interfaces so user can open from any browser on phone (localhost:5000)
    print("Starting WorkPulse Dashboard on http://127.0.0.1:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=False)
