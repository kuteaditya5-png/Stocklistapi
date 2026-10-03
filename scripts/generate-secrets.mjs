import {randomBytes} from 'node:crypto';
for(const name of ['ADMIN_PASSWORD','SESSION_SECRET','INVITATION_TOKEN'])console.log(name+'='+randomBytes(32).toString('hex'));
