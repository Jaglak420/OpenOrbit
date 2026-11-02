"""Panelowy edytor kanonicznych klanów i dyplomacji (save/klanlar.json)."""
import json, os, re, tempfile, time
class KlanPanelHatasi(ValueError): pass
def _dosya():
    import yollar as YOL
    return os.path.join(YOL.SAVE, 'klanlar.json')
def _oku():
    try:
        with open(_dosya(), encoding='utf8') as f: d=json.load(f)
    except FileNotFoundError: d={'klanlar':{},'silinen':{},'bot_ad_kaydi':0}
    except (OSError,ValueError) as e: raise KlanPanelHatasi('Nie można odczytać pliku klanów: %s'%e)
    d.setdefault('klanlar',{}); return d
def _zapisz(d):
    p=_dosya(); os.makedirs(os.path.dirname(p),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.klanlar-',suffix='.tmp',dir=os.path.dirname(p))
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f: json.dump(d,f,ensure_ascii=False,separators=(',',':')); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.remove(tmp)
def _id(v):
    try: return str(int(v))
    except (TypeError,ValueError): raise KlanPanelHatasi('Nieprawidłowe ID klanu.')
def liste():
    d=_oku(); out=[]
    for key,k in d['klanlar'].items():
        if not isinstance(k,dict): continue
        members=k.get('uyeler') or {}
        out.append({'id':int(k.get('id',key)),'ad':str(k.get('ad','')),'etiket':str(k.get('etiket','')),'aciklama':str(k.get('aciklama','')),
          'firma':int(k.get('firma',0) or 0),'lider':str(k.get('lider','')),'uye_sayisi':len(members),
          'uyeler':[{'pilot':str(n),'ad':str(u.get('ad',n)),'rutbe':int(u.get('rutbe',0) or 0)} for n,u in members.items()],
          'vergi':float(k.get('vergi',0) or 0),'alim':int(k.get('alim',0) or 0),'kasa':int(k.get('kasa',0) or 0),
          'diplomasi':list(k.get('diplomasi') or []),'diplo_istek':list(k.get('diplo_istek') or [])})
    return {'klanlar':sorted(out,key=lambda x:(x['ad'].casefold(),x['id']))}
def duzenle(b):
    d=_oku(); cid=_id(b.get('id')); k=d['klanlar'].get(cid)
    if not k: raise KlanPanelHatasi('Klan nie istnieje.')
    ad=str(b.get('ad',k.get('ad',''))).strip(); tag=str(b.get('etiket',k.get('etiket',''))).strip().upper(); opis=str(b.get('aciklama',k.get('aciklama',''))).strip()
    if not ad or len(ad)>40: raise KlanPanelHatasi('Nazwa klanu musi mieć 1–40 znaków.')
    if len(tag)>4 or not re.fullmatch(r'[A-Z0-9]*',tag): raise KlanPanelHatasi('Tag może mieć maksymalnie 4 znaki A-Z/0-9.')
    if len(opis)>500: raise KlanPanelHatasi('Opis może mieć maksymalnie 500 znaków.')
    for o in d['klanlar'].values():
        if o is k: continue
        if ad.casefold()==str(o.get('ad','')).casefold(): raise KlanPanelHatasi('Ta nazwa klanu jest już zajęta.')
        if tag and tag.casefold()==str(o.get('etiket','')).casefold(): raise KlanPanelHatasi('Ten tag klanu jest już zajęty.')
    firma=int(b.get('firma',k.get('firma',1))); vergi=float(b.get('vergi',k.get('vergi',0))); alim=int(b.get('alim',k.get('alim',0)))
    if firma not in (1,2,3): raise KlanPanelHatasi('Firma musi mieć wartość 1, 2 lub 3.')
    if not 0<=vergi<=100: raise KlanPanelHatasi('Podatek musi być w zakresie 0–100%.')
    if alim not in (0,1,2): raise KlanPanelHatasi('Nieprawidłowy tryb rekrutacji.')
    lider=str(b.get('lider',k.get('lider',''))).strip().lower()
    if lider and lider not in (k.get('uyeler') or {}): raise KlanPanelHatasi('Lider musi być członkiem klanu.')
    k.update(ad=ad,etiket=tag,aciklama=opis,firma=firma,vergi=vergi,alim=alim)
    if lider: k['lider']=lider
    k['surum']=int(k.get('surum',0))+1; _zapisz(d); return liste()
def dyplomacja(b):
    d=_oku(); clans=d['klanlar']; aid,bid=_id(b.get('id')),_id(b.get('cel'))
    if aid==bid: raise KlanPanelHatasi('Klan nie może mieć relacji sam ze sobą.')
    a,bk=clans.get(aid),clans.get(bid)
    if not a or not bk: raise KlanPanelHatasi('Nie znaleziono jednego z klanów.')
    action=b.get('akcja','ustaw'); tur=int(b.get('tur',0))
    if action=='usun' or (action=='ustaw' and tur==0):
        for c,o in ((a,bk),(bk,a)): c['diplomasi']=[x for x in c.get('diplomasi',[]) if int(x.get('klan',0))!=int(o['id'])]
    elif action=='ustaw':
        if tur not in (1,2,3): raise KlanPanelHatasi('Wybierz sojusz, pakt o nieagresji albo wojnę.')
        desc=str(b.get('metin',''))[:500]; did=int(time.time()*1000)%2147483647
        for c,o in ((a,bk),(bk,a)):
            c['diplomasi']=[x for x in c.get('diplomasi',[]) if int(x.get('klan',0))!=int(o['id'])]
            row={'id':did,'klan':int(o['id']),'ad':o.get('ad',''),'tur':tur,'tarih':time.strftime('%Y-%m-%d %H:%M:%S'),'metin':desc,'kimden':int(a['id'])}
            if tur==3: row['bitis']=time.time()+10*86400
            c.setdefault('diplomasi',[]).append(row)
    else: raise KlanPanelHatasi('Nieznana operacja dyplomatyczna.')
    for c in (a,bk):
        c['diplo_istek']=[x for x in c.get('diplo_istek',[]) if not (int(x.get('kimden',0)) in (int(a['id']),int(bk['id'])) and int(x.get('kime',0)) in (int(a['id']),int(bk['id'])))]
        c['surum']=int(c.get('surum',0))+1
    _zapisz(d); return liste()
def get(path,q):
    if path=='/api/klanlar': return liste()
    raise KlanPanelHatasi('Nieznane żądanie klanów.')
def post(path,b):
    if path=='/api/klanlar/duzenle': return duzenle(b)
    if path=='/api/klanlar/diplomasi': return dyplomacja(b)
    raise KlanPanelHatasi('Nieznane żądanie klanów.')
