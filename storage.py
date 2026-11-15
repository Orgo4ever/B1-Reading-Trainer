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
    try:
        gs = dict(secrets['gcp_service_account'])
        cfg = dict(secrets['gsheets'])
        spreadsheet_id = cfg['spreadsheet_id']
        return GoogleSheetsStorage(gs, spreadsheet_id, cfg.get('worksheet', 'progress'))
    except (KeyError, FileNotFoundError):
        return LocalStorage(local_path)
