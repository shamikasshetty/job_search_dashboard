#!/usr/bin/env python3
"""
process_jobs.py - Runs as GitHub Action daily at 8am
Fetches from Apify, processes jobs, builds complete index.html
Zero manual steps required.
"""
import json, os, sys, base64
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

APIFY_TOKEN    = os.environ.get('APIFY_API_TOKEN','')
APIFY_ACTOR_ID = os.environ.get('APIFY_ACTOR_ID','')

MY_SKILLS = ['sql','python','splunk','nist','grc','iam','soc','power bi','security+',
             'active directory','wireshark','rbac','iso 27001','log analysis',
             'incident response','siem','tableau','excel','pandas','mitre',
             'risk assessment','access review','threat hunting','compliance','vulnerability']
CLEARANCE_KW = ['secret clearance','top secret','ts/sci','clearance required',
                'security clearance','dod clearance','classified']
CITIZEN_KW   = ['us citizen','u.s. citizen','must be a citizen','citizenship required',
                'united states citizen']
TARGET_INCLUDE = ['soc analyst','security analyst','grc analyst','iam analyst','iam engineer',
                  'information security','cybersecurity','cyber security','security operations',
                  'compliance analyst','risk analyst','identity access','identity and access',
                  'security engineer','security specialist','security consultant',
                  'governance risk','information assurance','security architect']
TARGET_EXCLUDE = ['intern','seasonal','warehouse','administrative','coordinator',
                  'patient','driver','part-time','marketing','customer success',
                  'school','financial data','survey data','quality data',
                  'business intelligence data','advanced data analyst',
                  'contract compliance','criminology','nasa']

def get_location(j):
    cities  = j.get('cities_derived') or []
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
        if 'hour' in unit.lower(): return f"${mn}-${mx}/hr"
        return f"${int(mn/1000)}k-${int(mx/1000)}k"
    return None

def score_job(j):
    title  = (j.get('title') or '').lower()
    desc   = (j.get('description_text') or '').lower()
    skills = ' '.join(s.lower() for s in (j.get('ai_key_skills') or []))
    text   = f"{title} {desc} {skills}"
    matched = sum(1 for s in MY_SKILLS if s in text)
    base = min(95, 35 + matched * 6)
    if any(k in title for k in ['soc analyst','security analyst','grc','iam analyst',
                                 'information security','cybersecurity']):
        base = min(97, base + 12)
    if 'data analyst' in title: base = min(95, base + 8)
    if any(k in title for k in ['intern','seasonal','vp ','vice president','chief','director']):
        base = max(25, base - 25)
    return base

def is_relevant(j):
    title = (j.get('title') or '').lower()
    if any(ex in title for ex in TARGET_EXCLUDE): return False
    return any(inc in title for inc in TARGET_INCLUDE)

def fetch_jobs():
    print(f"Fetching from Apify actor: {APIFY_ACTOR_ID}")
    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs/last?token={APIFY_TOKEN}&status=SUCCEEDED"
    with urlopen(Request(url), timeout=30) as r:
        run = json.loads(r.read())
    dataset_id = run['data']['defaultDatasetId']
    print(f"Dataset: {dataset_id}")
    url2 = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&format=json&limit=500"
    with urlopen(Request(url2), timeout=60) as r:
        items = json.loads(r.read())
    print(f"Fetched {len(items)} raw jobs")
    return items

def process_jobs(raw):
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    
    def is_fresh(j):
        date_str = j.get('date_posted') or j.get('date_created') or ''
        if not date_str:
            return True  # include if no date
        try:
            # Handle both with and without timezone
            date_str = date_str.replace('Z', '+00:00')
            if '+' not in date_str and 'T' in date_str:
                date_str += '+00:00'
            posted = datetime.fromisoformat(date_str)
            if posted.tzinfo is None:
                from datetime import timezone as tz
                posted = posted.replace(tzinfo=timezone.utc)
            return posted >= cutoff
        except:
            return True  # include if can't parse date

    relevant = [j for j in raw if is_relevant(j) and is_fresh(j)]
    print(f"Fresh (last 48h): {len(relevant)} of {len([j for j in raw if is_relevant(j)])} relevant jobs")
    print(f"Relevant: {len(relevant)} of {len(raw)}")
    jobs = []
    for i, j in enumerate(relevant):
        title = j.get('title','')
        org   = j.get('organization','')
        desc  = j.get('description_text') or ''
        full  = title + ' ' + desc
        clr   = any(kw in full.lower() for kw in CLEARANCE_KW)
        cit   = any(kw in full.lower() for kw in CITIZEN_KW)
        clrt  = None
        if clr:
            clrt = 'Top Secret' if 'top secret' in full.lower() or 'ts/sci' in full.lower() else 'Secret'
        jobs.append({
            'id':       f"j{i}",
            'title':    title,
            'company':  org,
            'location': get_location(j),
            'remote':   bool(j.get('remote_derived') or
                             (j.get('ai_work_arrangement') or '').lower() in ['remote','hybrid']),
            'sal':      get_salary(j),
            'posted':   j.get('date_posted') or j.get('date_created') or datetime.now(timezone.utc).isoformat(),
            'date_posted_raw': j.get('date_posted') or '',
            'source':   j.get('source','Career Page'),
            'url':      get_url(j),
            'desc':     (desc[:300]+'...') if len(desc)>300 else desc,
            'skills':   (j.get('ai_key_skills') or [])[:6],
            'clr':      clr,
            'cit':      cit,
            'clrt':     clrt,
            'h4':       not clr and not cit,
            'score':    score_job(j),
            'status':   'skipped' if (clr or cit) else 'new',
            'rv':       'data' if 'data analyst' in title.lower() else 'security'
        })
    jobs.sort(key=lambda x: x['score'], reverse=True)
    return jobs

def build_html(jobs):
    today = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime('%b %d %Y at %I:%M %p CST')
    js_jobs = json.dumps(jobs, separators=(',',':'), ensure_ascii=True)
    js_jobs = js_jobs.replace('</script>', '<\\/script>')

    # Read master template
    with open('index_template.html') as f:
        template = f.read()

    # Replace jobs placeholder and date
    html = template.replace('/*JOBS_PLACEHOLDER*/', js_jobs)
    html = html.replace('JOBS_DATE_PLACEHOLDER', today)
    return html

def main():
    if not APIFY_TOKEN or not APIFY_ACTOR_ID:
        print("ERROR: Missing APIFY_API_TOKEN or APIFY_ACTOR_ID secrets")
        sys.exit(1)

    raw  = fetch_jobs()
    jobs = process_jobs(raw)

    today = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime('%b %d %Y at %I:%M %p CST')
    print(f"\nResults for {today}:")
    print(f"  Total jobs:     {len(jobs)}")
    print(f"  H4-EAD:         {sum(1 for j in jobs if j['h4'])}")
    print(f"  High match 80+: {sum(1 for j in jobs if j['score']>=80)}")
    print(f"  Remote:         {sum(1 for j in jobs if j['remote'])}")
    print(f"  Texas:          {sum(1 for j in jobs if 'texas' in j['location'].lower() or ', tx' in j['location'].lower())}")

    # Save jobs.json
    out = {'last_updated': datetime.now(timezone.utc).isoformat(),
           'total_jobs': len(jobs), 'jobs': jobs}
    with open('jobs.json','w') as f:
        json.dump(out, f, separators=(',',':'))
    print("Saved jobs.json")

    # Build index.html from template
    try:
        html = build_html(jobs)
        with open('index.html','w') as f:
            f.write(html)
        print(f"Built index.html ({len(html)//1024}KB)")
    except FileNotFoundError:
        print("index_template.html not found - skipping HTML build")

    print("\nDone!")

if __name__ == '__main__':
    main()
