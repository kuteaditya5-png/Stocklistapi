import {trusted,cookie} from '../server/security.js';
import {json,failure} from '../server/http.js';
export default function handler(req,res){if(req.method!=='POST')return json(res,405,{error:'Method not allowed'});try{if(!trusted(req))return json(res,403,{error:'Invalid request origin.'});res.setHeader('Set-Cookie',cookie('',0));return json(res,200,{signedOut:true});}catch(e){return failure(res,e)}}
