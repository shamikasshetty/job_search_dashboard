#!/usr/bin/env python3
"""
process_jobs.py
Runs as GitHub Action — fetches from Apify, scores jobs, saves jobs.json
No manual steps needed.
"""
import json, os, re, sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Config from GitHub Secrets ──────────────────────────────────────────────
APIFY_TOKEN    = os.environ.get('APIFY_API_TOKEN','')
APIFY_ACTOR_ID = os.environ.get('APIFY_ACTOR_ID','')  # e.g. Dn2KJLnaNC5vFGkEw
ANTHROPIC_KEY  = os.environ.get('ANTHROPIC_API_KEY','')

MY_SKILLS = [
    'sql','python','splunk','nist','grc','iam','soc','power bi','security+',
    'active directory','wireshark','rbac','iso 27001','log analysis',
    'incident response','siem','tableau','excel','pandas','mitre',
    'risk assessment','access review','control testing','threat hunting',
    'vulnerability','compliance','audit','data analysis','reporting','dashboard'
]
CLEARANCE_KW = [
    'secret clearance','top secret','ts/sci','clearance required',
    'security clearance','dod clearance','classified','active clearance'
]
CITIZEN_KW = [
    'us citizen','u.s. citizen','must be a citizen','citizenship required',
    'united states citizen','usc only','us citizenship'
]
TARGET_INCLUDE = [
    'security analyst','soc analyst','grc','iam analyst','iam engineer',
    'information security','cybersecurity','security operations',
    'data analyst','risk analyst','compliance analyst','identity access'
]
TARGET_EXCLUDE = [
    'intern','seasonal','mrt-c','actuarial','marketing','quality data',
    'customer success','front office','material data','finance data',
    'product operations','batch monitoring','reserving','sales','warehouse',
    'administrative','coordinator','patient','driver','front desk',
    'part-time','part time','hr data','financial data','school district'
]

def get_location(j):
    cities = j.get('cities_derived') or []
    regions = j.get('regions_derived') or []
    if cities and regions: return f"{cities[0]}, {regions[0]}"
    if regions: return regions[0]
    if j.get('remote_derived'): return 'Remote'
    return 'United States'

def get_url(j):
    u = j.get('url') or j.get('organization_url') or ''
    if u and u.startswith('http'): return u
    dom = j.get('source_domain','')
    return f"https://{dom}" if dom else '#'

def get_salary(j):
    mn = j.get('ai_salary_minvalue')
    mx = j.get('ai_salary_maxvalue')
    unit = str(j.get('ai_salary_unittext') or '')
    if mn and mx:
        if 'hour' in unit.lower(): return f"${mn}–${mx}/hr"
        return f"${int(mn/1000)}k–${int(mx/1000)}k"
    return None

def check_clearance(text):
    t = text.lower()
    return any(kw in t for kw in CLEARANCE_KW)

def check_citizen(text):
    t = text.lower()
    return any(kw in t for kw in CITIZEN_KW)

def get_clearance_type(text):
    t = text.lower()
    if 'top secret' in t or 'ts/sci' in t: return 'Top Secret'
    if 'secret' in t: return 'Secret'
    return 'Unspecified'

def score_job(j):
    title = (j.get('title') or '').lower()
    desc  = (j.get('description_text') or '').lower()
    skills = ' '.join(s.lower() for s in (j.get('ai_key_skills') or []))
    text = f"{title} {desc} {skills}"
    matched = sum(1 for s in MY_SKILLS if s in text)
    base = min(95, 35 + matched * 6)
    if any(k in title for k in ['soc analyst','security analyst','grc','iam analyst','information security','cybersecurity']):
        base = min(97, base + 12)
    if 'data analyst' in title: base = min(95, base + 8)
    if any(k in title for k in ['intern','seasonal','vp ','vice president','chief','ciso']):
        base = max(25, base - 25)
    return base

def detect_resume(title):
    t = title.lower()
    return 'data' if any(k in t for k in ['data analyst','data scientist','bi analyst']) else 'security'

def is_relevant(j):
    title = (j.get('title') or '').lower()
    if any(ex in title for ex in TARGET_EXCLUDE): return False
    return any(inc in title for inc in TARGET_INCLUDE)

def fetch_apify_data():
    """Fetch latest dataset from Apify actor's last run"""
    print(f"Fetching from Apify actor: {APIFY_ACTOR_ID}")
    
    # Get last run dataset ID
    runs_url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs/last?token={APIFY_TOKEN}&status=SUCCEEDED"
    req = Request(runs_url)
    with urlopen(req, timeout=30) as r:
        run_data = json.loads(r.read())
    
    dataset_id = run_data['data']['defaultDatasetId']
    print(f"Dataset ID: {dataset_id}")
    
    # Fetch all items from dataset
    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&format=json&limit=500"
    req = Request(items_url)
    with urlopen(req, timeout=60) as r:
        items = json.loads(r.read())
    
    print(f"Fetched {len(items)} raw jobs from Apify")
    return items

def process_jobs(raw):
    relevant = [j for j in raw if is_relevant(j)]
    print(f"Relevant after filter: {len(relevant)} of {len(raw)}")
    
    output = []
    for i, j in enumerate(relevant):
        title     = j.get('title','Unknown Role')
        org       = j.get('organization','Unknown Company')
        desc      = j.get('description_text') or ''
        full_text = f"{title} {desc}"
        clr       = check_clearance(full_text)
        cit       = check_citizen(full_text)
        h4ok      = not clr and not cit
        remote    = bool(j.get('remote_derived') or
                        (j.get('ai_work_arrangement') or '').lower() in ['remote','hybrid'])
        output.append({
            'id':     f"apify_{j.get('id', i)}",
            'title':  title,
            'company': org,
            'location': get_location(j),
            'remote': remote,
            'sal':    get_salary(j),
            'posted': j.get('date_posted') or j.get('date_created') or datetime.now(timezone.utc).isoformat(),
            'source': j.get('source','Career Page'),
            'url':    get_url(j),
            'desc':   (desc[:350]+'...') if len(desc)>350 else desc,
            'skills': (j.get('ai_key_skills') or [])[:8],
            'cit':    cit,
            'clr':    clr,
            'clrt':   get_clearance_type(full_text) if clr else None,
            'h4':     h4ok,
            'score':  score_job(j),
            'status': 'skipped' if (clr or cit) else 'new',
            'rv':     detect_resume(title)
        })
    
    output.sort(key=lambda x: x['score'], reverse=True)
    return output

def main():
    if not APIFY_TOKEN or not APIFY_ACTOR_ID:
        print("ERROR: APIFY_API_TOKEN or APIFY_ACTOR_ID not set in GitHub Secrets")
        sys.exit(1)
    
    raw   = fetch_apify_data()
    jobs  = process_jobs(raw)
    
    result = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'total_jobs':   len(jobs),
        'source':       'Apify Career Site Job Listing Feed — auto-processed',
        'jobs':         jobs
    }
    
    with open('jobs.json','w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✅ jobs.json updated with {len(jobs)} jobs")
    print(f"   H4-EAD compatible: {sum(1 for j in jobs if j['h4'])}")
    print(f"   High match 80+:    {sum(1 for j in jobs if j['score']>=80)}")
    print(f"   Clearance/citizen: {sum(1 for j in jobs if j['clr'] or j['cit'])}")
    print(f"   Remote/Hybrid:     {sum(1 for j in jobs if j['remote'])}")

if __name__ == '__main__':
    main()
