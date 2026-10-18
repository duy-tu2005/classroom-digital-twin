"""Visual QA of the deployed dashboard; uses a fresh browser and private API login."""
import argparse
import base64
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/.runtime'))
sys.path.insert(0,str(ROOT/'thingsboard'))
from playwright.sync_api import sync_playwright
from api import Client,env_file
from lighting_qa import mask_coverage

parser=argparse.ArgumentParser()
parser.add_argument('--preview',action='store_true')
args=parser.parse_args()
out=ROOT/'docs/screenshots'
out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1600,'height':1200},device_scale_factor=1,timezone_id='Asia/Ho_Chi_Minh')
    if args.preview: url='http://127.0.0.1:8095/preview/index.html'
    else:
        config=env_file(ROOT/'deployment/.env');runtime=env_file(ROOT/'.env.local')
        base=runtime['TB_BASE_URL'];auth=Client(base).post('/api/auth/login',{'username':config['TB_USERNAME'],'password':config['TB_PASSWORD']})
        storage={}
        for source,key in [('token','jwt_token'),('refreshToken','refresh_token')]:
            token=auth[source];encoded=token.split('.')[1];payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
            storage[key]=token;storage[key+'_expiration']=str(payload['exp']*1000)
        context.add_init_script('for (const [k,v] of Object.entries('+json.dumps(storage)+')) localStorage.setItem(k,v);')
        url=base+'/dashboards/'+runtime['TB_DASHBOARD_ID']
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda exc:errors.append(str(exc)))
    page.goto(url,wait_until='domcontentloaded',timeout=60000)
    page.locator('.cl-twin').wait_for(state='visible',timeout=60000)
    page.wait_for_timeout(2500)
    assert page.locator('.cl-lit-scene').count()==1
    assert page.locator('.cl-light-control').count()==4
    assert page.locator('.cl-base').evaluate('(img)=>img.complete && img.naturalWidth>1000')
    mask=page.locator('.cl-lit-scene').evaluate('(el)=>getComputedStyle(el).maskImage')
    assert 'image/svg+xml' in mask,'Combined perspective mask must be initialized'
    coverage={};masks=[]
    page.locator('.cl-twin').screenshot(path=str(out/('preview-dark.png' if args.preview else 'aws-dashboard.png')))
    if args.preview:
        lighting=json.loads((ROOT/'thingsboard/widgets/lighting-layout.json').read_text(encoding='utf-8'))
        # A successful RPC alone must never light the scene before telemetry arrives.
        page.evaluate('window.__originalPreviewPost=previewHttp.post;previewHttp.post=()=>({subscribe(ok){ok({success:true});return{unsubscribe(){}};}});')
        page.locator('.cl-light-control[data-light="1"]').click()
        assert page.locator('.cl-lit-scene.is-on').count()==0,'RPC acknowledgment is not telemetry'
        page.evaluate('previewHttp.post=window.__originalPreviewPost;delete window.__originalPreviewPost;')
        for i in range(1,5):
            page.locator('.cl-light-control[data-light="'+str(i)+'"]').click()
            page.wait_for_timeout(750)
            assert page.locator('.cl-light-control.is-on').count()==1
            assert page.locator('.cl-lit-scene').get_attribute('data-active-lights')==str(i)
            masks.append(page.locator('.cl-lit-scene').evaluate('(el)=>getComputedStyle(el).maskImage'))
            if i==1:
                probes=lighting['boardProbes']
                coverage['board']=mask_coverage(page,probes)
                assert min(coverage['board']['probeAlpha'])>=254,'Light 1 must fully illuminate the entire board'
            page.locator('.cl-twin').screenshot(path=str(out/f'preview-light-{i}.png'))
            page.locator('.cl-light-control[data-light="'+str(i)+'"]').click();page.wait_for_timeout(250)
        for i in range(1,5):page.locator('.cl-light-control[data-light="'+str(i)+'"]').click()
        assert len(set(masks))==4,'Each light must have its own transverse band'
        page.wait_for_function('()=>document.querySelector(".cl-lit-scene").dataset.activeLights==="1,2,3,4"')
        page.wait_for_timeout(650)
        page.locator('.cl-twin').screenshot(path=str(out/'preview-all-lights.png'))
        coverage['all']=mask_coverage(page)
        assert coverage['all']['dimPixels']==0,'All four lights must cover the complete scene without dark seams'
        for i in range(1,5):page.locator('.cl-light-control[data-light="'+str(i)+'"]').click()
        page.wait_for_function('()=>document.querySelector(".cl-lit-scene").dataset.activeLights===""')
        # Exhaust all 16 combinations at the actual centers of the four bands.
        coverage['combinations']=[]
        for bits in range(16):
            enabled=[i for i in range(1,5) if bits & (1<<(i-1))]
            page.evaluate('(enabled)=>{for(let i=1;i<=4;i++)sample["light"+i+"_state"]=enabled.includes(i);updateSample();}',enabled)
            sample=mask_coverage(page,[lane['marker'] for lane in lighting['lanes']])
            assert all(alpha>=254 if i in enabled else alpha<=1 for i,alpha in enumerate(sample['probeAlpha'],1)),sample
            coverage['combinations'].append({'lights':enabled,'centerAlpha':sample['probeAlpha']})
        page.evaluate('()=>{for(let i=1;i<=4;i++)sample["light"+i+"_state"]=false;updateSample();}')
        page.wait_for_timeout(650)
        page.set_viewport_size({'width':420,'height':1000});page.wait_for_timeout(250)
        assert page.evaluate('document.documentElement.scrollWidth')<=420
        assert page.locator('.cl-light-control .cl-switch,.cl-metrics .cl-word').evaluate_all('(els)=>els.every(e=>{const box=e.getBoundingClientRect(),parent=e.parentElement.getBoundingClientRect();return box.left>=parent.left-1 && box.right<=parent.right+1;})'),'Mobile text/switch overflow'
        page.screenshot(path=str(out/'preview-mobile.png'),full_page=True)
    boxes=page.locator('.cl-twin,.cl-scene,.cl-controls,.cl-lights,.cl-light-control').evaluate_all('(els)=>els.map(e=>({classes:e.className,display:getComputedStyle(e).display,rect:e.getBoundingClientRect().toJSON(),scrollHeight:e.scrollHeight,clientHeight:e.clientHeight}))')
    result={'url':url,'pageErrors':errors,'fourIndependentBands':True,'unionMask':True,'coverage':coverage,'baseImageLoaded':True,'layout':boxes,
        'connection':page.locator('[data-value="connection"]').inner_text(),'capturedAt':int(time.time()*1000)}
    (out/('preview-qa.json' if args.preview else 'aws-qa.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    browser.close()
    print(json.dumps(result,ensure_ascii=True))
    if errors: raise SystemExit(1)
