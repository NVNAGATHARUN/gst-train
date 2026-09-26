"""Exercise the built web proxy against an isolated, labeled simulated backend fixture.

This checks transport/session and saved-artifact wiring. It is not a visual test.
"""
import os
import httpx


def main():
    credential = os.environ['RAILSYNC_VISUAL_CREDENTIAL']
    with httpx.Client(base_url='http://127.0.0.1:3000', timeout=20, trust_env=False) as client:
        page = client.get('/login')
        assert page.status_code == 200 and 'RailSync AI' in page.text
        login = client.post('/api/v1/auth/session', json={'credential': credential},
            headers={'Origin': 'http://127.0.0.1:3000'})
        assert login.status_code == 201, login.text
        assert 'railsync_session=' in login.headers['set-cookie'].lower()
        read = client.get('/api/v1/auth/session')
        assert read.status_code == 200, read.text
        assert read.json()['user']['role'] == 'PLANNER'
        snapshots = client.get('/api/v1/workspace/snapshots', params={'scenario': 'ANY', 'limit': 100})
        assert snapshots.status_code == 200, snapshots.text
        items = snapshots.json()['items']
        assert items, 'The isolated backend fixture must include at least one snapshot.'
        chosen = None
        revision_id = None
        selected_runs = []
        for item in items:
            runs = client.get('/api/v1/workspace/runs', params={'snapshot_id': item['id'], 'limit': 100})
            assert runs.status_code == 200, runs.text
            optimized = next((run for run in runs.json()['items']
                if run['planner_type'] == 'CP_SAT' and run['revision_ids']), None)
            if optimized:
                chosen = item
                revision_id = optimized['revision_ids'][0]
                selected_runs = runs.json()['items']
                break
        assert chosen and revision_id and chosen['source_scope'] == 'SIMULATED', 'The fixture needs a simulated saved CP-SAT proposal.'
        workspace = client.get(f"/api/v1/snapshots/{chosen['id']}/workspace",
            params={'plan_revision_id': revision_id})
        assert workspace.status_code == 200, workspace.text
        view = workspace.json()
        assert view['snapshot']['id'] == chosen['id']
        assert view['selected_revision']['id'] == revision_id
        assert view['facts']['occupancy'] and view['facts']['requests']
        assert view['availability'] and view['coordination']
        assert isinstance(view['availability'][0]['result']['windows'], list)
        assert 'clearance_before_minutes' in view['availability'][0]['policy']
        assert view['selected_run']['result']['solver_status'] in ('OPTIMAL', 'FEASIBLE')
        assert view['authority'] == 'SOFTWARE_PROPOSAL_ONLY'
        pages = {route: client.get('/' + route) for route in
            ('planning', 'corridor', 'evaluation', 'validation', 'review', 'optimization')}
        assert all(page.status_code == 200 and 'RailSync AI' in page.text for page in pages.values())
        artifacts = client.get('/api/v1/workspace/report-artifacts', params={'plan_revision_id': revision_id})
        assert artifacts.status_code == 200, artifacts.text
        assert artifacts.json()['revision']['snapshot_id'] == chosen['id']
        saved_comparisons = [row for row in artifacts.json()['comparisons'] if row['role'] == 'RAILSYNC']
        comparison_status = 'NO_SAVED_COMPARISON'
        if saved_comparisons:
            saved = client.get('/api/v1/plan-comparisons/' + saved_comparisons[0]['id'])
            assert saved.status_code == 200, saved.text
            comparison = saved.json()
            baseline_ids = [revision for run in selected_runs if run['planner_type'] == 'BASELINE'
                for revision in run['revision_ids']]
            assert comparison['content']['snapshot_id'] == chosen['id']
            assert comparison['content']['snapshot_hash'] == chosen['content_hash']
            assert comparison['content']['railsync']['plan_revision_id'] == revision_id
            assert comparison['content']['baseline']['plan_revision_id'] in baseline_ids
            comparison_status = comparison['content']['status']
        sessions = client.get('/api/v1/workspace/planning-sessions', params={'snapshot_id':chosen['id']})
        assert sessions.status_code == 200 and isinstance(sessions.json()['items'], list)
        print({'login': login.status_code, 'session': read.status_code,
            'snapshot_count': len(items), 'selected_source': chosen['source_scope'],
            'occupancy_count': len(view['facts']['occupancy']),
            'demand_count': len(view['demands']),
            'candidate_count': len(view['coordination']['result']['candidates']),
            'revision': True, 'hero_pages': {route: pages[route].status_code for route in
                ('planning', 'corridor', 'evaluation', 'validation', 'review')},
            'optimization_page': pages['optimization'].status_code,
            'solver_status': view['selected_run']['result']['solver_status'],
            'capacity_windows': len(view['availability'][0]['result']['windows']),
            'saved_comparison_status': comparison_status})


if __name__ == '__main__':
    main()
