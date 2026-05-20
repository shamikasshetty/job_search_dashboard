#!/usr/bin/env python3
"""
transform.py
Converts raw Apify job data into the dashboard's jobs.json format.
Runs as part of the GitHub Actions workflow.
"""
import json, re, os
from datetime import datetime, timezone

CLEARANCE_KEYWORDS = ['clearance','secret','top secret','ts/sci','classified','dod','security clearance']
CITIZEN_KEYWORDS = ['us citizen','u.s. citizen','united states citizen','must be a citizen','citizenship required']
H4_BLOCK = ['clearance','must be a citizen','us citizen','u.s. citizen','citizenship required','green card required']

MY_SKILLS = ['sql','python','splunk','nist','grc','iam','soc','power bi','security+','active directory','wireshark','rbac','iso 27001','log analysis','incident response','siem','tableau','excel','pandas','mitre','risk assessment','access review','control testing']

def score_job(job):
    desc = (job.get('description','') + ' ' + ' '.join(job.get('required_skills',[])) + ' ' + job.get('title','')).lower()
    matched = sum(1 for s in MY_SKILLS if s in desc)
    base = min(95, 40 + (matched * 7))
    # Boost for target roles
    title = job.get('title','').lower()
    for kw in ['soc analyst','grc','iam','security analyst','data analyst']:
        if kw in title: base = min(98, base + 8)
    return base

def extract_clearance(text):
    t = text.lower()
    for kw in CLEARANCE_KEYWORDS:
        if kw in t: return True
    return False

def extract_citizenship(text):
    t = text.lower()
    for kw in CITIZEN_KEYWORDS:
        if kw in t: return True
    return False

def get_clearance_type(text):
    t = text.lower()
    if 'top secret' in t or 'ts/sci' in t: return 'Top Secret'
    if 'secret' in t: return 'Secret'
    if 'clearance' in t: return 'Unspecified'
    return None

def h4_compatible(text):
    t = text.lower()
    for kw in H4_BLOCK:
        if kw in t: return False
    return True

def detect_resume(title):
    t = title.lower()
    if any(k in t for k in ['data analyst','data engineer','analytics','bi analyst']): return 'data'
    return 'security'

def transform(raw_jobs):
    out = []
    for i, r in enumerate(raw_jobs):
        desc = r.get('description','') or r.get('job_description','') or ''
        title = r.get('title','') or r.get('job_title','') or 'Unknown Role'
        company = r.get('company','') or r.get('employer_name','') or 'Unknown Company'
        location = r.get('location','') or r.get('job_city','') or 'See listing'
        if r.get('job_state'): location = f"{location}, {r['job_state']}"
        
        clearance = extract_clearance(desc + ' ' + title)
        citizen = extract_citizenship(desc + ' ' + title)
        h4ok = h4_compatible(desc + ' ' + title)
        
        salary_min = r.get('salary_min') or r.get('job_min_salary')
        salary_max = r.get('salary_max') or r.get('job_max_salary')
        if salary_min and salary_max:
            salary_display = f"${int(salary_min/1000)}k–${int(salary_max/1000)}k"
        else:
            salary_display = None
        
        job = {
            'id': r.get('id') or r.get('job_id') or f'job_{i:04d}',
            'title': title,
            'company': company,
            'location': location,
            'remote': bool(r.get('remote') or r.get('job_is_remote') or 'remote' in location.lower()),
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_display': salary_display,
            'posted': r.get('posted') or r.get('job_posted_at_datetime_utc') or datetime.now(timezone.utc).isoformat(),
            'source': r.get('source') or r.get('job_publisher') or 'Career Page',
            'apply_url': r.get('apply_url') or r.get('job_apply_link') or r.get('url') or '#',
            'description': (desc[:400] + '...') if len(desc) > 400 else desc,
            'required_skills': r.get('required_skills') or [],
            'citizenship_required': citizen,
            'clearance_required': clearance,
            'clearance_type': get_clearance_type(desc) if clearance else None,
            'h4_ead_compatible': h4ok,
            'score': score_job({'title':title,'description':desc,'required_skills':r.get('required_skills',[])}),
            'status': 'skipped' if (clearance or citizen) else 'new',
            'resume_version': detect_resume(title),
        }
        out.append(job)
    
    out.sort(key=lambda j: j['score'], reverse=True)
    return out

if __name__ == '__main__':
    try:
        with open('raw_jobs.json') as f:
            raw = json.load(f)
        if isinstance(raw, dict): raw = raw.get('data') or raw.get('items') or raw.get('jobs') or []
    except Exception as e:
        print(f'No raw_jobs.json or parse error: {e}')
        raw = []
    
    jobs = transform(raw)
    output = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'total_jobs': len(jobs),
        'jobs': jobs,
    }
    with open('jobs.json','w') as f:
        json.dump(output, f, indent=2)
    print(f'✓ Transformed {len(jobs)} jobs → jobs.json')
