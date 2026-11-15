import pytest
import storage


def test_local_used_only_without_cloud_config(tmp_path):
    result = storage.make_storage({}, str(tmp_path / 'progress.json'))
    assert isinstance(result, storage.LocalStorage)


def test_partial_cloud_config_does_not_fall_back(tmp_path):
    with pytest.raises(RuntimeError, match=r'gcp_service_account'):
        storage.make_storage({'gsheets': {'spreadsheet_id': 'a-sheet'}}, str(tmp_path / 'progress.json'))


def test_missing_sheet_id_does_not_fall_back(tmp_path):
    with pytest.raises(RuntimeError, match=r'spreadsheet_id'):
        storage.make_storage({'gsheets': {}, 'gcp_service_account': {}}, str(tmp_path / 'progress.json'))


def test_missing_credential_fields_does_not_fall_back(tmp_path):
    with pytest.raises(RuntimeError, match=r'service account field'):
        storage.make_storage({'gsheets': {'spreadsheet_id': 'valid-sheet'}, 'gcp_service_account': {}}, str(tmp_path / 'progress.json'))


def test_configured_cloud_storage_is_selected(monkeypatch, tmp_path):
    class FakeCloudStorage:
        def __init__(self, credentials, spreadsheet_id, worksheet):
            self.credentials = credentials
            self.spreadsheet_id = spreadsheet_id
            self.worksheet = worksheet

    monkeypatch.setattr(storage, 'GoogleSheetsStorage', FakeCloudStorage)
    secrets = {
        'gsheets': {'spreadsheet_id': 'valid-sheet', 'worksheet': 'progress'},
        'gcp_service_account': {
            'type': 'service_account',
            'project_id': 'study-project',
            'private_key_id': 'key-id',
            'private_key': 'not-a-real-key',
            'client_email': 'study@example.org',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }
    result = storage.make_storage(secrets, str(tmp_path / 'progress.json'))
    assert isinstance(result, FakeCloudStorage)
    assert result.spreadsheet_id == 'valid-sheet'
    assert result.worksheet == 'progress'
