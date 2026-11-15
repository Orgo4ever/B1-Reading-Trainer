"""Pure functions for the B1 Reading Trainer. No Streamlit dependency."""
from __future__ import annotations
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from collections import Counter
import unicodedata
import re

AMSTERDAM = ZoneInfo('Europe/Amsterdam')
GRADES = ('Again', 'Hard', 'Good', 'Easy')


def local_today() -> date:
    return datetime.now(AMSTERDAM).date()


def blank_progress():
    return {'schema_version': 1, 'words': {}, 'lessons': {}, 'activity': {}, 'mocks': [], 'custom_words': [], 'settings': {'daily_new_goal': 6}}


def ensure_progress(raw):
    if not isinstance(raw, dict):
        return blank_progress()
    output = blank_progress()
    for section in ('words', 'lessons', 'activity'):
        if isinstance(raw.get(section), dict):
            output[section] = raw[section]
    if isinstance(raw.get('mocks'), list):
        output['mocks'] = raw['mocks'][-50:]
    if isinstance(raw.get('custom_words'), list):
        output['custom_words'] = raw['custom_words'][:2000]
    if isinstance(raw.get('settings'), dict):
        output['settings'].update(raw['settings'])
    return output


def today_activity(state, today=None):
    day = (today or local_today()).isoformat()
    return state['activity'].setdefault(day, {'new_words': 0, 'reviews': 0, 'lessons': 0, 'typed_correct': 0})


def due_words(vocab, state, today=None, new_limit=None, theme='All'):
    """Due words first, then a limited number of new words, in stable order."""
    now = (today or local_today()).isoformat()
    word_state = state.get('words', {})
    words = [v for v in vocab if theme == 'All' or v['theme'] == theme]
    due = [v for v in words if v['id'] in word_state and word_state[v['id']].get('due', now) <= now
           and word_state[v['id']].get('last_review_day') != now]
    due.sort(key=lambda v: (word_state[v['id']].get('due', now), v['priority'], v['dutch']))
    day_activity = state.get('activity', {}).get(now, {})
    remaining = max(0, int(new_limit if new_limit is not None else state.get('settings', {}).get('daily_new_goal', 6)) - int(day_activity.get('new_words', 0)))
    fresh = [v for v in sorted(words, key=lambda v: (v['priority'], v['dutch'])) if v['id'] not in word_state]
    return due + fresh[:remaining]


def review_word(state, word_id, grade, today=None):
    if grade not in GRADES:
        raise ValueError('Unknown card rating')
    day = today or local_today()
    key = day.isoformat()
    prev = state['words'].get(word_id, {})
    was_new = not prev
    ease = float(prev.get('ease', 2.5))
    reps = int(prev.get('reps', 0))
    interval = int(prev.get('interval', 0))
    if grade == 'Again':
        interval = 1
        reps = 0
        ease = max(1.3, ease - 0.2)
    elif grade == 'Hard':
        interval = 1 if reps < 1 else max(2, round(interval * 1.2))
        reps += 1
        ease = max(1.3, ease - 0.15)
    elif grade == 'Good':
        interval = 1 if reps == 0 else (3 if reps == 1 else max(4, round(interval * ease)))
        reps += 1
    elif grade == 'Easy':
        interval = 3 if reps == 0 else (7 if reps == 1 else max(8, round(interval * ease * 1.3)))
        ease += 0.1
        reps += 1
    record = dict(prev)
    record.update(reps=reps, ease=round(ease, 2), interval=interval, due=(day + timedelta(days=interval)).isoformat(), last_review_day=key, last_grade=grade, reviews=int(prev.get('reviews', 0))+1)
    record.setdefault('typed_days', [])
    state['words'][word_id] = record
    activity = today_activity(state, day)
    activity['new_words' if was_new else 'reviews'] += 1
    return record


def simplify(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', text)).strip()


def check_typed_answer(answer, word):
    accepted = [word['dutch']]
    # Reflexive lemmas: allow the answer without 'zich' as well as the exact dictionary form.
    if word['dutch'].startswith('zich '):
        accepted.append(word['dutch'][5:])
    return simplify(answer) in {simplify(w) for w in accepted}


def record_typed_result(state, word_id, correct, today=None):
    if not correct:
        return
    day = (today or local_today()).isoformat()
    record = state['words'].setdefault(word_id, {'due': day, 'ease': 2.5, 'interval': 0, 'reps': 0, 'reviews': 0})
    days = record.setdefault('typed_days', [])
    if day not in days:
        days.append(day)
        today_activity(state, date.fromisoformat(day))['typed_correct'] += 1


def is_mastered(record):
    """Conservative: spaced review plus correct typed recall on 2 different days."""
    return int(record.get('reps', 0)) >= 3 and len(set(record.get('typed_days', []))) >= 2


def grade_lesson(state, lesson, submitted, today=None):
    if len(submitted) != len(lesson['questions']):
        raise ValueError('You must answer every question')
    count = sum(submitted.get(str(i)) == q['correct'] for i, q in enumerate(lesson['questions']))
    day = (today or local_today()).isoformat()
    history = state['lessons'].setdefault(lesson['id'], {'attempts': []})['attempts']
    history.append({'date': day, 'score': count, 'max_score': len(lesson['questions']), 'answers': dict(submitted)})
    history[:] = history[-30:]
    today_activity(state, date.fromisoformat(day))['lessons'] += 1
    return count


def summary_stats(state, vocab, lessons, today=None):
    reviewed = len(state.get('words', {}))
    mastered = sum(is_mastered(w) for w in state.get('words', {}).values())
    lesson_count = sum(bool(v.get('attempts')) for v in state.get('lessons', {}).values())
    latest = [v['attempts'][-1] for v in state.get('lessons', {}).values() if v.get('attempts')]
    acc = (100 * sum(a['score'] for a in latest) / sum(a['max_score'] for a in latest)) if latest else None
    day = today or local_today()
    streak = 0
    while sum(state.get('activity', {}).get((day - timedelta(days=streak)).isoformat(), {}).values()) > 0:
        streak += 1
    return dict(introduced=reviewed, mastered=mastered, lesson_count=lesson_count, lesson_total=len(lessons), accuracy=acc, streak=streak)


def validate_catalog(vocab, lessons):
    ids = [w['id'] for w in vocab]
    assert len(ids) == len(set(ids)), 'Duplicate vocabulary IDs'
    vocab_ids = set(ids)
    for w in vocab:
        for f in ('dutch', 'english', 'example', 'theme'):
            assert w.get(f), f'Missing {f} for {w["id"]}'
    for l in lessons:
        assert set(l['word_ids']).issubset(vocab_ids), f'Unknown lesson vocabulary: {l["id"]}'
        assert 1 <= len(l['questions']) <= 20
        for q in l['questions']:
            assert q['correct'] in q['options']
            assert len(q['options']) >= 2
            assert q['explanation']


def add_mock(state, correct, minutes, comments, today=None):
    if not 0 <= correct <= 35:
        raise ValueError('Correct answers must be between 0 and 35')
    state['mocks'].append({'date': (today or local_today()).isoformat(), 'correct':correct, 'out_of':35, 'minutes':minutes, 'comments':comments})
    state['mocks'] = state['mocks'][-50:]
