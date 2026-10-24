"""Testgruppe order_outbox: dauerhafte Versandaufträge für Bestellwunsch-Mails – Teilfehler, SMTP-Ausfall, Sperren, Neuversand."""
import fcntl, hashlib, json, os, sqlite3, sys
from umgebung import SMTP_PORT  # Testserver je Gruppe (parallel)
from pathlib import Path
from kunden_hilfe import Client
from order_setup import setup
from smtp_test import TestSmtp

results=[]
def check(name, ok):
    results.append(bool(ok)); print(('PASS ' if ok else 'FAIL ')+name)
smtp,a,k,other,kid,payload,nr=setup()
def detail(n): return a.call('bestellung&nr='+n)[1]['order']
def retry(n,j,**extra): return a.call('bestellung_mail_retry',{**dict(nr=n,jobId=j['id'],attempts=j['attempts'],confirm=True),**extra})
root=Path(os.environ['UDATA'])
def mutate(fn):
    if (root/'.sqlite-active').exists():
        with sqlite3.connect(root/'.sqlite/store.sqlite') as db:
            data=json.loads(db.execute("SELECT payload FROM documents WHERE name='bestellungen'").fetchone()[0]);fn(data)
            db.execute("UPDATE documents SET payload=? WHERE name='bestellungen'",(json.dumps(data),))
    else:
        p=root/'bestellungen.php';guard,raw=p.read_text().split('\n',1);data=json.loads(raw);fn(data);p.write_text(guard+'\n'+json.dumps(data))
j=detail(nr)['outbox'][0];count=len(smtp.messages)
check('initial job persisted and sent once',j['state']=='sent' and j['attempts']==1)
check('sent job cannot be resent',retry(nr,j)[0]==409 and len(smtp.messages)==count)
check('customer does not receive outbox', 'outbox' not in k.call('kunde_bestellung_detail&nr='+nr)[1]['order'])
check('staff list excludes outbox payload', 'outbox' not in a.call('bestellungen')[1]['orders'][0])
check('staff detail excludes mail body', 'html' not in j and 'text' not in j)
def stored_jobs(n):
    box={}
    def grab(data):
        for o in data:
            if o['nr']==n: box['jobs']=o.get('outbox',[])
    mutate(grab); return box.get('jobs',[])
check('accepted job no longer stores the message body', all('html' not in x and 'text' not in x for x in stored_jobs(nr) if x['state']=='sent'))
check('retry requires POST',a.call('bestellung_mail_retry')[0]==405)
check('retry requires explicit confirmation',retry(nr,j,confirm=False)[0]==422)
check('retry requires integer attempt',retry(nr,j,attempts='1')[0]==422)
old=a.csrf;a.csrf='invalid';check('retry requires CSRF',retry(nr,j)[0]==403);a.csrf=old
check('customer cannot retry',k.call('bestellung_mail_retry',dict(nr=nr,jobId=j['id'],attempts=1,confirm=True))[0]==401)
check('missing order returns 404',retry('missing',j)[0]==404)
check('missing job returns 404',retry(nr,{**j,'id':'missing'})[0]==404)
for role in ['viewer','editor']:
    a.call('user_save',dict(username=role+'.test',name=role,role=role,active=True,password='Editor-Zugang-77',mustChange=False))
viewer=Client();viewer.call('login',dict(username='viewer.test',password='Editor-Zugang-77'))
check('viewer cannot retry',viewer.call('bestellung_mail_retry',dict(nr=nr,jobId=j['id'],attempts=1,confirm=True))[0]==403)
# Partial success retains precise failures, including a failed customer copy.
a.call('bestell_settings_save',dict(enabled=True,to='orders@example.org;abgelehnt@example.org',copy=True))
rr=k.call('kunde_bestellung',{**payload,'requestId':'partial-request-12345'});partial=rr[1]['nr'];jobs=detail(partial)['outbox']
check('partial failure tracked individually',[x['state'] for x in jobs]==['sent','failed','sent'])
check('partial failure visible to staff',bool(detail(partial)['deliveryError']))
count=len(smtp.messages);failed=jobs[1];rr=retry(partial,failed)
check('failed retry increments only target',rr[0]==200 and [x['attempts'] for x in rr[1]['order']['outbox']]==[1,2,1])
check('retry does not resend accepted recipients',len(smtp.messages)==count)
check('stale retry rejected',retry(partial,failed)[0]==409)
# Outage: queued copy remains durable; original recipient is frozen despite settings change.
smtp.close();a.call('bestell_settings_save',dict(enabled=True,to='orders@example.org',copy=True))
failedpayload={**payload,'requestId':'outage-request-123456'}
check('outage is reported but order saved',k.call('kunde_bestellung',failedpayload)[0]==502)
newnr=k.call('kunde_bestellung',failedpayload)[1]['nr'];jobs=detail(newnr)['outbox']
check('outage preserves failed internal and queued copy',[j['state'] for j in jobs]==['failed','queued'])
check('copy waits for internal acceptance',retry(newnr,jobs[1])[0]==409)
a.call('bestell_settings_save',dict(enabled=True,to='changed@example.org',copy=False))
smtp=TestSmtp(SMTP_PORT,password='Test-Postfach-1')
lockpath=root/('.order-mail-'+hashlib.sha256(newnr.encode()).hexdigest()+'.lock')
with lockpath.open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    check('active sender lock rejects concurrent retry',retry(newnr,jobs[0])[0]==409 and not smtp.messages)
editor=Client();editor.call('login',dict(username='editor.test',password='Editor-Zugang-77'))
rr=editor.call('bestellung_mail_retry',dict(nr=newnr,jobId=jobs[0]['id'],attempts=jobs[0]['attempts'],confirm=True))
check('editor may retry failed job',rr[0]==200 and rr[1]['order']['outbox'][0]['state']=='sent')
check('original recipient retained',smtp.messages[0]['to']==['orders@example.org'])
check('original order number retained in email',newnr in smtp.messages[0]['text'])
check('copy not silently sent by internal retry',len(smtp.messages)==1)
check('queued copy can be sent explicitly',retry(newnr,jobs[1])[0]==200 and len(smtp.messages)==2)
check('all errors clear after recovery',detail(newnr)['deliveryError']=='')
check('attempt history records staff actor',detail(newnr)['outbox'][0]['history'][-1]['by']=='editor')
count=len(smtp.messages);check('customer replay still no additional mail',k.call('kunde_bestellung',failedpayload)[1]['nr']==newnr and len(smtp.messages)==count)
check('no additional order created by retries',a.call('bestellungen')[1]['total']==3)
# Simulate process death after persisting a claim, before recording an outcome.
def interrupted(all):
    o=next(o for o in all if o['nr']==newnr);o['outbox'][0]['state']='sending';o['outbox'][0]['attempts']+=1
mutate(interrupted);j=detail(newnr)['outbox'][0]
check('interrupted send remains visible',j['state']=='sending')
check('interrupted send needs confirmation',retry(newnr,j,confirm=False)[0]==422)
check('interrupted send recoverable after lock release',retry(newnr,j)[0]==200)
# SMTP can accept DATA then lose the acknowledgement. Do not claim exactly-once delivery.
smtp.drop_after_data=True
ambiguous={**payload,'requestId':'ambiguous-request-1234'}
check('lost SMTP acknowledgement reported',k.call('kunde_bestellung',ambiguous)[0]==502)
ambnr=k.call('kunde_bestellung',ambiguous)[1]['nr'];j=detail(ambnr)['outbox'][0]
check('ambiguous delivery remains visible for review',j['state']=='failed' and detail(ambnr)['mailPending']==1)
count=len(smtp.messages)
check('ambiguous delivery never automatically resent',k.call('kunde_bestellung',ambiguous)[1]['nr']==ambnr and len(smtp.messages)==count)
smtp.drop_after_data=False
check('reviewed ambiguous delivery may be resent explicitly',retry(ambnr,j)[0]==200 and len(smtp.messages)==count+1)
# Old orders have no reconstructed recipients or guessed copy state.
def legacy(all):
    next(o for o in all if o['nr']==nr).pop('outbox')
mutate(legacy)
check('legacy order remains readable',detail(nr)['outbox']==[])
check('legacy order cannot be resent by guessing job',retry(nr,j)[0]==404)
smtp.close()
print(f'{sum(results)}/{len(results)} passed');sys.exit(0 if all(results) else 1)
