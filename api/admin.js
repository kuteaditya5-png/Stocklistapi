import {db} from '../server/db.js';
import {isAdmin,origin,trusted} from '../server/security.js';
import {withInvitations,newInvitation,linkLimit} from '../server/invitations.js';
import {json,body,failure} from '../server/http.js';
export default async function handler(req,res){
 if(!['GET','POST'].includes(req.method))return json(res,405,{error:'Method not allowed'});
 if(!isAdmin(req))return json(res,401,{error:'Sign in to manage invitations.'});
 try{
  if(req.method==='POST'){
   if(!trusted(req))return json(res,403,{error:'Invalid request origin.'});
   let b;try{b=body(req)}catch{return json(res,400,{error:'Invalid request.'})}
   if(!['create','reset','revoke'].includes(b.action))return json(res,400,{error:'Unknown action.'});
   const name=typeof b.name==='string'?b.name.trim():'';
   if(b.action==='create'&&(!name||name.length>60||/[\u0000-\u001f\u007f]/.test(name)))return json(res,400,{error:'Enter a name between 1 and 60 characters.'});
   if(b.action==='revoke'&&(typeof b.id!=='string'||b.id.length>50))return json(res,400,{error:'Invalid invitation.'});
   const result=await withInvitations(async client=>{
    if(b.action==='reset'){
     const r=await client.query('UPDATE date_invite.invitations SET active_slot=NULL,revoked_at=NOW() WHERE active_slot IS NOT NULL');
     return {status:200,data:{reset:true,count:r.rowCount}};
    }
    if(b.action==='revoke'){
     const r=await client.query('UPDATE date_invite.invitations SET active_slot=NULL,revoked_at=NOW() WHERE invitation_id=$1 AND active_slot IS NOT NULL',[b.id]);
     return {status:r.rowCount?200:404,data:r.rowCount?{revoked:true}:{error:'This link is no longer active.'}};
    }
    const r=await client.query('SELECT active_slot FROM date_invite.invitations WHERE active_slot IS NOT NULL');
    if(r.rows.length>=linkLimit)return {status:409,data:{error:'You already have 10 active links. Delete a link or reset all links first.'}};
    const occupied=new Set(r.rows.map(row=>row.active_slot));
    const slot=Array.from({length:linkLimit},(_,i)=>i+1).find(i=>!occupied.has(i));
    const invitation=newInvitation(name);
    await client.query('INSERT INTO date_invite.invitations (invitation_id,recipient_name,token,active_slot,response_key) VALUES ($1,$2,$3,$4,$5)',[invitation.id,name,invitation.token,slot,invitation.key]);
    return {status:201,data:{created:true}};
   });
   return json(res,result.status,result.data);
  }
  const invitations=await withInvitations(async client=>(await client.query('SELECT invitation_id,recipient_name,token,created_at FROM date_invite.invitations WHERE active_slot IS NOT NULL ORDER BY created_at DESC,invitation_id')).rows);
  const responses=await db().query("SELECT response_id,recipient_name,TO_CHAR(selected_date,'YYYY-MM-DD') AS selected_date,TO_CHAR(selected_time,'HH24:MI') AS selected_time,timezone,date_idea,created_at FROM date_invite.responses ORDER BY created_at DESC LIMIT 100");
  return json(res,200,{limit:linkLimit,invitations:invitations.map(row=>({id:row.invitation_id,name:row.recipient_name,createdAt:row.created_at,url:origin()+'/?invite='+encodeURIComponent(row.token)})),responses:responses.rows});
 }catch(e){return failure(res,e)}
}
