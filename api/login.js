import {createHash} from 'node:crypto';
import {db} from '../server/db.js';
import {equal,secret,trusted,session,cookie} from '../server/security.js';
import {json,body,failure} from '../server/http.js';
export default async function handler(req,res){if(req.method!=='POST')return json(res,405,{error:'Method not allowed'});try{if(!trusted(req))return json(res,403,{error:'Invalid request origin.'});let b;try{b=body(req)}catch{return json(res,400,{error:'Invalid request.'})}if(typeof b.password!=='string'||b.password.length>256)return json(res,400,{error:'Enter your admin password.'});secret('ADMIN_PASSWORD',16);secret('SESSION_SECRET');
 // Vercel sets this header; fall back to the socket for local development.
 const ip=process.env.VERCEL?(req.headers['x-vercel-forwarded-for']||'unknown'):req.socket?.remoteAddress||'local';
 const key=createHash('sha256').update(String(ip)+secret('SESSION_SECRET')).digest('hex');
 await db().query("DELETE FROM date_invite.login_limits WHERE window_start < NOW()-INTERVAL '1 day'");
 const result=await db().query("INSERT INTO date_invite.login_limits (key,attempts,window_start) VALUES ($1,1,NOW()) ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN date_invite.login_limits.window_start < NOW()-INTERVAL '15 minutes' THEN 1 ELSE date_invite.login_limits.attempts+1 END,window_start=CASE WHEN date_invite.login_limits.window_start < NOW()-INTERVAL '15 minutes' THEN NOW() ELSE date_invite.login_limits.window_start END RETURNING attempts",[key]);
 if(result.rows[0].attempts>10)return json(res,429,{error:'Too many attempts. Try again in 15 minutes.'});if(!equal(b.password,secret('ADMIN_PASSWORD',16)))return json(res,401,{error:'Incorrect password.'});await db().query('DELETE FROM date_invite.login_limits WHERE key=$1',[key]);res.setHeader('Set-Cookie',cookie(session()));return json(res,200,{signedIn:true});}catch(e){return failure(res,e)}}
