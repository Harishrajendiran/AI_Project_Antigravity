import os
import sys
import uuid
import pymysql

# Add parent directory to path to import app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, get_db_connection

def setup_test_db_user():
    # Make sure we have the test user initialized in the DB
    print("Testing DB Connection...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM users WHERE username = 'admin'")
            if not cursor.fetchone():
                print("Error: 'admin' user not found in database.")
                sys.exit(1)
            print("DB Connection OK. 'admin' user present.")
    finally:
        conn.close()

def run_tests():
    setup_test_db_user()

    # Create a test client
    client = app.test_client()

    print("\n1. Logging in as admin...")
    # Get CSRF token first by visiting login page
    resp = client.get('/')
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        csrf_token = sess.get('csrf_token')
        print(f"CSRF Token resolved: {csrf_token}")

    login_data = {
        'username': 'admin',
        'password': 'admin123',
        'csrf_token': csrf_token
    }
    resp = client.post('/login', data=login_data, follow_redirects=True)
    assert resp.status_code == 200
    print("Login successful.")

    # Create new tournament
    print("\n2. Creating a new test tournament...")
    tourney_name = f"Test Tourney {uuid.uuid4().hex[:6]}"
    create_data = {
        'name': tourney_name,
        'entry_deadline': '2026-12-31',
        'open_registration': '1',
        'csrf_token': csrf_token
    }
    resp = client.post('/tournament/new', data=create_data, follow_redirects=True)
    assert resp.status_code == 200
    print(f"Tournament '{tourney_name}' created.")

    # Retrieve tournament ID from database
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM tournaments WHERE name = %s", (tourney_name,))
            tourney_id = cursor.fetchone()['id']
            print(f"Tournament ID: {tourney_id}")
    finally:
        conn.close()

    # Register 5 teams
    print("\n3. Registering 5 teams to tournament...")
    teams = ["Team Alpha", "Team Beta", "Team Gamma", "Team Delta", "Team Epsilon"]
    for team in teams:
        reg_data = {
            'team_name': team,
            'csrf_token': csrf_token
        }
        resp = client.post(f'/tournament/{tourney_id}/register_team', data=reg_data, follow_redirects=True)
        assert resp.status_code == 200
        print(f"Registered {team}")

    # Start tournament with 3 groups (custom number of groups!)
    print("\n4. Starting tournament with 3 groups and 5 teams (underfilled)...")
    start_data = {
        'fixture_type': 'groups_leagues',
        'winning_point': '21',
        'num_sets': '3',
        'num_groups': '3',
        'teams_per_group': '4',
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/start', data=start_data, follow_redirects=True)
    assert resp.status_code == 200
    print("Tournament started successfully without blocking!")

    # Verify matches in DB (Group A: Alpha vs Delta; Group B: Beta vs Epsilon; Group C: Gamma has no match)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s", (tourney_id,))
            matches = cursor.fetchall()
            print(f"Total fixtures generated: {len(matches)}")
            assert len(matches) == 2
            for match in matches:
                print(f"Fixture: {match['team1']} vs {match['team2']} (Group {match['group_name']})")
    finally:
        conn.close()

    # Complete the two group stage matches
    print("\n5. Completing Group Stage matches...")
    for idx, match in enumerate(matches):
        for s_idx in ['1', '2']:
            score_data = {
                'match_id': match['id'],
                'set_num': s_idx,
                'num_sets': '3',
                'score1': '21',
                'score2': '15',
                'csrf_token': csrf_token
            }
            resp = client.post(f'/tournament/{tourney_id}/score', data=score_data, follow_redirects=True)
            assert resp.status_code == 200
        print(f"Match {idx+1} completed.")

    # Generate Quarter-finals
    print("\n6. Generating knockout brackets (3 groups -> 8-team Quarter-finals)...")
    resp = client.post(f'/tournament/{tourney_id}/knockout', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert resp.status_code == 200
    print("Knockout bracket generation successful!")

    # Verify Quarter-finals and check auto-completed BYEs
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s AND stage = 'quarter'", (tourney_id,))
            qf_matches = cursor.fetchall()
            print(f"Quarter-final matches: {len(qf_matches)}")
            assert len(qf_matches) == 4
            
            pending_qf = None
            for idx, qm in enumerate(qf_matches):
                print(f"QF {idx+1}: {qm['team1']} vs {qm['team2']} (Status: {qm['status']})")
                if qm['status'] == 'pending':
                    pending_qf = qm
                    # This should be Alpha vs Gamma (since Winner A is Alpha, Runner B is Gamma)
                    assert qm['team1'] == 'Team Alpha'
                    assert qm['team2'] == 'Team Gamma'
                else:
                    # The other matches must involve 'BYE' and be auto-completed!
                    assert 'BYE' in [qm['team1'], qm['team2']]
            assert pending_qf is not None
    finally:
        conn.close()

    # Submit score for the only pending Quarter-final match (Alpha vs Gamma)
    print("\n7. Completing the pending Quarter-final match...")
    for s_idx in ['1', '2']:
        score_data = {
            'match_id': pending_qf['id'],
            'set_num': s_idx,
            'num_sets': '3',
            'score1': '21',
            'score2': '18',
            'csrf_token': csrf_token
        }
        resp = client.post(f'/tournament/{tourney_id}/score', data=score_data, follow_redirects=True)
        assert resp.status_code == 200
    print("Pending Quarter-final match completed.")

    # Verify that Semi-finals were generated automatically as a result of QF completions
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s AND stage = 'semi'", (tourney_id,))
            semi_matches = cursor.fetchall()
            print(f"Semi-final matches generated: {len(semi_matches)}")
            assert len(semi_matches) == 2
            for idx, sm in enumerate(semi_matches):
                print(f"Semi-final {idx+1}: {sm['team1']} vs {sm['team2']} (Status: {sm['status']})")
    finally:
        conn.close()

    # Test PDF and Word exports (full and stage-filtered)
    print("\n7.5. Testing PDF and Word export routes...")
    # Full PDF export
    resp = client.get(f'/tournament/{tourney_id}/export/pdf')
    assert resp.status_code == 200
    assert b"Fixture Score Sheet" in resp.data or b"Fixture Schedule" in resp.data

    # Group stage PDF export
    resp = client.get(f'/tournament/{tourney_id}/export/pdf?stage=group')
    assert resp.status_code == 200
    assert b"Group Stage Fixtures" in resp.data

    # Quarter-final Word export
    resp = client.get(f'/tournament/{tourney_id}/export/word?stage=quarter')
    assert resp.status_code == 200
    assert resp.headers.get('Content-Type') == 'application/msword'
    assert b"Quarter-final Fixtures" in resp.data

    # Final Stage export (not generated yet -> should redirect to details page)
    resp = client.get(f'/tournament/{tourney_id}/export/pdf?stage=final', follow_redirects=True)
    assert resp.status_code == 200
    assert b"No matches generated for" in resp.data
    print("Export routes verification complete (all passed).")

    # Clean up test tournament
    print("\n8. Deleting test tournament...")
    delete_data = {
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/delete', data=delete_data, follow_redirects=True)
    assert resp.status_code == 200
    print("Test tournament cleaned up.")
    print("\nALL GENERIC BRACKET & PROGRESSION TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    run_tests()
