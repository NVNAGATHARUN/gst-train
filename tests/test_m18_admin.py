from conftest import auth
from test_m10 import START, END, policy, profile


def test_admin_collections_show_persisted_revisions_and_respect_roles(client):
    resource = {'id': 'CREW-ADMIN-1', 'resource_type': 'TRACK_CREW',
                'department': 'ENGINEERING', 'available_start': START,
                'available_end': END, 'source_mode': 'SIMULATED'}
    assert client.post('/api/v1/resources', json=resource, headers=auth()).status_code == 201
    saved_profile = client.post('/api/v1/resources/CREW-ADMIN-1/profiles',
        json={'expected_revision': 0, 'data': profile()}, headers=auth()).json()
    saved_policy = client.post('/api/v1/coordination-policies/DEMO-ADMIN',
        json={'expected_revision': 0, 'data': policy()}, headers=auth()).json()

    resources = client.get('/api/v1/resources', headers=auth('AUDITOR'))
    assert resources.status_code == 200
    assert resources.json()['items'] == [resource]
    assert client.get('/api/v1/resources', headers=auth('ENGINEERING')).status_code == 403

    profiles = client.get('/api/v1/coordination-rules?kind=RESOURCE_PROFILE', headers=auth('CONTROLLER'))
    assert profiles.status_code == 200
    assert profiles.json()['items'] == [saved_profile]
    policies = client.get('/api/v1/coordination-rules?kind=POLICY&key=DEMO-ADMIN', headers=auth('AUDITOR'))
    assert policies.json()['items'] == [saved_policy]
    assert client.get('/api/v1/coordination-rules', headers=auth('TRD')).status_code == 403

    updated = client.post('/api/v1/coordination-policies/DEMO-ADMIN',
        json={'expected_revision': 1, 'data': policy('FORBID')}, headers=auth()).json()
    history = client.get('/api/v1/coordination-rules?kind=POLICY&key=DEMO-ADMIN',
        headers=auth('AUDITOR')).json()['items']
    assert [row['revision'] for row in history] == [2, 1]
    assert history[0]['id'] == updated['id']
    assert history[1]['id'] == saved_policy['id']
