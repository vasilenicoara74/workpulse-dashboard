import sqlite3
import os
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(__file__))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'workpulse.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reseed=False):
    conn = get_connection()
    c = conn.cursor()

    if force_reseed:
        c.execute('DROP TABLE IF EXISTS daily_logs')
        c.execute('DROP TABLE IF EXISTS blockers')
        c.execute('DROP TABLE IF EXISTS tasks')
        c.execute('DROP TABLE IF EXISTS achievements')
        c.execute('DROP TABLE IF EXISTS time_entries')
        c.execute('DROP TABLE IF EXISTS projects')
        c.execute('DROP TABLE IF EXISTS salary_settings')
        c.execute('DROP TABLE IF EXISTS users')

    # Users & Cybersecurity (Admin account)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')

    # Daily Activity Logs (Jurnal Lejer pe Zile, Luni, Ani, Proiecte)
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            part_number TEXT DEFAULT 'ASM-001',
            revision TEXT DEFAULT 'Rev A',
            date TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            activity_type TEXT DEFAULT 'Modelare CAD 3D',
            description TEXT NOT NULL,
            status_tag TEXT DEFAULT 'Finalizat',
            is_highlight INTEGER DEFAULT 0,
            drawings_count INTEGER DEFAULT 1,
            manufacturing_process TEXT DEFAULT 'Tablă Sheet Metal',
            material TEXT DEFAULT 'Oțel',
            ecn_source TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Migration check for existing tables
    c.execute("PRAGMA table_info(daily_logs)")
    cols = [r['name'] for r in c.fetchall()]
    if 'drawings_count' not in cols:
        c.execute("ALTER TABLE daily_logs ADD COLUMN drawings_count INTEGER DEFAULT 1")
    if 'manufacturing_process' not in cols:
        c.execute("ALTER TABLE daily_logs ADD COLUMN manufacturing_process TEXT DEFAULT 'Tablă Sheet Metal'")
    if 'material' not in cols:
        c.execute("ALTER TABLE daily_logs ADD COLUMN material TEXT DEFAULT 'Oțel'")
    if 'ecn_source' not in cols:
        c.execute("ALTER TABLE daily_logs ADD COLUMN ecn_source TEXT DEFAULT ''")

    # Projects / Assemblies
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number TEXT DEFAULT 'ASM-001',
            revision TEXT DEFAULT 'Rev A',
            name TEXT NOT NULL,
            description TEXT,
            client TEXT,
            cad_software TEXT DEFAULT 'SolidWorks',
            status TEXT DEFAULT 'În Lucru',
            priority TEXT DEFAULT 'Medie',
            color TEXT DEFAULT '#2563eb',
            start_date TEXT,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Blockers (Scut de Apărare)
    c.execute('''
        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            cause_type TEXT DEFAULT 'Modificare Cerințe Client',
            description TEXT NOT NULL,
            solution_applied TEXT NOT NULL,
            time_lost_days REAL DEFAULT 1,
            prevented_risk TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Achievements (Brag Sheet pentru Mărire)
    c.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            impact_value TEXT NOT NULL,
            money_saved_est REAL DEFAULT 0,
            category TEXT DEFAULT 'Optimizare Proiectare & Cost',
            feedback_received TEXT,
            is_highlight INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Salary Settings & ROI
    c.execute('''
        CREATE TABLE IF NOT EXISTS salary_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_net_salary REAL DEFAULT 6500,
            target_raise_pct REAL DEFAULT 20,
            currency TEXT DEFAULT 'RON'
        )
    ''')

    # Default Admin User (username: admin, default password: admin)
    c.execute('SELECT COUNT(*) as cnt FROM users WHERE username = "admin"')
    if c.fetchone()['cnt'] == 0:
        c.execute('''
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        ''', ('admin', generate_password_hash('admin'), 'admin'))

    c.execute('''
        INSERT OR IGNORE INTO salary_settings (id, current_net_salary, target_raise_pct, currency)
        VALUES (1, 6500, 20, 'RON')
    ''')

    # Seed data only on explicit forced reseed
    if force_reseed:
        seed_data(conn)

    conn.commit()
    conn.close()

def seed_data(conn):
    c = conn.cursor()
    c.execute('DELETE FROM daily_logs')
    c.execute('DELETE FROM blockers')
    c.execute('DELETE FROM achievements')
    c.execute('DELETE FROM projects')

    today = date.today()

    # Projects
    projects = [
        ('ASM-100', 'Rev B', 'Sistem Transportor Robotic Modular', 'Bandă cu role conice, ghidaje reglabile și cadru aluminiu', 'Linie Automatizare Auto', 'SolidWorks', 'În Lucru', 'Critic', '#ef4444', (today - timedelta(days=50)).isoformat(), (today + timedelta(days=20)).isoformat()),
        ('ASM-204', 'Rev A', 'Șasiu & Carcase Sheet Metal Dispozitiv Testare', 'Ansamblu tablă îndoită laser, toleranțe îndoire și elemente PEM', 'Client Industrial', 'Autodesk Inventor', 'În Lucru', 'Ridicată', '#2563eb', (today - timedelta(days=40)).isoformat(), (today + timedelta(days=25)).isoformat()),
        ('TOOL-05', 'Rev C', 'Dispozitiv Modular Fixare Prelucrare CNC', 'Jig & fixture pentru frezare piese turnate Al cu prindere rapidă', 'Atelier Prelucrări Mecanice', 'SolidWorks', 'Finalizat', 'Ridicată', '#10b981', (today - timedelta(days=65)).isoformat(), (today - timedelta(days=5)).isoformat()),
        ('GEAR-02', 'Rev A', 'Redesign Reductor & Ax Transmisie Putere', 'Calcul cinematic angrenaje cilindrice, selecție rulmenți și cotare toleranțe', 'Sector Energetic', 'SolidWorks', 'În Lucru', 'Medie', '#f59e0b', (today - timedelta(days=25)).isoformat(), (today + timedelta(days=30)).isoformat())
    ]

    c.executemany('''
        INSERT INTO projects (part_number, revision, name, description, client, cad_software, status, priority, color, start_date, deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', projects)

    # Daily Logs (Jurnalul Lejer pe Zile & Luni)
    logs = [
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=1)).isoformat(), today.year, today.month, 'Modelare CAD 3D', 'Finalizat modelarea ansamblului ghidaje laterale și suporți senzori optici', 'Finalizat', 0),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=2)).isoformat(), today.year, today.month, 'Verificare 3D', 'Rulat detecție de coliziune; identificat interferență braț-motoreductor și corectat modelul', 'Realizare Cheie ⭐', 1),
        (2, 'ASM-204', 'Rev A', (today - timedelta(days=3)).isoformat(), today.year, today.month, 'Desene 2D & BOM', 'Generat desenele de execuție pentru carcasele de tablă, cotare toleranțe și export fișiere DXF debitare', 'Finalizat', 0),
        (4, 'GEAR-02', 'Rev A', (today - timedelta(days=4)).isoformat(), today.year, today.month, 'Calcule & Cotare', 'Calculat rapoarte de transmitere, dimensionat arbore principal și stabilit lanțul de toleranțe ISO', 'Finalizat', 0),
        (3, 'TOOL-05', 'Rev C', (today - timedelta(days=6)).isoformat(), today.year, today.month, 'Asistență Atelier', 'Coborât în atelier pentru proba pe mașina CNC; probat prinderea piesei brute și validat prima piesă', 'Finalizat', 1),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=7)).isoformat(), today.year, today.month, 'Modificare ECN', 'Adaptat cotele flanșei motorului conform noii specificații transmise de client', 'Modificare Client', 0),
        (2, 'ASM-204', 'Rev A', (today - timedelta(days=9)).isoformat(), today.year, today.month, 'Modelare CAD 3D', 'Proiectat sistemul de balamale interioare și prinderi rapide pentru panourile de vizitare', 'În curs', 0),
        (3, 'TOOL-05', 'Rev C', (today - timedelta(days=12)).isoformat(), today.year, today.month, 'Standardizare BOM', 'Standardizat șuruburile și plăcuțele de uzură din dispozitiv (reducere de la 18 repere la 5 repere)', 'Realizare Cheie ⭐', 1),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=15)).isoformat(), today.year, today.month, 'Documentație', 'Întocmit caietul tehnic și fișa de montaj pentru linia de asamblare a transportorului', 'Finalizat', 0),
        # Luna trecuta (Septembrie)
        (3, 'TOOL-05', 'Rev B', (today - timedelta(days=22)).isoformat(), today.year, (today - timedelta(days=22)).month, 'Concept CAD', 'Definit conceptul cinematic de prindere rapidă pneumatică cu pârghie', 'Finalizat', 0),
        (2, 'ASM-204', 'Rev A', (today - timedelta(days=26)).isoformat(), today.year, (today - timedelta(days=26)).month, 'Calcule Tablă', 'Calculat factorii K de îndoire pentru tabla de 2.0 mm oțel pe prisma R=4', 'Finalizat', 0),
        (1, 'ASM-100', 'Rev A', (today - timedelta(days=32)).isoformat(), today.year, (today - timedelta(days=32)).month, 'Ședință Tehnică', 'Clarificat cerințele funcționale și viteza de transport cu echipa de automatizări', 'Finalizat', 0)
    ]

    c.executemany('''
        INSERT INTO daily_logs (project_id, part_number, revision, date, year, month, activity_type, description, status_tag, is_highlight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', logs)

    # Achievements
    achievements = [
        (1, (today - timedelta(days=2)).isoformat(), 'Detecție & Eliminare Coliziuni 3D Înainte de Fabricație', 'Identificat interferență critică braț oscilant - motoreductor înainte de debitare laser. Prevenit rebutarea a 4 subansamble.', 18000.0, 'Eliminare Rebuturi & Calitate', 'Seful de producție: "Ne-ai salvat de la 2 săptămâni de întârziere în atelier!"', 1),
        (3, (today - timedelta(days=6)).isoformat(), 'Proiectare Dispozitiv Prindere Rapidă CNC', 'Redus timpul de montare și centrare a piesei brute de la 14 min la 3 min per ciclu (creștere productivitate atelier cu 300%).', 12500.0, 'Optimizare Producție & Timp', 'Maistrul atelierului a cerut standardizarea pe toate frezele CNC.', 1),
        (4, (today - timedelta(days=4)).isoformat(), 'Optimizare Masă & Geometrie Ax Transmisie', 'Redus masa arborelui cu 18% prin reproiectare trepte și degajări optime. Economie oțel aliat și inerție redusă.', 6400.0, 'Optimizare Proiectare & Cost', 'Validat de inginerul șef fără obiecții.', 1),
        (3, (today - timedelta(days=12)).isoformat(), 'Standardizare Organe de Asamblare & BOM', 'Redus diversitatea de șuruburi și șaibe din ansamblul Sheet Metal de la 26 dimensiuni la 6 tipuri standardizate ISO.', 4200.0, 'Standardizare & Achiziții', 'Responsabil achiziții: "A scăzut considerabil stocul mort."', 1)
    ]

    c.executemany('''
        INSERT INTO achievements (project_id, date, title, impact_value, money_saved_est, category, feedback_received, is_highlight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', achievements)

    # Blockers (Scut de Apărare)
    blockers = [
        (1, (today - timedelta(days=7)).isoformat(), 'Modificare Specificații Motor de către Client', 'Modificare Cerințe Client', 'Clientul a schimbat furnizorul de motoare în fază finală (flanșă B14 în loc de B5 și ax diferit).', 'Am reproiectat suportul și cuplajul elastic în 24h, actualizat desenele 2D fără decalarea montajului general.', 2.0, 'Prevenit întârzierea livrării utilajului către client.' ),
        (2, (today - timedelta(days=18)).isoformat(), 'Lipsă Model 3D Senzor de la Furnizor', 'Întârziere Furnizor', 'Furnizorul nu a trimis fișierele CAD STEP ale senzorilor la data convenită.', 'Am generat model preliminar din fișa PDF cu găuri oblongi de reglaj pe carcasă, permițând lansarea debitării tablei.', 1.0, 'Atelierul a debitat tabla fără pauze de producție.' ),
        (3, (today - timedelta(days=28)).isoformat(), 'Rază Îndoire Neconformă în Atelier', 'Limitare Tehnologică Atelier', 'Abkant-ul nu avea prisma R=2 montată, fiind disponibilă doar R=4.', 'Am recalculat toleranțele de îndoire (K-Factor) pentru R=4 și am refăcut desenele 2D în aceeași zi.', 1.0, 'Evitat oprirea liniei de fabricație.' )
    ]

    c.executemany('''
        INSERT INTO blockers (project_id, date, title, cause_type, description, solution_applied, time_lost_days, prevented_risk)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', blockers)
