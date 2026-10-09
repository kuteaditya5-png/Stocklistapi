const $=id=>document.getElementById(id);function error(message){$('error').textContent=message;$('error').hidden=!message}
async function load(){error('');try{const r=await fetch('/api/admin');if(r.status===401){$('login').hidden=false;$('dashboard').hidden=true;return}const d=await r.json();if(!r.ok)throw Error(d.error);$('login').hidden=true;$('dashboard').hidden=false;renderInvitations(d.invitations,d.limit);const area=$('responses');area.replaceChildren();if(!d.responses.length){const p=document.createElement('p');p.textContent='No responses yet. Come back after confirmation and click Refresh.';area.append(p)}for(const row of d.responses){const article=document.createElement('article');article.className='reply';const h=document.createElement('h3');h.textContent=row.recipient_name+' said yes! ♥';const p=document.createElement('p');p.textContent=new Date(row.selected_date+'T12:00:00+05:30').toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Kolkata'});const t=document.createElement('strong');const [hh,mm]=row.selected_time.split(':');t.textContent=`${+hh%12||12}:${mm} ${+hh>=12?'PM':'AM'} · IST`;const received=document.createElement('p');received.className='small muted';received.textContent='Received '+new Date(row.created_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST';const idea=document.createElement('p');const labels={coffee:'☕ Coffee & conversation',movie:'🎬 Movie date',sunset:'🌅 Watch the sunset',dinner:'🍽️ Dinner together'};idea.textContent=labels[row.date_idea]||'Date idea: Not selected (earlier response)';article.append(h,idea,p,t,received);area.append(article)}}catch(e){error(e.message)}}
$('login-form').onsubmit=async e=>{e.preventDefault();error('');$('login-button').disabled=true;try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('password').value})});const d=await r.json();if(!r.ok)throw Error(d.error);$('password').value='';await load()}catch(e){error(e.message)}finally{$('login-button').disabled=false}};$('logout').onclick=async()=>{try{const r=await fetch('/api/logout',{method:'POST'});if(!r.ok)throw Error('Could not sign out.');$('responses').replaceChildren();$('invitations').replaceChildren();$('new-invitation').reset();toggleForm(false);await load()}catch(e){error(e.message)}};$('refresh').onclick=load;let busy=false;
function toggleForm(open){$('new-invitation').hidden=!open;$('new-link').setAttribute('aria-expanded',String(open));if(open)$('recipient-name').focus()}
function renderInvitations(invitations,limit){
 $('link-count').textContent=invitations.length+' / '+limit;
 $('new-link').disabled=invitations.length>=limit;
 $('generate').disabled=invitations.length>=limit;
 $('reset-links').disabled=!invitations.length;
 if(invitations.length>=limit)toggleForm(false);
 const area=$('invitations');area.replaceChildren();
 if(!invitations.length){const p=document.createElement('p');p.className='empty';p.textContent='No active links. Tap + New invitation to create your first one.';area.append(p)}
 for(const item of invitations){
  const card=document.createElement('article');card.className='invitation-item';
  const head=document.createElement('div');head.className='section-top';
  const title=document.createElement('h3');title.textContent=item.name;
  const badge=document.createElement('span');badge.className='badge active-badge';badge.textContent='Active';head.append(title,badge);
  const url=document.createElement('input');url.readOnly=true;url.value=item.url;url.setAttribute('aria-label','Invitation link for '+item.name);
  const actions=document.createElement('div');actions.className='row';
  const copy=document.createElement('button');copy.className='secondary';copy.textContent='Copy link';copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(item.url);$('notice').textContent='Link copied for '+item.name+'.'}catch{url.focus();url.select();$('notice').textContent='Select and copy the highlighted link.'}};
  const preview=document.createElement('a');preview.className='secondary';preview.textContent='Preview';preview.href=item.url;preview.target='_blank';preview.rel='noopener noreferrer';
  const remove=document.createElement('button');remove.className='secondary danger';remove.type='button';remove.textContent='Delete link';remove.onclick=()=>{if(confirm('Disable the invitation link for '+item.name+'? Saved responses will remain.'))mutate({action:'revoke',id:item.id},'Link deleted.')};
  actions.append(copy,preview,remove);card.append(head,url,actions);area.append(card);
 }
}
async function mutate(payload,message){
 if(busy)return;busy=true;error('');$('notice').textContent='Saving…';
 const buttons=[...$('dashboard').querySelectorAll('button')];const disabled=buttons.map(b=>b.disabled);buttons.forEach(b=>b.disabled=true);
 try{const r=await fetch('/api/admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error||'Could not update invitations.');if(payload.action==='create'){$('new-invitation').reset();toggleForm(false)}$('notice').textContent=message}
 catch(e){$('notice').textContent='';error(e.message)}
 finally{buttons.forEach((b,i)=>b.disabled=disabled[i]);busy=false;await loadPreservingError()}
}
async function loadPreservingError(){const previous=$('error').textContent;await load();if(previous&&!$('error').textContent)error(previous)}
$('new-link').onclick=()=>toggleForm($('new-invitation').hidden);
$('cancel-new').onclick=()=>toggleForm(false);
$('new-invitation').onsubmit=e=>{e.preventDefault();const name=$('recipient-name').value.trim();if(!name)return error('Enter a recipient name.');mutate({action:'create',name},'Invitation created. Copy the link below to share it.')};
$('reset-links').onclick=()=>{if(confirm('Reset ALL active invitation links? Everyone with an old link will need a new one. Saved responses will remain.'))mutate({action:'reset'},'All links disabled. You can now create up to 10 new links.')};
load();
