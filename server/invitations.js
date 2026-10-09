import {randomBytes,randomUUID} from 'node:crypto';
import {siteConfig} from '../config/site.js';
import {db} from './db.js';
import {secret,invitationKey} from './security.js';
export const linkLimit=10;
export function validToken(token){return typeof token==='string'&&token.length>=32&&token.length<=512;}
// Serialize creation, revocation and response saves on one connection. The unique
// 1..10 slot constraint also enforces the active-link limit in PostgreSQL.
export async function withInvitations(work){
 const client=await db().connect();
 try{
  await client.query('BEGIN');
  await client.query('SELECT pg_advisory_xact_lock(742018,10)');
  const legacy=await client.query("SELECT invitation_id FROM date_invite.invitations WHERE invitation_id='legacy'");
  if(!legacy.rowCount)await client.query('INSERT INTO date_invite.invitations (invitation_id,recipient_name,token,active_slot,response_key) VALUES ($1,$2,$3,1,$4)', ['legacy',siteConfig.recipientName,secret('INVITATION_TOKEN'),invitationKey(siteConfig.recipientName,siteConfig.invitationId)]);
  const value=await work(client);
  await client.query('COMMIT');
  return value;
 }catch(e){await client.query('ROLLBACK').catch(()=>{});throw e;}finally{client.release();}
}
export async function findInvitation(client,token){
 const result=await client.query('SELECT invitation_id,recipient_name,response_key FROM date_invite.invitations WHERE token=$1 AND active_slot IS NOT NULL',[token]);
 return result.rows[0];
}
export function newInvitation(name){const id=randomUUID();return {id,name,token:randomBytes(32).toString('base64url'),key:'invitation:'+id};}
