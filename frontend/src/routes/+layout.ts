// Fully static output on both hosts — see docs/FRONTEND_PLAN.md "Hosting".
export const prerender = true;

// GitHub Pages doesn't resolve /dashboard -> dashboard.html the way Vercel
// does — always emit /dashboard/index.html instead, which both hosts serve
// correctly with no rewrite config needed.
export const trailingSlash = 'always';
