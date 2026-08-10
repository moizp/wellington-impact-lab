import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// Prerendered static output — works identically on Vercel and GitHub
		// Pages, no server runtime needed (see docs/FRONTEND_PLAN.md "Hosting").
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: undefined,
			precompress: false,
			strict: true
		}),
		// Blank for Vercel/local; set to '/<repo-name>' via BASE_PATH for a
		// GitHub Pages project site (see docs/FRONTEND_PLAN.md "Hosting").
		paths: {
			base: process.env.BASE_PATH || ''
		}
	}
};

export default config;
