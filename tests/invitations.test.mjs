import test from 'node:test';
import assert from 'node:assert/strict';
import pg from 'pg';
import admin from '../api/admin.js';
import invitation from '../api/invitation.js';
import respond from '../api/respond.js';
import {session,invitationKey} from '../server/security.js';
import {siteConfig} from '../config/site.js';
process.env.APP_URL='https://example.test';process.env.SESSION_SECRET='s'.repeat(64);process.env.INVITATION_TOKEN='t'.repeat(64);process.env.DATABASE_URL='postgresql://test:test@localhost/test';
const res=()=>({setHeader(){},status(n){this.statusCode=n;return this},json(data){this.data=data;return this}});
const headers=()=>({origin:process.env.APP_URL,cookie:'gotham_admin='+session()});
// Stateful database double validates the API lifecycle. Production concurrency
// additionally relies on PostgreSQL advisory locks and unique slot constraints.
function database(){
 const rows=[];const responses=[];const calls=[];let queue=Promise.resolve();
 const originalConnect=pg.Pool.prototype.connect,originalQuery=pg.Pool.prototype.query;
 pg.Pool.prototype.query=async()=>({rows:responses});
 pg.Pool.prototype.connect=async()=>{
  let unlock;let snapshot;
  return {release(){assert.equal(unlock,undefined,'transaction must finish before release')},async query(sql,p=[]){
   calls.push(sql);
   if(sql==='BEGIN')return {};
   if(sql.includes('pg_advisory_xact_lock')){const previous=queue;queue=new Promise(r=>unlock=r);await previous;snapshot=structuredClone(rows);return {}};
   if(sql==='COMMIT'||sql==='ROLLBACK'){if(sql==='ROLLBACK')rows.splice(0,rows.length,...snapshot);unlock?.();unlock=undefined;return {}};
   if(sql.includes("WHERE invitation_id='legacy'"))return {rows:rows.filter(r=>r.invitation_id==='legacy'),rowCount:rows.some(r=>r.invitation_id==='legacy')?1:0};
   if(sql.startsWith('INSERT INTO date_invite.invitations')){const legacy=p[0]==='legacy';rows.push({invitation_id:p[0],recipient_name:p[1],token:p[2],active_slot:legacy?1:p[3],response_key:legacy?p[3]:p[4],created_at:new Date().toISOString()});return {rowCount:1}};
   if(sql.startsWith('UPDATE')){const targets=rows.filter(r=>r.active_slot!==null&&(!p.length||r.invitation_id===p[0]));targets.forEach(r=>r.active_slot=null);return {rowCount:targets.length}};
   if(sql.startsWith('SELECT active_slot'))return {rows:rows.filter(r=>r.active_slot!==null)};
   if(sql.includes('WHERE token=$1'))return {rows:rows.filter(r=>r.token===p[0]&&r.active_slot!==null)};
   if(sql.startsWith('SELECT invitation_id,recipient_name,token'))return {rows:rows.filter(r=>r.active_slot!==null)};
   if(sql.startsWith('INSERT INTO date_invite.responses')){if(responses.some(r=>r.key===p[0]))return {rowCount:0};responses.push({key:p[0],name:p[1],idea:p[5]});return {rowCount:1}};
   throw Error('Unexpected query: '+sql);
  }};
 };
 return {rows,responses,calls,restore(){pg.Pool.prototype.connect=originalConnect;pg.Pool.prototype.query=originalQuery}};
}
async function command(body){const r=res();await admin({method:'POST',headers:headers(),body},r);return r}
async function getAdmin(){const r=res();await admin({method:'GET',headers:headers()},r);return r}
async function open(token){const r=res();await invitation({method:'GET',url:'/?invite='+encodeURIComponent(token),headers:{}},r);return r}
async function save(token){const r=res();await respond({method:'POST',headers:{origin:process.env.APP_URL},body:{token,date:new Date(Date.now()+86400000*7).toISOString().slice(0,10),time:'19:00',idea:'coffee'}},r);return r}
test('full invitation lifecycle: legacy migration, unique names/links, cap, revoke, reset and reuse',async()=>{
 const db=database();try{
  let r=await getAdmin();assert.equal(r.statusCode,200);assert.equal(r.data.invitations.length,1);
  assert.equal(db.rows[0].response_key,invitationKey(siteConfig.recipientName,siteConfig.invitationId));
  assert.equal((await open(process.env.INVITATION_TOKEN)).statusCode,200);
  assert.equal((await command({action:'create',name:'  Priya  '})).statusCode,201);
  assert.equal((await command({action:'create',name:'Priya'})).statusCode,201);
  const first=db.rows[1],second=db.rows[2];assert.notEqual(first.token,second.token);assert.notEqual(first.response_key,second.response_key);
  assert.equal((await open(first.token)).data.name,'Priya');assert.equal((await save(first.token)).statusCode,200);assert.equal((await save(first.token)).statusCode,409);
  assert.equal((await save(second.token)).statusCode,200);
  const concurrent=await Promise.all(Array.from({length:12},(_,i)=>command({action:'create',name:'Guest '+i})));
  assert.equal(concurrent.filter(r=>r.statusCode===201).length,7);assert.equal(concurrent.filter(r=>r.statusCode===409).length,5);
  assert.equal((await getAdmin()).data.invitations.length,10);
  assert.equal((await command({action:'revoke',id:first.invitation_id})).statusCode,200);
  assert.equal((await open(first.token)).statusCode,403);assert.equal((await save(first.token)).statusCode,403);
  assert.equal((await command({action:'create',name:'Replacement'})).statusCode,201);
  assert.equal((await command({action:'reset'})).data.count,10);
  assert.equal((await getAdmin()).data.invitations.length,0);assert.equal(db.responses.length,2);
  assert.equal((await open(process.env.INVITATION_TOKEN)).statusCode,403);assert.equal((await save(second.token)).statusCode,403);
  for(let i=0;i<10;i++)assert.equal((await command({action:'create',name:'New '+i})).statusCode,201);
  assert.equal((await getAdmin()).data.invitations.length,10);
 }finally{db.restore()}
});
test('admin mutation authorization and validation fail before any database call',async()=>{
 const original=pg.Pool.prototype.connect;pg.Pool.prototype.connect=async()=>{throw Error('Database must not be reached')};
 try{for(const action of ['create','reset','revoke']){let r=res();await admin({method:'POST',headers:{},body:{action}},r);assert.equal(r.statusCode,401);r=res();await admin({method:'POST',headers:{...headers(),origin:'https://evil.test'},body:{action}},r);assert.equal(r.statusCode,403)}
 for(const name of ['', '  ', 'x'.repeat(61),42,'bad\nname'])assert.equal((await command({action:'create',name})).statusCode,400);
 assert.equal((await command({action:'unknown'})).statusCode,400);
 }finally{pg.Pool.prototype.connect=original}
});
test('transaction error rolls back and releases the connection',async()=>{
 const original=pg.Pool.prototype.connect;const queries=[];let released=false;
 pg.Pool.prototype.connect=async()=>({release(){released=true},async query(sql){queries.push(sql);if(sql==='BEGIN'||sql==='ROLLBACK'||sql.includes('pg_advisory'))return {};throw Error('Simulated failure')}});
 const old=console.error;console.error=()=>{};
 try{assert.equal((await getAdmin()).statusCode,503);assert.ok(queries.includes('ROLLBACK'));assert.equal(released,true)}finally{pg.Pool.prototype.connect=original;console.error=old}
});
