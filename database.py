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

    # Projects (Inginerie Mecanică)
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            client TEXT,
            cad_software TEXT DEFAULT 'SolidWorks',
            status TEXT DEFAULT 'În Lucru',
            priority TEXT DEFAULT 'Medie',
            color TEXT DEFAULT '#3b82f6',
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
            date TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            category TEXT DEFAULT 'Modelare CAD 3D',
            description TEXT,
            is_overtime INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
    ''')

    # Achievements / Brag Document (pentru Evaluare & Marire Inginer Mecanic)
    c.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            impact_value TEXT NOT NULL,
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

    # Tasks / Etape Inginerie (CAD, 2D, BOM, Atelier)
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            stage TEXT DEFAULT 'Concept 3D',
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

    # Populate seed data tailored for Mechanical Engineering if empty or forced
    c.execute('SELECT COUNT(*) as cnt FROM projects')
    first_proj = c.fetchone()
    if first_proj['cnt'] == 0 or force_reseed:
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
        ('Sistem Transportor Robotic Modular', 'Proiectare mecanică completă bandă cu role conice, ghidaje reglabile și cadru de susținere din profile Al', 'Linie Automatizare Auto', 'SolidWorks', 'În Lucru', 'Critic', '#ef4444', 140, (today - timedelta(days=45)).isoformat(), (today + timedelta(days=15)).isoformat()),
        ('Șasiu & Carcase Sheet Metal Dispozitiv Testare', 'Proiectare ansamblu tablă îndoită, toleranțe de decupare laser, optimizare linii de îndoire și elemente PEM', 'Client Industrial', 'Inventor', 'În Lucru', 'Ridicată', '#3b82f6', 95, (today - timedelta(days=35)).isoformat(), (today + timedelta(days=20)).isoformat()),
        ('Dispozitiv Modular Fixare Prelucrare CNC', 'Jig & fixture pentru frezare piese turnate din aluminiu cu prindere rapidă pneumatică', 'Atelier Prelucrări Mecanice', 'SolidWorks', 'Finalizat', 'Ridicată', '#10b981', 65, (today - timedelta(days=60)).isoformat(), (today - timedelta(days=5)).isoformat()),
        ('Redesign Reductor & Ax Transmisie Putere', 'Calcul angrenaje cilindrice dințate, rulmenți, verificări FEA la torsiune și oboseală, fișe tratamente termice', 'Sector Energetic', 'SolidWorks / FEA', 'În Lucru', 'Medie', '#f59e0b', 80, (today - timedelta(days=20)).isoformat(), (today + timedelta(days=25)).isoformat())
    ]

    c.executemany('''
        INSERT INTO projects (name, description, client, cad_software, status, priority, color, target_hours, start_date, deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', projects)

    # Achievements / Brag Sheet (Strict Inginerie Mecanică)
    achievements = [
        (1, (today - timedelta(days=10)).isoformat(), 'Detecție & Eliminare Coliziuni Cinematice în 3D', 'Identificat interferență critică între brațul oscilant și motoreductor înainte de trimiterea la debitare laser. Am evitat rebutarea a 4 subansamble în valoare estimată de peste 18.000 RON.', 'Eliminare Rebuturi & Calitate', 'Seful de producție: "Dacă ajungea în atelier așa, pierdeam 2 săptămâni de montaj. Excelentă verificare!"', 1),
        (3, (today - timedelta(days=18)).isoformat(), 'Proiectare Dispozitiv Prindere Rapidă CNC', 'Redus timpul de montare și centrare a piesei brute de la 14 minute la sub 3 minute per ciclu (creștere productivitate atelier cu 300%).', 'Optimizare Producție & Timp', 'Maistrul atelierului mecanic a solicitat standardizarea soluției pentru toate frezele.', 1),
        (4, (today - timedelta(days=7)).isoformat(), 'Optimizare Topologică & Calcul Rezistență FEA Ax', 'Redus masa arborelui cu 18% menținând factorul de siguranță peste 2.4. Economie directă de material și inerție redusă la pornire.', 'Calcul Tehnic & FEA', 'Inginerul șef a validat raportul FEA fără obiecții.', 1),
        (2, (today - timedelta(days=14)).isoformat(), 'Standardizare Organe de Asamblare & BOM', 'Redus diversitatea de șuruburi și șaibe din ansamblul Sheet Metal de la 26 de dimensiuni diferite la doar 6 tipuri standardizate ISO.', 'Standardizare & Achiziții', 'Responsabilul de achiziții: "A redus considerabil costul și stocurile blocate."', 1)
    ]

    c.executemany('''
        INSERT INTO achievements (project_id, date, title, impact_value, category, feedback_received, is_highlight)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', achievements)

    # Scut de Apărare & Blocaje (Dovezi în caz de probleme / reproșuri la evaluare)
    blockers = [
        (1, (today - timedelta(days=12)).isoformat(), 'Modificare Specificații Motor de către Client', 'Modificare Cerințe Client', 'Clientul a schimbat furnizorul de motoreductoare în stadiu avansat al proiectului (flanșă și ax de cuplare diferite).', 'Am reproiectat suportul mecanic și cuplajul elastic în 24 de ore, ajustând cotele fără a decala termenul final de asamblare.', 16.0, 'Prevenit întârzierea livrării utilajului către client.', ),
        (2, (today - timedelta(days=22)).isoformat(), 'Lipsă Mostră & Cotare Senzor de la Furnizor', 'Întârziere Furnizor', 'Furnizorul nu a trimis modelul CAD 3D al senzorilor optici la data promisă.', 'Am modelat componentele provizoriu pe baza fișei tehnice PDF și am prevăzut găuri oblongi de reglaj pentru a evita blocarea producției de carcase.', 8.0, 'Atelierul de debitare a putut lansa tabla la timp.', ),
        (3, (today - timedelta(days=30)).isoformat(), 'Rază de Îndoire Neconformă în Atelier', 'Limitare Tehnologică Atelier', 'Abkant-ul din fabrică nu deținea prisma cu raza R=2 cerută inițial.', 'Am recalculat toleranțele de îndoire (K-Factor) pentru prisma R=4 disponibilă și am refăcut desenele 2D în aceeași zi.', 6.0, 'Evitat oprirea liniei de fabricație.' )
    ]

    c.executemany('''
        INSERT INTO blockers (project_id, date, title, cause_type, description, solution_applied, time_lost_hours, prevented_risk)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', blockers)

    # Mechanical Engineering Tasks
    tasks = [
        (1, 'Modelare 3D ansamblu role conice și rulmenți', 'Concept & Modelare 3D', 'done', (today - timedelta(days=5)).isoformat()),
        (1, 'Generare desene de execuție 2D cu toleranțe H7/g6', 'Desene 2D & Cotație', 'in_progress', (today + timedelta(days=3)).isoformat()),
        (1, 'Extragere BOM complet (listă de repere și componente standard)', 'BOM & Achiziții', 'todo', (today + timedelta(days=6)).isoformat()),
        (2, 'Verificare deschideri tablă (sheet metal unfolding / flat pattern)', 'Desene 2D & Cotație', 'done', (today - timedelta(days=2)).isoformat()),
        (4, 'Rulare simulare FEA de eforturi von Mises pe flanșă', 'Simulare & FEA', 'in_progress', (today + timedelta(days=5)).isoformat())
    ]

    c.executemany('''
        INSERT INTO tasks (project_id, title, stage, status, due_date)
        VALUES (?, ?, ?, ?, ?)
    ''', tasks)

    # Realistic Time entries for Mechanical Engineering
    time_samples = [
        (1, (today - timedelta(days=1)).isoformat(), 270, 'Modelare CAD 3D', 'Modelare ansamblu ghidaje laterale și suporți senzori prezență', 0),
        (1, (today - timedelta(days=1)).isoformat(), 90, 'Ore Suplimentare', 'Corectat interferențe 3D urgente semnalate de maistru', 1),
        (2, (today - timedelta(days=2)).isoformat(), 300, 'Desene de Execuție 2D & BOM', 'Generat vederi, secțiuni și cote de execuție cu rugozități Ra 3.2', 0),
        (4, (today - timedelta(days=3)).isoformat(), 240, 'Calcule & Simulări FEA', 'Aplicat condiții de frontieră și forțe torsiune, generat mesh fin', 0),
        (3, (today - timedelta(days=4)).isoformat(), 180, 'Asistență Tehnică Atelier', 'Verificat prima piesă etalon pe mașina de măsurat în coordonate CMM', 0),
        (1, (today - timedelta(days=5)).isoformat(), 240, 'Modelare CAD 3D', 'Generare configurații alternative pentru reglaj pe lățime bandă', 0),
        (2, (today - timedelta(days=6)).isoformat(), 150, 'Modificări Proiectare (ECN)', 'Actualizat desene tablă ca urmare a modificării grosimii de la 2 la 2.5 mm', 0),
        (1, (today - timedelta(days=7)).isoformat(), 120, 'Ore Suplimentare', 'Finalizat BOM urgent pentru plasarea comenzilor de rulmenți la furnizor', 1),
        (4, (today - timedelta(days=8)).isoformat(), 210, 'Documentație Tehnică', 'Redactat caiet de sarcini și instrucțiuni de montaj reductor', 0)
    ]

    c.executemany('''
        INSERT INTO time_entries (project_id, date, duration_minutes, category, description, is_overtime)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', time_samples)
