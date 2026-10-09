import test from 'node:test';
import assert from 'node:assert/strict';
import pg from 'pg';
import respond from '../api/respond.js';
process.env.APP_URL='https://example.test';
process.env.INVITATION_TOKEN='y'.repeat(64);
process.env.DATABASE_URL='postgresql://test:test@localhost/test';
const response=()=>({setHeader(){},status(n){this.statusCode=n;return this},json(d){this.data=d;return this}});
const date=new Date(Date.now()+7*86400000).toISOString().slice(0,10);
test('rejects absent and unsupported ideas before database access',async()=>{
 for(const idea of [undefined,'walk','',{},['coffee']]){
 const r=response();await respond({method:'POST',headers:{origin:process.env.APP_URL},body:{token:process.env.INVITATION_TOKEN,date,time:'19:00',idea}},r);assert.equal(r.statusCode,400);
 }
});
test('persists all four choices with the recipient from the database and rejects duplicates',async()=>{
 const original=pg.Pool.prototype.connect;let calls=[];let rowCount=1;
 pg.Pool.prototype.connect=async()=>({release(){},async query(sql,params){calls.push({sql,params});if(sql.startsWith('SELECT'))return {rowCount:1,rows:[{recipient_name:'Priya',response_key:'fixed-key'}]};return {rowCount};}});
 try{for(const idea of ['coffee','movie','sunset','dinner']){
 const r=response();await respond({method:'POST',headers:{origin:process.env.APP_URL},body:{token:process.env.INVITATION_TOKEN,name:'Forged name',date,time:'19:00',idea}},r);assert.equal(r.statusCode,200);const saved=calls.findLast(c=>c.sql.startsWith('INSERT'));assert.equal(saved.params[5],idea);assert.equal(saved.params[1],'Priya');assert.match(saved.sql,/date_idea/);
 }rowCount=0;const r=response();await respond({method:'POST',headers:{origin:process.env.APP_URL},body:{token:process.env.INVITATION_TOKEN,date,time:'19:00',idea:'coffee'}},r);assert.equal(r.statusCode,409);
 }finally{pg.Pool.prototype.connect=original;}
});
