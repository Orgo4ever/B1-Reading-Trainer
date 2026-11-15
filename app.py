"""Streamlit B1 Reading Trainer — independent from DutchLearner and Woordkracht."""
from __future__ import annotations
import csv
import hmac
import io
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core import (blank_progress, ensure_progress, due_words, review_word, grade_lesson,
                  summary_stats, local_today, check_typed_answer, record_typed_result,
                  is_mastered, add_mock, validate_catalog)
from storage import make_storage

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='B1 Reading Trainer',page_icon='📖',layout='wide',initial_sidebar_state='expanded')

@st.cache_data(show_spinner=False)
def load_content():
    vocab=json.loads((ROOT/'content'/'vocabulary.json').read_text(encoding='utf-8'))
    lessons=json.loads((ROOT/'content'/'lessons.json').read_text(encoding='utf-8'))
    validate_catalog(vocab,lessons)
    return vocab,lessons

BASE_VOCAB,LESSONS=load_content()

def secret_or(name,default=None):
    try:
        return st.secrets.get(name, default)
    except (FileNotFoundError, KeyError):
        return default

# Optional single-person access protection for a deployed app.
passcode=secret_or('APP_PASSCODE')
if passcode:
    if not st.session_state.get('signed_in'):
        st.title('📖 B1 Reading Trainer')
        attempt=st.text_input('Enter your personal app passcode',type='password')
        if st.button('Unlock',type='primary'):
            if hmac.compare_digest(attempt,str(passcode)):
                st.session_state['signed_in']=True
                st.rerun()
            else:
                st.error('The passcode is incorrect.')
        st.stop()

@st.cache_resource(show_spinner=False)
def get_store():
    return make_storage(st.secrets,local_path=str(ROOT/'data'/'progress.json'))

try:
    store=get_store()
except Exception as e:
    st.error(f'Could not connect to progress storage: {e}')
    st.info('Check your Google Sheet ID, permissions, and Streamlit secrets. Your data has not been overwritten.')
    st.stop()

USER_ID=str(secret_or('USER_ID','main'))
if 'progress' not in st.session_state:
    try:
        st.session_state['progress']=store.load(USER_ID)
    except Exception as e:
        st.error(f'Could not load your saved progress: {e}')
        st.stop()

state=st.session_state['progress']

def save():
    try:
        store.save(st.session_state['progress'],USER_ID)
        st.session_state['last_saved']=local_today().isoformat()
        return True
    except Exception as e:
        st.error(f'Save failed: {e}. Export a JSON backup from Settings to protect your current session.')
        return False

VOCAB=BASE_VOCAB + state.get('custom_words',[])
WORDS={v['id']:v for v in VOCAB}
TODAY=local_today()
st.markdown('''<style>
.block-container {padding-top:1.6rem;padding-bottom:3rem;max-width:1080px}
[data-testid="stSidebar"] {border-right:1px solid rgba(128,128,128,.12)}
[data-testid="stMetricValue"] {font-size:1.65rem}
div.stButton > button {border-radius:0.5rem}
</style>''', unsafe_allow_html=True)

with st.sidebar:
    st.title('📖 B1 Reading')
    st.caption('NT2 Programma I · Lezen')
    menu=st.radio('Go to', ['Today','Flashcards','Reading lessons','Progress','Exam prep','Settings'],label_visibility='collapsed')
    st.divider()
    ss=summary_stats(state,VOCAB,LESSONS,TODAY)
    st.metric('Words introduced', ss['introduced'])
    st.metric('Lessons completed', f"{ss['lesson_count']}/{ss['lesson_total']}")
    st.caption(f'🗓️ {TODAY.strftime("%d %b %Y")} · {store.mode}')
    if store.mode=='Local JSON':
        st.warning('Local progress is saved on this server. Streamlit Community Cloud may erase it during restarts. Connect Google Sheets before relying on cross-device progress.',icon='⚠️')


def review_card():
    queue=due_words(VOCAB,state,TODAY)
    if not queue:
        st.success('Vocabulary goal complete for today. Return tomorrow for your next review.')
        return
    current=queue[0]
    key=current['id']
    st.caption(f"{len(queue)} word(s) in today's queue · {current['theme'].title()}")
    st.subheader(current['dutch'])
    st.caption('Recall the English meaning first. Then reveal the answer.')
    reveal=st.session_state.get('reveal_word') == key
    if not reveal:
        if st.button('Reveal meaning',type='primary',key=f'reveal_{key}'):
            st.session_state['reveal_word']=key
            st.rerun()
    else:
        st.info(f"**{current['english']}**\n\nExample: {current['example']}")
        cols=st.columns(4)
        for col,label in zip(cols,['Again','Hard','Good','Easy']):
            with col:
                if st.button(label,key=f'grade_{key}_{label}',use_container_width=True):
                    review_word(state,key,label,TODAY)
                    if save():
                        st.session_state['reveal_word']=None
                        st.rerun()
        st.caption('Again = forgotten · Hard = difficult · Good = remembered · Easy = instant recall')


def lesson_label(x):
    done = bool(state['lessons'].get(x['id'],{}).get('attempts'))
    return f"{'✓ ' if done else ''}{x['id'][1:]} · {x['title']} ({x['level']})"


def render_lesson():
    options=[x['id'] for x in LESSONS]
    default=next((i for i,l in enumerate(LESSONS) if not state['lessons'].get(l['id'],{}).get('attempts')),len(LESSONS)-1)
    choice=st.selectbox('Choose a lesson',options,index=default,format_func=lambda s:lesson_label(next(x for x in LESSONS if x['id']==s)))
    l=next(x for x in LESSONS if x['id']==choice)
    st.subheader(l['title'])
    st.caption(f"{l['theme']} · {l['level']} · around {l['estimated_minutes']} min")
    st.markdown('### Reading passage')
    st.markdown('**Read for meaning, not word-for-word translation.**')
    for para in l['reading'].strip().split('\n\n'):
        st.markdown(para)
    with st.expander('Vocabulary help — open only when needed'):
        for word_id in l['word_ids']:
            w=WORDS[word_id]
            st.write(f"**{w['dutch']}** — {w['english']}")
        st.caption('You can also review these words on the Flashcards page.')
    st.divider()
    st.markdown('### Answer the questions')
    with st.form(f'lesson_form_{choice}'):
        given={}
        for idx,q in enumerate(l['questions']):
            st.markdown(f"**{idx+1}. {q['prompt']}**")
            selected=st.radio('Choose one',options=list(q['options']),format_func=lambda x,opts=q['options']:f'{x}. {opts[x]}',key=f'{choice}_q_{idx}',index=None,label_visibility='collapsed')
            given[str(idx)]=selected
        submitted=st.form_submit_button('Check answers and save progress',type='primary')
    if submitted:
        if any(x is None for x in given.values()):
            st.warning('Please answer all four questions before submitting.')
        else:
            score=grade_lesson(state,l,given,TODAY)
            if save():
                st.session_state[f'feedback_{choice}']=len(state['lessons'][choice]['attempts'])-1
                st.success(f'Your result: {score} / {len(l["questions"])}')
    attempts=state['lessons'].get(choice,{}).get('attempts',[])
    if attempts:
        last=attempts[-1]
        with st.expander(f"Latest review: {last['score']}/{last['max_score']} — see explanations",expanded=submitted):
            for idx,q in enumerate(l['questions']):
                chosen=last['answers'].get(str(idx))
                correct=chosen==q['correct']
                st.write(f"{'✅' if correct else '❌'} **{idx+1}. {q['prompt']}**")
                st.caption(f"Your answer: {chosen or '—'} · Correct: {q['correct']}. {q['options'][q['correct']]}")
                st.write(q['explanation'])
    st.caption(l['source_note'])


def render_typed_recall():
    studied=[w for w in VOCAB if w['id'] in state['words']]
    if not studied:
        st.info('Introduce a few flashcards first. Typed recall appears once you have reviewed words.')
        return
    ids=[w['id'] for w in studied]
    if st.session_state.get('typed_word_id') not in ids:
        st.session_state['typed_word_id']=ids[0]
    current=WORDS[st.session_state['typed_word_id']]
    st.write('Type the Dutch word for:')
    st.subheader(current['english'])
    with st.form('typed_recall_form',clear_on_submit=True):
        typed=st.text_input('Dutch word or phrase',placeholder='Type in Dutch…')
        sub=st.form_submit_button('Check my answer')
    if sub:
        ok=check_typed_answer(typed,current)
        record_typed_result(state,current['id'],ok,TODAY)
        if ok:
            save()
            st.session_state['typed_feedback']='✅ Correct!'
        else:
            st.session_state['typed_feedback']=f"Not quite. The answer is: **{current['dutch']}**."
    if st.session_state.get('typed_feedback'):
        st.info(st.session_state['typed_feedback'])
    if st.button('Next word'):
        i=(ids.index(current['id'])+1)%len(ids)
        st.session_state['typed_word_id']=ids[i]
        st.session_state['typed_feedback']=''
        st.rerun()
    st.caption('For conservative mastery, a word needs successful spaced reviews and correct typed recall on two different days.')

if menu=='Today':
    st.title('Your daily B1 reading practice')
    st.caption('Built around NT2 Lezen I · Target: February/March 2027')
    a=state['activity'].get(TODAY.isoformat(),{})
    c1,c2,c3=st.columns(3)
    c1.metric('New words today', f"{a.get('new_words',0)}/{state['settings'].get('daily_new_goal',6)}")
    c2.metric('Review cards today',a.get('reviews',0))
    c3.metric('Reading sessions today',a.get('lessons',0))
    st.markdown('### Part 1 · Vocabulary (10 min)')
    review_card()
    st.divider()
    next_l=next((l for l in LESSONS if not state['lessons'].get(l['id'],{}).get('attempts')),None)
    st.markdown('### Part 2 · Reading (15 min)')
    if next_l:
        st.write(f"**Next lesson:** {next_l['title']} — {next_l['theme']}")
        st.caption('Open Reading lessons in the left sidebar to complete it.')
    else:
        st.success('All starter lessons completed! Repeat the difficult ones and use Exam prep for authentic mock practice.')
    st.markdown('### Part 3 · Review (5 min)')
    st.write('Review the answers you missed, then type two or three words from memory on the Flashcards page.')
    st.info('Start at your own pace. Your 2025 official practice booklet is being held back for a realistic assessment.')

elif menu=='Flashcards':
    st.title('Vocabulary studio')
    st.caption('A2+ to B1; focused on useful exam-language, not beginner A1 lists.')
    tab1,tab2,tab3=st.tabs(['Study cards','Type from memory','Browse vocabulary'])
    with tab1:
        review_card()
    with tab2:
        render_typed_recall()
    with tab3:
        query=st.text_input('Search Dutch or English')
        theme=st.selectbox('Theme', ['All']+sorted({w['theme'] for w in VOCAB}))
        filtered=[w for w in VOCAB if (theme=='All' or w['theme']==theme) and (query.lower() in w['dutch'].lower() or query.lower() in w['english'].lower())]
        rows=[]
        for w in filtered:
            state_w=state['words'].get(w['id'],{})
            rows.append({'Dutch':w['dutch'],'English':w['english'],'Theme':w['theme'],'Source years':', '.join(map(str,w.get('source_years',[]))) or 'supporting','Due':state_w.get('due','Not started'),'Mastered':is_mastered(state_w)})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.caption('Source years indicate an exact lemma match in the uploaded 2023/2024 text; “supporting” words were added to bridge useful B1 vocabulary.')

elif menu=='Reading lessons':
    st.title('Guided reading lessons')
    st.write('Original passages inspired by the 2023 and 2024 official examination themes. These are **training materials**, not copies of official test questions.')
    render_lesson()

elif menu=='Progress':
    st.title('Your progress')
    stats=summary_stats(state,VOCAB,LESSONS,TODAY)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Introduced',stats['introduced'])
    c2.metric('Mastered',stats['mastered'])
    c3.metric('Completed lessons',stats['lesson_count'])
    c4.metric('Latest lesson accuracy','—' if stats['accuracy'] is None else f"{stats['accuracy']:.0f}%")
    st.caption('Mastered = repeated spaced reviews + correct typed recall on at least two different days.')
    st.markdown('### Last 14 days')
    dates=[TODAY-timedelta(days=i) for i in range(13,-1,-1)]
    data=[]
    for d in dates:
        a=state['activity'].get(d.isoformat(),{})
        data.append({'Date':d,'New words':a.get('new_words',0),'Reviews':a.get('reviews',0),'Lessons':a.get('lessons',0)})
    chart=pd.DataFrame(data).set_index('Date')
    st.bar_chart(chart,stack=False)
    st.markdown('### Reading history')
    table=[]
    for l in LESSONS:
        hist=state['lessons'].get(l['id'],{}).get('attempts',[])
        if hist:
            last=hist[-1]
            table.append({'Lesson':l['title'],'Date':last['date'],'Latest':f"{last['score']}/{last['max_score']}",'Attempts':len(hist)})
    if table:
        st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True)
    else:
        st.info('Complete your first lesson to populate this dashboard.')

elif menu=='Exam prep':
    st.title('Official exam preparation')
    st.info('2025 has been reserved as a held-out practice exam. Avoid reading it before your timed assessment.')
    st.markdown('**Official format:** 6 texts, 35 multiple-choice questions, 110 minutes. You can revisit and change answers. The 2025 booklet distinguishes comprehensive reading in texts 1–5 from question-first scanning in text 6.')
    st.link_button('Open the official online practice exams','https://oefenexamensnt2.nl/')
    st.caption('You uploaded the 2023, 2024 and 2025 text booklets. They do not include the separate official question files or keys; this app does not claim to reproduce those questions.')
    st.markdown('### Log a timed official mock')
    with st.form('mock_form'):
        correct=st.number_input('Correct out of 35',min_value=0,max_value=35,value=20)
        minutes=st.number_input('Time used (minutes)',min_value=1,max_value=240,value=110)
        comments=st.text_area('What was difficult?',placeholder='e.g., unknown words, long sentences, time pressure')
        submit=st.form_submit_button('Save mock result')
    if submit:
        add_mock(state,int(correct),int(minutes),comments,TODAY)
        if save():
            st.success('Mock result saved. This is practice data, not an official scaled exam result.')
    if state.get('mocks'):
        st.dataframe(pd.DataFrame(state['mocks']),use_container_width=True,hide_index=True)
    st.markdown('### What to focus on next')
    st.write('Build recognition first → complete guided lessons → use authentic 2023/2024 questions when available → complete the held-out 2025 mock without support.')

elif menu=='Settings':
    st.title('Settings and data safety')
    st.markdown('### Daily goals')
    goal=st.slider('New words per study day',2,15,int(state['settings'].get('daily_new_goal',6)))
    if goal!=state['settings'].get('daily_new_goal',6):
        state['settings']['daily_new_goal']=goal
        save()
    st.markdown('### Export your progress')
    backup=json.dumps(ensure_progress(state),ensure_ascii=False,indent=2)
    st.download_button('Download progress backup (.json)',backup,file_name=f'b1-reading-progress-{TODAY.isoformat()}.json',mime='application/json')
    st.markdown('### Restore a backup')
    file=st.file_uploader('Choose a B1 Reading Trainer JSON backup',type=['json'])
    accept=st.checkbox('I understand this will replace my current progress')
    if st.button('Restore the backup',disabled=file is None or not accept):
        try:
            if file.size>2_000_000:raise ValueError('File is larger than 2 MB')
            raw=json.loads(file.getvalue().decode('utf-8'))
            if not isinstance(raw,dict) or not all(x in raw for x in ('words','lessons','activity')):
                raise ValueError('Not a valid B1 Reading Trainer backup')
            new=ensure_progress(raw)
            st.session_state['progress']=new
            if save():
                st.success('Backup restored and saved.')
                st.rerun()
        except (ValueError,UnicodeError) as e:
            st.error(f'Could not restore: {e}')
    st.markdown('### Add vocabulary from a CSV')
    st.caption('Use columns: dutch, english, example, theme. Imported words join your vocabulary library and are included in JSON backups.')
    csvfile=st.file_uploader('Import custom vocabulary (CSV)',type=['csv'],key='csvimport')
    if csvfile and st.button('Add these words'):
        try:
            rows=list(csv.DictReader(io.StringIO(csvfile.getvalue().decode('utf-8-sig'))))
            if len(rows)>500:raise ValueError('Limit 500 rows per import')
            if not {'dutch','english','example','theme'}.issubset(set(rows[0]) if rows else set()):
                raise ValueError('The CSV must contain dutch, english, example, theme')
            known={v['id'] for v in VOCAB}
            added=0
            for row in rows:
                dutch=row['dutch'].strip()
                if not dutch or not row['english'].strip():continue
                word_id='custom-'+re.sub(r'[^a-z0-9]+','-',dutch.lower()).strip('-')
                if word_id in known:continue
                state['custom_words'].append({'id':word_id,'dutch':dutch,'english':row['english'].strip(),'example':row['example'].strip() or dutch,'theme':row['theme'].strip() or 'custom','priority':2,'source_years':[]})
                known.add(word_id);added+=1
            if save():
                st.success(f'Added {added} new words.')
                st.rerun()
        except (ValueError,UnicodeError) as e:
            st.error(str(e))
    st.markdown('### Persistence')
    st.write(f'Current storage: **{store.mode}**')
    if store.mode=='Local JSON':
        st.warning('For reliable Streamlit Cloud use and cross-device continuation, configure Google Sheets via secrets as described in README.md.')
    else:
        st.success('Progress is saved to Google Sheets after each card and lesson submission.')
    st.caption('No third-party AI API or subscription is required to use the included lessons.')
