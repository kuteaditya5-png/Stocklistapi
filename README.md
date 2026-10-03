# A date in Gotham — Vercel + PostgreSQL

This is a standalone Vercel project, with the NEW clean baby Batman image. It does not require ChatGPT Sites or Cloudflare. Extract the ZIP, put the contents of this folder in your Git repository, then import that repository into Vercel.

## 1. Change the name

Edit **config/site.js**:

```js
export const siteConfig = {
  recipientName: 'Avinash', // Replace this name
  invitationId: 'date-001',
  timezone: 'Asia/Kolkata'
};
```

Commit and push the change. Vercel redeploys the connected production branch. Do not edit names separately in HTML: the invitation reads this configuration through the API.

To send a fresh invitation to the SAME name after testing, change `invitationId` to `date-002` and redeploy. Existing responses remain in the database. Changing the name also creates a distinct response key. The latest recipient and invitation ID use the same invitation-link token unless you rotate INVITATION_TOKEN.

## 2. Where responses arrive

Open **https://YOUR-VERCEL-DOMAIN/admin** and sign in with your `ADMIN_PASSWORD`. This page shows the name, selected date, time in IST, and received timestamp. Click Refresh for new responses. It also provides the complete invitation link to copy and send. Do not send the admin password.

You can also read responses in pgAdmin:

```sql
SELECT response_id,recipient_name,selected_date,selected_time,timezone,created_at
FROM date_invite.responses
ORDER BY created_at DESC;
```

There are no email/WhatsApp/push notifications in this package. Responses are saved to PostgreSQL and viewed on `/admin` or in pgAdmin. The prior ChatGPT-hosted site's database is separate; its existing records are not migrated.

## 3. Set up PostgreSQL

1. Open pgAdmin and connect to the database you want to use.
2. Open Query Tool and execute **database/setup.sql** once.
3. Use a dedicated application database user with the permissions shown at the end of that script.
4. Prepare a PostgreSQL connection URL: `postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=verify-full`. URL-encode special characters in username/password.

pgAdmin is the management application, not the database host. The database must be reachable from Vercel. A database available only at `localhost`, on your laptop, or behind an office-only network will not be reachable by a Vercel deployment without a suitable network setup. Do not expose an office database for this personal project. A separately hosted PostgreSQL database is simplest.

Use your provider's trusted TLS settings. The sample uses certificate validation. If your provider uses a private CA, set `PG_CA_CERT` to its trusted PEM certificate. The code does not disable certificate verification. For local-only development against a local PostgreSQL server without TLS, omit the `sslmode` query parameter.

## 4. Generate private configuration

Install Node.js 22 or newer. In this folder run:

```bash
npm ci
npm run generate-secrets
```

This prints three independent random values for ADMIN_PASSWORD, SESSION_SECRET and INVITATION_TOKEN. Save them privately and put them in Vercel environment variables. Do not commit them to Git. ADMIN_PASSWORD is your login password. SESSION_SECRET signs the admin cookie. INVITATION_TOKEN protects the invitation link; anyone you give that link to can submit one response.

## 5. GitHub and Vercel deployment

1. Create a GitHub repository and upload the extracted project contents. Keep `package.json`, `vercel.json`, `api/`, `server/`, `config/` and `public/` at the repository root. Do not upload just `public/`.
2. In Vercel, choose **Add New → Project**, import your Git repository.
3. Select Framework Preset **Other**, Output Directory **public**, Install Command **npm ci**. Leave Build Command empty; this frontend has no compilation step. Node functions in `api/` run on Vercel.
4. Add these server environment variables:

| Variable | Value |
| --- | --- |
| DATABASE_URL | Your real PostgreSQL connection URL |
| APP_URL | The canonical production origin, such as `https://your-project.vercel.app`; no path |
| ADMIN_PASSWORD | The generated password (minimum 16 characters) |
| SESSION_SECRET | Generated random secret (minimum 32 characters) |
| INVITATION_TOKEN | Generated random token (minimum 32 characters) |
| PG_CA_CERT | Optional provider CA certificate |

5. Deploy. If you did not know the domain beforehand, copy the assigned production domain, correct APP_URL, and redeploy. APP_URL must exactly match the origin you open for login and form submissions. If you use a custom domain, update APP_URL and use that domain consistently.
6. Open `/admin`, sign in, and copy the complete invitation link. The normal link includes `?invite=...`; opening only the root URL without an admin session or token intentionally shows an invitation-link message.
7. If Vercel deployment protection prevents your guest from opening the production link, adjust that project's production access settings deliberately. The app's `/admin` API still requires its private password session.

Git command example (replace YOUR_REPOSITORY_URL yourself):

```bash
git init
git add .
git commit -m "Add Gotham date invitation"
git branch -M main
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

Use a separate database and APP_URL for previews if you enable preview deployments. Preview branches should not share production response data by accident.

## 6. Run locally

Copy `.env.example` to `.env.local` and fill in real values. Set `APP_URL=http://localhost:3000`. Execute the database SQL first, then run:

```bash
npm ci
npm run dev
```

Open `http://localhost:3000/admin`, sign in and copy the invitation link. Static-file preview alone cannot save responses; use this server or Vercel.

## 7. Image and appearance

- **public/baby-batman.jpg** — the new uploaded image, without orange markings.
- **public/styles.css** — colors, spacing, responsive image sizes.
- **public/index.html** — invitation copy and the 10-attempt popup text.
- **public/invitation.js** — moving No button, date/time selection, confirmation.
- **public/admin.html / public/admin.js** — private dashboard interface.
- **api/respond.js** — validation and PostgreSQL insert.
- **database/setup.sql** — database tables and response query.

The No button moves on mouse approach, touch attempt or keyboard click, debounced to count one attempt per gesture. The popup appears at attempt 10. Yes opens native date and time pickers. Past/invalid dates are rejected again on the server. One response per configured invitation is enforced by a database unique constraint. A successful confirmation is shown only after the database insert succeeds.

## Validation performed

`npm test` passed for session signing/tamper rejection, private API access, request-origin and invitation-token checks, and date/IST validation. Frontend JavaScript syntax was checked. PostgreSQL connectivity and an actual Vercel deployment were NOT tested because your database credentials and Vercel project were not provided. After configuring them, test one submission, verify it in `/admin`, and change invitationId for the real invitation.

## Troubleshooting

- **Service unavailable:** verify DATABASE_URL, TLS settings, network reachability, and that setup.sql ran in the same database.
- **Invalid request origin:** APP_URL differs from the browser's origin. Correct it and redeploy.
- **Too many attempts:** wait 15 minutes after repeated login attempts.
- **Already confirmed:** change invitationId for a new invitation/test. Do not delete historical data unnecessarily.
- **Name did not change:** edit config/site.js, commit, push, and wait for the latest production deployment.
- **Forgot admin password:** replace ADMIN_PASSWORD and SESSION_SECRET in Vercel, then redeploy. Rotating SESSION_SECRET invalidates existing sessions.

## Official deployment references

- https://vercel.com/docs/git
- https://vercel.com/docs/functions/runtimes/node-js
- https://vercel.com/docs/project-configuration/vercel-json
- https://vercel.com/kb/guide/how-to-add-vercel-environment-variables
- https://node-postgres.com/features/ssl
