import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import (blank_progress, due_words, review_word, is_mastered, record_typed_result,
                  grade_lesson, summary_stats, check_typed_answer, validate_catalog,ensure_progress)
from storage import LocalStorage
ROOT=Path(__file__).resolve().parents[1]
VOCAB=json.loads((ROOT/'content/vocabulary.json').read_text(encoding='utf-8'))
LESSONS=json.loads((ROOT/'content/lessons.json').read_text(encoding='utf-8'))


def test_catalog():
    validate_catalog(VOCAB,LESSONS)
    assert len(VOCAB)>=140
    assert len(LESSONS)>=12
    assert all('2025' not in l['source_note'] for l in LESSONS)
    assert len({l['id'] for l in LESSONS})==len(LESSONS)
    assert sum(len(l['questions']) for l in LESSONS)==48


def test_initial_review_queue_and_day_limit():
    state=blank_progress()
    day=date(2026,11,15)
    queue=due_words(VOCAB,state,day)
    assert len(queue)==6
    assert set(x['dutch'] for x in queue).issubset({
        'daarnaast','plaatsvinden','vooraf','zich aanmelden','twijfelen','af en toe','regelmatig','uiteindelijk'})
    for word in queue:
        review_word(state,word['id'],'Good',day)
    assert len(due_words(VOCAB,state,day))==0
    assert state['activity'][day.isoformat()]['new_words']==6
    assert len(due_words(VOCAB,state,date(2026,11,16)))>=6


def test_spaced_review_typed_mastery():
    state=blank_progress()
    word='daarnaast'
    review_word(state,word,'Good',date(2026,11,15))
    assert state['words'][word]['due']=='2026-11-16'
    review_word(state,word,'Good',date(2026,11,16))
    assert state['words'][word]['due']=='2026-11-19'
    review_word(state,word,'Good',date(2026,11,19))
    assert not is_mastered(state['words'][word])
    record_typed_result(state,word,True,date(2026,11,16))
    record_typed_result(state,word,True,date(2026,11,16))
    record_typed_result(state,word,True,date(2026,11,19))
    assert is_mastered(state['words'][word])
    assert len(state['words'][word]['typed_days'])==2


def test_typed_answers():
    word=next(w for w in VOCAB if w['dutch']=='zich aanmelden')
    assert check_typed_answer('ZICH   AANMELDEN',word)
    assert check_typed_answer('aanmelden',word)
    assert not check_typed_answer('aanvragen',word)


def test_lesson_grading_and_stats():
    state=blank_progress()
    lesson=LESSONS[0]
    answers={str(i):q['correct'] for i,q in enumerate(lesson['questions'])}
    assert grade_lesson(state,lesson,answers,date(2026,11,15))==4
    stats=summary_stats(state,VOCAB,LESSONS,date(2026,11,15))
    assert stats['lesson_count']==1
    assert stats['accuracy']==100
    assert stats['streak']==1


def test_local_storage_survives_new_instance(tmp_path):
    file=tmp_path/'progress.json'
    first=LocalStorage(file)
    s=blank_progress()
    review_word(s,'daarnaast','Hard',date(2026,11,15))
    first.save(s,'main')
    other=LocalStorage(file)
    assert other.load('main')['words']['daarnaast']['last_grade']=='Hard'
    assert other.load('other')['words']=={}
    assert ensure_progress({'words':[]})['words']=={}
