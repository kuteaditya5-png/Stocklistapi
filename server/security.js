import {createHash,createHmac,timingSafeEqual} from 'node:crypto';
export const cookieName='gotham_admin';
export function equal(a,b){return timingSafeEqual(createHash('sha256').update(String(a)).digest(),createHash('sha256').update(String(b)).digest());}
export function secret(key,min=32){const value=process.env[key];if(!value||value.length<min||value.startsWith('REPLACE_'))throw Error(`${key} is missing or too short`);return value;}
export function origin(){const value=process.env.APP_URL;if(!value)throw Error('APP_URL is missing');return new URL(value).origin;}
export function trusted(req){return req.headers.origin===origin();}
export function session(){const payload=Buffer.from(JSON.stringify({expires:Date.now()+12*60*60*1000})).toString('base64url');return payload+'.'+createHmac('sha256',secret('SESSION_SECRET')).update(payload).digest('base64url');}
export function isAdmin(req){try{const token=(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith(cookieName+'='))?.slice(cookieName.length+1);if(!token)return false;const parts=token.split('.');if(parts.length!==2)return false;const [p,signature]=parts;if(!equal(signature,createHmac('sha256',secret('SESSION_SECRET')).update(p).digest('base64url')))return false;const d=JSON.parse(Buffer.from(p,'base64url'));return Number.isFinite(d.expires)&&d.expires>Date.now();}catch{return false;}}
export function cookie(value,maxAge=43200){return `${cookieName}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${origin().startsWith('https:')?'; Secure':''}`;}
export function invitationKey(name,id){return createHash('sha256').update(JSON.stringify([name,id,secret('INVITATION_TOKEN')])).digest('hex');}
export function validSlot(date,time,now=Date.now()){if(typeof date!=='string'||typeof time!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^([01]\d|2[0-3]):[0-5]\d$/.test(time))return false;const value=new Date(`${date}T${time}:00+05:30`);return Number.isFinite(+value)&&new Date(+value+19800000).toISOString().slice(0,10)===date&&+value>now&&+value<now+366*86400000;}
