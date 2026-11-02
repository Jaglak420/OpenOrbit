/* Panelowy edytor klanów i dyplomacji. */
'use strict';
async function renderKlanlar() {
  const root = $('#content');
  let data;
  try { data = await api('/api/klanlar'); } catch(e) {
    root.replaceChildren(h('div',{class:'alert hata'},icon('alert'),h('div',null,e.message))); return;
  }
  if (S.page !== 'klanlar') return;
  let clans = data.klanlar || [], selected = clans[0]?.id || null;
  const refresh = async () => { const d=await api('/api/klanlar'); clans=d.klanlar||[]; draw(); };
  const field = (label, value, type='text') => {
    const inp=h('input',{class:'input',type,value:value??''});
    return {node:h('label',{class:'field'},h('span',{class:'lbl'},T(label)),inp),input:inp};
  };
  const draw = () => {
    const current=clans.find(c=>c.id===selected);
    const left=h('div',{class:'card stack'},h('h2',null,icon('users'),T('Klany ({0})',clans.length)),
      clans.length ? clans.map(c=>h('button',{class:'list-row'+(c.id===selected?' active':''),onclick:()=>{selected=c.id;draw();}},
        h('div',null,h('b',null,'['+c.etiket+'] '+c.ad),h('div',{class:'small muted'},T('ID {0} · {1} członków',c.id,c.uye_sayisi))),
        h('span',{class:'badge'},'F'+c.firma))) : h('div',{class:'empty'},T('Brak klanów.')));
    let right;
    if (!current) right=h('div',{class:'card'},T('Wybierz klan.'));
    else {
      const fAd=field('Nazwa',current.ad), fTag=field('Tag',current.etiket), fDesc=field('Opis',current.aciklama);
      const fFirma=field('Firma (1 MMO, 2 EIC, 3 VRU)',current.firma,'number');
      const fTax=field('Podatek (%)',current.vergi,'number'), fLeader=field('Lider (login)',current.lider);
      const fRecruit=field('Rekrutacja (0 zamknięta, 1 otwarta, 2 wymagane podanie)',current.alim,'number');
      const save=btn(T('Zapisz zmiany'),async()=>{const r=await act(()=>api('/api/klanlar/duzenle',{id:current.id,ad:fAd.input.value,etiket:fTag.input.value,aciklama:fDesc.input.value,
        firma:+fFirma.input.value,vergi:+fTax.input.value,lider:fLeader.input.value,alim:+fRecruit.input.value}),T('Zapisano klan.'));if(r) await refresh();},'primary');
      const members=h('div',{class:'stack'},h('h3',null,T('Członkowie ({0})',current.uye_sayisi)),
        current.uyeler.length?current.uyeler.map(m=>h('div',{class:'row between'},h('span',null,m.ad,' ',h('small',{class:'muted'},'('+m.pilot+')')),h('small',{class:'muted'},T('Ranga {0}',m.rutbe),m.pilot===current.lider?' · Lider':''))):h('div',{class:'muted'},T('Brak członków.')));
      const rels=current.diplomasi||[];
      const diplomacy=h('div',{class:'stack'},h('h3',null,T('Dyplomacja')),
        rels.length?rels.map(d=>{const other=clans.find(c=>c.id===d.klan);const names={1:T('Sojusz'),2:T('Pakt o nieagresji'),3:T('Wojna')};
          return h('div',{class:'row between wrap'},h('div',null,h('b',null,other?other.ad:(d.ad||d.klan)),h('div',{class:'small muted'},names[d.tur]||T('Relacja'))),
            btn(T('Usuń relację'),async()=>{const r=await act(()=>api('/api/klanlar/diplomasi',{id:current.id,cel:d.klan,akcja:'usun'}),T('Usunięto relację.'));if(r)await refresh();},'ghost sm'));}):h('div',{class:'muted'},T('Brak relacji.')));
      const target=h('select',{class:'input'},clans.filter(c=>c.id!==current.id).map(c=>h('option',{value:c.id},'['+c.etiket+'] '+c.ad+' · '+c.id)));
      const kind=h('select',{class:'input'},[[1,T('Sojusz')],[2,T('Pakt o nieagresji')],[3,T('Wojna')],[0,T('Pokój / zakończ relację')]].map(([v,n])=>h('option',{value:v},n)));
      const note=h('input',{class:'input',placeholder:T('Opis (opcjonalnie)')});
      const apply=btn(T('Ustaw relację'),async()=>{if(!target.value)return;const r=await act(()=>api('/api/klanlar/diplomasi',{id:current.id,cel:+target.value,tur:+kind.value,metin:note.value}),T('Zaktualizowano dyplomację.'));if(r)await refresh();},'primary sm');
      right=h('div',{class:'stack'},
        h('div',{class:'card stack'},h('div',{class:'row between'},h('h2',null,'['+current.etiket+'] '+current.ad),h('span',{class:'badge'},'ID '+current.id)),
          h('div',{class:'grid g2'},fAd.node,fTag.node,fFirma.node,fTax.node,fRecruit.node,fLeader.node),fDesc.node,save,
          h('div',{class:'small muted'},T('Kasa klanu: {0} kredytów · lider: {1}',fmtN(current.kasa),current.lider))),
        h('div',{class:'card stack'},members),
        h('div',{class:'card stack'},diplomacy,h('h3',null,T('Dodaj / zmień relację')),target,kind,note,apply));
    }
    root.replaceChildren(h('div',{class:'grid g2'},left,right));
  };
  draw();
}
