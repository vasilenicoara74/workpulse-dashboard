import sqlite3
import os
from datetime import datetime, date, timedelta

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
        c.execute('DROP TABLE IF EXISTS blockers')
        c.execute('DROP TABLE IF EXISTS tasks')
        c.execute('DROP TABLE IF EXISTS achievements')
        c.execute('DROP TABLE IF EXISTS time_entries')
        c.execute('DROP TABLE IF EXISTS projects')
        c.execute('DROP TABLE IF EXISTS salary_settings')

    # Projects / Assemblies (Inginerie Mecanică & PDM)
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
            target_hours REAL DEFAULT 0,
            start_date TEXT,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Time entries (Pontaj pe etape de proiectare inginerească)
    c.execute('''
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            part_number TEXT,
            revision TEXT DEFAULT 'Rev A',
            date TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            category TEXT DEFAULT 'Modelare CAD 3D',
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
            money_saved_est REAL DEFAULT 0,
            category TEXT DEFAULT 'Optimizare Proiectare & Cost',
            feedback_received TEXT,
            is_highlight INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Blockers & Incidents (Scut de apărare la evaluare în caz de probleme/întârzieri)
    c.execute('''
        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            cause_type TEXT DEFAULT 'Modificare Cerințe Client',
            description TEXT NOT NULL,
            solution_applied TEXT NOT NULL,
            time_lost_hours REAL DEFAULT 0,
            prevented_risk TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Tasks / Kanban CAD Etape
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            stage TEXT DEFAULT 'Modelare 3D',
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

    # Salary & ROI settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS salary_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_net_salary REAL DEFAULT 6500,
            target_raise_pct REAL DEFAULT 20,
            currency TEXT DEFAULT 'RON'
        )
    ''')

    c.execute('''
        INSERT OR IGNORE INTO active_timer (id, is_running, project_id, category, description, is_overtime, start_timestamp)
        VALUES (1, 0, NULL, 'Modelare CAD 3D', '', 0, NULL)
    ''')

    c.execute('''
        INSERT OR IGNORE INTO salary_settings (id, current_net_salary, target_raise_pct, currency)
        VALUES (1, 6500, 20, 'RON')
    ''')

    # Seed data if empty
    c.execute('SELECT COUNT(*) as cnt FROM projects')
    if c.fetchone()['cnt'] == 0:
        seed_mechanical_data(conn)

    conn.commit()
    conn.close()

def seed_mechanical_data(conn):
    c = conn.cursor()
    c.execute('DELETE FROM time_entries')
    c.execute('DELETE FROM achievements')
    c.execute('DELETE FROM blockers')
    c.execute('DELETE FROM tasks')
    c.execute('DELETE FROM projects')
    
    today = date.today()

    # Mechanical Engineering Projects
    projects = [
        ('ASM-100', 'Rev B', 'Sistem Transportor Robotic Modular', 'Proiectare mecanică completă bandă cu role conice, ghidaje reglabile și cadru profile Al', 'Linie Automatizare Auto', 'SolidWorks', 'În Lucru', 'Critic', '#ef4444', 140, (today - timedelta(days=45)).isoformat(), (today + timedelta(days=15)).isoformat()),
        ('ASM-204', 'Rev A', 'Șasiu & Carcase Sheet Metal Dispozitiv Testare', 'Proiectare ansamblu tablă îndoită, toleranțe decupare laser, optimizare linii îndoire și elemente PEM', 'Client Industrial', 'Autodesk Inventor', 'În Lucru', 'Ridicată', '#2563eb', 95, (today - timedelta(days=35)).isoformat(), (today + timedelta(days=20)).isoformat()),
        ('TOOL-05', 'Rev C', 'Dispozitiv Modular Fixare Prelucrare CNC', 'Jig & fixture pentru frezare piese turnate Al cu prindere rapidă pneumatică și opritori reglabili', 'Atelier Prelucrări Mecanice', 'SolidWorks', 'Finalizat', 'Ridicată', '#10b981', 65, (today - timedelta(days=60)).isoformat(), (today - timedelta(days=5)).isoformat()),
        ('GEAR-02', 'Rev A', 'Redesign Reductor & Ax Transmisie Putere', 'Calcul angrenaje cilindrice dințate, rulmenți, verificări FEA la torsiune și oboseală, fișe tratamente termice', 'Sector Energetic', 'SolidWorks / FEA', 'În Lucru', 'Medie', '#f59e0b', 80, (today - timedelta(days=20)).isoformat(), (today + timedelta(days=25)).isoformat())
    ]

    c.executemany('''
        INSERT INTO projects (part_number, revision, name, description, client, cad_software, status, priority, color, target_hours, start_date, deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', projects)

    # Achievements / Brag Sheet
    achievements = [
        (1, (today - timedelta(days=10)).isoformat(), 'Detecție & Eliminare Coliziuni Cinematice 3D', 'Identificat interferență critică braț oscilant - motoreductor înainte de debitare laser. Prevenit rebutarea a 4 subansamble.', 18000.0, 'Eliminare Rebuturi & Calitate', 'Seful de producție: "Ne-ai salvat de 2 săptămâni de întârziere în atelier!"', 1),
        (3, (today - timedelta(days=18)).isoformat(), 'Proiectare Dispozitiv Prindere Rapidă CNC', 'Redus timpul de montare și centrare a piesei brute de la 14 min la 3 min per ciclu (creștere productivitate atelier cu 300%).', 12500.0, 'Optimizare Producție & Timp', 'Maistrul atelierului a cerut standardizarea pe toate frezele CNC.', 1),
        (4, (today - timedelta(days=7)).isoformat(), 'Optimizare Topologică & Calcul FEA Ax Transmisie', 'Redus masa arborelui cu 18% menținând factorul de siguranță peste 2.4. Economie oțel aliat și inerție redusă.', 6400.0, 'Calcul Tehnic & FEA', 'Validat de inginerul șef fără obiecții.', 1),
        (2, (today - timedelta(days=14)).isoformat(), 'Standardizare Organe de Asamblare & BOM', 'Redus diversitatea de șuruburi și șaibe din ansamblul Sheet Metal de la 26 dimensiuni la 6 tipuri standardizate ISO.', 4200.0, 'Standardizare & Achiziții', 'Responsabil achiziții: "A scăzut considerabil stocul mort."', 1)
    ]

    c.executemany('''
        INSERT INTO achievements (project_id, date, title, impact_value, money_saved_est, category, feedback_received, is_highlight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', achievements)

    # Scut de Apărare & Blocaje
    blockers = [
        (1, (today - timedelta(days=12)).isoformat(), 'Modificare Specificații Motor de către Client', 'Modificare Cerințe Client', 'Clientul a schimbat furnizorul de motoare în fază finală (flanșă B14 în loc de B5 și ax diferit).', 'Am reproiectat suportul și cuplajul elastic în 24h, actualizat desenele 2D fără decalarea montajului general.', 16.0, 'Prevenit întârzierea livrării utilajului către client.' ),
        (2, (today - timedelta(days=22)).isoformat(), 'Lipsă Model 3D Senzor de la Furnizor', 'Întârziere Furnizor', 'Furnizorul nu a trimis fișierele CAD STEP ale senzorilor la data convenită.', 'Am generat model preliminar din fișa PDF cu găuri oblongi de reglaj pe carcasă, permițând lansarea debitării tablei.', 8.0, 'Atelierul a debitat tabla fără pauze de producție.' ),
        (3, (today - timedelta(days=30)).isoformat(), 'Rază Îndoire Neconformă în Atelier', 'Limitare Tehnologică Atelier', 'Abkant-ul nu avea prisma R=2 montată, fiind disponibilă doar R=4.', 'Am recalculat toleranțele de îndoire (K-Factor) pentru R=4 și am refăcut desenele 2D în aceeași zi.', 6.0, 'Evitat oprirea liniei de fabricație.' )
    ]

    c.executemany('''
        INSERT INTO blockers (project_id, date, title, cause_type, description, solution_applied, time_lost_hours, prevented_risk)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', blockers)

    # Tasks / Kanban
    tasks = [
        (1, 'Modelare 3D ansamblu role conice și rulmenți', 'Concept 3D', 'done', (today - timedelta(days=5)).isoformat()),
        (1, 'Verificare interferențe cinematice ansamblu general', 'Modelare 3D', 'done', (today - timedelta(days=3)).isoformat()),
        (1, 'Generare desene de execuție 2D cu toleranțe H7/g6', 'Desene 2D & BOM', 'in_progress', (today + timedelta(days=3)).isoformat()),
        (1, 'Extragere BOM complet (listă repere și piese standard)', 'Lansat Atelier', 'todo', (today + timedelta(days=6)).isoformat()),
        (2, 'Verificare deschideri tablă (sheet metal flat pattern)', 'Desene 2D & BOM', 'done', (today - timedelta(days=2)).isoformat()),
        (4, 'Rulare simulare FEA de eforturi von Mises pe flanșă', 'Simulare FEA', 'in_progress', (today + timedelta(days=5)).isoformat()),
        (3, 'Asistență montaj prototip pe linia de asamblare', 'Prototip Validat', 'done', (today - timedelta(days=6)).isoformat())
    ]

    c.executemany('''
        INSERT INTO tasks (project_id, title, stage, status, due_date)
        VALUES (?, ?, ?, ?, ?)
    ''', tasks)

    # Time entries
    time_samples = [
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=1)).isoformat(), 270, 'Modelare CAD 3D', 'Modelare ansamblu ghidaje laterale și suporți senzori', 0),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=1)).isoformat(), 90, 'Ore Suplimentare', 'Corectat interferențe 3D urgente semnalate din atelier', 1),
        (2, 'ASM-204', 'Rev A', (today - timedelta(days=2)).isoformat(), 300, 'Desene de Execuție 2D & BOM', 'Generat vederi, secțiuni și cote de execuție cu rugozități Ra 3.2', 0),
        (4, 'GEAR-02', 'Rev A', (today - timedelta(days=3)).isoformat(), 240, 'Calcule & Simulări FEA', 'Condiții de frontieră, cuplu torsiune și generare mesh tetraedric', 0),
        (3, 'TOOL-05', 'Rev C', (today - timedelta(days=4)).isoformat(), 180, 'Asistență Tehnică Atelier', 'Verificare prima piesă etalon pe mașina CMM de măsurat', 0),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=5)).isoformat(), 240, 'Modelare CAD 3D', 'Configurații alternative pentru reglare pe lățime bandă', 0),
        (2, 'ASM-204', 'Rev A', (today - timedelta(days=6)).isoformat(), 150, 'Modificări Proiectare (ECN)', 'Actualizat desene tablă în urma schimbării grosimii 2.0 -> 2.5 mm', 0),
        (1, 'ASM-100', 'Rev B', (today - timedelta(days=7)).isoformat(), 120, 'Ore Suplimentare', 'Finalizat BOM urgent pt. lansare comenzi rulmenți la furnizor', 1)
    ]

    c.executemany('''
        INSERT INTO time_entries (project_id, part_number, revision, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', time_samples)
