import {siteConfig} from '../config/site.js';
import {equal,secret,isAdmin} from '../server/security.js';
import {json,failure} from '../server/http.js';
export default function handler(req,res){if(req.method!=='GET')return json(res,405,{error:'Method not allowed'});try{const token=new URL(req.url,'https://local.invalid').searchParams.get('invite')||'';const owner=isAdmin(req);if(!owner&&!equal(token,secret('INVITATION_TOKEN')))return json(res,403,{error:'Please open the full invitation link you received.'});return json(res,200,{name:siteConfig.recipientName,owner});}catch(e){return failure(res,e)}}
