"""Durable progress providers: local atomic JSON or optional Google Sheets sync."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from core import ensure_progress, blank_progress


class LocalStorage:
    mode = 'Local JSON'
    def __init__(self, path='data/progress.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, user_id='main'):
        if not self.path.exists():
            return blank_progress()
        try:
            payload=json.loads(self.path.read_text(encoding='utf-8'))
            return ensure_progress(payload.get(user_id))
        except (OSError, ValueError, TypeError):
            raise RuntimeError('Could not read the local progress file. Restore from a backup rather than overwriting it.')

    def save(self, state, user_id='main'):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        except (OSError, ValueError):
            raise RuntimeError('Progress file is unreadable; refusing to overwrite it.')
        data[user_id]=ensure_progress(state)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, self.path)


class GoogleSheetsStorage:
    mode = 'Google Sheets (cross-device)'
    def __init__(self, credentials, spreadsheet_id, worksheet='progress'):
        import gspread
        from gspread.exceptions import WorksheetNotFound
        client = gspread.service_account_from_dict(credentials)
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            self.sheet = spreadsheet.worksheet(worksheet)
        except WorksheetNotFound:
            self.sheet=spreadsheet.add_worksheet(title=worksheet, rows=100, cols=16)
        if not self.sheet.get_all_values():
            self.sheet.append_row(['user_id','updated_at','state_part_1'], value_input_option='RAW')

    def _find(self, user_id):
        vals = self.sheet.get_all_values()
        for idx,row in enumerate(vals[1:], start=2):
            if row and row[0]==user_id:
                return idx,row
        return None,None

    def load(self, user_id='main'):
        _,row=self._find(user_id)
        if not row or len(row)<3:
            return blank_progress()
        try:
            return ensure_progress(json.loads(''.join(row[2:])))
        except (ValueError,TypeError):
            raise RuntimeError('Google Sheets progress data is invalid. Restore a JSON backup.')

    def save(self,state,user_id='main'):
        import gspread
        serialized=json.dumps(ensure_progress(state),ensure_ascii=False,separators=(',',':'))
        chunks=[serialized[i:i+35000] for i in range(0,len(serialized),35000)]
        if len(chunks)>12:
            raise RuntimeError('Progress record is too large for Google Sheets. Export a backup.')
        row=[user_id,datetime.now(timezone.utc).isoformat()]+chunks
        index,existing=self._find(user_id)
        if index is None:
            self.sheet.append_row(row,value_input_option='RAW')
        else:
            # Replace all chunk cells in one Sheets update, including old trailing chunks.
            padded=row + [''] * (14-len(row))
            self.sheet.update(range_name=f'A{index}:N{index}',values=[padded],value_input_option='RAW')


def make_storage(secrets, local_path='data/progress.json'):
    """Use local storage only when cloud settings are entirely absent.

    Once cloud sync is configured, never silently fall back to volatile local JSON:
    surface configuration / connectivity problems so progress cannot be lost.
    """
    try:
        configured = set(secrets.keys())
    except FileNotFoundError:
        configured = set()

    have_sheet = 'gsheets' in configured
    have_account = 'gcp_service_account' in configured
    if not have_sheet and not have_account:
        return LocalStorage(local_path)
    if not have_sheet:
        raise RuntimeError('Google Sheets setup incomplete: [gsheets] section missing in Streamlit Secrets.')
    if not have_account:
        raise RuntimeError('Google Sheets setup incomplete: [gcp_service_account] section missing in Streamlit Secrets.')

    cfg = dict(secrets['gsheets'])
    credentials = dict(secrets['gcp_service_account'])
    spreadsheet_id = str(cfg.get('spreadsheet_id', '')).strip()
    if not spreadsheet_id or spreadsheet_id.startswith('YOUR_'):
        raise RuntimeError('Google Sheets setup incomplete: [gsheets].spreadsheet_id is missing or still a placeholder.')

    required = ('type', 'project_id', 'private_key_id', 'private_key', 'client_email', 'token_uri')
    missing = [key for key in required if not str(credentials.get(key, '')).strip()
               or str(credentials[key]).startswith(('YOUR_', 'COPY_FROM_'))]
    if missing:
        raise RuntimeError('Google Sheets setup incomplete: service account field(s) missing or placeholders: ' + ', '.join(missing))

    try:
        return GoogleSheetsStorage(credentials, spreadsheet_id, str(cfg.get('worksheet') or 'progress'))
    except Exception as exc:
        # Do not render an API exception directly: it may contain sensitive identifiers.
        raise RuntimeError(
            'Google Sheets connection failed (' + type(exc).__name__ +
            '). Check the spreadsheet ID, Sheets API, service-account key and Editor sharing permission.'
        ) from exc
