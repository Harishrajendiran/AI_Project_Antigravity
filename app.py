import os
import re
import json
import uuid
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, abort

# Configure logger
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# --- Load environment variables from .env file (if available) ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# --- Secure Secret Key Resolution ---
# TODO(security): Secret key must be injected via a secure production environment variable (e.g. KMS).
# For local testing, we query environment variables or fallback to an ephemeral, secure randomly generated value.
def resolve_secret_key():
    secret = os.environ.get('FLASK_SECRET_KEY')
    if secret:
        return secret
    logger.warning("Generating ephemeral Flask Secret Key. Instance-isolated!")
    return secrets.token_hex(32)

app.config['SECRET_KEY'] = resolve_secret_key()

# --- Hardened Cookie and Session Policies ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# If running over HTTPS in production, set app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)

# --- MySQL Database Configuration & Connection ---
import pymysql
import pymysql.cursors

def get_db_connection(use_db=True):
    """Resolve database connection parameters securely from environment variables."""
    host = os.environ.get('MYSQL_HOST', '127.0.0.1')
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    port_str = os.environ.get('MYSQL_PORT', '3306')
    try:
        port = int(port_str)
    except ValueError:
        port = 3306
    db = os.environ.get('MYSQL_DB', 'badminton_tournament')

    conn_args = {
        'host': host,
        'user': user,
        'password': password,
        'port': port,
        'autocommit': True,
        'cursorclass': pymysql.cursors.DictCursor
    }
    if use_db:
        conn_args['database'] = db
    
    return pymysql.connect(**conn_args)

def init_db():
    """Create database and set up tables if they do not exist."""
    # Connect without specifying database to create it
    conn = get_db_connection(use_db=False)
    try:
        with conn.cursor() as cursor:
            db_name = os.environ.get('MYSQL_DB', 'badminton_tournament')
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
    finally:
        conn.close()

    # Connect to the database to initialize schema
    conn = get_db_connection(use_db=True)
    try:
        with conn.cursor() as cursor:
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `users` (
                    `username` VARCHAR(20) PRIMARY KEY,
                    `mobile` VARCHAR(15) NOT NULL,
                    `email` VARCHAR(100) NOT NULL UNIQUE,
                    `hash` VARCHAR(128) NOT NULL,
                    `salt` VARCHAR(32) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Tournaments metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `tournaments` (
                    `id` VARCHAR(36) PRIMARY KEY,
                    `name` VARCHAR(100) NOT NULL,
                    `creator` VARCHAR(20) NOT NULL,
                    `fixture_type` VARCHAR(30) DEFAULT NULL,
                    `winning_point` INT NOT NULL DEFAULT 21,
                    `num_sets` INT NOT NULL DEFAULT 3,
                    `num_groups` INT NOT NULL DEFAULT 2,
                    `teams_per_group` INT NOT NULL DEFAULT 4,
                    `status` VARCHAR(20) NOT NULL DEFAULT 'active',
                    `open_registration` BOOLEAN NOT NULL DEFAULT TRUE,
                    `entry_deadline` DATE NOT NULL,
                    `created_at` DATETIME NOT NULL,
                    FOREIGN KEY (`creator`) REFERENCES `users` (`username`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Registered teams table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `tournament_teams` (
                    `tournament_id` VARCHAR(36) NOT NULL,
                    `team_name` VARCHAR(30) NOT NULL,
                    `registered_by` VARCHAR(20) NOT NULL,
                    PRIMARY KEY (`tournament_id`, `team_name`),
                    FOREIGN KEY (`tournament_id`) REFERENCES `tournaments` (`id`) ON DELETE CASCADE,
                    FOREIGN KEY (`registered_by`) REFERENCES `users` (`username`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Group distribution table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `tournament_groups` (
                    `tournament_id` VARCHAR(36) NOT NULL,
                    `group_name` VARCHAR(5) NOT NULL,
                    `team_name` VARCHAR(30) NOT NULL,
                    PRIMARY KEY (`tournament_id`, `group_name`, `team_name`),
                    FOREIGN KEY (`tournament_id`, `team_name`) REFERENCES `tournament_teams` (`tournament_id`, `team_name`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Matches schedule table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `matches` (
                    `id` VARCHAR(36) PRIMARY KEY,
                    `tournament_id` VARCHAR(36) NOT NULL,
                    `round` INT NOT NULL,
                    `group_name` VARCHAR(5) DEFAULT NULL,
                    `stage` VARCHAR(20) NOT NULL,
                    `team1` VARCHAR(30) NOT NULL,
                    `team2` VARCHAR(30) NOT NULL,
                    `score1` INT DEFAULT NULL,
                    `score2` INT DEFAULT NULL,
                    `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
                    FOREIGN KEY (`tournament_id`) REFERENCES `tournaments` (`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Match individual set scores table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `match_scores` (
                    `match_id` VARCHAR(36) NOT NULL,
                    `set_num` INT NOT NULL,
                    `team1_score` INT DEFAULT NULL,
                    `team2_score` INT DEFAULT NULL,
                    PRIMARY KEY (`match_id`, `set_num`),
                    FOREIGN KEY (`match_id`) REFERENCES `matches` (`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
    except Exception as e:
        logger.error(f"Failed to initialize tables: {e}")
    finally:
        conn.close()

def fix_completed_tournaments():
    """Correct the status of any existing tournaments whose status was corrupted by legacy logic."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, fixture_type, status FROM tournaments")
            tournaments = cursor.fetchall()
            for t in tournaments:
                cursor.execute("SELECT stage, status FROM matches WHERE tournament_id = %s", (t['id'],))
                matches = cursor.fetchall()
                if not matches:
                    continue
                
                if t['fixture_type'] == 'groups_leagues':
                    final_match = next((m for m in matches if m['stage'] == 'final'), None)
                    is_completed = (final_match is not None and final_match['status'] == 'completed')
                else:
                    is_completed = all(m['status'] == 'completed' for m in matches)
                
                new_status = 'completed' if is_completed else 'active'
                if t['status'] != new_status:
                    cursor.execute("UPDATE tournaments SET status = %s WHERE id = %s", (new_status, t['id']))
                    logger.warning(f"Fixed status of tournament {t['id']} to {new_status}")
    except Exception as e:
        logger.error(f"Error fixing tournament statuses: {e}")
    finally:
        conn.close()

# Initialize schema and fix legacy statuses on load
init_db()
fix_completed_tournaments()

# --- DB-API Parameterized Helpers ---

def get_user_by_username_or_email(identifier):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (identifier, identifier))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Database error in get_user_by_username_or_email: {e}")
        return None
    finally:
        conn.close()

def check_user_exists(username, email, mobile):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return "Username is already taken."
            cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return "An account with this email is already registered."
            cursor.execute("SELECT 1 FROM users WHERE mobile = %s", (mobile,))
            if cursor.fetchone():
                return "An account with this mobile is already registered."
            return None
    except Exception as e:
        logger.error(f"Database error in check_user_exists: {e}")
        return "Database service error."
    finally:
        conn.close()

def create_user(username, mobile, email, pwd_hash, pwd_salt):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, mobile, email, hash, salt) VALUES (%s, %s, %s, %s, %s)",
                (username, mobile, email, pwd_hash, pwd_salt)
            )
            return True
    except Exception as e:
        logger.error(f"Database error in create_user: {e}")
        return False
    finally:
        conn.close()

def get_all_tournaments():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tournaments ORDER BY created_at DESC")
            tourneys = cursor.fetchall()
            for t in tourneys:
                if t.get('entry_deadline'):
                    t['entry_deadline'] = str(t['entry_deadline'])
                if t.get('created_at'):
                    t['created_at'] = t['created_at'].isoformat()
                cursor.execute("SELECT team_name FROM tournament_teams WHERE tournament_id = %s", (t['id'],))
                t['teams'] = [row['team_name'] for row in cursor.fetchall()]
            return tourneys
    except Exception as e:
        logger.error(f"Database error in get_all_tournaments: {e}")
        return []
    finally:
        conn.close()

def get_tournament_by_id(tourney_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tournaments WHERE id = %s", (tourney_id,))
            t = cursor.fetchone()
            if not t:
                return None
            
            if t.get('entry_deadline'):
                t['entry_deadline'] = str(t['entry_deadline'])
            if t.get('created_at'):
                t['created_at'] = t['created_at'].isoformat()
            t['open_registration'] = bool(t['open_registration'])
            
            cursor.execute("SELECT team_name, registered_by FROM tournament_teams WHERE tournament_id = %s", (tourney_id,))
            teams_rows = cursor.fetchall()
            t['teams'] = [row['team_name'] for row in teams_rows]
            t['registered_by'] = {row['team_name']: row['registered_by'] for row in teams_rows}
            
            cursor.execute("SELECT group_name, team_name FROM tournament_groups WHERE tournament_id = %s", (tourney_id,))
            groups_rows = cursor.fetchall()
            groups = {}
            for row in groups_rows:
                g_name = row['group_name']
                t_name = row['team_name']
                groups.setdefault(g_name, []).append(t_name)
            t['groups'] = groups
            
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s", (tourney_id,))
            matches_rows = cursor.fetchall()
            matches = []
            for m in matches_rows:
                cursor.execute("SELECT set_num, team1_score, team2_score FROM match_scores WHERE match_id = %s ORDER BY set_num ASC", (m['id'],))
                scores_rows = cursor.fetchall()
                m['scores'] = [{'team1': row['team1_score'], 'team2': row['team2_score']} for row in scores_rows]
                m['group'] = m.get('group_name')
                if m.get('score1') is not None:
                    m['score1'] = int(m['score1'])
                if m.get('score2') is not None:
                    m['score2'] = int(m['score2'])
                m['round'] = int(m['round'])
                matches.append(m)
            
            # Sort matches systematically: Group stage (Group A, B, C...) -> Round -> Knockouts
            def match_sort_key(m):
                stage_order = {'group': 0, 'league': 0, 'quarter': 1, 'semi': 2, 'final': 3}
                stage_priority = stage_order.get(m.get('stage'), 4)
                group = m.get('group_name') or ""
                round_num = m.get('round') or 0
                return (stage_priority, group, round_num, m.get('team1', ''), m.get('team2', ''))

            matches.sort(key=match_sort_key)
            t['matches'] = matches
            return t
    except Exception as e:
        logger.error(f"Database error in get_tournament_by_id: {e}")
        return None
    finally:
        conn.close()

def save_tournament(t):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO tournaments (
                    id, name, creator, fixture_type, winning_point, num_sets, 
                    num_groups, teams_per_group, status, open_registration, 
                    entry_deadline, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    fixture_type = VALUES(fixture_type),
                    winning_point = VALUES(winning_point),
                    num_sets = VALUES(num_sets),
                    num_groups = VALUES(num_groups),
                    teams_per_group = VALUES(teams_per_group),
                    status = VALUES(status),
                    open_registration = VALUES(open_registration),
                    entry_deadline = VALUES(entry_deadline)
            """, (
                t['id'], t['name'], t['creator'], t.get('fixture_type'), 
                t.get('winning_point', 21), t.get('num_sets', 3), 
                t.get('num_groups', 2), t.get('teams_per_group', 4), 
                t.get('status', 'active'), t.get('open_registration', True), 
                t.get('entry_deadline'), t.get('created_at')
            ))
            
            cursor.execute("DELETE FROM tournament_teams WHERE tournament_id = %s", (t['id'],))
            registered_by = t.get('registered_by', {})
            for team_name in t.get('teams', []):
                creator = registered_by.get(team_name, t['creator'])
                cursor.execute(
                    "INSERT INTO tournament_teams (tournament_id, team_name, registered_by) VALUES (%s, %s, %s)",
                    (t['id'], team_name, creator)
                )
                
            cursor.execute("DELETE FROM tournament_groups WHERE tournament_id = %s", (t['id'],))
            for g_name, g_teams in t.get('groups', {}).items():
                for team_name in g_teams:
                    cursor.execute(
                        "INSERT INTO tournament_groups (tournament_id, group_name, team_name) VALUES (%s, %s, %s)",
                        (t['id'], g_name, team_name)
                    )
            
            cursor.execute("DELETE FROM matches WHERE tournament_id = %s", (t['id'],))
            for m in t.get('matches', []):
                cursor.execute("""
                    INSERT INTO matches (
                        id, tournament_id, `round`, group_name, stage, team1, team2, score1, score2, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    m['id'], t['id'], m['round'], m.get('group'), m['stage'], 
                    m['team1'], m['team2'], m.get('score1'), m.get('score2'), m['status']
                ))
                
                for idx, set_score in enumerate(m.get('scores', [])):
                    cursor.execute("""
                        INSERT INTO match_scores (match_id, set_num, team1_score, team2_score)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        m['id'], idx + 1, set_score.get('team1'), set_score.get('team2')
                    ))
            
        return True
    except Exception as e:
        logger.error(f"Database error in save_tournament: {e}")
        return False
    finally:
        conn.close()

def delete_tournament(tourney_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tournaments WHERE id = %s", (tourney_id,))
        return True
    except Exception as e:
        logger.error(f"Database error in delete_tournament: {e}")
        return False
    finally:
        conn.close()

# --- Cryptographic Password Hashing (scrypt) ---
def hash_password(password, salt=None):
    """Hash password securely using memory-hard scrypt algorithm."""
    if salt is None:
        salt = os.urandom(16)
    # Parameters n=16384 (work factor), r=8 (block size), p=1 (parallelization)
    hashed = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1)
    return hashed.hex(), salt.hex()

def verify_password(password, stored_hash, stored_salt):
    """Verify password against stored scrypt hash and salt."""
    try:
        salt = bytes.fromhex(stored_salt)
        hashed, _ = hash_password(password, salt)
        return hashed == stored_hash
    except Exception:
        return False

# --- Validation Utilities ---
def is_valid_username(username):
    # Alphanumeric and underscores only, 3 to 20 characters
    return bool(re.match(r'^[a-zA-Z0-9_]{3,20}$', username))

def is_valid_mobile(mobile):
    # Digits only, 10 to 12 digits
    return bool(re.match(r'^[0-9]{10,12}$', mobile))

def is_valid_email(email):
    # RFC 5322 compliant simple regex
    pattern = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
    return bool(re.match(pattern, email))

# --- PII Masking Utilities ---
def mask_email(email):
    if '@' not in email:
        return '***'
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        return f"{name[0]}***@{domain}"
    return f"{name[0]}***{name[-1]}@{domain}"

def mask_mobile(mobile):
    if len(mobile) < 4:
        return '******'
    return '•' * (len(mobile) - 4) + mobile[-4:]

# --- Fixture Generation Helpers ---
def generate_round_robin(teams, group_name=None):
    """Generate round-robin match schedules (Berger circle method)."""
    temp_teams = list(teams)
    # If odd number of teams, pad with None to represent a "Bye"
    if len(temp_teams) % 2 != 0:
        temp_teams.append(None)
    
    n = len(temp_teams)
    matches = []
    
    for r in range(n - 1):
        for i in range(n // 2):
            t1 = temp_teams[i]
            t2 = temp_teams[n - 1 - i]
            if t1 is not None and t2 is not None:
                matches.append({
                    'id': str(uuid.uuid4()),
                    'round': r + 1,
                    'group': group_name,
                    'stage': 'group' if group_name else 'league',
                    'team1': t1,
                    'team2': t2,
                    'score1': None,
                    'score2': None,
                    'status': 'pending'
                })
        # Rotate all teams except the first one
        temp_teams = [temp_teams[0]] + [temp_teams[-1]] + temp_teams[1:-1]
        
    return matches

# --- Standings Calculator ---
def calculate_standings(tournament, group=None):
    """Calculate group or league standings dynamically from matches with set point differences."""
    teams = tournament['teams']
    if group:
        teams = tournament.get('groups', {}).get(group, [])
        
    standings = {t: {'team': t, 'played': 0, 'won': 0, 'lost': 0, 'sets_won': 0, 'sets_lost': 0, 'point_diff': 0, 'points': 0} for t in teams}
    
    for m in tournament.get('matches', []):
        if m.get('stage') in ['semi', 'final']:
            continue # Knockout matches do not count toward group/league standings table
        if group and (m.get('group') != group):
            continue
        if m['status'] == 'completed':
            t1, t2 = m['team1'], m['team2']
            
            if t1 in standings and t2 in standings:
                sets_t1 = 0
                sets_t2 = 0
                points_t1 = 0
                points_t2 = 0
                
                # Dynamic set points collection
                if 'scores' in m:
                    for set_score in m.get('scores', []):
                        s1 = set_score.get('team1')
                        s2 = set_score.get('team2')
                        if s1 is not None and s2 is not None:
                            points_t1 += s1
                            points_t2 += s2
                            if s1 > s2:
                                sets_t1 += 1
                            elif s2 > s1:
                                sets_t2 += 1
                else:
                    # Fallback for set-level records
                    s1 = int(m['score1']) if m.get('score1') is not None else 0
                    s2 = int(m['score2']) if m.get('score2') is not None else 0
                    points_t1 += s1
                    points_t2 += s2
                    if s1 > s2:
                        sets_t1 += 1
                    elif s2 > s1:
                        sets_t2 += 1
                
                standings[t1]['played'] += 1
                standings[t2]['played'] += 1
                
                standings[t1]['sets_won'] += sets_t1
                standings[t1]['sets_lost'] += sets_t2
                standings[t2]['sets_won'] += sets_t2
                standings[t2]['sets_lost'] += sets_t1
                
                standings[t1]['point_diff'] += (points_t1 - points_t2)
                standings[t2]['point_diff'] += (points_t2 - points_t1)
                
                if sets_t1 > sets_t2:
                    standings[t1]['won'] += 1
                    standings[t1]['points'] += 2
                    standings[t2]['lost'] += 1
                elif sets_t2 > sets_t1:
                    standings[t2]['won'] += 1
                    standings[t2]['points'] += 2
                    standings[t1]['lost'] += 1
                else:
                    if points_t1 > points_t2:
                        standings[t1]['won'] += 1
                        standings[t1]['points'] += 2
                        standings[t2]['lost'] += 1
                    elif points_t2 > points_t1:
                        standings[t2]['won'] += 1
                        standings[t2]['points'] += 2
                        standings[t1]['lost'] += 1
                    else:
                        standings[t1]['points'] += 1
                        standings[t2]['points'] += 1
                    
    sorted_standings = list(standings.values())
    # Sort by Points (DESC), Sets diff (DESC), Points diff (DESC)
    sorted_standings.sort(key=lambda x: (x['points'], x['sets_won'] - x['sets_lost'], x['point_diff']), reverse=True)
    return sorted_standings

# --- Custom CSRF Synchronizer Token Protection ---
@app.before_request
def enforce_csrf_protection():
    """Verify CSRF token for all state-changing (POST) requests."""
    if request.method == "POST":
        submitted_token = request.form.get('csrf_token')
        session_token = session.get('csrf_token')
        
        if not session_token or not submitted_token or not secrets.compare_digest(session_token, submitted_token):
            abort(400, "CSRF security verification failed. Invalid or expired token.")

@app.context_processor
def inject_csrf_token():
    """Inject a CSRF token dynamically into the session if not present."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return dict(csrf_token=session['csrf_token'])

# --- Web Page Routes ---

@app.route('/')
def login_page():
    """Render the login form."""
    if 'user' in session:
        return redirect(url_for('dashboard_page'))
    
    error = request.args.get('error')
    success = request.args.get('success')
    return render_template('login.html', error=error, success=success)

@app.route('/login', methods=['POST'])
def handle_login():
    """Authenticate credentials submitted via login form."""
    if 'user' in session:
        return redirect(url_for('dashboard_page'))

    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')

    if not username or not password:
        return redirect(url_for('login_page', error="Please fill in all credentials."))

    user_record = get_user_by_username_or_email(username)

    if user_record and verify_password(password, user_record['hash'], user_record['salt']):
        session.permanent = True
        session['user'] = user_record['username']
        session['email'] = user_record['email']
        session['mobile'] = user_record['mobile']
        return redirect(url_for('dashboard_page'))
    
    return redirect(url_for('login_page', error="Invalid username or password."))

@app.route('/register')
def register_page():
    """Render the registration form."""
    if 'user' in session:
        return redirect(url_for('dashboard_page'))
    
    error = request.args.get('error')
    return render_template('register.html', error=error)

@app.route('/register', methods=['POST'])
def handle_register():
    """Process new user registration registration form."""
    if 'user' in session:
        return redirect(url_for('dashboard_page'))

    username = request.form.get('username', '').strip().lower()
    mobile = request.form.get('mobile', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    form_data = {'username': username, 'mobile': mobile, 'email': email}

    if not is_valid_username(username):
        return render_template('register.html', error="Username must be alphanumeric and 3-20 characters long.", form_data=form_data)
        
    if not is_valid_mobile(mobile):
        return render_template('register.html', error="Mobile number must be digits only (10 to 12 digits).", form_data=form_data)

    if not is_valid_email(email):
        return render_template('register.html', error="Please enter a valid email address.", form_data=form_data)

    if len(password) < 8:
        return render_template('register.html', error="Password must contain at least 8 characters.", form_data=form_data)

    existing_error = check_user_exists(username, email, mobile)
    if existing_error:
        return render_template('register.html', error=existing_error, form_data=form_data)

    pwd_hash, pwd_salt = hash_password(password)

    if create_user(username, mobile, email, pwd_hash, pwd_salt):
        return redirect(url_for('login_page', success="Profile created successfully. Please sign in."))
    
    return render_template('register.html', error="Failed to store user profile database.", form_data=form_data)

@app.route('/dashboard')
def dashboard_page():
    """Secure dashboard displaying user details and list of active tournaments."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Unauthorized access. Please login first."))
    
    masked_email = mask_email(session['email'])
    masked_mobile = mask_mobile(session['mobile'])

    tournaments = get_all_tournaments()

    success = request.args.get('success')
    error = request.args.get('error')

    return render_template(
        'dashboard.html', 
        username=session['user'], 
        email=masked_email, 
        mobile=masked_mobile,
        tournaments=tournaments,
        success=success,
        error=error
    )

@app.route('/tournament/new')
def create_tournament_page():
    """Render Step 1 of Tournament Registration."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))
    
    error = request.args.get('error')
    return render_template('create_tournament.html', error=error)

@app.route('/tournament/new', methods=['POST'])
def handle_create_tournament():
    """Process tournament name and register tournament configuration."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    name = request.form.get('name', '').strip()
    open_registration_checked = (request.form.get('open_registration') == '1')
    entry_deadline = request.form.get('entry_deadline', '').strip()

    def render_error(error, name=name):
        return render_template('create_tournament.html', error=error, name=name)

    if not name:
        return render_error("Tournament Name is required.")

    if not entry_deadline:
        return render_error("Registration Closing Date is required.")

    if not re.match(r'^\d{4}-\d{2}-\d{2}$', entry_deadline):
        return render_error("Invalid Registration Closing Date format. Use YYYY-MM-DD.")

    tourney_id = str(uuid.uuid4())
    
    new_tournament = {
        'id': tourney_id,
        'name': name,
        'creator': session['user'],
        'teams': [],
        'groups': {},
        'registered_by': {},
        'fixture_type': None,
        'winning_point': 21,
        'num_sets': 3,
        'num_groups': 2,
        'teams_per_group': 4,
        'status': 'active',
        'matches': [],
        'open_registration': open_registration_checked,
        'entry_deadline': entry_deadline,
        'created_at': datetime.utcnow().isoformat()
    }
    
    if not save_tournament(new_tournament):
        return render_error("Failed to save tournament record.")

    success_msg = f"Tournament '{name}' created successfully!"
    return redirect(url_for('dashboard_page', success=success_msg))

@app.route('/tournament/fixture')
def select_fixture_page():
    """Render Step 2 of Tournament Setup."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    name = session.get('new_tourney_name')
    teams = session.get('new_tourney_teams') or []
    num_groups = session.get('new_tourney_num_groups', 2)

    if not name:
        return redirect(url_for('create_tournament_page', error="Session expired. Please start again."))

    error = request.args.get('error')
    return render_template('select_fixture.html', name=name, teams=teams, num_groups=num_groups, error=error)

@app.route('/tournament/fixture', methods=['POST'])
def handle_select_fixture():
    """Generate fixtures and finalize tournament registration."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    name = session.get('new_tourney_name')
    teams = session.get('new_tourney_teams') or []
    winning_point = session.get('new_tourney_winning_point', 21)
    num_sets = session.get('new_tourney_num_sets', 3)
    num_groups = session.get('new_tourney_num_groups', 2)
    teams_per_group = session.get('new_tourney_teams_per_group', 4)

    if not name:
        return redirect(url_for('create_tournament_page', error="Session expired. Please start again."))

    fixture_type = request.form.get('fixture_type')
    if fixture_type not in ['leagues', 'groups', 'groups_leagues']:
        return render_template('select_fixture.html', name=name, teams=teams, num_groups=num_groups, error="Invalid fixture model selected.")

    matches = []
    groups = {}

    if teams:
        if fixture_type == 'leagues':
            matches = generate_round_robin(teams)
        else:
            # Split teams dynamically into defined number of groups using round-robin distribution
            groups = {}
            for i, t in enumerate(teams):
                group_idx = i % num_groups
                group_name = chr(65 + group_idx)  # 'A', 'B', 'C', 'D', ...
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(t)

            for g_name, g_teams in groups.items():
                matches.extend(generate_round_robin(g_teams, g_name))

    tourney_id = session.get('new_tourney_id')
    tournament = None
    if tourney_id:
        tournament = get_tournament_by_id(tourney_id)

    if tournament:
        # Update existing tournament record
        tournament['fixture_type'] = fixture_type
        tournament['groups'] = groups
        tournament['matches'] = matches
        if len(tournament.get('teams', [])) > 0:
            tournament['open_registration'] = False
    else:
        # Fallback to create from scratch (preserves compatibility)
        tourney_id = tourney_id or str(uuid.uuid4())
        open_reg = session.get('new_tourney_open_registration', True)
        if len(teams) > 0:
            open_reg = False

        tournament = {
            'id': tourney_id,
            'name': name,
            'creator': session['user'],
            'teams': teams,
            'groups': groups,
            'fixture_type': fixture_type,
            'winning_point': winning_point,
            'num_sets': num_sets,
            'num_groups': num_groups,
            'teams_per_group': teams_per_group,
            'status': 'active',
            'matches': matches,
            'open_registration': open_reg,
            'entry_deadline': session.get('new_tourney_entry_deadline', (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%d')),
            'created_at': datetime.utcnow().isoformat()
        }

    if save_tournament(tournament):
        # Clear temporary setup sessions
        session.pop('new_tourney_id', None)
        session.pop('new_tourney_name', None)
        session.pop('new_tourney_teams', None)
        session.pop('new_tourney_winning_point', None)
        session.pop('new_tourney_num_sets', None)
        session.pop('new_tourney_num_groups', None)
        session.pop('new_tourney_teams_per_group', None)
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success="Tournament successfully generated!"))

    return render_template('select_fixture.html', name=name, teams=teams, num_groups=num_groups, error="Failed to store new tournament database.")

@app.route('/tournament/<tourney_id>')
def tournament_details_page(tourney_id):
    """View tournament standings, brackets, and fixtures. Controls scale based on creator privileges."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    is_creator = (session['user'] == tournament['creator'] or session['user'] == 'admin')

    standings = []
    group_standings = {}
    group_stage_done = False
    knockout_generated = False

    expected_teams = 0
    slots_remaining = 0
    registration_closed = False

    if not tournament.get('matches'):
        expected_teams = tournament['num_groups'] * tournament['teams_per_group']
        slots_remaining = expected_teams - len(tournament.get('teams', []))
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        registration_closed = (today_str > tournament.get('entry_deadline', ''))
    else:
        if tournament['fixture_type'] == 'leagues':
            standings = calculate_standings(tournament)
        else:
            for g in tournament.get('groups', {}).keys():
                group_standings[g] = calculate_standings(tournament, g)

        if tournament['fixture_type'] == 'groups_leagues':
            group_matches = [m for m in tournament['matches'] if m.get('stage') == 'group']
            if group_matches:
                group_stage_done = all(m['status'] == 'completed' for m in group_matches)
            knockout_generated = any(m.get('stage') in ['quarter', 'semi', 'final'] for m in tournament['matches'])

    error = request.args.get('error')
    success = request.args.get('success')

    return render_template(
        'tournament_detail.html',
        username=session['user'],
        tournament=tournament,
        is_creator=is_creator,
        standings=standings,
        group_standings=group_standings,
        group_stage_done=group_stage_done,
        knockout_generated=knockout_generated,
        expected_teams=expected_teams,
        slots_remaining=slots_remaining,
        registration_closed=registration_closed,
        error=error,
        success=success
    )

@app.route('/tournament/<tourney_id>/score', methods=['POST'])
def handle_submit_score(tourney_id):
    """Update match score (restricted to tournament creator)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Role Authorization Enforcement
    if session['user'] != tournament['creator'] and session['user'] != 'admin':
        abort(403, "Forbidden. Only the organizer who created the tournament or admin can modify scores.")

    match_id = request.form.get('match_id')

    match_record = None
    for m in tournament.get('matches', []):
        if m['id'] == match_id:
            match_record = m
            break

    if not match_record:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Match not found."))

    num_sets_form = request.form.get('num_sets')
    if num_sets_form is not None:
        try:
            num_sets_val = int(num_sets_form)
            if num_sets_val in [1, 3, 5]:
                tournament['num_sets'] = num_sets_val
        except ValueError:
            pass

    num_sets = tournament.get('num_sets', 3)
    winning_point = tournament.get('winning_point', 21)

    set_num_raw = request.form.get('set_num')

    if set_num_raw is not None:
        # Individual set submission
        try:
            set_num = int(set_num_raw)
            if set_num < 1 or set_num > num_sets:
                raise ValueError("Invalid set number.")
            
            score1_raw = request.form.get('score1')
            score2_raw = request.form.get('score2')
            
            if score1_raw == '' or score2_raw == '':
                s1 = None
                s2 = None
            else:
                s1 = int(score1_raw)
                s2 = int(score2_raw)
                if s1 < 0 or s2 < 0 or s1 > 99 or s2 > 99:
                    raise ValueError("Scores must be positive integers between 0 and 99.")
                
            # Initialize or adjust scores list length
            if 'scores' not in match_record or not match_record['scores']:
                match_record['scores'] = [{'team1': None, 'team2': None} for _ in range(num_sets)]
            elif len(match_record['scores']) < num_sets:
                while len(match_record['scores']) < num_sets:
                    match_record['scores'].append({'team1': None, 'team2': None})
            elif len(match_record['scores']) > num_sets:
                match_record['scores'] = match_record['scores'][:num_sets]
                
            match_record['scores'][set_num - 1] = {'team1': s1, 'team2': s2}
            
            # Count sets won
            total_sets_won1 = 0
            total_sets_won2 = 0
            sets_played = 0
            for s in match_record['scores']:
                t1 = s.get('team1')
                t2 = s.get('team2')
                if t1 is not None and t2 is not None:
                    sets_played += 1
                    if t1 > t2:
                        total_sets_won1 += 1
                    elif t2 > t1:
                        total_sets_won2 += 1
            
            match_record['score1'] = total_sets_won1
            match_record['score2'] = total_sets_won2
            
            # Determine match completion status
            majority = (num_sets // 2) + 1
            if total_sets_won1 >= majority or total_sets_won2 >= majority or sets_played == num_sets:
                match_record['status'] = 'completed'
            else:
                match_record['status'] = 'pending'
                
        except ValueError as e:
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e), active_tab="matches"))
    else:
        # Bulk set submission (compatible with tests and legacy forms)
        scores = []
        total_sets_won1 = 0
        total_sets_won2 = 0
        sets_played = 0
        try:
            for i in range(1, num_sets + 1):
                s1_raw = request.form.get(f'score1_set{i}')
                s2_raw = request.form.get(f'score2_set{i}')
                if s1_raw == '' or s2_raw == '' or s1_raw is None or s2_raw is None:
                    s1 = None
                    s2 = None
                else:
                    try:
                        s1 = int(s1_raw)
                        s2 = int(s2_raw)
                    except ValueError:
                        raise ValueError("Scores must be valid integers.")
                    if s1 < 0 or s2 < 0 or s1 > 99 or s2 > 99:
                        raise ValueError("Scores must be positive integers between 0 and 99.")
                
                if s1 is not None and s2 is not None:
                    sets_played += 1
                    if s1 > s2:
                        total_sets_won1 += 1
                    elif s2 > s1:
                        total_sets_won2 += 1
                scores.append({'team1': s1, 'team2': s2})
        except ValueError as e:
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e), active_tab="matches"))

        match_record['score1'] = total_sets_won1
        match_record['score2'] = total_sets_won2
        match_record['scores'] = scores
        
        majority = (num_sets // 2) + 1
        if total_sets_won1 >= majority or total_sets_won2 >= majority or sets_played == num_sets:
            match_record['status'] = 'completed'
        else:
            match_record['status'] = 'pending'

    # Generic Bracket progression trigger
    current_stage = match_record.get('stage')
    stage_progression = {
        'round_of_32': 'round_of_16',
        'round_of_16': 'quarter',
        'quarter': 'semi',
        'semi': 'final'
    }

    if current_stage in stage_progression:
        next_stage = stage_progression[current_stage]
        current_stage_matches = [m for m in tournament['matches'] if m.get('stage') == current_stage]
        
        if all(m['status'] == 'completed' for m in current_stage_matches):
            # Check if next stage matches have already been generated
            next_stage_matches = [m for m in tournament['matches'] if m.get('stage') == next_stage]
            if not next_stage_matches:
                w = []
                for m in current_stage_matches:
                    winner = m['team1'] if (m.get('score1') or 0) > (m.get('score2') or 0) else m['team2']
                    w.append(winner)
                
                # Pair the winners to generate the next stage matches
                num_next_matches = len(w) // 2
                for k in range(num_next_matches):
                    # Maintain original cross-pairing compatibility for Quarter-finals to Semi-finals
                    if current_stage == 'quarter' and len(w) == 4:
                        t1 = w[0] if k == 0 else w[1]
                        t2 = w[2] if k == 0 else w[3]
                    else:
                        t1 = w[2 * k]
                        t2 = w[2 * k + 1]
                        
                    next_match = {
                        'id': str(uuid.uuid4()),
                        'round': 1,
                        'group': None,
                        'stage': next_stage,
                        'team1': t1,
                        'team2': t2,
                        'score1': None,
                        'score2': None,
                        'status': 'pending'
                    }
                    
                    # Auto-complete BYE matches
                    if t1 == 'BYE' or t2 == 'BYE':
                        next_match['status'] = 'completed'
                        if t1 == 'BYE' and t2 == 'BYE':
                            next_match['score1'] = 0
                            next_match['score2'] = 0
                        elif t1 == 'BYE':
                            next_match['score1'] = 0
                            next_match['score2'] = 1
                        else:
                            next_match['score1'] = 1
                            next_match['score2'] = 0
                            
                    tournament['matches'].append(next_match)

    # Determine if tournament is completed and update status based on fixture type
    fixture_type = tournament.get('fixture_type')
    if fixture_type == 'groups_leagues':
        final_match = next((m for m in tournament['matches'] if m.get('stage') == 'final'), None)
        is_completed = (final_match is not None and final_match['status'] == 'completed')
    else:
        is_completed = all(m['status'] == 'completed' for m in tournament['matches']) if tournament['matches'] else False

    if is_completed:
        tournament['status'] = 'completed'
    else:
        tournament['status'] = 'active'

    if save_tournament(tournament):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success="Match score recorded.", active_tab="matches"))

    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to write score to database.", active_tab="matches"))

@app.route('/tournament/<tourney_id>/knockout', methods=['POST'])
def handle_generate_knockout(tourney_id):
    """Generate Semi-finals and Finals brackets from Group stage standings (restricted to creator)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Role Authorization Enforcement
    if session['user'] != tournament['creator'] and session['user'] != 'admin':
        abort(403, "Forbidden. Only the organizer who created the tournament or admin can generate knockout fixtures.")

    if tournament['fixture_type'] != 'groups_leagues':
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Fixture type does not support knockouts."))

    group_matches = [m for m in tournament['matches'] if m.get('stage') == 'group']
    if not all(m['status'] == 'completed' for m in group_matches):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Please complete all group stage matches first."))

    # Check duplicate knockout creation
    if any(m.get('stage') in ['quarter', 'semi', 'final'] for m in tournament['matches']):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Knockout brackets are already generated."))

    num_groups = tournament.get('num_groups', 2)

    # 1. Collect all winners and runners from all groups
    winners = []
    runners = []
    for g_idx in range(num_groups):
        group_name = chr(65 + g_idx)
        group_standings = calculate_standings(tournament, group_name)
        
        w_team = group_standings[0]['team'] if len(group_standings) > 0 else 'BYE'
        r_team = group_standings[1]['team'] if len(group_standings) > 1 else 'BYE'
        
        winners.append((w_team, group_name))
        runners.append((r_team, group_name))

    # 2. Find the next power of 2 size for the bracket
    p = 2
    while p < (num_groups * 2):
        p *= 2
    num_matches = p // 2

    # 3. Pad both winners and runners lists with 'BYE' to ensure size is num_matches
    while len(winners) < num_matches:
        winners.append(('BYE', None))
    while len(runners) < num_matches:
        runners.append(('BYE', None))

    # 4. Determine stage name based on bracket size p
    stage_names = {2: 'final', 4: 'semi', 8: 'quarter', 16: 'round_of_16', 32: 'round_of_32'}
    stage_name = stage_names.get(p, f"round_of_{p}")
    success_msg = f"Knockout {stage_name.replace('_', ' ')} fixtures generated!"

    # 5. Generate first round matches pairing winners with runners
    for i in range(num_matches):
        t1 = winners[i][0]
        # Shift runner pairings to ensure no winner plays a runner from their own group if possible
        t2 = runners[(i + 1) % num_matches][0]

        qf = {
            'id': str(uuid.uuid4()),
            'round': 1,
            'group': None,
            'stage': stage_name,
            'team1': t1,
            'team2': t2,
            'score1': None,
            'score2': None,
            'status': 'pending'
        }

        # Auto-complete BYE matches
        if t1 == 'BYE' or t2 == 'BYE':
            qf['status'] = 'completed'
            if t1 == 'BYE' and t2 == 'BYE':
                qf['score1'] = 0
                qf['score2'] = 0
            elif t1 == 'BYE':
                qf['score1'] = 0
                qf['score2'] = 1
            else:
                qf['score1'] = 1
                qf['score2'] = 0

        tournament['matches'].append(qf)

    # Determine if tournament is completed and update status based on fixture type
    fixture_type = tournament.get('fixture_type')
    if fixture_type == 'groups_leagues':
        final_match = next((m for m in tournament['matches'] if m.get('stage') == 'final'), None)
        is_completed = (final_match is not None and final_match['status'] == 'completed')
    else:
        is_completed = all(m['status'] == 'completed' for m in tournament['matches']) if tournament['matches'] else False

    if is_completed:
        tournament['status'] = 'completed'
    else:
        tournament['status'] = 'active'

    if save_tournament(tournament):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success=success_msg))

    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to save knockout fixtures database."))

@app.route('/tournament/<tourney_id>/export/pdf')
def export_fixtures_pdf(tourney_id):
    """Render print-friendly fixtures page for PDF saving with optional stage filtering."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)
    if not tournament:
        abort(404, "Tournament not found.")

    if not tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Fixtures have not been generated yet."))

    stage = request.args.get('stage')
    filtered_matches = tournament['matches']
    stage_title = "Fixture Schedule"
    if stage:
        if stage == 'group':
            filtered_matches = [m for m in filtered_matches if m.get('stage') in ['group', 'league']]
            stage_title = "Group Stage Fixtures"
        elif stage == 'knockout':
            filtered_matches = [m for m in filtered_matches if m.get('stage') in ['quarter', 'semi', 'final']]
            stage_title = "Knockout Stage Fixtures"
        elif stage == 'quarter':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'quarter']
            stage_title = "Quarter-final Fixtures"
        elif stage == 'semi':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'semi']
            stage_title = "Semi-final Fixtures"
        elif stage == 'final':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'final']
            stage_title = "Final Fixtures"

    if not filtered_matches:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=f"No matches generated for {stage_title} yet."))

    tournament_copy = dict(tournament)
    tournament_copy['matches'] = filtered_matches

    return render_template('export_fixtures.html', tournament=tournament_copy, export_type='pdf', stage_title=stage_title)


@app.route('/tournament/<tourney_id>/export/word')
def export_fixtures_word(tourney_id):
    """Download fixtures list as a Word document with optional stage filtering."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)
    if not tournament:
        abort(404, "Tournament not found.")

    if not tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Fixtures have not been generated yet."))

    stage = request.args.get('stage')
    filtered_matches = tournament['matches']
    stage_title = "Fixture Schedule"
    if stage:
        if stage == 'group':
            filtered_matches = [m for m in filtered_matches if m.get('stage') in ['group', 'league']]
            stage_title = "Group Stage Fixtures"
        elif stage == 'knockout':
            filtered_matches = [m for m in filtered_matches if m.get('stage') in ['quarter', 'semi', 'final']]
            stage_title = "Knockout Stage Fixtures"
        elif stage == 'quarter':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'quarter']
            stage_title = "Quarter-final Fixtures"
        elif stage == 'semi':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'semi']
            stage_title = "Semi-final Fixtures"
        elif stage == 'final':
            filtered_matches = [m for m in filtered_matches if m.get('stage') == 'final']
            stage_title = "Final Fixtures"

    if not filtered_matches:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=f"No matches generated for {stage_title} yet."))

    tournament_copy = dict(tournament)
    tournament_copy['matches'] = filtered_matches

    from flask import make_response
    html_content = render_template('export_fixtures.html', tournament=tournament_copy, export_type='word', stage_title=stage_title)
    
    response = make_response(html_content)
    safe_name = "".join([c if c.isalnum() else "_" for c in tournament['name']])
    stage_suffix = f"_{stage}" if stage else ""
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_name}_fixtures{stage_suffix}.doc"'
    response.headers['Content-Type'] = 'application/msword'
    return response

@app.route('/tournament/<tourney_id>/delete', methods=['POST'])
def handle_delete_tournament(tourney_id):
    """Delete a tournament (restricted to admin)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    if session['user'] != 'admin':
        abort(403, "Forbidden. Only admins can delete tournaments.")

    if delete_tournament(tourney_id):
        return redirect(url_for('dashboard_page', success="Tournament deleted successfully."))
    return redirect(url_for('dashboard_page', error="Failed to delete tournament."))
    
@app.route('/tournament/<tourney_id>/register_team', methods=['POST'])
def handle_register_team(tourney_id):
    """Register a new team/player to a tournament with open registration."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Cannot register after tournament has started
    if tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Cannot register teams after tournament has started."))

    is_creator_or_admin = (session['user'] == tournament['creator'] or session['user'] == 'admin')

    if not is_creator_or_admin:
        if not tournament.get('open_registration'):
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Registration is not open for this tournament."))

        # Check deadline
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        if today_str > tournament.get('entry_deadline', ''):
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Registration deadline has passed."))

        # User limitation check: one team per user
        registered_by = tournament.get('registered_by', {})
        if session['user'] in registered_by.values():
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="You have already registered a team in this tournament."))

    team_name = request.form.get('team_name', '').strip()
    if not team_name:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Team name cannot be empty."))

    if len(team_name) < 2 or len(team_name) > 30:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Team name must be between 2 and 30 characters."))

    # Unique team names constraint
    if team_name.lower() in [t.lower() for t in tournament.get('teams', [])]:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="A team with this name is already registered."))

    # Add team
    tournament.setdefault('teams', []).append(team_name)
    tournament.setdefault('registered_by', {})[team_name] = session['user']

    if save_tournament(tournament):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success=f"Successfully registered team '{team_name}'!"))

    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to save registration."))

@app.route('/tournament/<tourney_id>/remove_team', methods=['POST'])
def handle_remove_team(tourney_id):
    """Remove a registered team from a tournament (restricted to creator/admin)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Role Authorization Enforcement
    if session['user'] != tournament['creator'] and session['user'] != 'admin':
        abort(403, "Forbidden. Only the organizer who created the tournament or admin can manage registered teams.")

    if tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Cannot modify teams after tournament has started."))

    team_name = request.form.get('team_name', '').strip()
    if not team_name:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Team name cannot be empty."))

    if team_name in tournament.get('teams', []):
        tournament['teams'].remove(team_name)
        if team_name in tournament.get('registered_by', {}):
            del tournament['registered_by'][team_name]
        
        if save_tournament(tournament):
            return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success=f"Successfully removed team '{team_name}'.", show_entries=1))
        
    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to remove team."))

@app.route('/tournament/<tourney_id>/modify_team', methods=['POST'])
def handle_modify_team(tourney_id):
    """Modify a registered team name (restricted to creator/admin)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Role Authorization Enforcement
    if session['user'] != tournament['creator'] and session['user'] != 'admin':
        abort(403, "Forbidden. Only the organizer who created the tournament or admin can modify registered teams.")

    if tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Cannot modify teams after tournament has started."))

    old_team_name = request.form.get('old_team_name', '').strip()
    new_team_name = request.form.get('new_team_name', '').strip()

    if not old_team_name or not new_team_name:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Team names cannot be empty."))

    if len(new_team_name) < 2 or len(new_team_name) > 30:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Team name must be between 2 and 30 characters."))

    teams = tournament.get('teams', [])
    if old_team_name not in teams:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Original team not found in registration."))

    # Unique team names constraint (excluding old_team_name)
    existing_lowers = [t.lower() for t in teams if t != old_team_name]
    if new_team_name.lower() in existing_lowers:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="A team with this new name is already registered."))

    # Update team name in the list (preserve index)
    try:
        idx = teams.index(old_team_name)
        teams[idx] = new_team_name
    except ValueError:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to modify team name."))

    # Update registered_by mapping
    registered_by = tournament.get('registered_by', {})
    if old_team_name in registered_by:
        registered_by[new_team_name] = registered_by.pop(old_team_name)

    if save_tournament(tournament):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success=f"Successfully renamed team '{old_team_name}' to '{new_team_name}'.", show_entries=1))

    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to save tournament modification."))

@app.route('/tournament/<tourney_id>/start', methods=['POST'])
def handle_start_tournament(tourney_id):
    """Close registration and generate fixtures to start the tournament (creator/admin only)."""
    if 'user' not in session:
        return redirect(url_for('login_page', error="Please login first."))

    tournament = get_tournament_by_id(tourney_id)

    if not tournament:
        return redirect(url_for('dashboard_page', error="Tournament not found."))

    # Authorization check
    if session['user'] != tournament['creator'] and session['user'] != 'admin':
        abort(403, "Forbidden. Only the creator or admin can start the tournament.")

    if tournament.get('matches'):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Tournament is already started."))

    teams = tournament.get('teams', [])
    if len(teams) < 2:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Cannot start a tournament with less than 2 registered teams."))

    # Parse and validate setup configurations
    try:
        winning_point = int(request.form.get('winning_point', 21))
        if winning_point < 11 or winning_point > 30:
            raise ValueError("Winning point must be between 11 and 30.")
    except ValueError as e:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e)))

    try:
        num_sets = int(request.form.get('num_sets', 3))
        if num_sets not in [1, 3, 5]:
            raise ValueError("Number of sets must be 1, 3, or 5.")
    except ValueError as e:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e)))

    try:
        num_groups = int(request.form.get('num_groups', 2))
        if num_groups < 1 or num_groups > 16:
            raise ValueError("Number of groups must be between 1 and 16.")
    except ValueError as e:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e)))

    try:
        teams_per_group = int(request.form.get('teams_per_group', 4))
        if teams_per_group < 2 or teams_per_group > 32:
            raise ValueError("Teams per group must be between 2 and 32.")
    except ValueError as e:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=str(e)))

    fixture_type = request.form.get('fixture_type')
    if not fixture_type:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Fixture Mode must be selected to start the tournament."))

    if fixture_type not in ['leagues', 'groups', 'groups_leagues']:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Invalid fixture mode selected."))

    if num_groups == 1 and fixture_type != 'leagues':
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="For 1 group, leagues is the only supported fixture mode."))

    total_capacity = num_groups * teams_per_group
    if len(teams) > total_capacity:
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error=f"The number of registered teams ({len(teams)}) exceeds the configured total capacity ({total_capacity}). Please adjust the number of groups or teams per group."))

    # Save setup configurations to tournament record
    tournament['winning_point'] = winning_point
    tournament['num_sets'] = num_sets
    tournament['num_groups'] = num_groups
    tournament['teams_per_group'] = teams_per_group
    tournament['fixture_type'] = fixture_type

    # Generate fixtures
    matches = []
    groups = {}

    if fixture_type == 'leagues':
        matches = generate_round_robin(teams)
    else:
        # Partition registered teams into defined number of groups
        for i, t in enumerate(teams):
            group_idx = i % num_groups
            group_name = chr(65 + group_idx)
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(t)

        tournament['groups'] = groups
        for g_name, g_teams in groups.items():
            matches.extend(generate_round_robin(g_teams, g_name))

    tournament['matches'] = matches
    tournament['open_registration'] = False

    if save_tournament(tournament):
        return redirect(url_for('tournament_details_page', tourney_id=tourney_id, success="Registration closed and fixtures generated! Tournament started!"))

    return redirect(url_for('tournament_details_page', tourney_id=tourney_id, error="Failed to save tournament startup."))

@app.route('/logout', methods=['POST'])
def handle_logout():
    """Clear session data and sign out."""
    session.clear()
    return redirect(url_for('login_page', success="You have been signed out successfully."))

# Security Headers Enforcer
@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

if __name__ == '__main__':
    # Listen only on localhost/127.0.0.1 for secure local execution
    app.run(host='127.0.0.1', port=5000, debug=True)

