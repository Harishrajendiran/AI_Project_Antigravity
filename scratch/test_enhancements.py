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

    # Register 8 teams
    print("\n3. Registering 8 teams to tournament...")
    teams = ["Team Alpha", "Team Beta", "Team Delta", "Team Epsilon", "Team Eta", "Team Gamma", "Team Theta", "Team Zeta"]
    for team in teams:
        reg_data = {
            'team_name': team,
            'csrf_token': csrf_token
        }
        resp = client.post(f'/tournament/{tourney_id}/register_team', data=reg_data, follow_redirects=True)
        assert resp.status_code == 200
        print(f"Registered {team}")

    # Start tournament with 4 groups and 2 teams per group, 2 promoted per group
    print("\n4. Starting tournament with 4 groups, 2 teams per group, 2 promoted per group...")
    start_data = {
        'fixture_type': 'groups_leagues',
        'winning_point': '21',
        'num_sets': '3',
        'num_groups': '4',
        'teams_per_group': '2',
        'promoted_per_group': '2',
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/start', data=start_data, follow_redirects=True)
    assert resp.status_code == 200
    print("Tournament started successfully!")

    # Verify matches in DB (4 matches expected)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s", (tourney_id,))
            matches = cursor.fetchall()
            print(f"Total group stage fixtures: {len(matches)}")
            assert len(matches) == 4
            for m in matches:
                print(f"Fixture: {m['team1']} vs {m['team2']} (Group {m['group_name']})")
    finally:
        conn.close()

    # Complete the group stage matches
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
        print(f"Group match {idx+1} completed.")

    # 5.5. Testing manual promotion override (checking ticks/checkboxes toggling)
    print("\n5.5. Testing manual promotion override...")
    # Trigger auto-promotion by calling GET on tournament details page
    resp = client.get(f'/tournament/{tourney_id}')
    assert resp.status_code == 200

    # Verify that all 8 teams are auto-promoted initially
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT team_name FROM tournament_teams WHERE tournament_id = %s AND is_promoted = 1", (tourney_id,))
            promoted = [row['team_name'] for row in cursor.fetchall()]
            print(f"Initially auto-promoted teams ({len(promoted)}): {promoted}")
            assert len(promoted) == 8
    finally:
        conn.close()

    # Test selected count restriction: demote Team Alpha so count becomes 7 (which is invalid)
    print("Demoting Team Alpha to make selected count = 7...")
    promote_data_alpha = {
        'team_name': 'Team Alpha',
        'promote': '0',
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/promote_team', data=promote_data_alpha)
    assert resp.status_code == 200
    assert resp.json['success'] is True
    assert resp.json['promoted'] is False

    # Attempt to generate knockout stage with 7 teams -> should FAIL validation
    print("Attempting to generate knockout with 7 teams (should fail)...")
    resp = client.post(f'/tournament/{tourney_id}/knockout', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Knockout fixtures can only be generated if the selected team count is exactly 8, 16, or 32" in resp.data
    print("Knockout generation blocked correctly for invalid count.")

    # Re-promote Team Alpha to restore count to 8
    print("Re-promoting Team Alpha to restore count to 8...")
    promote_data_alpha_back = {
        'team_name': 'Team Alpha',
        'promote': '1',
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/promote_team', data=promote_data_alpha_back)
    assert resp.status_code == 200
    assert resp.json['success'] is True
    assert resp.json['promoted'] is True

    # Generate Quarter-finals directly (8 selected teams -> 8-team Quarter-finals)
    print("\n6. Generating knockout brackets (8 selected teams -> 8-team Quarter-finals)...")
    resp = client.post(f'/tournament/{tourney_id}/knockout', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert resp.status_code == 200
    print("Knockout bracket generation successful!")

    # Verify Quarter-finals matches (4 matches)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s AND stage = 'quarter'", (tourney_id,))
            q_matches = cursor.fetchall()
            print(f"Quarter-final matches: {len(q_matches)}")
            assert len(q_matches) == 4
            for idx, qm in enumerate(q_matches):
                print(f"Quarter-final {idx+1}: {qm['team1']} vs {qm['team2']} (Status: {qm['status']})")
                assert qm['status'] == 'pending'
    finally:
        conn.close()

    # Complete Quarter-finals
    print("\n6.5. Completing Quarter-final matches...")
    for idx, qm in enumerate(q_matches):
        for s_idx in ['1', '2']:
            score_data = {
                'match_id': qm['id'],
                'set_num': s_idx,
                'num_sets': '3',
                'score1': '21',
                'score2': '15',
                'csrf_token': csrf_token
            }
            resp = client.post(f'/tournament/{tourney_id}/score', data=score_data, follow_redirects=True)
            assert resp.status_code == 200
        print(f"Quarter-final {idx+1} completed.")

    # Verify Semi-finals (2 matches should have been automatically generated)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s AND stage = 'semi'", (tourney_id,))
            semi_matches = cursor.fetchall()
            print(f"Semi-final matches generated: {len(semi_matches)}")
            assert len(semi_matches) == 2
            for idx, sm in enumerate(semi_matches):
                print(f"Semi-final {idx+1}: {sm['team1']} vs {sm['team2']} (Status: {sm['status']})")
                assert sm['status'] == 'pending'
    finally:
        conn.close()

    # Complete Semi-finals
    print("\n7. Completing Semi-final matches...")
    for idx, sm in enumerate(semi_matches):
        for s_idx in ['1', '2']:
            score_data = {
                'match_id': sm['id'],
                'set_num': s_idx,
                'num_sets': '3',
                'score1': '21',
                'score2': '15',
                'csrf_token': csrf_token
            }
            resp = client.post(f'/tournament/{tourney_id}/score', data=score_data, follow_redirects=True)
            assert resp.status_code == 200
        print(f"Semi-final {idx+1} completed.")

    # Verify that Final was generated automatically
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM matches WHERE tournament_id = %s AND stage = 'final'", (tourney_id,))
            final_matches = cursor.fetchall()
            print(f"Final matches generated: {len(final_matches)}")
            assert len(final_matches) == 1
            for idx, fm in enumerate(final_matches):
                print(f"Final {idx+1}: {fm['team1']} vs {fm['team2']} (Status: {fm['status']})")
                assert fm['status'] == 'pending'
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
    assert b"Group" in resp.data

    # Semi-final Word export
    resp = client.get(f'/tournament/{tourney_id}/export/word?stage=semi')
    assert resp.status_code == 200
    assert resp.headers.get('Content-Type') == 'application/msword'
    assert b"semi" in resp.data

    # Export routes verification complete
    print("Export routes verification complete (all passed).")

    # 7.8. Testing Reset Fixtures
    print("\n7.8. Testing Reset Fixtures endpoint...")
    reset_data = {
        'csrf_token': csrf_token
    }
    resp = client.post(f'/tournament/{tourney_id}/reset_fixtures', data=reset_data, follow_redirects=True)
    assert resp.status_code == 200
    print("Reset fixtures POST request successful.")

    # Query DB to assert clean state
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check tournament metadata
            cursor.execute("SELECT fixture_type, status, open_registration FROM tournaments WHERE id = %s", (tourney_id,))
            tourney = cursor.fetchone()
            print(f"Tournament state after reset: fixture_type={tourney['fixture_type']}, status={tourney['status']}, open_registration={tourney['open_registration']}")
            assert tourney['fixture_type'] is None
            assert tourney['status'] == 'active'
            assert tourney['open_registration'] == 1

            # Check matches are deleted
            cursor.execute("SELECT COUNT(*) as cnt FROM matches WHERE tournament_id = %s", (tourney_id,))
            match_count = cursor.fetchone()['cnt']
            print(f"Match count after reset: {match_count}")
            assert match_count == 0

            # Check group assignments are deleted
            cursor.execute("SELECT COUNT(*) as cnt FROM tournament_groups WHERE tournament_id = %s", (tourney_id,))
            group_count = cursor.fetchone()['cnt']
            print(f"Group count after reset: {group_count}")
            assert group_count == 0

            # Check team registrations are preserved but is_promoted is reset
            cursor.execute("SELECT team_name, is_promoted FROM tournament_teams WHERE tournament_id = %s", (tourney_id,))
            teams_rows = cursor.fetchall()
            print(f"Registered teams remaining: {len(teams_rows)}")
            assert len(teams_rows) == 8
            for row in teams_rows:
                assert row['is_promoted'] == 0
            print("Verified: all 8 teams preserved and is_promoted reset to 0.")
    finally:
        conn.close()

    print("Reset fixtures endpoint verification complete (all assertions passed).")

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
