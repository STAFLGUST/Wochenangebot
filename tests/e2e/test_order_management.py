import sys
from kunden_hilfe import Client
from order_setup import setup, PW

res=[]
def check(n,c):
    res.append(bool(c));print(('PASS ' if c else 'FAIL ')+n)
smtp,a,k,other,kid,payload,nr=setup()
check('anonymous staff list denied',Client().call('bestellungen')[0]==401)
check('customer staff list denied',k.call('bestellungen')[0]==401)
check('anonymous customer list denied',Client().call('kunde_bestellungen')[0]==401)
check('only own orders listed',len(k.call('kunde_bestellungen')[1]['orders'])==1 and other.call('kunde_bestellungen')[1]['total']==0)
check('other customer detail hidden',other.call('kunde_bestellung_detail&nr='+nr)[0]==404)
check('customer detail visible',k.call('kunde_bestellung_detail&nr='+nr)[0]==200)
original=k.call('kunde_bestellung_detail&nr='+nr)[1]['order']['positions']
count=len(smtp.messages); replay=k.call('kunde_bestellung',payload)
check('same key returns original order',replay[0]==200 and replay[1]['nr']==nr and replay[1]['replayed'])
check('retry creates no email or order',len(smtp.messages)==count and a.call('bestellungen')[1]['total']==1)
check('key reuse with other data rejected',k.call('kunde_bestellung',{**payload,'referenz':'different'})[0]==409)
a.call('user_save',{'username':'editor.test','name':'Editor Test','role':'editor','active':True,'password':'Editor-Zugang-77','mustChange':False})
a.call('user_save',{'username':'viewer.test','name':'Viewer Test','role':'viewer','active':True,'password':'Leserin-Zugang-1','mustChange':False})
e=Client();e.call('login',{'username':'editor.test','password':'Editor-Zugang-77'})
v=Client();v.call('login',{'username':'viewer.test','password':'Leserin-Zugang-1'})
check('viewer list denied',v.call('bestellungen')[0]==403)
check('editor list allowed',e.call('bestellungen')[0]==200)
o=e.call('bestellung&nr='+nr)[1]['order']; assignee=e.call('status')[1]['user']['id']
body={'nr':nr,'revision':o['revision'],'workflow':'in_bearbeitung','assignee':assignee,'note':'Internal <script>secret</script>'}
check('mutation requires POST',e.call('bestellung_save')[0]==405)
old=e.csrf;e.csrf='wrong';check('mutation requires CSRF',e.call('bestellung_save',body)[0]==403);e.csrf=old
check('customer cannot mutate staff order',k.call('bestellung_save',body)[0]==401)
check('viewer cannot mutate',v.call('bestellung_save',body)[0]==403)
check('valid update saved',e.call('bestellung_save',body)[0]==200)
check('stale revision rejected',e.call('bestellung_save',body)[0]==409)
public=k.call('kunde_bestellung_detail&nr='+nr)[1]['order']
check('customer sees new status',public['workflow']=='in_bearbeitung')
check('customer never receives internal fields',all(x not in public for x in ['note','history','assignee','kunde','requestId','requestHash','deliveryError']))
o=e.call('bestellung&nr='+nr)[1]['order']
check('history records actor and note',o['history'][-1]['by']=='Editor Test' and o['history'][-1]['note']==body['note'])
check('snapshot unchanged by staff update',o['positions']==original)
body['revision']=o['revision'];body['workflow']='erledigt'
check('invalid transition rejected',e.call('bestellung_save',body)[0]==422)
body['workflow']='bestaetigt';body['assignee']='missing'
check('unknown assignee rejected',e.call('bestellung_save',body)[0]==422)
body['assignee']=assignee;body['note']='x'*2001
check('note length limited',e.call('bestellung_save',body)[0]==422)
body['note']='Confirmed internally';r=e.call('bestellung_save',body)
check('confirmation transition works',r[0]==200)
body['revision']=r[1]['order']['revision'];body['workflow']='erledigt';r=e.call('bestellung_save',body)
check('completion works',r[0]==200)
body['revision']=r[1]['order']['revision'];body['workflow']='neu'
check('completed order cannot reopen silently',e.call('bestellung_save',body)[0]==422)
check('status filter works',a.call('bestellungen&workflow=neu')[1]['total']==0)
check('search works',a.call('bestellungen&q=Testreferenz')[1]['total']==1)
check('limit capped',a.call('bestellungen&limit=9999')[1]['limit']==100)
check('internal updates send no emails',len(smtp.messages)==count)
check('contact snapshot preserved',o['kunde']['firma']=='Kantine <Test>')
draft=a.call('draft')[1]; model=draft['published'];model['items'][0]['price']={'status':'value','value':999}
check('new offer can be published',a.call('publish',{'model':model,'revision':draft['revision']})[0]==200)
check('old order keeps original prices',k.call('kunde_bestellung_detail&nr='+nr)[1]['order']['positions']==original)
check('replay survives changed publication',k.call('kunde_bestellung',payload)[1].get('nr')==nr)
check('no duplicate after publication change',a.call('bestellungen')[1]['total']==1 and len(smtp.messages)==count)
smtp.close()
print(f'{sum(res)}/{len(res)} passed');sys.exit(0 if all(res) else 1)
