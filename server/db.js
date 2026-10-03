import pg from 'pg';
let pool;
export function db(){
 if(!process.env.DATABASE_URL)throw Error('DATABASE_URL is missing');
 if(!pool){const settings={connectionString:process.env.DATABASE_URL,max:2,idleTimeoutMillis:10000,connectionTimeoutMillis:8000,allowExitOnIdle:true};
 if(process.env.PG_CA_CERT){const url=new URL(settings.connectionString);for(const k of ['sslmode','sslcert','sslkey','sslrootcert'])url.searchParams.delete(k);settings.connectionString=url.toString();settings.ssl={rejectUnauthorized:true,ca:process.env.PG_CA_CERT.replaceAll('\\n','\n')};}
 pool=new pg.Pool(settings);pool.on('error',()=>console.error('Idle database connection failed'));}
 return pool;
}
