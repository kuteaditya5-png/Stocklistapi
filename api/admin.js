import {siteConfig} from '../config/site.js';
import {db} from '../server/db.js';
import {isAdmin,origin,secret} from '../server/security.js';
import {json,failure} from '../server/http.js';
export default async function handler(req,res){if(req.method!=='GET')return json(res,405,{error:'Method not allowed'});if(!isAdmin(req))return json(res,401,{error:'Sign in to view responses.'});try{const result=await db().query("SELECT response_id,recipient_name,TO_CHAR(selected_date,'YYYY-MM-DD') AS selected_date,TO_CHAR(selected_time,'HH24:MI') AS selected_time,timezone,created_at FROM date_invite.responses ORDER BY created_at DESC LIMIT 100");return json(res,200,{name:siteConfig.recipientName,invitationUrl:origin()+'/?invite='+encodeURIComponent(secret('INVITATION_TOKEN')),responses:result.rows});}catch(e){return failure(res,e)}}
