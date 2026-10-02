import sqlite3
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'workpulse.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Projects
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            client TEXT,
            status TEXT DEFAULT 'În Lucru',
            priority TEXT DEFAULT 'Medie',
            color TEXT DEFAULT '#3b82f6',
            target_hours REAL DEFAULT 0,
            start_date TEXT,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Time entries (pontaj & activitati)
    c.execute('''
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            category TEXT DEFAULT 'Dezvoltare',
            description TEXT,
            is_overtime INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Achievements / Brag Document (pentru Evaluare & Marire)
    c.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            impact_value TEXT NOT NULL,
            category TEXT DEFAULT 'Eficiență & Valoare',
            feedback_received TEXT,
            is_highlight INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Tasks / Obiective
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'todo',
            due_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    ''')

    # Active timer state
    c.execute('''
        CREATE TABLE IF NOT EXISTS active_timer (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_running INTEGER DEFAULT 0,
            project_id INTEGER,
            category TEXT,
            description TEXT,
            is_overtime INTEGER DEFAULT 0,
            start_timestamp REAL
        )
    ''')

    # Insert default timer row if not exists
    c.execute('''
        INSERT OR IGNORE INTO active_timer (id, is_running, project_id, category, description, is_overtime, start_timestamp)
        VALUES (1, 0, NULL, 'Dezvoltare', '', 0, NULL)
    ''')

    # Populate seed data if database is empty so user sees immediate value
    c.execute('SELECT COUNT(*) as cnt FROM projects')
    if c.fetchone()['cnt'] == 0:
        seed_data(conn)

    conn.commit()
    conn.close()

def seed_data(conn):
    c = conn.cursor()
    today = date.today()
    
    # Sample Projects
    projects = [
        ('Sistem Plăți & Facturare', 'Integrare procesator nou și automatizare reconciliere financiară', 'Finanțe / Intern', 'În Lucru', 'Critic', '#ef4444', 120, (today - timedelta(days=45)).isoformat(), (today + timedelta(days=20)).isoformat()),
        ('Portal Clienți B2B v2', 'Redesign interfață și îmbunătățire timp de încărcare', 'Departament Vânzări', 'În Lucru', 'Ridicată', '#3b82f6', 160, (today - timedelta(days=60)).isoformat(), (today + timedelta(days=15)).isoformat()),
        ('Migrare Bază de Date Cloud', 'Optimizare indexare, securitate și backup automat', 'IT & DevOps', 'Finalizat', 'Ridicată', '#10b981', 80, (today - timedelta(days=90)).isoformat(), (today - timedelta(days=10)).isoformat()),
        ('Automatizare Rapoarte & Notificări', 'Microserviciu generare PDF și alerte email/webhook', 'Operațiuni', 'În Lucru', 'Medie', '#f59e0b', 50, (today - timedelta(days=20)).isoformat(), (today + timedelta(days=30)).isoformat())
    ]
    
    c.executemany('''
        INSERT INTO projects (name, description, client, status, priority, color, target_hours, start_date, deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', projects)

    # Sample Achievements (Brag Sheet for salary raise)
    achievements = [
        (1, (today - timedelta(days=12)).isoformat(), 'Optimizare Reconciliere Tranzacții', 'Timpul de procesare redus de la 4 ore la 15 minute (93% mai rapid), eliminând 100% din erorile de calcul manual.', 'Eficiență & Automatizare', 'Manager Financiar: "O realizare excepțională, ne-a salvat zeci de ore lunar!"', 1),
        (3, (today - timedelta(days=15)).isoformat(), 'Rezolvare Incident Critic Producție P1', 'Identificat bottleneck în sub 25 de minute în afara orelor de program, restabilit sistemul fără pierderi financiare.', 'Rezolvare Crize & Incidente', 'CTO a transmis felicitări pe canalul general de Slack.', 1),
        (2, (today - timedelta(days=25)).isoformat(), 'Creștere Performanță Încărcare Portal', 'LCP (Largest Contentful Paint) îmbunătățit de la 4.2s la 1.1s. Conversia comenzilor a crescut cu 18%.', 'Valoare Financiară & UX', 'Directorul de vânzări a confirmat feedback pozitiv de la clienți cheie.', 1),
        (4, (today - timedelta(days=5)).isoformat(), 'Mentorat și Onboarding 2 Colegi Noi', 'Creat documentație de arhitectură de la zero; noii colegi au livrat primele modificări în producție în prima săptămână.', 'Leadership & Mentorat', 'Echipa este mult mai autonomă și eficientă.', 1)
    ]

    c.executemany('''
        INSERT INTO achievements (project_id, date, title, impact_value, category, feedback_received, is_highlight)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', achievements)

    # Sample Tasks
    tasks = [
        (1, 'Finalizare teste unitare modul webhook-uri', 'done', (today - timedelta(days=2)).isoformat()),
        (1, 'Implementare retry automat la eșec tranzacții', 'in_progress', (today + timedelta(days=3)).isoformat()),
        (2, 'Adăugare filtru dinamic după dată în rapoarte', 'todo', (today + timedelta(days=5)).isoformat()),
        (3, 'Configurare alertă automată spațiu disc', 'done', (today - timedelta(days=12)).isoformat()),
        (4, 'Creare template PDF pentru facturi recurente', 'in_progress', (today + timedelta(days=7)).isoformat())
    ]

    c.executemany('''
        INSERT INTO tasks (project_id, title, status, due_date)
        VALUES (?, ?, ?, ?)
    ''', tasks)

    # Sample Time Entries for the last 14 days
    time_samples = [
        (1, (today - timedelta(days=1)).isoformat(), 240, 'Dezvoltare / Cod', 'Scriere logică procesare plăți asincrone', 0),
        (1, (today - timedelta(days=1)).isoformat(), 90, 'Overtime', 'Fixare bug urgență identificat la testare', 1),
        (2, (today - timedelta(days=2)).isoformat(), 300, 'Dezvoltare / Cod', 'Integrare componente dashboard B2B', 0),
        (2, (today - timedelta(days=2)).isoformat(), 60, 'Meeting / Ședință', 'Sincronizare cu echipa de design și PO', 0),
        (4, (today - timedelta(days=3)).isoformat(), 210, 'Arhitectură & Design', 'Definire flux microserviciu generare rapoarte', 0),
        (1, (today - timedelta(days=4)).isoformat(), 270, 'Dezvoltare / Cod', 'Implementare validare webhook-uri cu HMAC', 0),
        (3, (today - timedelta(days=5)).isoformat(), 180, 'Mentenanță / Bugfix', 'Optimizare query-uri lente și indexare baze de date', 0),
        (2, (today - timedelta(days=6)).isoformat(), 360, 'Dezvoltare / Cod', 'Refactorizare tabele și stări comenzi', 0),
        (1, (today - timedelta(days=7)).isoformat(), 120, 'Overtime', 'Deploy intermediar și monitorizare logs pe staging', 1),
        (4, (today - timedelta(days=8)).isoformat(), 240, 'Documentație', 'Redactat ghid tehnic și specificații API', 0),
        (2, (today - timedelta(days=9)).isoformat(), 300, 'Dezvoltare / Cod', 'Construit filtre avansate și sortări tabele', 0),
        (1, (today - timedelta(days=10)).isoformat(), 180, 'Meeting / Ședință', 'Sprint review și planificare arhitectură Q4', 0)
    ]

    c.executemany('''
        INSERT INTO time_entries (project_id, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', time_samples)
