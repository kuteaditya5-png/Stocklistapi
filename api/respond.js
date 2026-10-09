import {siteConfig} from '../config/site.js';
import {trusted,validSlot} from '../server/security.js';
import {withInvitations,findInvitation,validToken} from '../server/invitations.js';
import {json,body,failure} from '../server/http.js';
export default async function handler(req,res){
 if(req.method!=='POST')return json(res,405,{error:'Method not allowed'});
 try{
  if(!trusted(req))return json(res,403,{error:'Invalid request origin.'});
  let b;try{b=body(req)}catch{return json(res,400,{error:'Invalid request.'})}
  if(!validToken(b.token))return json(res,403,{error:'Invalid invitation link.'});
  if(typeof b.idea!=='string'||!['coffee','movie','sunset','dinner'].includes(b.idea))return json(res,400,{error:'Choose coffee, movie, sunset, or dinner.'});
  if(!validSlot(b.date,b.time))return json(res,400,{error:'Choose a future date and time within the next year (IST).'});
  const result=await withInvitations(async client=>{
   const invitation=await findInvitation(client,b.token);
   if(!invitation)return {status:403,data:{error:'This invitation link is no longer active. Please ask for a new link.'}};
   const saved=await client.query('INSERT INTO date_invite.responses (invitation_key,recipient_name,selected_date,selected_time,timezone,date_idea) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT(invitation_key) DO NOTHING RETURNING response_id',[invitation.response_key,invitation.recipient_name,b.date,b.time,siteConfig.timezone,b.idea]);
   return saved.rowCount?{status:200,data:{saved:true}}:{status:409,data:{error:'This invitation has already been confirmed. Please contact me if the plan needs to change.'}};
  });
  return json(res,result.status,result.data);
 }catch(e){return failure(res,e)}
}
