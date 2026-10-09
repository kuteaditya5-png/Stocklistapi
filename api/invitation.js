import {withInvitations,findInvitation,validToken} from '../server/invitations.js';
import {json,failure} from '../server/http.js';
export default async function handler(req,res){
 if(req.method!=='GET')return json(res,405,{error:'Method not allowed'});
 try{
  const token=new URL(req.url,'https://local.invalid').searchParams.get('invite')||'';
  if(!validToken(token))return json(res,403,{error:'Please open the full invitation link you received.'});
  const invitation=await withInvitations(client=>findInvitation(client,token));
  if(!invitation)return json(res,403,{error:'This invitation link is no longer active. Please ask for a new link.'});
  return json(res,200,{name:invitation.recipient_name});
 }catch(e){return failure(res,e)}
}
